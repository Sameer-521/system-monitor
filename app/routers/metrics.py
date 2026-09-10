import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.sse import EventSourceResponse

from app.collectors.cpu import fetch_cpu_info
from app.collectors.disk import fetch_disk_info
from app.collectors.memory import fetch_mem_info
from app.collectors.process import fetch_process_by_pid, fetch_processes
from app.engine.pipeline import fetch_system_resources
from app.pubsub import Subscription
from app.schema import MetricsParams, ProcessPidParam
from app.settings import _settings
from app.shared import client_subs, sub_lock
from app.ticket import TicketStore

tickets_store = TicketStore(_settings.ticket_lifetime)
metrics_router = APIRouter(prefix="/metrics")


@metrics_router.get("/stream/{user_id}", response_class=EventSourceResponse)
async def stream_all(
    request: Request,
    user_id: str,
    metrics_filters: Annotated[MetricsParams, Query()],
    valid_ticket: bool = Depends(tickets_store.verify_ticket_header),
):
    _filters = [str(key) for key, val in metrics_filters.model_dump().items() if val]
    # drop existing sub if any
    async with sub_lock:
        old_sub = client_subs.get(user_id, None)
        if old_sub is not None:
            _ = client_subs.pop(user_id, None)

        sub = Subscription(user_id, _filters)
        client_subs[user_id] = sub
        # print(client_subs)

    try:
        async for event in sub.consumer(user_id):
            yield event
    finally:
        async with sub_lock:
            print(f"client: {user_id} disconnected from stream")
            _ = client_subs.pop(user_id, None)


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
    data = await asyncio.to_thread(fetch_cpu_info)
    return {"response": data}


@metrics_router.get("/memory")
async def get_memory_info():
    data = await asyncio.to_thread(fetch_mem_info)
    return {"response": data}


@metrics_router.get("/disk")
async def get_disk_info():
    data = await asyncio.to_thread(fetch_disk_info)
    return {"response": data}


@metrics_router.get("/processes")
async def get_all_processes():
    data = await asyncio.to_thread(fetch_processes)
    return {"response": data}


@metrics_router.get("/process")
async def get_process_by_pid(pid: Annotated[ProcessPidParam, Query()]):
    result = await asyncio.to_thread(fetch_process_by_pid, pid.pid)
    if isinstance(result, Exception):
        raise result
    return {"response": result}
