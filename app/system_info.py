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


def fetch_system_resources() -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {"cpu": {}, "memory": {}, "disk": {}}

    cpu_percent = psutil.cpu_percent()
    cpu_freq = psutil.cpu_freq()
    memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()
    disk = psutil.disk_usage("/")

    resources["cpu"].update(
        [
            ("cpu_percent", f"{round(cpu_percent, 1)}%"),
            ("cpu_freq", f"{round(cpu_freq.current, 1)}"),
        ]
    )

    resources["memory"].update(
        [
            ("total", get_readable_size(memory.total)),
            ("used", get_readable_size(memory.used)),
            ("available", get_readable_size(memory.available)),
            ("percent", f"{round(memory.percent, 1)}%"),
            (
                "swap",
                {
                    "total": get_readable_size(swap_memory.total),
                    "used": get_readable_size(swap_memory.used),
                    "percent": f"{round(swap_memory.percent, 1)}%",
                },
            ),
        ]
    )

    resources["disk"].update(
        [
            ("size", get_readable_size(disk.total)),
            ("used", get_readable_size(disk.used)),
            ("percent", f"{round(disk.percent, 1)}%"),
        ]
    )

    return resources
