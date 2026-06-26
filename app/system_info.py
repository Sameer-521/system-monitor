from collections import deque
import platform
import itertools
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field
from enum import Enum
import psutil
from fastapi import HTTPException, status

from app.settings import _settings

CPU_TEMP_THRESHOLD = 90
CPU_USAGE_THRESHOLD = 70

ACCESS_DENIED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "access denied"}
)

ZOMBIE_PROCESS = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "zombie process"}
)


class Counter:
    def __init__(self, initial=0):
        self.value = initial

    def increment(self, amount=1):
        self.value += amount
        return self.value

    def reset(self, to=0):
        self.value = to
        return self.value


@dataclass
class RingBuffer:
    metric_id: str
    contents: deque = field(default_factory=lambda: deque(maxlen=300))  # 5mins


class AlertLevel(Enum):
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    CRITICAL = "critical"


cpu_buffer = RingBuffer("cpu")
mem_buffer = RingBuffer("memory")

high_cpu_usage_counter = Counter(0)


def no_such_process(pid: int):
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": f"no such process with pid: {pid}"},
    )


def fetch_processes(top: int = 0):
    processes = []

    attrs = ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]

    for proc in psutil.process_iter(attrs):
        try:
            p_info = proc.info

            p_info["cpu_percent"] = round(p_info["cpu_percent"], 1)
            p_info["memory_percent"] = round(p_info["memory_percent"], 1)

            processes.append(p_info)
        except psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess:
            continue

    if top > 0:
        return sorted(processes, key=lambda proc: proc["cpu_percent"])[:top]
    # sort by cpu_percent in ascending order
    return sorted(processes, key=lambda proc: proc["cpu_percent"], reverse=True)


def fetch_process_by_pid(pid: int) -> dict[str, Any] | Exception:
    p_info: dict[str, Any] = {"pid": pid}

    try:
        p = psutil.Process(pid)
        with p.oneshot():
            p_info["name"] = p.name()
            p_info["username"] = p.username()
            p_info["cpu_percent"] = round(p.cpu_percent(), 1)
            p_info["memory_percent"] = round(p.memory_percent(), 1)
            p_info["status"] = p.status()

        return p_info

    except psutil.ZombieProcess:
        return ZOMBIE_PROCESS
    except psutil.NoSuchProcess:
        return no_such_process(pid)
    except psutil.AccessDenied:
        return ACCESS_DENIED
    except Exception as e:
        return e


def get_readable_size(bytes_value):
    """Convert bytes to a human-readable format (GB, MB, etc.)"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0


def _fetch_cpu_info() -> dict[str, Any]:
    cpu_percent = round(psutil.cpu_percent(), 1)
    cpu_freq = [round(freq.current, 1) for freq in psutil.cpu_freq(percpu=True)]
    num_cores = psutil.cpu_count() or 0

    load_avg = psutil.getloadavg()
    load_per_cpu = [(x / float(num_cores)) * 100 for x in load_avg]
    min_times = ["1min", "5min", "15min"]

    core_temps = psutil.sensors_temperatures().get("coretemp", [])
    core_temp = core_temps[0].current if len(core_temps) > 0 else None

    cpu_buffer.contents.append(cpu_percent)

    return {
        "usage_percentage": round(cpu_percent, 1),
        "cores": num_cores,
        "cpu_freq": cpu_freq,
        "load_average": dict(zip(min_times, load_per_cpu)),
        "temp_celcius": core_temp,
    }


def _fetch_mem_info() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()

    mem_usage = round(memory.percent, 1)
    mem_buffer.contents.append(mem_usage)

    return {
        "total": get_readable_size(memory.total),
        "used": get_readable_size(memory.total - memory.available),
        "available": get_readable_size(memory.available),
        "usage_percentage": mem_usage,
        "swap": {
            "total": get_readable_size(swap_memory.total),
            "used": get_readable_size(swap_memory.used),
            "free": get_readable_size(swap_memory.free),
        },
    }


def _fetch_alerts(
    cpu_buffer: RingBuffer, mem_buffer: RingBuffer, high_cpu_usage_counter: Counter
):
    alerts = {}
    window = _settings.cpu_buffer_interval_window  # 2mins

    # basic alerts
    if len(cpu_buffer.contents) >= window:
        cpu_usage = list(
            itertools.islice(
                cpu_buffer.contents,
                len(cpu_buffer.contents) - window,
                len(cpu_buffer.contents),
            )
        )
        avg_cpu_usage = sum(cpu_usage) / window
        if avg_cpu_usage >= CPU_USAGE_THRESHOLD:
            high_cpu_usage_counter.increment()
            if high_cpu_usage_counter.value >= 2:
                alerts.update(
                    {
                        "severity": AlertLevel.CRITICAL,  # will change this later
                        "message": f"CPU usage capped at {avg_cpu_usage}% for the past {window * 2 / 60} mins.",
                        "top processes": fetch_processes(top=10),
                    }
                )
        else:
            high_cpu_usage_counter.reset()

    if len(mem_buffer.contents) >= window:
        mem_usage = list(
            itertools.islice(
                mem_buffer.contents,
                len(mem_buffer.contents) - window,
                len(mem_buffer.contents),
            )
        )
        avg_mem_usage = sum(mem_usage) / window
        alerts.update(
            {
                "severity": AlertLevel.WARNING,
                "message": f"Memory usage capped at {avg_mem_usage}% for the past {window / 60} mins.",
            }
        )

    return alerts
    # TODO: finish off this


def _fetch_disk_info() -> list[dict[str, Any]]:
    partitions = psutil.disk_partitions()

    p_info = []

    for p in partitions:
        p_usage = psutil.disk_usage(p.mountpoint)
        p_info.append(
            {
                "mount": p.mountpoint,
                "device": p.device,
                "total": get_readable_size(p_usage.total),
                "used": get_readable_size(p_usage.used),
                "free": get_readable_size(p_usage.free),
                "usage_percentage": p_usage.percent,
            }
        )

    return p_info


def _fetch_network_info():
    pass


def fetch_system_resources() -> dict[str, str | dict[str, Any] | list[dict] | Any]:
    dt_now = datetime.now()
    dt_object = datetime.fromtimestamp(dt_now.timestamp())
    uptime = datetime.fromtimestamp(psutil.boot_time()) - dt_now
    resources: dict[str, Any] = {
        "timestamp": dt_object.strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": platform.node(),
        "uptime_seconds": uptime.seconds,
        "cpu": {},
        "memory": {},
        "disk": {},
    }

    resources["cpu"] = _fetch_cpu_info()
    resources["memory"] = _fetch_mem_info()
    resources["disk"] = _fetch_disk_info()

    return resources
