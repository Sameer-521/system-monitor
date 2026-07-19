import time
from dataclasses import dataclass, field
from enum import Enum


class AlertLevel(Enum):
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(Enum):
    FIRING = "firing"
    ACKED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class Alert:
    metric: str
    severity: AlertLevel
    message: str
    state: AlertState
    fired_at: float = field(default_factory=time.monotonic)
    extra: dict = field(default_factory=dict)


class AlertsManager:
    def __init__(self) -> None:
        self.alerts: dict[str, Alert] = {}

    def register_alert(self, alert: Alert) -> bool:
        stored = self.alerts.get(alert.metric, None)

        if stored and stored.state == AlertState.FIRING:
            return False
        alert.state = AlertState.FIRING
        self.alerts[alert.metric] = alert
        return True

    def view_alerts(self) -> None:
        print(self.alerts)
