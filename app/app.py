import asyncio
import time
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.data import SYSTEM_DATA
from app.schema import MetricsParams, Register, Snapshot

TICKET_LIFETIME = 300
DEFAULT_FILTERS = ["timestamp", "hostname", "uptime_seconds"]
clients = set()


async def verify_ticket(ticket: Annotated[str, Query(max_length=50)]):
    if not tickets_store.consume(ticket):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid ticket"}
        )
    return ticket


@dataclass(frozen=True)
class Ticket:
    id: str
    issued_at: float
    claims: dict[str, str]


class TicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def issue(self, client_id: str) -> Ticket:
        ticket_id = str(uuid4())
        curr_time = time.monotonic()
        claims = {"client_id": client_id}
        ticket = Ticket(ticket_id, curr_time, claims)
        self._tickets[ticket_id] = ticket
        return ticket

    def consume(self, ticket_id) -> bool:
        """Returns True if ticket was valid and consumed succesfully else False"""
        curr_time = time.monotonic()
        ticket = self._tickets.get(ticket_id, None)

        if ticket and (curr_time - ticket.issued_at) <= TICKET_LIFETIME:
            self._tickets.pop(ticket_id)
            # print("Valid")
            return True

        # print("Invalid")
        return False


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
    clients.add("Sameer")

    yield

    print("Initiating graceful shutdown for all tasks...")
    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("All background tasks closed safely.")


app = FastAPI(lifespan=lifespan)

sys_info = asyncio.Queue()
tickets_store = TicketStore()


class Subscription:
    def __init__(self, owner_id: str, _filters: list[str]):
        self.id = str(uuid4())
        self.owner_id = owner_id
        self.queue = asyncio.Queue(maxsize=1)
        self._filters = _filters

    async def consumer(self) -> AsyncIterable[ServerSentEvent]:
        while True:
            payload = await self.queue.get()
            filtered = {
                key: payload[key]
                for key in self._filters
                if key in payload.keys() or key in DEFAULT_FILTERS
            }
            yield ServerSentEvent(data=Snapshot(info=filtered))


client_subs: dict[str, Subscription] = {}
sub_lock = asyncio.Lock()


async def poller():
    while True:
        await sys_info.put(SYSTEM_DATA)
        await asyncio.sleep(2)


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
    valid_ticket=Depends(verify_ticket),
):
    # drop existing sub if any
    async with sub_lock:
        old_sub = client_subs.get(id, None)
        if old_sub is not None:
            client_subs.pop(old_sub.id, None)

    _filters = [str(key) for key, val in metrics_filters.model_dump().items() if val]
    sub = Subscription(id, _filters)
    client_subs[id] = sub
    print(client_subs)

    try:
        async for event in sub.consumer():
            yield event
    finally:
        async with sub_lock:
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
