import time

from app.models.alert import Alert, AlertCategory, AlertState, AlertTier
from app.alerts.base import AlertEvaluator


def _validate_classification(evaluator: AlertEvaluator) -> None:
    label = type(evaluator).__name__
    missing = [
        attr for attr in ("name", "category", "tier") if getattr(evaluator, attr, None) is None
    ]
    if missing:
        raise ValueError(f"{label} is missing alert classification metadata: {', '.join(missing)}")
    if not isinstance(evaluator.name, str) or not evaluator.name.strip():
        raise ValueError(f"{label}.name must be a non-empty string")
    if not isinstance(evaluator.category, AlertCategory):
        raise ValueError(f"{label}.category must be an AlertCategory, got {evaluator.category!r}")
    if not isinstance(evaluator.tier, AlertTier):
        raise ValueError(f"{label}.tier must be an AlertTier, got {evaluator.tier!r}")


class AlertRegistry:
    def __init__(self, evaluators: list[AlertEvaluator]) -> None:
        self.evaluators: list[AlertEvaluator] = []
        self.alerts_store: dict[str, dict] = {}
        self.cooldown: int = 60  # seconds
        for evaluator in evaluators:
            self.register(evaluator)

    def register(self, evaluator: AlertEvaluator) -> None:
        _validate_classification(evaluator)
        self.evaluators.append(evaluator)

    def cooldown_active(self, old: Alert) -> bool:
        return (time.monotonic() - old.fired_at) <= self.cooldown

    def manage(self, alerts: list[Alert]):
        to_send: list[Alert] = []

        for alert in alerts:
            if alert.metric in self.alerts_store:
                old_alert: Alert = self.alerts_store[alert.metric]["content"]

                if alert.state == AlertState.RESOLVED and old_alert.state != AlertState.RESOLVED:
                    self.alerts_store[alert.metric] = {
                        "content": alert,
                        "cooldown_till": alert.fired_at + self.cooldown,
                    }
                    to_send.append(alert)
                else:
                    match old_alert.state:
                        case AlertState.RESOLVED:
                            if self.cooldown_active(old_alert):
                                # drop flapping alert
                                continue
                            else:
                                # fire again
                                self.alerts_store[alert.metric] = {
                                    "content": alert,
                                    "cooldown_till": alert.fired_at + self.cooldown,
                                }
                                to_send.append(alert)
                        case AlertState.FIRING:
                            if alert.severity == old_alert.severity:
                                # new is duplicate
                                continue
                            else:
                                self.alerts_store[alert.metric] = {
                                    "content": alert,
                                    "cooldown_till": alert.fired_at + self.cooldown,
                                }
                                to_send.append(alert)

            else:
                # register
                self.alerts_store[alert.metric] = {
                    "content": alert,
                    "cooldown_till": alert.fired_at + self.cooldown,
                }
                to_send.append(alert)

        return to_send

    def evaluate(self, snapshot: dict) -> list[Alert]:
        alerts: list[Alert] = []
        for evaluator in self.evaluators:
            emitted = evaluator.evaluate(snapshot)
            for alert in emitted:
                alert.name = evaluator.name
                alert.category = evaluator.category
                alert.tier = evaluator.tier
            alerts.extend(emitted)
        return self.manage(alerts)
