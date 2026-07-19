from app.models.alert import Alert
from app.models.buffer import RingBuffer
from app.models.counter import Counter


class HighMemoryAlert:
    MEM_USAGE_THRESHOLD: int = 80
    WINDOW: int = 120

    def __init__(self) -> None:
        self.buffer = RingBuffer("memory")
        self.streak = Counter(0)

    def evaluate(self, snapshot: dict, timestamp: float) -> list[Alert]:
        raise NotImplementedError
