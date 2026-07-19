from collections import deque
from dataclasses import dataclass, field


@dataclass
class RingBuffer:
    metric_id: str
    contents: deque[float] = field(default_factory=lambda: deque(maxlen=300))


class BucketedRingBuffer:
    def __init__(self, bucket_size: int = 10, max_buckets: int = 30) -> None:
        self.bucket_size = bucket_size
        self.current: list[float] = []
        self.buckets: deque[float] = deque(maxlen=max_buckets)

    def ready(self) -> bool:
        max = self.buckets.maxlen or 0
        return len(self.buckets) >= max

    def feed(self, value: float) -> float | None:
        self.current.append(value)
        if len(self.current) >= self.bucket_size:
            avg = sum(self.current) / self.bucket_size
            self.buckets.append(avg)
            self.current.clear()
            return avg
        return None
