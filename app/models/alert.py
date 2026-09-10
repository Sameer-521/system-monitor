import time
from dataclasses import dataclass, field
from enum import Enum


class AlertLevel(Enum):
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(Enum):
    OK = "ok"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class Alert:
    metric: str
    severity: AlertLevel
    message: str
    state: AlertState
    fired_at: float = field(default_factory=time.monotonic)
    extra: dict = field(default_factory=dict)
