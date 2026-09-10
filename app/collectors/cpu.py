from typing import Any

import psutil

from app.buffers import cpu_buffer


def fetch_cpu_info() -> dict[str, Any]:
    cpu_percent = round(psutil.cpu_percent(), 1)
    cpu_freq = [round(freq.current, 1) for freq in psutil.cpu_freq(percpu=True)]
    num_cores = psutil.cpu_count() or 0

    load_avg = psutil.getloadavg()
    min_times = ["1min", "5min", "15min"]

    core_temps = psutil.sensors_temperatures().get("coretemp", [])
    core_temp = core_temps[0].current if len(core_temps) > 0 else None

    cpu_buffer.contents.append(cpu_percent)

    return {
        "usage_percentage": round(cpu_percent, 1),
        "cores": num_cores,
        "cpu_freq": cpu_freq,
        "load_average": dict(zip(min_times, [round(x, 2) for x in load_avg])),
        "temp_celcius": core_temp,
    }
