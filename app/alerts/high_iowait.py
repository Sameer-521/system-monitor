from app.alerts.threshold import ThresholdAlert, ThresholdState
from app.models.alert import AlertCategory, AlertTier

# for tests!
IowaitState = ThresholdState


def _max_value(values: list[float]) -> float:
    return max(values)


class HighIowait(ThresholdAlert):
    metric = "iowait"
    display_name = "IO wait"
    name = "high_iowait"
    category = AlertCategory.CPU
    tier = AlertTier.CORE
    snapshot_key = ("cpu", "iowait")
    extra_key = "iowait"
    reducer = staticmethod(_max_value)

    warning_threshold: int = 30
    critical_threshold: int = 50
