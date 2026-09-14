from app.alerts.threshold import ThresholdAlert, ThresholdState

# for tests!
CpuUsageState = ThresholdState


class HighCpuUsage(ThresholdAlert):
    metric = "cpu_usage"
    display_name = "CPU usage"
    snapshot_key = ("cpu", "usage_percentage")
    extra_key = "cpu_usage"

    warning_threshold: int = 70
    critical_threshold: int = 90

    WARNING_CPU_THRESHOLD = property(lambda self: self.warning_threshold)
    CRITICAL_CPU_THRESHOLD = property(lambda self: self.critical_threshold)
