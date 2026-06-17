import asyncio

from contextlib import asynccontextmanager
from collections.abc import AsyncIterable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.data import SYSTEM_DATA
from app.schema import Register, Snapshot


async def broadcast_to_all():
    while True:
        data = await sys_info.get()

        async with sub_lock:
            await asyncio.gather(
                *(sub.queue.put(data) for id, sub in client_subs.items()),
                return_exceptions=True,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks = [
        asyncio.create_task(poller()),
        asyncio.create_task(broadcast_to_all()),
    ]
    print("Tasks created succesfully...")

    yield

    print("Initiating graceful shutdown for all tasks...")
    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("All background tasks closed safely.")


app = FastAPI(lifespan=lifespan)

sys_info = asyncio.Queue()


class Subscription:
    def __init__(self, owner_id: str):
        self.id = str(uuid4())
        self.owner_id = owner_id
        self.queue = asyncio.Queue(maxsize=1)

    async def consumer(self) -> AsyncIterable[ServerSentEvent]:
        while True:
            payload = await self.queue.get()
            yield ServerSentEvent(data=Snapshot(info=payload))


client_subs: dict[str, Subscription] = {}
clients = set()
sub_lock = asyncio.Lock()


async def poller():
    while True:
        for item in SYSTEM_DATA:
            await sys_info.put(item)
            await asyncio.sleep(2)


@app.post("/register", status_code=201)
async def register(user: Register):
    username = user.model_dump().get("username")
    if username in clients:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "user already exists"}
        )
    clients.add(username)
    print(f"Client: {username}")


@app.get("/stream/all/{id}", response_class=EventSourceResponse)
async def stream_all(id: str):
    async with sub_lock:
        old_sub = client_subs.get(id, None)
        if old_sub is not None:
            client_subs.pop(old_sub.id, None)

    sub = Subscription(id)
    client_subs[id] = sub
    print(client_subs)

    try:
        async for event in sub.consumer():
            yield event
    finally:
        async with sub_lock:
            client_subs.pop(id, None)
