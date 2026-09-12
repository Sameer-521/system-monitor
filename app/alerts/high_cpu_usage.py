from collections import deque
from enum import Enum

from app.models.alert import Alert, AlertLevel, AlertState
from app.models.buffer import BucketedRingBuffer


class CpuUsageState(Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class HighCpuUsage:
    BUCKET_SIZE: int = 10
    MAX_BUCKETS: int = 2

    CRITICAL_CPU_THRESHOLD: int = 90
    WARNING_CPU_THRESHOLD: int = 70

    # M means max num of values for the specific metric
    M_WARNING_TICKS: int = 6
    M_CRITICAL_TICKS: int = 4

    M_WARNING_RECOVERY_TICKS: int = 8
    M_CRITICAL_RECOVERY_TICKS: int = 6

    N_WARNING_TRIGGER_TICKS: int = 5  # 5 of 6
    N_CRITICAL_TRIGGER_TICKS: int = 3  # 3 of 4
    N_WARNING_RECOVERY_TICKS: int = 6  # 6 of 8
    N_CRITICAL_RECOVERY_TICKS: int = 5  # 5 of 6

    def __init__(self) -> None:
        self.state: CpuUsageState = CpuUsageState.OK

        self.buffer = BucketedRingBuffer(bucket_size=self.BUCKET_SIZE, max_buckets=self.MAX_BUCKETS)

        self.critical_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_TICKS)
        self.critical_recovery_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_RECOVERY_TICKS)

        self.warning_ticks: deque[bool] = deque(maxlen=self.M_WARNING_TICKS)
        self.warning_recovery_ticks: deque[bool] = deque(maxlen=self.M_WARNING_RECOVERY_TICKS)

    def evaluate(self, snapshot: dict) -> list[Alert]:
        new_usage: float = snapshot["cpu"]["usage_percentage"]
        alerts: list[Alert] = []

        bucket_avg: float | None = self.buffer.feed(new_usage)
        if bucket_avg is None:
            return alerts

        crit_breach: bool = bucket_avg >= self.CRITICAL_CPU_THRESHOLD
        warn_breach: bool = bucket_avg >= self.WARNING_CPU_THRESHOLD

        self.critical_ticks.append(crit_breach)
        self.warning_ticks.append(warn_breach)

        if self.state == CpuUsageState.CRITICAL:
            self.critical_recovery_ticks.append(not crit_breach)
        if self.state != CpuUsageState.OK:
            self.warning_recovery_ticks.append(not warn_breach)

        if (
            sum(self.critical_ticks) >= self.N_CRITICAL_TRIGGER_TICKS
            and self.state != CpuUsageState.CRITICAL
        ):
            # ok / warning -> critical, bypasses warning from ok
            self.state = CpuUsageState.CRITICAL
            self.critical_ticks.clear()
            self.critical_recovery_ticks.clear()
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric="cpu_usage",
                severity=AlertLevel.CRITICAL,
                message=(
                    f"CPU usage {bucket_avg:.2f}% exceeds critical threshold "
                    f"{self.CRITICAL_CPU_THRESHOLD}%"
                ),
                state=AlertState.FIRING,
                extra={
                    "cpu_usage": bucket_avg,
                    "threshold": self.CRITICAL_CPU_THRESHOLD,
                    "window": f"{self.N_CRITICAL_TRIGGER_TICKS}/{self.M_CRITICAL_TICKS} buckets",
                },
            )
            alerts.append(new_alert)

        elif (
            self.state == CpuUsageState.CRITICAL
            and sum(self.critical_recovery_ticks) >= self.N_CRITICAL_RECOVERY_TICKS
        ):
            if sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS:
                # critical -> ok, full recovery
                self.state = CpuUsageState.OK
                self.critical_ticks.clear()
                self.critical_recovery_ticks.clear()
                self.warning_ticks.clear()
                self.warning_recovery_ticks.clear()
                new_alert = Alert(
                    metric="cpu_usage",
                    severity=AlertLevel.INFO,
                    message=(
                        f"CPU usage {bucket_avg:.2f}% back to normal "
                        f"(below {self.WARNING_CPU_THRESHOLD}%) — resolved"
                    ),
                    state=AlertState.RESOLVED,
                    extra={
                        "cpu_usage": bucket_avg,
                        "threshold": self.WARNING_CPU_THRESHOLD,
                        "window": (
                            f"{self.N_WARNING_RECOVERY_TICKS}/"
                            f"{self.M_WARNING_RECOVERY_TICKS} buckets"
                        ),
                    },
                )
                alerts.append(new_alert)
            else:
                # critical -> warning, partial recovery
                self.state = CpuUsageState.WARNING
                self.critical_ticks.clear()
                self.critical_recovery_ticks.clear()
                new_alert = Alert(
                    metric="cpu_usage",
                    severity=AlertLevel.WARNING,
                    message=(
                        f"CPU usage {bucket_avg:.2f}% recovered below critical threshold "
                        f"{self.CRITICAL_CPU_THRESHOLD}% — de-escalating to warning"
                    ),
                    state=AlertState.FIRING,
                    extra={
                        "cpu_usage": bucket_avg,
                        "threshold": self.CRITICAL_CPU_THRESHOLD,
                        "window": (
                            f"{self.N_CRITICAL_RECOVERY_TICKS}/"
                            f"{self.M_CRITICAL_RECOVERY_TICKS} buckets"
                        ),
                    },
                )
                alerts.append(new_alert)

        elif (
            self.state == CpuUsageState.OK
            and sum(self.warning_ticks) >= self.N_WARNING_TRIGGER_TICKS
        ):
            # ok -> warning
            self.state = CpuUsageState.WARNING
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric="cpu_usage",
                severity=AlertLevel.WARNING,
                message=(
                    f"CPU usage {bucket_avg:.2f}% exceeds warning threshold "
                    f"{self.WARNING_CPU_THRESHOLD}%"
                ),
                state=AlertState.FIRING,
                extra={
                    "cpu_usage": bucket_avg,
                    "threshold": self.WARNING_CPU_THRESHOLD,
                    "window": f"{self.N_WARNING_TRIGGER_TICKS}/{self.M_WARNING_TICKS} buckets",
                },
            )
            alerts.append(new_alert)

        elif (
            self.state == CpuUsageState.WARNING
            and sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS
        ):
            # warning -> ok
            self.state = CpuUsageState.OK
            self.warning_ticks.clear()
            self.warning_recovery_ticks.clear()
            new_alert = Alert(
                metric="cpu_usage",
                severity=AlertLevel.INFO,
                message=(
                    f"CPU usage {bucket_avg:.2f}% back to normal "
                    f"(below {self.WARNING_CPU_THRESHOLD}%) — resolved"
                ),
                state=AlertState.RESOLVED,
                extra={
                    "cpu_usage": bucket_avg,
                    "threshold": self.WARNING_CPU_THRESHOLD,
                    "window": (
                        f"{self.N_WARNING_RECOVERY_TICKS}/{self.M_WARNING_RECOVERY_TICKS} buckets"
                    ),
                },
            )
            alerts.append(new_alert)

        return alerts
