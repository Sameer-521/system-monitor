from app.models.alert import Alert
from app.alerts.base import AlertEvaluator


class AlertRegistry:
    def __init__(self, evaluators: list[AlertEvaluator]) -> None:
        self.evaluators = evaluators

    def evaluate(self, snapshot: dict, timestamp: float) -> list[Alert]:
        alerts: list[Alert] = []
        for evaluator in self.evaluators:
            alerts.extend(evaluator.evaluate(snapshot, timestamp))
        return alerts
