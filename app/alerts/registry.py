import time

from app.models.alert import Alert, AlertLevel, AlertState
from app.alerts.base import AlertEvaluator


def int_value(severity: AlertLevel) -> int:
    map: dict[AlertLevel, int] = {
        AlertLevel.INFO: 1,
        AlertLevel.DEBUG: 2,
        AlertLevel.WARNING: 3,
        AlertLevel.CRITICAL: 4,
    }

    return map[severity]


class AlertRegistry:
    def __init__(self, evaluators: list[AlertEvaluator]) -> None:
        self.evaluators = evaluators
        self.alerts_store: dict[str, dict] = {}
        self.cooldown: int = 60  # seconds

    def cooldown_active(self, old: Alert) -> bool:
        return (time.monotonic() - old.fired_at) <= self.cooldown

    def manage(self, alerts: list[Alert]):
        to_send: list[Alert] = []

        for alert in alerts:
            if alert.metric in self.alerts_store:
                old_alert: Alert = self.alerts_store[alert.metric]["content"]

                if alert.state == AlertState.RESOLVED:
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
            alerts.extend(evaluator.evaluate(snapshot))
        return alerts
