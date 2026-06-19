# Streaming Pipeline Architecture

## Overview

The streaming pipeline delivers real-time system resource snapshots (CPU, memory, disk) to multiple SSE (Server-Sent Events) clients. A background poller collects data from `/proc` via `psutil` every second, pushes it into a condition-variable-backed snapshot holder, and a broadcaster fans it out to per-client `asyncio.Queue` instances. Each client's queue feeds an async generator that filters the payload, wraps it in JSON, and streams it over an SSE connection.

```
poller (1s) → LatestSnapshot → broadcaster → [Subscription queues] → consumers → SSE clients
```

---

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                       │
│                                                                               │
│  ┌──────────────────────┐      every 1 sec       ┌──────────────────────┐    │
│  │  fetch_system_       │  ────────────────────▶  │   LatestSnapshot     │    │
│  │  resources()         │    via asyncio.to_thread │                      │    │
│  │  (psutil: CPU,mem,   │                         │  .value              │    │
│  │   disk)              │                         │  ._version           │    │
│  └──────────────────────┘                         │  ._condition         │    │
│                                                   │    (notify/wait)     │    │
└───────────────────────────────────────────────────┴──────────────────────┘    │
                                                    │                           │
                                         blocks until version changes            │
                                                    │                           │
┌───────────────────────────────────────────────────┼──────────────────────┐    │
│                          BROADCAST LAYER          ▼                       │    │
│                                                                          │    │
│  ┌────────────────────────────────────────────────────────────────────┐  │    │
│  │  broadcast()                                                       │  │    │
│  │  • waits on snapshot.get_latest()  ◀── condition-based, no polling │  │    │
│  │  • under sub_lock, fans out to every Subscription.queue            │  │    │
│  │  • if queue full → discards oldest, inserts newest (maxsize=1)     │  │    │
│  └──────────────────────────┬─────────────────────────────────────────┘  │    │
│                             │ put_nowait(data)                             │    │
│         ┌───────────────────┼───────────────────┬──────────────┐          │    │
│         ▼                   ▼                   ▼              ▼          │    │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐   ┌───────────┐  │    │
│  │ Sub("Joe") │      │Sub("John") │      │Sub("Sameer")│  │   ...     │  │    │
│  │q:maxsize=1 │      │q:maxsize=1 │      │q:maxsize=1  │  │           │  │    │
│  │f: [cpu]    │      │f: [mem]    │      │f: [cpu,disk]│  │           │  │    │
│  └──────┬─────┘      └──────┬─────┘      └──────┬───────┘  └─────┬─────┘  │    │
└─────────┼───────────────────┼───────────────────┼────────────────┼────────┘    │
          │                   │                   │                │             │
┌─────────┼───────────────────┼───────────────────┼────────────────┼────────┐    │
│         │    CONSUMER / SSE LAYER               │                │        │    │
│         ▼                   ▼                   ▼                ▼        │    │
│  ┌──────────────────────────────────────────────────────────────────────┐ │    │
│  │  consumer() async generator per Subscription                         │ │    │
│  │  • awaits queue.get()                                               │ │    │
│  │  • filters payload to requested keys + [timestamp,hostname,uptime]  │ │    │
│  │  • wraps in Snapshot JSON → yields ServerSentEvent                  │ │    │
│  └──────────────────────────────┬───────────────────────────────────────┘ │    │
│                                 │ async for                               │    │
│                                 ▼                                         │    │
│  ┌──────────────────────────────────────────────────────────────────────┐ │    │
│  │  GET /stream/system/{id}  (FastAPI SSE endpoint)                     │ │    │
│  │  • validates one-time ticket via x-ticket header                     │ │    │
│  │  • parses ?cpu=true&memory=true → _filters                           │ │    │
│  │  • creates Subscription → EventSourceResponse                        │ │    │
│  └──────────────────────────────┬───────────────────────────────────────┘ │    │
│                                 │ text/event-stream                       │    │
│                                 ▼                                         │    │
│                           ┌──────────┐                                    │    │
│                           │  CLIENT  │  (browser EventSource / curl -N)   │    │
│                           └──────────┘                                    │    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Poller (`app/pubsub.py:51`)

