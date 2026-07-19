from typing import Any

import psutil

from app.collectors.process import get_readable_size


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
