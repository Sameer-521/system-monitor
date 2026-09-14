# sys-monitor

Real-time system monitoring API built with FastAPI (Python 3.14). Polls CPU, memory, disk, and
process metrics via psutil every second, streams per-client filtered snapshots over
Server-Sent Events (SSE), and runs in-process alerts (CPU anomaly detection, load-average,
high-CPU-usage and high-iowait threshold state machines).

## Current state

Working in progress:

- Poller/broadcast/SSE pipeline, REST endpoints, and ticket auth are implemented
- CPU anomaly, high-load-average, high-CPU-usage, and high-iowait alerts are implemented (with tests)
- Network collector and high-memory alert are stubs
- Auth is a minimal one-time ticket scheme; users are hard-coded in memory (`/register` stores usernames only)

## Alerting

Evaluators run on every snapshot and emit alerts; `AlertRegistry` dedupes, escalates,
resolves, and cooldowns them before fanning out over SSE — see
[Alert_Lifecycle.md](docs/Alert_Lifecycle.md). State-machine specs:
[threshold state machines (high CPU usage, high iowait)](docs/Threshold_Alert_State_Machine.md),
[load average](docs/Load_Average_State_Machine.md).

## Dev environment

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                  # install dependencies
uv run python server.py  # serve at http://127.0.0.1:8000
uv run pytest            # run tests
```

Optional: `python scripts/cpu_spike.py` burns CPU to trigger alerts while streaming.
