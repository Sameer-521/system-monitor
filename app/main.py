import asyncio
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.sse import EventSourceResponse

from app.schema import MetricsParams, Register
from app.pubsub import Subscription, LatestSnapshot, broadcast, poller
from app.ticket import TicketStore
from app.system_info import fetch_processes, fetch_process_by_pid

TICKET_LIFETIME = 300
DEFAULT_FILTERS = ["timestamp", "hostname", "uptime_seconds"]
clients = set()
sub_lock = asyncio.Lock()

latest_snapshot = LatestSnapshot()
tickets_store = TicketStore(TICKET_LIFETIME)
client_subs: dict[str, Subscription] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks = [
        asyncio.create_task(poller(latest_snapshot)),
        asyncio.create_task(broadcast(latest_snapshot, client_subs, sub_lock)),
    ]
    print("Tasks created succesfully...")
    clients.add("Sameer")
    clients.add("John")

    yield

    print("Initiating graceful shutdown for all tasks...")
    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("All background tasks closed safely.")


app = FastAPI(lifespan=lifespan)


@app.post("/register", status_code=201)
async def register(user: Register):
    username: str = user.model_dump().get("username", "")
    if username in clients:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "user already exists"}
        )
    clients.add(username)
    print(f"Client: {username}")


@app.get("/stream/all/{id}", response_class=EventSourceResponse)
async def stream_all(
    id: str,
    metrics_filters: Annotated[MetricsParams, Query()],
    valid_ticket=Depends(tickets_store.verify_ticket),
):
    _filters = [str(key) for key, val in metrics_filters.model_dump().items() if val]
    # drop existing sub if any
    async with sub_lock:
        old_sub = client_subs.get(id, None)
        if old_sub is not None:
            client_subs.pop(old_sub.id, None)

        sub = Subscription(id, _filters)
        client_subs[id] = sub
        # print(client_subs)

    try:
        async for event in sub.consumer():
            yield event
    finally:
        async with sub_lock:
            print(f"client: {id} disconnected from stream")
            client_subs.pop(id, None)


@app.post("/stream/ticket/{user_id}")
async def issue_ticket(user_id: str):
    if user_id not in clients:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user not authorized"},
        )

    ticket = tickets_store.issue(user_id)
    return {"ticket": ticket}


@app.get("/system/snapshot")
async def get_sys_snapshot():
    data = await latest_snapshot.get_latest()
    return {"response": data}


@app.get("/processes")
async def get_all_processes():
    data = await asyncio.to_thread(fetch_processes)
    return {"response": data}


@app.get("/processes/{pid}")
async def get_process_by_pid(pid: Annotated[int, Path(ge=1)]):
    result = await asyncio.to_thread(fetch_process_by_pid, pid)
    if isinstance(result, Exception):
        raise result
    return {"response": result}
