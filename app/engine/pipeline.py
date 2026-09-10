import platform
import time
from datetime import datetime
from typing import Any

import psutil

from app.alerts.cpu_anomaly import CpuAnomalyAlert
from app.alerts.high_load_avg import HighLoadAvg
from app.alerts.registry import AlertRegistry
from app.collectors.cpu import fetch_cpu_info
from app.collectors.disk import fetch_disk_info
from app.collectors.memory import fetch_mem_info

alerts_registry = AlertRegistry([CpuAnomalyAlert(), HighLoadAvg()])


def fetch_system_resources() -> dict[str, str | dict[str, Any] | list[dict]]:
    dt_now = datetime.now()
    dt_object = datetime.fromtimestamp(dt_now.timestamp())
    uptime = round(time.time() - psutil.boot_time(), 2)
    resources: dict[str, Any] = {
        "timestamp": dt_object.strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": platform.node(),
        "uptime_seconds": uptime,
        "cpu": {},
        "memory": {},
        "disk": {},
    }

    resources["cpu"] = fetch_cpu_info()
    resources["memory"] = fetch_mem_info()
    resources["disk"] = fetch_disk_info()

    resources["alerts"] = alerts_registry.evaluate(resources)

    return resources
