import asyncio
from app.pubsub import LatestSnapshot, Subscription

sub_lock = asyncio.Lock()
client_subs: dict[str, Subscription] = {}
latest_snapshot = LatestSnapshot()
