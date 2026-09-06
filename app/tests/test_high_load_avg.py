import pytest
from app.alerts.high_load_avg import HighLoadAvg
from app.models.alert import Alert, AlertLevel


def test_transition_ok_to_warning():
    high_load = HighLoadAvg()
    high_load.num_cpus = 8
    w_avg = high_load.warning_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_WARNING_TRIGGER_TICKS - 1):
        high_load.warning_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert triggered[0].severity == AlertLevel.WARNING
    assert high_load.state == "warning"


def test_transition_ok_to_critical():
    high_load = HighLoadAvg()
    high_load.num_cpus = 8
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered != []
    assert triggered[0].severity == AlertLevel.CRITICAL
    assert high_load.state == "critical"


def test_transition_warning_to_ok():
    high_load = HighLoadAvg()
    high_load.num_cpus = 8
    w_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []
    for i in range(high_load.N_WARNING_RECOVERY_TICKS - 1):
        high_load.warning_recovery_ticks.append(True)

    high_load.transition_phase1(w_avg, triggered)

    assert triggered == []
    assert high_load.state == "ok"


def test_transition_warning_to_critical():
    high_load = HighLoadAvg()
    high_load.num_cpus = 8
    high_load.state = "warning"
    c_avg = high_load.critical_threshold + 1
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_TRIGGER_TICKS - 1):
        high_load.critical_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered != []
    assert triggered[0].severity.value == "critical"
    assert high_load.state == "critical"


def test_transition_critical_to_warning():
    high_load = HighLoadAvg()
    high_load.num_cpus = 8
    high_load.state = "critical"
    c_avg = high_load.NORMAL - 0.2
    triggered: list[Alert] = []
    for i in range(high_load.N_CRITICAL_RECOVERY_TICKS - 1):
        high_load.critical_recovery_ticks.append(True)

    high_load.transition_phase2(c_avg, triggered)

    assert triggered == []
    assert high_load.state == "warning"
