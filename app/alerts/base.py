from typing import Protocol

from app.models.alert import Alert


class AlertEvaluator(Protocol):
    def evaluate(self, snapshot: dict) -> list[Alert]: ...
