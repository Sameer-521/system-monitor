import psutil
from collections import deque

from app.models.alert import Alert, AlertLevel, AlertState


class HighLoadAvg:
    num_cpus: int = psutil.cpu_count(logical=True) or 0

    NORMAL: float = num_cpus * 1.0
    WARNING_MULTIPLIER: float = 1.5
    CRITICAL_MULTIPLIER: float = 3.0
    warning_threshold: float = num_cpus * WARNING_MULTIPLIER
    critical_threshold: float = num_cpus * CRITICAL_MULTIPLIER

    SAMPLES: int = 10
    M_WARNING_TICKS: int = 18
    M_CRITICAL_TICKS: int = 12

    N_WARNING_TRIGGER_TICKS: int = 14  # 14 of 18
    N_CRITICAL_TRIGGER_TICKS: int = 9  # 9 of 12
    N_WARNING_RECOVERY_TICKS: int = 24  # 24 of 30
    N_CRITICAL_RECOVERY_TICKS: int = 5  # 5 of 6

    def __init__(self) -> None:
        self.state = "ok"

        self.buffer: deque[tuple[float, float]] = deque(maxlen=self.SAMPLES)

        self.critical_ticks: deque[bool] = deque(maxlen=self.M_CRITICAL_TICKS)
        self.critical_recovery_ticks: deque[bool] = deque(maxlen=6)

        self.warning_ticks: deque[bool] = deque(maxlen=self.M_WARNING_TICKS)
        self.warning_recovery_ticks: deque[bool] = deque(maxlen=30)

    def transition_phase1(self, w_avg: float, alerts: list):
        """
        5-min load-avg phase (ok <-> warning).

        Trigger path (state == ok):
            w_avg >= `warning_threshold` appends True to warning_ticks, else False;
            ok -> warning fires on `N_WARNING_TRIGGER_TICKS` of the last `M_WARNING_TICKS` ticks breaching.

        Recovery path (state in warning/critical):
            each tick classifies w_avg against NORMAL (1.0c):
            below -> True, else False.
            warning -> ok fires on `N_WARNING_RECOVERY_TICKS` of the last 30 ticks below NORMAL.
            Gated on state == "warning", so in critical it only accrues.
        """
        # ok - warning phase
        if w_avg >= self.warning_threshold:
            self.warning_ticks.append(True)
            self.warning_recovery_ticks.append(False)

            if sum(self.warning_ticks) >= self.N_WARNING_TRIGGER_TICKS and self.state == "ok":
                # ok -> warning
                self.state = "warning"
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
            if self.state == "ok":
                # skip warning tick
                self.warning_ticks.append(False)

            if self.state in ["warning", "critical"] and w_avg < self.NORMAL:
                # the check on critical is to make sure warning_recovery_ticks still land
                self.warning_recovery_ticks.append(True)
                if (
                    sum(self.warning_recovery_ticks) >= self.N_WARNING_RECOVERY_TICKS
                    and self.state == "warning"
                ):
                    # warning -> ok
                    self.state = "ok"
                    self.warning_ticks.clear()
            else:  # ok
                self.warning_recovery_ticks.append(False)

    def transition_phase2(self, c_avg, alerts):
        """
        1-min load-avg phase (ok/warning <-> critical).

        Trigger path (state in (ok, warning)):
            hot ticks (c_avg >= `critical_threshold`) append True to critical_ticks;
            ok/warning -> critical fires on `N_CRITICAL_TRIGGER_TICKS` of the last
            `M_CRITICAL_TICKS` hot ticks. On entry all four windows are cleared:
            the 5-min phase pauses (but keeps observing) and both critical windows
            start fresh.

        Recovery path (state == critical):
            each tick classifies c_avg against `warning_threshold` (1.5c):
            below -> True, else False (the critical -> critical self-loop).
            critical -> warning fires on `N_CRITICAL_RECOVERY_TICKS` of the last
            6 ticks below 1.5c; the critical windows are cleared on exit while
            accrued 5-min recovery progress carries over to warning.
        """
        # critical phase
        if c_avg >= self.critical_threshold:
            self.critical_ticks.append(True)
            self.critical_recovery_ticks.append(False)

            if sum(self.critical_ticks) >= self.N_CRITICAL_TRIGGER_TICKS and self.state in [
                "ok",
                "warning",
            ]:
                # ok / warning -> critical
                self.state = "critical"
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
            if self.state == "critical":
                if c_avg < self.warning_threshold:
                    self.critical_recovery_ticks.append(True)
                    if sum(self.critical_recovery_ticks) >= self.N_CRITICAL_RECOVERY_TICKS:
                        # critical -> warning
                        self.state = "warning"
                        self.critical_recovery_ticks.clear()
                        self.critical_ticks.clear()
                else:
                    self.critical_recovery_ticks.append(False)

    def evaluate(self, snapshot: dict) -> list[Alert]:
        alerts = []
        new_load_avgs: dict[str, float] = snapshot["cpu"].get("load_average", {})
        new_load_avgs.pop("15min")
        c_tick, w_tick = [float(v) for v in new_load_avgs.values()]

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
