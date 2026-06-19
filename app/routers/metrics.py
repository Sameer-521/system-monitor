import asyncio
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request, status
from fastapi.sse import EventSourceResponse

from app.pubsub import Subscription
from app.schema import MetricsParams
from app.system_info import (
    fetch_process_by_pid,
    fetch_processes,
    _fetch_cpu_info,
    _fetch_disk_info,
    _fetch_mem_info,
    fetch_system_resources,
)
from app.shared import sub_lock, client_subs
from app.ticket import TicketStore
from app.settings import _settings


from fastapi import APIRouter

tickets_store = TicketStore(_settings.ticket_lifetime)
metrics_router = APIRouter(prefix="/metrics")


@metrics_router.get("/stream/{id}", response_class=EventSourceResponse)
async def stream_all(
    request: Request,
    id: str,
    metrics_filters: Annotated[MetricsParams, Query()],
    valid_ticket=Depends(tickets_store.verify_ticket_header),
):
    _filters = [str(key) for key, val in metrics_filters.model_dump().items() if val]
    # drop existing sub if any
    async with sub_lock:
        old_sub = client_subs.get(id, None)
        if old_sub is not None:
            _ = client_subs.pop(id, None)

        sub = Subscription(id, _filters)
        client_subs[id] = sub
        # print(client_subs)

    try:
        async for event in sub.consumer(id):
            yield event
    finally:
        async with sub_lock:
            print(f"client: {id} disconnected from stream")
            _ = client_subs.pop(id, None)


@metrics_router.post("/stream/ticket/{user_id}")
async def issue_ticket(request: Request, user_id: str):
    if user_id not in request.app.state.clients:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user not authorized"},
        )

    ticket = tickets_store.issue(user_id)
    return {"ticket": ticket}


@metrics_router.get("/snapshot")
async def get_all_resources():
    data = await asyncio.to_thread(fetch_system_resources)
    return {"response": data}


@metrics_router.get("/cpu")
async def get_cpu_info():
    data = await asyncio.to_thread(_fetch_cpu_info)
    return {"response": data}


@metrics_router.get("/memory")
async def get_memory_info():
    data = await asyncio.to_thread(_fetch_mem_info)
    return {"response": data}


@metrics_router.get("/disk")
async def get_disk_info():
    data = await asyncio.to_thread(_fetch_disk_info)
    return {"response": data}


@metrics_router.get("/processes")
async def get_all_processes():
    data = await asyncio.to_thread(fetch_processes)
    return {"response": data}


@metrics_router.get("/processes/{pid}")
async def get_process_by_pid(pid: Annotated[int, Path(ge=1)]):
    result = await asyncio.to_thread(fetch_process_by_pid, pid)
    if isinstance(result, Exception):
        raise result
    return {"response": result}
