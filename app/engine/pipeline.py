import platform
from datetime import datetime
from typing import Any

import psutil

from app.collectors.cpu import _fetch_cpu_info
from app.collectors.memory import _fetch_mem_info
from app.collectors.disk import _fetch_disk_info


def fetch_system_resources() -> dict[str, str | dict[str, Any] | list[dict]]:
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
