import pytest
from app.alerts.high_load_avg import HighLoadAvg, LoadAvgState
from app.models.alert import Alert, AlertLevel


def test_transition_ok_to_warning():
    high_load = HighLoadAvg()
    w_avg = high_load.warning_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_WARNING_TRIGGER_TICKS - 1):
        high_load.warning_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert triggered[0].severity == AlertLevel.WARNING
    assert high_load.state == LoadAvgState.WARNING


def test_transition_ok_to_critical():
    high_load = HighLoadAvg()
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered != []
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_transition_warning_to_ok():
    high_load = HighLoadAvg()
    w_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []
    for i in range(high_load.N_WARNING_RECOVERY_TICKS - 1):
        high_load.warning_recovery_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert triggered == []
    assert high_load.state == LoadAvgState.OK


def test_transition_warning_to_critical():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.WARNING
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered != []
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_transition_critical_to_warning():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.CRITICAL
    c_avg = high_load.warning_threshold - 0.2
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_RECOVERY_TICKS - 1):
        high_load.critical_recovery_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered == []
    assert high_load.state == LoadAvgState.WARNING


def test_transition_cri_to_warn_to_ok():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.CRITICAL

    c_avg = high_load.warning_threshold - 0.2
    w_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []

    for i in range(high_load.N_CRITICAL_RECOVERY_TICKS - 1):
        high_load.critical_recovery_ticks.append(True)

    for i in range(high_load.N_WARNING_RECOVERY_TICKS - 1):
        high_load.warning_recovery_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)
    high_load.transition_phase1(w_avg, triggered)

    assert triggered == []
    assert high_load.state == LoadAvgState.OK


def test_transition_ok_to_warn_to_cri():
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    c_avg = high_load.critical_threshold + 1
    w_avg = high_load.warning_threshold + 1
    triggered: list[Alert] = []

    for i in range(high_load.N_WARNING_TRIGGER_TICKS - 1):
        high_load.warning_ticks.append(True)

    for i in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)
    high_load.transition_phase2(c_avg, triggered)

    assert triggered != []
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == LoadAvgState.CRITICAL


def test_recover_from_warning():
    # ok -> warning -> ok
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    seq = [{"cpu": {"load_average": {"1min": 8.0, "5min": 8.0, "15min": 8.0}}}] * 140 + [
        {"cpu": {"load_average": {"1min": 2.0, "5min": 2.0, "15min": 2.0}}}
    ] * 240

    alerts = []
    for i, s in enumerate(seq):
        alerts += high_load.evaluate(s)
        if i == 140:
            assert alerts != []
            assert high_load.state == LoadAvgState.WARNING

    assert high_load.state == LoadAvgState.OK


def test_recover_all_from_critical():
    # ok -> critical -> warning -> ok
    high_load = HighLoadAvg()
    high_load.state = LoadAvgState.OK

    seq = [{"cpu": {"load_average": {"1min": 13.0, "5min": 13.0}}} for _ in range(90)] + [
        {"cpu": {"load_average": {"1min": 3.0, "5min": 3.0}}} for _ in range(240)
    ]
    triggered = []
    for i, s in enumerate(seq, 1):
        triggered += high_load.evaluate(s)
        match i:
            case 90:
                assert high_load.state == LoadAvgState.CRITICAL
            case 140:
                assert high_load.state == LoadAvgState.WARNING
            case 330:
                assert high_load.state == LoadAvgState.OK
            case _:
                pass

    assert len(triggered) == 1
