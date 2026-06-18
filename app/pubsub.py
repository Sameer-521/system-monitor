import asyncio
from uuid import uuid4
from typing import Any
from collections.abc import AsyncIterable
from fastapi.sse import ServerSentEvent

from app.settings import _settings
from app.schema import Snapshot
from app.system_info import fetch_system_resources


DEFAULT_FILTERS = ["timestamp", "hostname", "uptime_seconds"]


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


class LatestSnapshot:
    def __init__(self) -> None:
        self.value = 0
        self._condition = asyncio.Condition()
        self._version = 0

    async def set(self, value) -> None:
        async with self._condition:
            self.value = value
            self._version += 1
            self._condition.notify_all()

    async def get_latest(self, last_seen_version: int = -1) -> tuple[Any, int]:
        async with self._condition:
            await self._condition.wait_for(lambda: self._version != last_seen_version)
            return self.value, self._version


async def poller(snapshot: LatestSnapshot) -> None:
    while True:
        await asyncio.sleep(_settings.poller_interval)
        info = await asyncio.to_thread(fetch_system_resources)
        await snapshot.set(info)


async def broadcast(
    snapshot: LatestSnapshot, subs: dict[str, Subscription], sub_lock: asyncio.Lock
) -> None:
    last_version = -1
    while True:
        data, last_version = await snapshot.get_latest(last_version)
        async with sub_lock:
            for _, sub in subs.items():
                try:
                    sub.queue.put_nowait(data)
                except asyncio.QueueFull:
                    pass  # drop snapshot for the client
