from app.models.alert import Alert, AlertLevel, AlertState
from app.models.buffer import BucketedRingBuffer
from app.models.counter import Counter

import statistics


class CpuAnomalyAlert:
    BUCKET_SIZE: int = 10
    MAX_BUCKETS: int = 30
    Z_THRESHOLD: float = 3.0
    STREAK: int = 6

    def __init__(self) -> None:
        self.buffer = BucketedRingBuffer(bucket_size=self.BUCKET_SIZE, max_buckets=self.MAX_BUCKETS)
        self.streak = Counter(0)
        self.streak_miss = Counter(0)

    def evaluate(self, snapshot: dict) -> list[Alert]:
        new_usage = snapshot["cpu"]["usage_percentage"]
        alerts = []
        current_avg = self.buffer.feed(new_usage)

        if current_avg is not None and self.buffer.ready():
            stdv = statistics.stdev(self.buffer.buckets)
            median = statistics.median(self.buffer.buckets)
            z = 0 if stdv == 0 else abs(current_avg - median) / stdv
            if z >= self.Z_THRESHOLD:
                self.streak.increment()
                # 1 bucket = 10s of data, 30 buckets = 10s * 30
                # a single streak is 10s of history, 6 medians 60s -> 1 min
                if self.streak.value >= self.STREAK:
                    new_alert = Alert(
                        metric="cpu_anomaly",
                        severity=AlertLevel.WARNING,
                        message=f"CPU usage anomaly: {new_usage}% — {z:.1f}σ above baseline ({median:.1f}%)",
                        state=AlertState.FIRING,
                    )
                    alerts.append(new_alert)
            self.streak_miss.increment()
            if self.streak_miss.value >= 2:
                self.streak.reset()

        return alerts
