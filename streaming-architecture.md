# Streaming Endpoint Architecture

## Sequence Diagram

```mermaid
sequenceDiagram
    participant P as Poller
    participant Q as sys_info (global Queue)
    participant B as broadcast_to_all
    participant SA as Sub A (private Queue)
    participant SB as Sub B (private Queue)
    participant SC as Sub C (private Queue)
    participant CA as Client A (SSE)
    participant CB as Client B (SSE)
    participant CC as Client C (SSE)

    Note over CA,CC: Each client connects to GET /stream/all/{id}

    loop Every 2 seconds
        P->>Q: put(SYSTEM_DATA item)
        B->>Q: get()
        Q-->>B: snapshot
        par Fan-out
            B->>SA: put(snapshot)
        and
            B->>SB: put(snapshot)
        and
            B->>SC: put(snapshot)
        end
        par SSE push to each client
            SA-->>CA: ServerSentEvent(snapshot)
        and
            SB-->>CB: ServerSentEvent(snapshot)
        and
            SC-->>CC: ServerSentEvent(snapshot)
        end
    end

    Note over CA,CC: Disconnect -> client_subs.pop(id)

    Note right of B: Fan-out via asyncio.gather
```

## Component Diagram

```mermaid
flowchart LR
    subgraph Background Tasks
        poller["Poller (cycles SYSTEM_DATA every 2s)"]
        broadcast["broadcast_to_all (fans out to all subs)"]
    end

    subgraph Central Queue
        sys_info(("sys_info (asyncio.Queue)"))
    end

    subgraph Client Subscriptions
        sub_a["Sub A (Queue maxsize=1)"]
        sub_b["Sub B (Queue maxsize=1)"]
        sub_c["Sub C (Queue maxsize=1)"]
    end

    subgraph Clients
        client_a["Client A (SSE stream)"]
        client_b["Client B (SSE stream)"]
        client_c["Client C (SSE stream)"]
    end

    poller -->|put| sys_info
    sys_info -->|get| broadcast
    broadcast -->|put| sub_a
    broadcast -->|put| sub_b
    broadcast -->|put| sub_c
    sub_a -->|consumer generator| client_a
    sub_b -->|consumer generator| client_b
    sub_c -->|consumer generator| client_c
```

## Data Flow Summary

| Step | Component                  | Action                                                                                  |
|------|----------------------------|-----------------------------------------------------------------------------------------|
| 1    | `poller`                   | Iterates `SYSTEM_DATA`, puts item into `sys_info` queue, sleeps 2s                      |
| 2    | `broadcast_to_all`         | Awaits `sys_info.get()`, then fans out via `asyncio.gather` to every `sub.queue`        |
| 3    | `Subscription.consumer()`  | Each client's async generator awaits `self.queue.get()`, yielding `ServerSentEvent`     |
| 4    | FastAPI SSE                | `EventSourceResponse` wraps the generator, pushing events to the HTTP response          |

### Key Implementation Details (`app/app.py`)

- **`client_subs: dict[str, Subscription]`** — Maps client id → Subscription (created at `app/app.py:60`)
- **`sub_lock: asyncio.Lock`** — Guards concurrent access to `client_subs` (created at `app/app.py:62`)
- **`GET /stream/all/{id}`** — Drops old sub if exists, creates new `Subscription`, streams until disconnect (`app/app.py:83-100`)
- **`Subscription.queue`** — Private per-client queue with `maxsize=1` — newest snapshot replaces old if client is slow (`app/app.py:52`)
- **`broadcast_to_all`** — Runs forever, pulls from `sys_info`, pushes to all subs simultaneously (`app/app.py:14-22`)
