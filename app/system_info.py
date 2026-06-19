import platform
from datetime import datetime
from typing import Any

import psutil
from fastapi import HTTPException, status

ACCESS_DENIED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "access denied"}
)

ZOMBIE_PROCESS = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "zombie process"}
)


def no_such_process(pid: int):
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": f"no such process with pid: {pid}"},
    )


def fetch_processes():
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
    cpu_percent = psutil.cpu_percent()
    cpu_freq = [round(freq.current, 1) for freq in psutil.cpu_freq(percpu=True)]
    num_cores = psutil.cpu_count() or 0

    load_avg = psutil.getloadavg()
    load_per_cpu = [(x / float(num_cores)) * 100 for x in load_avg]
    min_times = ["1min", "5min", "15min"]

    core_temps = psutil.sensors_temperatures().get("coretemp", [])
    core_temp = core_temps[0].current if len(core_temps) > 0 else None

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

    return {
        "total": get_readable_size(memory.total),
        "used": get_readable_size(memory.total - memory.available),
        "available": get_readable_size(memory.available),
        "usage_percentage": round(memory.percent, 1),
        "swap": {
            "total": get_readable_size(swap_memory.total),
            "used": get_readable_size(swap_memory.used),
            "free": get_readable_size(swap_memory.free),
        },
    }


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
