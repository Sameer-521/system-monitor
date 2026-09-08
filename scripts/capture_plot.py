import argparse
import asyncio
import json
import statistics
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_URL = "http://127.0.0.1:8000/metrics"
USER = "Sameer"
PARAMS = (
    "cpu=true&alerts=true&memory=false&disk=false&network=false&processes=false&containers=false"
)
OUTFILE = Path(__file__).parent / "capture.jsonl"
PLOTFILE = Path(__file__).parent / "capture_plot.png"

BUCKET_SIZE = 10
MAX_BUCKETS = 30
Z_THRESHOLD = 3.0
STREAK = 2

SEVERITY_COLORS = {"warning": "orange", "critical": "red", "info": "gray", "debug": "gray"}


async def issue_ticket(client: httpx.AsyncClient, user: str) -> str:
    resp = await client.post(f"{BASE_URL}/stream/ticket/{user}")
    resp.raise_for_status()
    return resp.json()["ticket"]["id"]


async def capture(duration: int, done: asyncio.Event) -> None:
    async with httpx.AsyncClient() as client:
        ticket = await issue_ticket(client, USER)
        print(f"{USER}'s ticket: {ticket}")
        url = f"{BASE_URL}/stream/{USER}?{PARAMS}"
        headers = {"Accept": "text/event-stream", "x-ticket": ticket}
        try:
            async with client.stream("GET", url, headers=headers, timeout=None) as resp:
                resp.raise_for_status()
                with open(OUTFILE, "w") as fh:
                    async for line in resp.aiter_lines():
                        if done.is_set():
                            break
                        if line.startswith("data: "):
                            payload = line.removeprefix("data: ")
                            try:
                                data = json.loads(payload)
                                if isinstance(data, str):
                                    data = json.loads(data)
                                info = data["info"]
                            except (json.JSONDecodeError, KeyError, TypeError):
                                continue
                            fh.write(json.dumps(info) + "\n")
        except httpx.HTTPStatusError as e:
            print(f"ERROR: stream failed HTTP {e.response.status_code}")
        except (httpx.RequestError, OSError) as e:
            if not done.is_set():
                print(f"ERROR: connection error: {e}")
        finally:
            done.set()


def load_records() -> tuple[
    list[datetime], list[float], dict[str, list[float]], list[dict[str, Any]]
]:
    records = [json.loads(line) for line in OUTFILE.open() if line.strip()]
    times = [datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") for r in records]
    cpu = [r["cpu"]["usage_percentage"] for r in records]
    loads = {k: [r["cpu"]["load_average"][k] for r in records] for k in ("1min", "5min", "15min")}
    alerts = [
        {"time": t, **a}
        for r, t in zip(records, times)
        for a in r.get("alerts", [])
        if isinstance(a, dict)
    ]
    return times, cpu, loads, alerts


def offline_zscore(times: list[datetime], cpu: list[float]) -> None:
    """Replicate CpuAnomalyAlert logic on captured data to show what z did."""
    buckets: deque[float] = deque(maxlen=MAX_BUCKETS)
    current: list[float] = []
    z_rows = []
    for t, u in zip(times, cpu):
        current.append(u)
        if len(current) >= BUCKET_SIZE:
            avg = sum(current) / BUCKET_SIZE
            current.clear()
            buckets.append(avg)
            if len(buckets) >= MAX_BUCKETS:
                med = statistics.median(buckets)
                std = statistics.stdev(buckets)
                z = 0 if std == 0 else abs(avg - med) / std
                z_rows.append((t, avg, med, std, z))

    print()
    print(
        f"=== Offline CpuAnomalyAlert replay (z >= {Z_THRESHOLD} for {STREAK} consecutive buckets) ==="
    )
    print(f"buckets collected: {len(buckets)} (needs {MAX_BUCKETS} to arm)")
    if len(buckets) < MAX_BUCKETS:
        print("-> alert never armed during capture window")
        return
    print(f"{'time':20s} {'avg':>7s} {'median':>7s} {'std':>7s} {'z':>7s}")
    fired = 0
    streak = 0
    streak_miss = 0
    for t, avg, med, std, z in z_rows:
        flag = ""
        if z >= Z_THRESHOLD:
            streak += 1
            if streak >= STREAK:
                fired += 1
                flag = "  <-- FIRED"
        else:
            streak_miss += 1
            if streak_miss >= 2:
                streak = 0
        print(f"{t:%H:%M:%S} {avg:7.1f} {med:7.1f} {std:7.2f} {z:7.2f}{flag}")
    zs = [r[4] for r in z_rows]
    max_z = max(zs) if zs else 0.0
    print(f"max z: {max_z:.2f} | buckets that would fire: {fired}")


def plot(
    times: list[datetime],
    cpu: list[float],
    loads: dict[str, list[float]],
    alerts: list[dict[str, Any]],
) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    alert_times = [a["time"] for a in alerts]
    for ax in (ax1, ax2):
        for a in alerts:
            color = SEVERITY_COLORS.get(str(a.get("severity")), "gray")
            ax.axvline(a["time"], color=color, linestyle="--", alpha=0.7)

    ax1.plot(times, cpu, color="tab:blue", linewidth=0.9)
    ax1.set_ylabel("CPU usage %")
    ax1.set_ylim(0, 105)
    ax1.grid(alpha=0.3)
    if alert_times:
        ax1.text(
            alert_times[0],
            ax1.get_ylim()[1] * 0.95,
            "alerts fired",
            color="red",
            fontsize=8,
            ha="right",
        )

    for key, color in (("1min", "tab:red"), ("5min", "tab:orange"), ("15min", "tab:green")):
        ax2.plot(times, loads[key], color=color, linewidth=0.9, label=f"{key} load")
    ax2.set_ylabel("Load avg (raw)")
    ax2.grid(alpha=0.3)
    ax2.legend(loc="upper left")

    ax2.set_xlabel("time")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOTFILE)
    print(f"plot saved to {PLOTFILE}")


def report_alerts(alerts: list[dict[str, Any]]) -> None:
    print()
    print("=== Alerts received ===")
    if not alerts:
        print("(none)")
        return
    for a in alerts:
        print(f"{a['time']:%H:%M:%S}  {a.get('severity'):<8} {a.get('metric')}: {a.get('message')}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=180, help="capture seconds")
    args = parser.parse_args()

    print(f"Capturing {USER} stream for {args.duration}s...")
    done = asyncio.Event()
    task = asyncio.create_task(capture(args.duration, done))
    try:
        await asyncio.wait_for(task, timeout=args.duration + 30)
    except asyncio.TimeoutError:
        pass
    finally:
        done.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    print(f"events captured: {sum(1 for _ in OUTFILE.open())}")
    times, cpu, loads, alerts = load_records()
    report_alerts(alerts)
    offline_zscore(times, cpu)
    plot(times, cpu, loads, alerts)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
