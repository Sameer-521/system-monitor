from collections import deque
from collections.abc import Callable
from enum import Enum
from statistics import fmean
from typing import Any

from app.models.alert import Alert, AlertCategory, AlertLevel, AlertState, AlertTier
from app.models.buffer import BucketedRingBuffer


class ThresholdState(Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class ThresholdAlert:
    metric: str
    display_name: str
    name: str
    category: AlertCategory
    tier: AlertTier
    snapshot_key: tuple[str, ...]
    extra_key: str
    reducer: Callable[[list[float]], float] = staticmethod(fmean)

    BUCKET_SIZE: int = 10
    MAX_BUCKETS: int = 2

    warning_threshold: int
    critical_threshold: int

    M_WARNING_TICKS: int = 6
    M_CRITICAL_TICKS: int = 4

    M_WARNING_RECOVERY_TICKS: int = 8
    M_CRITICAL_RECOVERY_TICKS: int = 6

    N_WARNING_TRIGGER_TICKS: int = 5
    N_CRITICAL_TRIGGER_TICKS: int = 3
    N_WARNING_RECOVERY_TICKS: int = 6
    N_CRITICAL_RECOVERY_TICKS: int = 5

    def __init__(self) -> None:
        self.state = ThresholdState.OK

        self.buffer = BucketedRingBuffer(
            bucket_size=self.BUCKET_SIZE, max_buckets=self.MAX_BUCKETS, reducer=self.reducer
        )

        self.critical_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_TICKS)
        self.critical_recovery_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_RECOVERY_TICKS)

        self.warning_ticks: deque[bool] = deque(maxlen=self.M_WARNING_TICKS)
        self.warning_recovery_ticks: deque[bool] = deque(maxlen=self.M_WARNING_RECOVERY_TICKS)

    def evaluate(self, snapshot: dict) -> list[Alert]:
        value: Any = snapshot
        for key in self.snapshot_key:
            value = value[key]

        alerts: list[Alert] = []

        bucket_value: float | None = self.buffer.feed(value)
        if bucket_value is None:
            return alerts

        crit_breach: bool = bucket_value >= self.critical_threshold
        warn_breach: bool = bucket_value >= self.warning_threshold

        self.critical_ticks.append(crit_breach)
        self.warning_ticks.append(warn_breach)

        if self.state == ThresholdState.CRITICAL:
            self.critical_recovery_ticks.append(not crit_breach)
        if self.state != ThresholdState.OK:
            self.warning_recovery_ticks.append(not warn_breach)

        if (
            sum(self.critical_ticks) >= self.N_CRITICAL_TRIGGER_TICKS
            and self.state != ThresholdState.CRITICAL
        ):
            # ok / warning -> critical, bypasses warning from ok
            self.state = ThresholdState.CRITICAL
            self.critical_ticks.clear()
            self.critical_recovery_ticks.clear()
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric=self.metric,
                severity=AlertLevel.CRITICAL,
                message=(
                    f"{self.display_name} {bucket_value:.2f}% exceeds critical threshold "
                    f"{self.critical_threshold}%"
                ),
                state=AlertState.FIRING,
                extra={
                    self.extra_key: bucket_value,
                    "threshold": self.critical_threshold,
                    "window": f"{self.N_CRITICAL_TRIGGER_TICKS}/{self.M_CRITICAL_TICKS} buckets",
                },
            )
            alerts.append(new_alert)

        elif (
            self.state == ThresholdState.CRITICAL
            and sum(self.critical_recovery_ticks) >= self.N_CRITICAL_RECOVERY_TICKS
        ):
            if sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS:
                # critical -> ok, full recovery
                self.state = ThresholdState.OK
                self.critical_ticks.clear()
                self.critical_recovery_ticks.clear()
                self.warning_ticks.clear()
                self.warning_recovery_ticks.clear()
                new_alert = Alert(
                    metric=self.metric,
                    severity=AlertLevel.INFO,
                    message=(
                        f"{self.display_name} {bucket_value:.2f}% back to normal "
                        f"(below {self.warning_threshold}%) — resolved"
                    ),
                    state=AlertState.RESOLVED,
                    extra={
                        self.extra_key: bucket_value,
                        "threshold": self.warning_threshold,
                        "window": (
                            f"{self.N_WARNING_RECOVERY_TICKS}/"
                            f"{self.M_WARNING_RECOVERY_TICKS} buckets"
                        ),
                    },
                )
                alerts.append(new_alert)
            else:
                # critical -> warning, partial recovery
                self.state = ThresholdState.WARNING
                self.critical_ticks.clear()
                self.critical_recovery_ticks.clear()
                new_alert = Alert(
                    metric=self.metric,
                    severity=AlertLevel.WARNING,
                    message=(
                        f"{self.display_name} {bucket_value:.2f}% recovered below critical "
                        f"threshold {self.critical_threshold}% — de-escalating to warning"
                    ),
                    state=AlertState.FIRING,
                    extra={
                        self.extra_key: bucket_value,
                        "threshold": self.critical_threshold,
                        "window": (
                            f"{self.N_CRITICAL_RECOVERY_TICKS}/"
                            f"{self.M_CRITICAL_RECOVERY_TICKS} buckets"
                        ),
                    },
                )
                alerts.append(new_alert)

        elif (
            self.state == ThresholdState.OK
            and sum(self.warning_ticks) >= self.N_WARNING_TRIGGER_TICKS
        ):
            # ok -> warning
            self.state = ThresholdState.WARNING
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric=self.metric,
                severity=AlertLevel.WARNING,
                message=(
                    f"{self.display_name} {bucket_value:.2f}% exceeds warning threshold "
                    f"{self.warning_threshold}%"
                ),
                state=AlertState.FIRING,
                extra={
                    self.extra_key: bucket_value,
                    "threshold": self.warning_threshold,
                    "window": f"{self.N_WARNING_TRIGGER_TICKS}/{self.M_WARNING_TICKS} buckets",
                },
            )
            alerts.append(new_alert)

        elif (
            self.state == ThresholdState.WARNING
            and sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS
        ):
            # warning -> ok
            self.state = ThresholdState.OK
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric=self.metric,
                severity=AlertLevel.INFO,
                message=(
                    f"{self.display_name} {bucket_value:.2f}% back to normal "
                    f"(below {self.warning_threshold}%) — resolved"
                ),
                state=AlertState.RESOLVED,
                extra={
                    self.extra_key: bucket_value,
                    "threshold": self.warning_threshold,
                    "window": (
                        f"{self.N_WARNING_RECOVERY_TICKS}/{self.M_WARNING_RECOVERY_TICKS} buckets"
                    ),
                },
            )
            alerts.append(new_alert)

        return alerts
