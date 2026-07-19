from app.models.alert import Alert
from app.models.buffer import RingBuffer
from app.models.counter import Counter


class HighCpuAlert:
    CPU_USAGE_THRESHOLD: int = 70
    WINDOW: int = 120

    def __init__(self) -> None:
        self.buffer = RingBuffer("cpu")
        self.streak = Counter(0)

    def evaluate(self, snapshot: dict, timestamp: float) -> list[Alert]:
        raise NotImplementedError
