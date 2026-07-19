from typing import Any

import psutil

from app.buffers import mem_buffer
from app.collectors.process import get_readable_size


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