```python
async def poller(snapshot: LatestSnapshot) -> None:
    while True:
        await asyncio.sleep(_settings.poller_interval)
        info = await asyncio.to_thread(fetch_system_resources)
        await snapshot.set(info)
```

- Runs as a background `asyncio.Task` started at server boot.
- Sleeps for `poller_interval` seconds (default: 1, configurable via `POLLER_INTERVAL` env var).
- Offloads `fetch_system_resources()` to a thread via `asyncio.to_thread()` because `psutil` calls are blocking.
- Pushes the result into `LatestSnapshot`, which notifies all waiters.

### 2. LatestSnapshot (`app/pubsub.py:33`)

```python
class LatestSnapshot:
    def __init__(self):
        self.value = 0
        self._condition = asyncio.Condition()
        self._version = 0

    async def set(self, value):
        async with self._condition:
            self.value = value
            self._version += 1
            self._condition.notify_all()

    async def get_latest(self, last_seen_version=-1):
        async with self._condition:
            await self._condition.wait_for(lambda: self._version != last_seen_version)
            return self.value, self._version
```

- **Write path**: `set()` increments an internal version counter and calls `notify_all()`, waking every coroutine blocked on `get_latest()`.
- **Read path**: `get_latest()` blocks on `wait_for()` until the version differs from the caller's `last_seen_version`. Returns `(value, version)`. This is a **blocking-wake-on-change** pattern — broadcast does no polling.
- The `asyncio.Condition` guarantees that all waiters are woken atomically when new data arrives, and only one waiter at a time can observe the latest value under the condition's internal lock.

### 3. Broadcaster (`app/pubsub.py:58`)

```python
async def broadcast(snapshot, subs, sub_lock):
    last_version = -1
    while True:
        data, last_version = await snapshot.get_latest(last_version)
        async with sub_lock:
            for _, sub in subs.items():
                try:
                    sub.queue.put_nowait(data)
                except asyncio.QueueFull:
                    _ = sub.queue.get_nowait()   # drain stale entry
                    sub.queue.put_nowait(data)    # push fresh entry
```

