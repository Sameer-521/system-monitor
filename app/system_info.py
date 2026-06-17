from fastapi import HTTPException, status
import psutil
from typing import Any

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


def fetch_process_by_pid(pid: int) -> dict | Exception:
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
