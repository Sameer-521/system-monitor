from collections import deque

from app.models.buffer import RingBuffer
from app.models.counter import Counter
from app.models.alert import AlertsManager

cpu_buffer = RingBuffer("cpu")
mem_buffer = RingBuffer("memory")

high_cpu_usage_counter = Counter(0)
alert_manager = AlertsManager()

bucketed_cpu: deque[float] = deque(maxlen=30)
current_bucket: list[float] = []
