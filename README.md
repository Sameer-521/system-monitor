# sys-monitor

Real-time system monitoring API built with FastAPI (Python 3.14). Polls CPU, memory, disk, and
process metrics via psutil every second, streams per-client filtered snapshots over
Server-Sent Events (SSE), and runs in-process alerts (CPU anomaly detection, load-average
state machine).

## Current state

Working in progress:

- Poller/broadcast/SSE pipeline, REST endpoints, and ticket auth are implemented
- CPU anomaly and high-load-average alerts are implemented (with tests)
- Network collector and high-memory alert are stubs
- Auth is a minimal one-time ticket scheme; users are hard-coded in memory (`/register` stores usernames only)

## Dev environment

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                  # install dependencies
uv run python server.py  # serve at http://127.0.0.1:8000
uv run pytest            # run tests
```

Optional: `python scripts/cpu_spike.py` burns CPU to trigger alerts while streaming.