- Runs as a background `asyncio.Task` started at server boot.
- Blocks on `snapshot.get_latest()` — no CPU-wasteful polling, wakes only when the poller produces new data.
- Under `sub_lock`, iterates every active `Subscription` in the `client_subs` dict.
- **Non-blocking push**: uses `put_nowait()` (the non-blocking variant of `put()`) to avoid a slow consumer stalling the entire broadcast loop.
- **Backpressure**: if a queue is full (consumer hasn't consumed the previous entry), drains the stale entry and inserts the fresh one (see [Backpressure Strategy](#backpressure-strategy)).

### 4. Subscription (`app/pubsub.py:15`)

```python
class Subscription:
    def __init__(self, owner_id, _filters):
        self.id = str(uuid4())
        self.owner_id = owner_id
        self.queue = asyncio.Queue(maxsize=1)
        self._filters = _filters

    async def consumer(self, id):
        while True:
            payload = await self.queue.get()
            keys_to_send = set(self._filters) | set(DEFAULT_FILTERS)
            filtered = {k: payload[k] for k in keys_to_send if k in payload}
            s = Snapshot(info=filtered).model_dump_json()
            yield ServerSentEvent(data=s)
```

- Each SSE-connected client gets one `Subscription`.
- `queue`: an `asyncio.Queue` with `maxsize=1`. Prevents unbounded memory growth on slow clients.
- `_filters`: list of metric keys the client requested (e.g., `["cpu", "memory"]`).
- `consumer(id)`: an **async generator** that loops forever:
  1. Awaits the next payload from `self.queue`.
  2. Merges requested filters with `DEFAULT_FILTERS` (`["timestamp", "hostname", "uptime_seconds"]`).
  3. Extracts only the matching keys from the payload.
  4. Serializes via Pydantic's `Snapshot` → JSON → yields as `ServerSentEvent`.

### 5. SSE Endpoint (`app/main.py:60`)

```
GET /stream/system/{id}?cpu=true&memory=true
Header: x-ticket: <one-time-ticket>
```

**Connection flow**:
1. **Ticket verification**: `verify_ticket_header` dependency validates and consumes the one-time ticket from the `x-ticket` header (see [Ticket System](#ticket-system)).
2. **Filter parsing**: Query params are parsed by the `MetricsParams` Pydantic model into a list of metric key names.
3. **Subscription creation** (under `sub_lock`):
   - Any previous `Subscription` for this `id` is popped from `client_subs` (replaces old stream).
   - A new `Subscription(id, _filters)` is created and stored.
4. **Streaming loop**: `async for event in sub.consumer(id)` yields `ServerSentEvent` objects back to the client via `EventSourceResponse`.
5. **Disconnect cleanup** (in `finally` block): acquires `sub_lock` and removes the subscription from `client_subs`.

### 6. Ticket System (`app/ticket.py`)

- **`TicketStore`** holds an in-memory dict of one-time tickets.
- **Issue** (`POST /stream/ticket/{user_id}`): creates a `Ticket` (UUID4 ID, monotonic timestamp, `{client_id}` claim), stores it with a configurable lifetime (default: 300s).
- **Consume** (`verify_ticket_header` dependency): reads `x-ticket` header, checks expiry and validity, then **pops** the ticket from the store (one-time use). Returns 401 if invalid or expired.

### 7. Lifespan Management (`app/main.py:25`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks = [
        asyncio.create_task(poller(latest_snapshot)),
        asyncio.create_task(broadcast(latest_snapshot, client_subs, sub_lock)),
    ]
    # seed default users
    clients.add("Sameer"); clients.add("John"); clients.add("Joe")
    yield
    # graceful shutdown: cancel all tasks, await completion
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
```

- `poller` and `broadcast` are spawned as `asyncio.Task` at server startup.
- They run for the lifetime of the server.
- On shutdown, each task is cancelled, and `gather` awaits their completion (swallowing `CancelledError`).

---

## Backpressure Strategy

### Problem

If a consumer is slow (e.g., network latency, slow client), the broadcaster could accumulate unbounded data in the queue, causing memory bloat.

### Solution: Bounded Queue + Drop-Oldest

Each `Subscription.queue` is capped at `maxsize=1`. When the broadcaster tries to push and the queue is full:

```python
try:
    sub.queue.put_nowait(data)
except asyncio.QueueFull:
    _ = sub.queue.get_nowait()   # drain the stale entry
    sub.queue.put_nowait(data)    # push the fresh entry
```

This implements a **drop-oldest, keep-newest** backpressure policy:
- The stale snapshot is discarded.
- The fresh snapshot is inserted.
- The consumer always sees the most recent data, never a backlog of outdated snapshots.

For a monitoring system, this is the correct tradeoff: a current snapshot is always more useful than a stale one.

### Why This Pattern Is Necessary (Not Redundant)

Without the `QueueFull` handler:
- `put_nowait` would silently fail.
- The stale entry would remain in the queue.
- The consumer would eventually wake up and receive **old data** (up to `poller_interval` seconds behind).

The `get_nowait()` + `put_nowait()` guarantees that every consumer, no matter how slow, always receives the **latest** snapshot.

### Atomicity

`asyncio.Queue` operations (`put`, `put_nowait`, `get`, `get_nowait`) are concurrency-safe:
- Internally serialized by an `asyncio.Lock` on the underlying `collections.deque`.
- A concurrent `get()` from the consumer and `put_nowait()` from the broadcaster cannot corrupt queue state.

The `get_nowait()` after `QueueFull` is also safe:
- The queue was full because the consumer is blocked inside `await self.queue.get()` — the item hasn't been consumed yet.
- The broadcast loop holds `sub_lock`, so no other producer can drain the queue.
- Therefore, `get_nowait()` is guaranteed to succeed and retrieve the stale entry.

---

## Data Flow Walkthrough

```
Time 0s    Server boots
           ├── lifespan() spawns poller task
           ├── lifespan() spawns broadcast task
           └── broadcast blocks on snapshot.get_latest()  [waiting for first poll]

Time 1s    poller: asyncio.sleep(1) completes
           ├── asyncio.to_thread(fetch_system_resources)  [offloads to thread]
           │   ├── psutil.cpu_percent(), cpu_freq(), getloadavg()
           │   ├── psutil.virtual_memory(), swap_memory()
           │   └── psutil.disk_usage("/")
           ├── snapshot.set(info)
           │   ├── version: 0 → 1
           │   └── notify_all()  [wakes broadcast]
           └── poller sleeps again

           broadcast wakes up
           ├── receives (data, version=1)
           ├── acquires sub_lock
           │   for each sub in client_subs:
           │       sub.queue.put_nowait(data)
           │       → consumer() wakes from queue.get()
           │       → filters payload, serializes JSON
           │       → yields ServerSentEvent(data=s)
           │       → SSE flushed to client
           └── loops back, blocks on get_latest(version=1)  [waiting for version 2]

Time 2s    poller produces next snapshot → cycle repeats
```

---

## Concurrency & Thread Safety

| Resource | Protection Mechanism |
|---|---|
| `client_subs` dict | `sub_lock` (`asyncio.Lock`) — acquired during connect, disconnect, and broadcast iteration |
| `LatestSnapshot` | `_condition` (`asyncio.Condition`) — serializes `set()` and `get_latest()`, ensures atomic notify/wait |
| `Subscription.queue` | Internal `asyncio.Queue` lock — serializes `put`/`get` on the deque |
| `clients` set (registered users) | No lock needed — reads/writes are single-coroutine (only FastAPI route handlers, no background task access) |
| `tickets_store._tickets` | No lock needed — `dict.pop()` is atomic in asyncio's single-threaded event loop |
| `fetch_system_resources()` | Runs in thread via `asyncio.to_thread()` — no GIL contention, data is read-only after creation |

### Why No Races Exist

1. **Single producer**: only `broadcast` writes to `Subscription.queue` (under `sub_lock`).
2. **Single consumer**: only `consumer()` reads from its own queue.
3. **Single poller**: only `poller` calls `snapshot.set()`.
4. **Event loop model**: asyncio is single-threaded cooperative multitasking — no true parallelism between coroutines, only yield points (`await`).

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `maxsize=1` queue | Prevents memory bloat on slow clients; monitoring data goes stale quickly, so keeping old snapshots is useless |
| Drop-oldest on full | Ensures the consumer always gets the freshest data, even at the cost of losing intermediate snapshots |
| `put_nowait` instead of `await put()` | Prevents a single slow consumer from blocking the entire broadcast loop and delaying delivery to all other clients |
| Condition-variable (`asyncio.Condition`) | Broadcast sleeps until data is available — zero CPU wasted on polling |
| Thread offloading (`asyncio.to_thread`) | `psutil` reads `/proc` filesystem synchronously; running it in the event loop would block all other coroutines |
| One subscription per user ID | Prevents duplicate streams for the same user; new connection replaces old one |
| One-time tickets | Prevents SSE endpoint from being called directly without prior authorization; ticket is consumed on first use |
| `sub_lock` at broadcast level | Protects `client_subs` dict during concurrent connect/disconnect, preventing iteration over a mutating dict |

---

## File Reference

| File | Purpose |
|---|---|
| `app/pubsub.py` | Core streaming: `LatestSnapshot`, `Subscription`, `poller`, `broadcast` |
| `app/main.py` | FastAPI app: lifespan, SSE endpoint, registration, tickets, REST snapshots |
| `app/system_info.py` | Data collection: `fetch_system_resources()`, process info via `psutil` |
| `app/schema.py` | Pydantic models: `Snapshot`, `MetricsParams`, `TicketHeader` |
| `app/ticket.py` | One-time ticket: `Ticket`, `TicketStore`, `verify_ticket_header` |
| `app/settings.py` | Configuration: `poller_interval`, `ticket_lifetime` (env vars) |
| `test_concurrency.py` | Integration test: 3 concurrent SSE clients |
| `dummy_client.py` | Reference client: ticket → SSE stream |
