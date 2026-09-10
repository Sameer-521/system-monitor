from collections import deque
from enum import Enum

import psutil

from app.models.alert import Alert, AlertLevel, AlertState


class LoadAvgState(Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class HighLoadAvg:
    num_cpus: int = psutil.cpu_count(logical=True) or 0

    NORMAL: float = num_cpus * 1.0
    WARNING_MULTIPLIER: float = 1.5
    CRITICAL_MULTIPLIER: float = 3.0
    warning_threshold: float = num_cpus * WARNING_MULTIPLIER
    critical_threshold: float = num_cpus * CRITICAL_MULTIPLIER

    SAMPLES: int = 10

    # M means max num of values for the specific metric
    M_WARNING_TICKS: int = 18
    M_CRITICAL_TICKS: int = 12

    M_WARNING_RECOVERY_TICKS: int = 30
    M_CRITICAL_RECOVERY_TICKS: int = 6

    N_WARNING_TRIGGER_TICKS: int = 14  # 14 of 18
    N_CRITICAL_TRIGGER_TICKS: int = 9  # 9 of 12
    N_WARNING_RECOVERY_TICKS: int = 24  # 24 of 30
    N_CRITICAL_RECOVERY_TICKS: int = 5  # 5 of 6

    def __init__(self) -> None:
        self.state: LoadAvgState = LoadAvgState.OK

        self.buffer: deque[tuple[float, float]] = deque(maxlen=self.SAMPLES)

        self.critical_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_TICKS)
        self.critical_recovery_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_RECOVERY_TICKS)

        self.warning_ticks: deque[bool] = deque(maxlen=self.M_WARNING_TICKS)
        self.warning_recovery_ticks: deque[bool] = deque(maxlen=self.M_WARNING_RECOVERY_TICKS)

    def transition_phase1(self, w_avg: float, alerts: list[Alert]) -> None:
        """
        transition between ok and warning.
        can escalate from ok to critical.
        """
        # ok - warning phase
        if w_avg >= self.warning_threshold:
            self.warning_ticks.append(True)
            self.warning_recovery_ticks.append(False)

            if (
                sum(self.warning_ticks) >= self.N_WARNING_TRIGGER_TICKS
                and self.state == LoadAvgState.OK
            ):
                # ok -> warning
                self.state = LoadAvgState.WARNING
                self.warning_recovery_ticks.clear()
                new_alert = Alert(
                    metric="load_average",
                    severity=AlertLevel.WARNING,
                    message=(
                        f"5m load average {w_avg:.2f} exceeds warning threshold "
                        f"{self.warning_threshold:.2f}"
                    ),
                    state=AlertState.FIRING,
                    extra={
                        "load_avg_5m": w_avg,
                        "threshold": self.warning_threshold,
                        "window": f"{self.N_WARNING_TRIGGER_TICKS}/{self.M_WARNING_TICKS} ticks",
                    },
                )
                alerts.append(new_alert)

        else:
            if self.state == LoadAvgState.OK:
                # skip warning tick
                self.warning_ticks.append(False)

            if self.state in [LoadAvgState.WARNING, LoadAvgState.CRITICAL] and w_avg < self.NORMAL:
                # the check on critical is to make sure warning_recovery_ticks still land
                self.warning_recovery_ticks.append(True)
                if (
                    sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS
                    and self.state == LoadAvgState.WARNING
                ):
                    # warning -> ok
                    self.state = LoadAvgState.OK
                    self.warning_ticks.clear()
                    new_alert = Alert(
                        metric="load_average",
                        severity=AlertLevel.INFO,
                        message=(
                            f"5m load average {w_avg:.2f} back to normal (below {self.NORMAL:.2f}) — resolved"
                        ),
                        state=AlertState.RESOLVED,
                        extra={
                            "load_avg_5m": w_avg,
                            "threshold": self.NORMAL,
                            "window": f"{self.N_WARNING_RECOVERY_TICKS}/{self.M_WARNING_RECOVERY_TICKS} ticks",
                        },
                    )
                    alerts.append(new_alert)
            else:  # ok
                self.warning_recovery_ticks.append(False)

    def transition_phase2(self, c_avg: float, alerts: list[Alert]) -> None:
        """
        Transition between warning and critical.
        Can only de-escalate critical to warning and not critical to normal.
        """
        # critical phase
        if c_avg >= self.critical_threshold:
            self.critical_ticks.append(True)
            self.critical_recovery_ticks.append(False)

            if sum(self.critical_ticks) >= self.N_CRITICAL_TRIGGER_TICKS and self.state in [
                LoadAvgState.OK,
                LoadAvgState.WARNING,
            ]:
                # ok / warning -> critical
                self.state = LoadAvgState.CRITICAL
                self.critical_recovery_ticks.clear()
                self.critical_ticks.clear()
                self.warning_ticks.clear()
                self.warning_recovery_ticks.clear()
                new_alert = Alert(
                    metric="load_average",
                    severity=AlertLevel.CRITICAL,
                    message=(
                        f"1m load average {c_avg:.2f} exceeds critical threshold "
                        f"{self.critical_threshold:.2f}"
                    ),
                    state=AlertState.FIRING,
                    extra={
                        "load_avg_1m": c_avg,
                        "threshold": self.critical_threshold,
                        "window": f"{self.N_CRITICAL_TRIGGER_TICKS}/{self.M_CRITICAL_TICKS} ticks",
                    },
                )
                if len(alerts) > 0:
                    alerts[0] = new_alert
                else:
                    alerts.append(new_alert)
        else:
            self.critical_ticks.append(False)
            if self.state == LoadAvgState.CRITICAL:
                if c_avg < self.warning_threshold:
                    self.critical_recovery_ticks.append(True)
                    if sum(self.critical_recovery_ticks) >= self.N_CRITICAL_RECOVERY_TICKS:
                        # critical -> warning
                        self.state = LoadAvgState.WARNING
                        self.critical_recovery_ticks.clear()
                        self.critical_ticks.clear()
                        new_alert = Alert(
                            metric="load_average",
                            severity=AlertLevel.WARNING,
                            message=(
                                f"1m load average {c_avg:.2f} recovered below critical threshold "
                                f"{self.critical_threshold:.2f} — de-escalating to warning"
                            ),
                            state=AlertState.FIRING,
                            extra={
                                "load_avg_1m": c_avg,
                                "threshold": self.warning_threshold,
                                "window": f"{self.N_CRITICAL_RECOVERY_TICKS}/{self.M_CRITICAL_RECOVERY_TICKS} ticks",
                            },
                        )
                        alerts.append(new_alert)
                else:
                    self.critical_recovery_ticks.append(False)

    def evaluate(self, snapshot: dict) -> list[Alert]:
        alerts = []
        new_load_avgs: dict[str, float] = snapshot["cpu"]["load_average"]
        c_tick = new_load_avgs["1min"]
        w_tick = new_load_avgs["5min"]

        self.buffer.append((c_tick, w_tick))

        if len(self.buffer) >= self.SAMPLES:
            c_avg = sum([sample[0] for sample in self.buffer]) / self.SAMPLES
            w_avg = sum([sample[1] for sample in self.buffer]) / self.SAMPLES

            self.transition_phase1(w_avg, alerts)
            self.transition_phase2(c_avg, alerts)

            self.buffer.clear()
            return alerts

        # not enough samples
        else:
            return []
