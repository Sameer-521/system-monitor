import time
from app.engine.pipeline import fetch_system_resources


def measure():
    start = time.monotonic()
    _ = fetch_system_resources()
    end = time.monotonic()
    return round(end - start, 4)


RUNS = 5
sum = 0

for i in range(RUNS):
    time.sleep(0.2)
    t = measure()
    sum += t
    print(f"[{i}]: {t}secs")

print(f"Average: {round(sum / RUNS, 4)}secs")
