from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RingBuffer:
    metric_id: str
    contents: deque[float] = field(default_factory=lambda: deque(maxlen=300))


class BucketedRingBuffer:
    def __init__(
        self,
        bucket_size: int = 10,
        max_buckets: int = 30,
        reducer: Callable[[list[float]], float] | None = None,
    ) -> None:
        self.bucket_size = bucket_size
        self.reducer: Callable[[list[float]], float] = reducer if reducer else self._mean
        self.current: list[float] = []
        self.buckets: deque[float] = deque(maxlen=max_buckets)

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    def ready(self) -> bool:
        max = self.buckets.maxlen or 0
        return len(self.buckets) >= max

    def feed(self, value: float) -> float | None:
        self.current.append(value)
        if len(self.current) >= self.bucket_size:
            bucket_value = self.reducer(self.current)
            self.buckets.append(bucket_value)
            self.current.clear()
            return bucket_value
        return None
