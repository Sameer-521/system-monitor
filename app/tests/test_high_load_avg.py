from app.alerts.high_load_avg import HighLoadAvg, LoadAvgState
from app.models.alert import Alert, AlertLevel, AlertState


def test_transition_ok_to_warning():
    high_load = HighLoadAvg()
    w_avg = high_load.warning_threshold + 1
    triggered: list[Alert] = []
    for _ in range(high_load.N_WARNING_TRIGGER_TICKS - 1):
        high_load.warning_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert triggered[0].severity == AlertLevel.WARNING
    assert high_load.state == LoadAvgState.WARNING


def test_transition_ok_to_critical():
    high_load = HighLoadAvg()
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for _ in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_transition_warning_to_ok():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.WARNING
    w_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []
    for _ in range(high_load.N_WARNING_RECOVERY_TICKS - 1):
        high_load.warning_recovery_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert len(triggered) == 1
    assert triggered[0].state == AlertState.RESOLVED
    assert high_load.state == LoadAvgState.OK


def test_transition_warning_to_critical():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.WARNING
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for _ in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_transition_critical_to_warning():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.CRITICAL
    c_avg = high_load.warning_threshold - 0.2
    triggered: list[Alert] = []
    for _ in range(high_load.N_CRITICAL_RECOVERY_TICKS - 1):
        high_load.critical_recovery_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert len(triggered) == 1
    assert "recovered" in triggered[0].message
    assert high_load.state == LoadAvgState.WARNING


def test_transition_cri_to_warn_to_ok():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.CRITICAL

    c_avg = high_load.warning_threshold - 0.2
    w_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []

    for _ in range(high_load.N_CRITICAL_RECOVERY_TICKS - 1):
        high_load.critical_recovery_ticks.append(True)

    for _ in range(high_load.N_WARNING_RECOVERY_TICKS - 1):
        high_load.warning_recovery_ticks.append(True)

    # should append a critical -> warning event
    high_load.transition_phase2(c_avg, triggered)
    assert len(triggered) == 1
    assert "recovered" in triggered[0].message
    assert triggered[0].state == AlertState.FIRING

    # should append a warning -> ok event
    high_load.transition_phase1(w_avg, triggered)
    assert len(triggered) == 2
    assert triggered[1].state == AlertState.RESOLVED
    assert high_load.state == LoadAvgState.OK


def test_transition_ok_to_warn_to_cri():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    c_avg = high_load.critical_threshold + 1
    w_avg = high_load.warning_threshold + 1
    triggered: list[Alert] = []

    for _ in range(high_load.N_WARNING_TRIGGER_TICKS - 1):
        high_load.warning_ticks.append(True)

    for _ in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)
    high_load.transition_phase2(c_avg, triggered)

    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_recover_from_warning():
    # ok -> warning -> ok
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    hot = high_load.warning_threshold + 0.5
    cool = high_load.NORMAL * 0.5
    seq = [{"cpu": {"load_average": {"1min": hot, "5min": hot, "15min": hot}}}] * (
        high_load.N_WARNING_TRIGGER_TICKS * high_load.SAMPLES
    ) + [{"cpu": {"load_average": {"1min": cool, "5min": cool, "15min": cool}}}] * (
        high_load.N_WARNING_RECOVERY_TICKS * high_load.SAMPLES
    )

    triggered: list[Alert] = []
    for i, s in enumerate(seq):
        triggered += high_load.evaluate(s)
        if i == high_load.N_WARNING_TRIGGER_TICKS * high_load.SAMPLES:
            assert len(triggered) == 1
            assert high_load.state == LoadAvgState.WARNING

    assert len(triggered) == 2
    assert triggered[1].state == AlertState.RESOLVED
    assert high_load.state == LoadAvgState.OK


def test_recover_all_from_critical():
    # ok -> critical -> warning -> ok
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    hot = high_load.critical_threshold + 1
    cool = high_load.NORMAL * 0.5
    hot_ticks = high_load.N_CRITICAL_TRIGGER_TICKS * high_load.SAMPLES
    seq = [{"cpu": {"load_average": {"1min": hot, "5min": hot}}} for _ in range(hot_ticks)] + [
        {"cpu": {"load_average": {"1min": cool, "5min": cool}}}
        for _ in range(high_load.N_WARNING_RECOVERY_TICKS * high_load.SAMPLES)
    ]
    triggered: list[Alert] = []
    for i, s in enumerate(seq, 1):
        triggered += high_load.evaluate(s)
        match i:
            case _ if i == hot_ticks:
                assert high_load.state == LoadAvgState.CRITICAL
            case _ if i == hot_ticks + high_load.N_CRITICAL_RECOVERY_TICKS * high_load.SAMPLES:
                assert high_load.state == LoadAvgState.WARNING
            case _ if i == hot_ticks + high_load.N_WARNING_RECOVERY_TICKS * high_load.SAMPLES:
                assert high_load.state == LoadAvgState.OK
            case _:
                pass

    assert len(triggered) == 3
    assert triggered[0].state == AlertState.FIRING
    assert triggered[1].severity == AlertLevel.WARNING
    assert triggered[2].state == AlertState.RESOLVED
