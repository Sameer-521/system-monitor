import time
from dataclasses import dataclass, field
from enum import Enum, StrEnum


class AlertLevel(Enum):
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(Enum):
    OK = "ok"
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertCategory(StrEnum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    PROCESS = "process"
    SYSTEM_HEALTH = "system_health"


class AlertTier(StrEnum):
    CORE = "core"
    OPTIONAL = "optional"
    EXTENSION = "extension"


@dataclass
class Alert:
    metric: str
    severity: AlertLevel
    message: str
    state: AlertState
    fired_at: float = field(default_factory=time.monotonic)
    extra: dict = field(default_factory=dict)
    name: str | None = None
    category: AlertCategory | None = None
    tier: AlertTier | None = None
