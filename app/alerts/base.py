from typing import Protocol

from app.models.alert import Alert


class AlertEvaluator(Protocol):
    def evaluate(self, snapshot: dict, timestamp: float) -> list[Alert]: ...
