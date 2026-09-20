from typing import Protocol

from app.models.alert import Alert, AlertCategory, AlertTier


class AlertEvaluator(Protocol):
    name: str
    category: AlertCategory
    tier: AlertTier

    def evaluate(self, snapshot: dict) -> list[Alert]: ...
