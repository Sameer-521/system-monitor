from app.alerts.high_iowait import HighIowait, IowaitState
from app.models.alert import Alert, AlertLevel, AlertState


def feed_bucket(alert: HighIowait, value: float) -> list[Alert]:
    triggered: list[Alert] = []
    for _ in range(alert.BUCKET_SIZE):
        triggered += alert.evaluate({"cpu": {"iowait": value}})
    return triggered


def test_no_alert_during_warmup():
    high_iowait = HighIowait()
    hot = high_iowait.critical_threshold + 5

    triggered: list[Alert] = []
    for _ in range(high_iowait.BUCKET_SIZE - 1):
        triggered += high_iowait.evaluate({"cpu": {"iowait": hot}})

    assert triggered == []
    assert high_iowait.state == IowaitState.OK


def test_transition_ok_to_warning():
    high_iowait = HighIowait()
    for _ in range(high_iowait.N_WARNING_TRIGGER_TICKS - 1):
        high_iowait.warning_ticks.append(True)

    hot = high_iowait.warning_threshold + 1
    triggered: list[Alert] = feed_bucket(high_iowait, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.WARNING
    assert triggered[0].state == AlertState.FIRING
    assert high_iowait.state == IowaitState.WARNING


def test_transition_ok_to_critical_bypasses_warning():
    high_iowait = HighIowait()
    for _ in range(high_iowait.N_CRITICAL_TRIGGER_TICKS - 1):
        high_iowait.critical_ticks.append(True)

    hot = high_iowait.critical_threshold + 5
    triggered: list[Alert] = feed_bucket(high_iowait, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert triggered[0].state == AlertState.FIRING
    assert high_iowait.state == IowaitState.CRITICAL


def test_transition_warning_to_critical():
    high_iowait = HighIowait()
    high_iowait.state = IowaitState.WARNING
    for _ in range(high_iowait.N_CRITICAL_TRIGGER_TICKS - 1):
        high_iowait.critical_ticks.append(True)

    hot = high_iowait.critical_threshold + 5
    triggered: list[Alert] = feed_bucket(high_iowait, hot)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert triggered[0].state == AlertState.FIRING
    assert high_iowait.state == IowaitState.CRITICAL


def test_transition_critical_to_warning():
    high_iowait = HighIowait()
    high_iowait.state = IowaitState.CRITICAL
    for _ in range(high_iowait.N_CRITICAL_RECOVERY_TICKS - 1):
        high_iowait.critical_recovery_ticks.append(True)
    for _ in range(2):
        high_iowait.warning_recovery_ticks.append(True)

    cool = high_iowait.warning_threshold - 20
    triggered: list[Alert] = feed_bucket(high_iowait, cool)

    assert len(triggered) == 1
    assert "de-escalating" in triggered[0].message
    assert triggered[0].state == AlertState.FIRING
    assert high_iowait.state == IowaitState.WARNING


def test_transition_critical_to_ok_full_recovery():
    high_iowait = HighIowait()
    high_iowait.state = IowaitState.CRITICAL
    for _ in range(high_iowait.N_CRITICAL_RECOVERY_TICKS - 1):
        high_iowait.critical_recovery_ticks.append(True)
    for _ in range(high_iowait.N_WARNING_RECOVERY_TICKS - 1):
        high_iowait.warning_recovery_ticks.append(True)

    cool = high_iowait.warning_threshold - 20
    triggered: list[Alert] = feed_bucket(high_iowait, cool)

    assert len(triggered) == 1
    assert triggered[0].severity == AlertLevel.INFO
    assert triggered[0].state == AlertState.RESOLVED
    assert high_iowait.state == IowaitState.OK


def test_transition_warning_to_ok():
    high_iowait = HighIowait()
    high_iowait.state = IowaitState.WARNING
    for _ in range(high_iowait.N_WARNING_RECOVERY_TICKS - 1):
        high_iowait.warning_recovery_ticks.append(True)

    cool = high_iowait.warning_threshold - 20
    triggered: list[Alert] = feed_bucket(high_iowait, cool)

    assert len(triggered) == 1
    assert triggered[0].state == AlertState.RESOLVED
    assert high_iowait.state == IowaitState.OK


def test_no_transition_when_window_not_met():
    high_iowait = HighIowait()
    high_iowait.critical_ticks.append(True)

    hot = high_iowait.critical_threshold + 5
    triggered: list[Alert] = feed_bucket(high_iowait, hot)

    assert triggered == []
    assert high_iowait.state == IowaitState.OK


def test_bucket_uses_max_not_mean():
    high_iowait = HighIowait()
    hot = high_iowait.critical_threshold + 10
    cool = 0.0

    for _ in range(high_iowait.BUCKET_SIZE - 1):
        high_iowait.evaluate({"cpu": {"iowait": cool}})
    triggered: list[Alert] = high_iowait.evaluate({"cpu": {"iowait": hot}})

    assert triggered == []
    assert list(high_iowait.critical_ticks) == [True]
    assert list(high_iowait.warning_ticks) == [True]


def test_full_lifecycle_warn_escalate_recover():
    # ok -> warning -> critical -> warning -> ok
    high_iowait = HighIowait()

    warm = high_iowait.warning_threshold + 5
    hot = high_iowait.critical_threshold + 5
    cool = high_iowait.warning_threshold - 20

    triggered: list[Alert] = []
    for _ in range(high_iowait.N_WARNING_TRIGGER_TICKS):
        triggered += feed_bucket(high_iowait, warm)
    assert len(triggered) == 1
    assert high_iowait.state == IowaitState.WARNING

    for _ in range(high_iowait.N_CRITICAL_TRIGGER_TICKS):
        triggered += feed_bucket(high_iowait, hot)
    assert len(triggered) == 2
    assert triggered[1].severity == AlertLevel.CRITICAL
    assert high_iowait.state == IowaitState.CRITICAL

    # de-escalation fires on the 5th cool bucket, warn recovery not met yet
    for _ in range(high_iowait.N_CRITICAL_RECOVERY_TICKS):
        triggered += feed_bucket(high_iowait, cool)
    assert len(triggered) == 3
    assert "de-escalating" in triggered[2].message
    assert high_iowait.state == IowaitState.WARNING

    triggered += feed_bucket(high_iowait, cool)
    assert len(triggered) == 4
    assert triggered[3].state == AlertState.RESOLVED
    assert high_iowait.state == IowaitState.OK
