from app.alerts.high_cpu_usage import CpuUsageState, HighCpuUsage
from app.models.alert import Alert, AlertLevel, AlertState


def feed_bucket(alert: HighCpuUsage, value: float) -> list[Alert]:
    triggered: list[Alert] = []
    for _ in range(alert.BUCKET_SIZE):
        triggered += alert.evaluate({"cpu": {"usage_percentage": value}})
    return triggered


def test_no_alert_during_warmup():
    high_cpu = HighCpuUsage()
    hot = high_cpu.CRITICAL_CPU_THRESHOLD + 5

    triggered: list[Alert] = []
    for _ in range(high_cpu.BUCKET_SIZE - 1):
        triggered += high_cpu.evaluate({"cpu": {"usage_percentage": hot}})

    assert triggered == []
    assert high_cpu.state == CpuUsageState.OK


def test_transition_ok_to_warning():
    high_cpu = HighCpuUsage()
    for _ in range(high_cpu.N_WARNING_TRIGGER_TICKS - 1):
        high_cpu.warning_ticks.append(True)

    hot = high_cpu.WARNING_CPU_THRESHOLD + 1
    triggered: list[Alert] = feed_bucket(high_cpu, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.WARNING
    assert triggered[0].state == AlertState.FIRING
    assert high_cpu.state == CpuUsageState.WARNING


def test_transition_ok_to_critical_bypasses_warning():
    high_cpu = HighCpuUsage()
    for _ in range(high_cpu.N_CRITICAL_TRIGGER_TICKS - 1):
        high_cpu.critical_ticks.append(True)

    hot = high_cpu.CRITICAL_CPU_THRESHOLD + 5
    triggered: list[Alert] = feed_bucket(high_cpu, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert triggered[0].state == AlertState.FIRING
    assert high_cpu.state == CpuUsageState.CRITICAL


def test_transition_warning_to_critical():
    high_cpu = HighCpuUsage()
    high_cpu.state = CpuUsageState.WARNING
    for _ in range(high_cpu.N_CRITICAL_TRIGGER_TICKS - 1):
        high_cpu.critical_ticks.append(True)

    hot = high_cpu.CRITICAL_CPU_THRESHOLD + 5
    triggered: list[Alert] = feed_bucket(high_cpu, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert triggered[0].state == AlertState.FIRING
    assert high_cpu.state == CpuUsageState.CRITICAL


def test_transition_critical_to_warning():
    high_cpu = HighCpuUsage()
    high_cpu.state = CpuUsageState.CRITICAL
    for _ in range(high_cpu.N_CRITICAL_RECOVERY_TICKS - 1):
        high_cpu.critical_recovery_ticks.append(True)
    for _ in range(2):
        high_cpu.warning_recovery_ticks.append(True)

    cool = high_cpu.WARNING_CPU_THRESHOLD - 20
    triggered: list[Alert] = feed_bucket(high_cpu, cool)

    assert len(triggered) == 1
    assert "de-escalating" in triggered[0].message
    assert triggered[0].state == AlertState.FIRING
    assert high_cpu.state == CpuUsageState.WARNING


def test_transition_critical_to_ok_full_recovery():
    high_cpu = HighCpuUsage()
    high_cpu.state = CpuUsageState.CRITICAL
    for _ in range(high_cpu.N_CRITICAL_RECOVERY_TICKS - 1):
        high_cpu.critical_recovery_ticks.append(True)
    for _ in range(high_cpu.N_WARNING_RECOVERY_TICKS - 1):
        high_cpu.warning_recovery_ticks.append(True)

    cool = high_cpu.WARNING_CPU_THRESHOLD - 20
    triggered: list[Alert] = feed_bucket(high_cpu, cool)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.INFO
    assert triggered[0].state == AlertState.RESOLVED
    assert high_cpu.state == CpuUsageState.OK


def test_transition_warning_to_ok():
    high_cpu = HighCpuUsage()
    high_cpu.state = CpuUsageState.WARNING
    for _ in range(high_cpu.N_WARNING_RECOVERY_TICKS - 1):
        high_cpu.warning_recovery_ticks.append(True)

    cool = high_cpu.WARNING_CPU_THRESHOLD - 20
    triggered: list[Alert] = feed_bucket(high_cpu, cool)

    assert len(triggered) == 1
    assert triggered[0].state == AlertState.RESOLVED
    assert high_cpu.state == CpuUsageState.OK


def test_no_transition_when_window_not_met():
    high_cpu = HighCpuUsage()
    high_cpu.critical_ticks.append(True)

    hot = high_cpu.CRITICAL_CPU_THRESHOLD + 5
    triggered: list[Alert] = feed_bucket(high_cpu, hot)

    assert triggered == []
    assert high_cpu.state == CpuUsageState.OK


def test_full_lifecycle_warn_escalate_recover():
    # ok -> warning -> critical -> warning -> ok
    high_cpu = HighCpuUsage()

    warm = high_cpu.WARNING_CPU_THRESHOLD + 5
    hot = high_cpu.CRITICAL_CPU_THRESHOLD + 5
    cool = high_cpu.WARNING_CPU_THRESHOLD - 20

    triggered: list[Alert] = []
    for _ in range(high_cpu.N_WARNING_TRIGGER_TICKS):
        triggered += feed_bucket(high_cpu, warm)
    assert len(triggered) == 1
    assert high_cpu.state == CpuUsageState.WARNING

    for _ in range(high_cpu.N_CRITICAL_TRIGGER_TICKS):
        triggered += feed_bucket(high_cpu, hot)
    assert len(triggered) == 2
    assert triggered[1].severity == AlertLevel.CRITICAL
    assert high_cpu.state == CpuUsageState.CRITICAL

    # de-escalation fires on the 5th cool bucket, warn recovery not met yet
    for _ in range(high_cpu.N_CRITICAL_RECOVERY_TICKS):
        triggered += feed_bucket(high_cpu, cool)
    assert len(triggered) == 3
    assert "de-escalating" in triggered[2].message
    assert high_cpu.state == CpuUsageState.WARNING

    triggered += feed_bucket(high_cpu, cool)
    assert len(triggered) == 4
    assert triggered[3].state == AlertState.RESOLVED
    assert high_cpu.state == CpuUsageState.OK
