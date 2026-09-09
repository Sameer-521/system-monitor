import time
import pytest
from app.models.alert import Alert, AlertLevel, AlertState
from app.alerts.registry import AlertRegistry


@pytest.fixture
def alert_registry():
    return AlertRegistry([])


@pytest.fixture
def fresh_warning():
    return Alert(
        metric="load_average",
        severity=AlertLevel.WARNING,
        message="5m load above warning threshold",
        state=AlertState.FIRING,
    )


@pytest.fixture
def fresh_critical():
    return Alert(
        metric="cpu_anomaly",
        severity=AlertLevel.CRITICAL,
        message="cpu anomaly",
        state=AlertState.FIRING,
    )


@pytest.fixture
def dup():
    return Alert(
        metric="load_average",
        severity=AlertLevel.WARNING,
        message="still above warning threshold",
        state=AlertState.FIRING,
    )


@pytest.fixture
def escalation():
    return Alert(
        metric="load_average",
        severity=AlertLevel.CRITICAL,
        message="escalated to critical",
        state=AlertState.FIRING,
    )


@pytest.fixture
def deescalation():
    return Alert(
        metric="load_average",
        severity=AlertLevel.WARNING,
        message="dropped back to warning",
        state=AlertState.FIRING,
    )


@pytest.fixture
def resolved():
    return Alert(
        metric="load_average",
        severity=AlertLevel.INFO,
        message="back to normal",
        state=AlertState.RESOLVED,
    )


@pytest.fixture
def stale_resolved():
    return Alert(
        metric="load_average",
        severity=AlertLevel.INFO,
        message="back to normal",
        state=AlertState.RESOLVED,
        fired_at=time.monotonic() - 100_000,
    )


@pytest.fixture
def refire_recent():
    return Alert(
        metric="load_average",
        severity=AlertLevel.WARNING,
        message="flap: fired right after resolve",
        state=AlertState.FIRING,
        fired_at=time.monotonic(),
    )


@pytest.fixture
def refire_stale():
    return Alert(
        metric="load_average",
        severity=AlertLevel.WARNING,
        message="fired long after resolve",
        state=AlertState.FIRING,
        fired_at=time.monotonic() - 100_000,
    )


def test_fresh_warning(alert_registry: AlertRegistry, fresh_warning: Alert):
    fanned: list[Alert] = alert_registry.manage([fresh_warning])

    assert len(fanned) == 1
    assert fanned[0].severity == AlertLevel.WARNING
    assert fanned[0].state == AlertState.FIRING


def test_incoming_resolved(alert_registry: AlertRegistry, resolved: Alert):
    fanned: list[Alert] = alert_registry.manage([resolved])

    assert len(fanned) == 1
    assert fanned[0].severity == AlertLevel.INFO
    assert fanned[0].state == AlertState.RESOLVED


def test_duplicate_warning(alert_registry: AlertRegistry, fresh_warning: Alert, dup: Alert):
    fanned = alert_registry.manage([fresh_warning, dup])

    assert len(fanned) == 1
    assert fanned[0].state == AlertState.FIRING


def test_resolved_cooldown_not_active(
    alert_registry: AlertRegistry, stale_resolved: Alert, fresh_warning: Alert
):
    fanned = alert_registry.manage([stale_resolved, fresh_warning])

    # fanned should contain the initial resolve and new alert
    assert len(fanned) == 2
    assert fanned[0].state == AlertState.RESOLVED
    assert fanned[1].state == AlertState.FIRING


def test_escalation(alert_registry: AlertRegistry, fresh_warning: Alert, escalation: Alert):
    fanned = alert_registry.manage([fresh_warning, escalation])

    assert len(fanned) == 2
    assert fanned[1].severity == AlertLevel.CRITICAL
    assert fanned[1].state == AlertState.FIRING


def test_deescalation(alert_registry: AlertRegistry, escalation: Alert, deescalation: Alert):
    fanned = alert_registry.manage([escalation, deescalation])

    assert len(fanned) == 2
    assert fanned[1].severity == AlertLevel.WARNING
    assert fanned[1].state == AlertState.FIRING


def test_resolve_after_firing(alert_registry: AlertRegistry, fresh_warning: Alert, resolved: Alert):
    fanned = alert_registry.manage([fresh_warning, resolved])

    assert len(fanned) == 2
    assert fanned[1].state == AlertState.RESOLVED


def test_flap_dropped_in_cooldown(
    alert_registry: AlertRegistry, resolved: Alert, refire_recent: Alert
):
    fanned = alert_registry.manage([resolved, refire_recent])

    assert len(fanned) == 1
    assert fanned[0].state == AlertState.RESOLVED


def test_refire_after_cooldown_expired(
    alert_registry: AlertRegistry, stale_resolved: Alert, refire_stale: Alert
):
    fanned = alert_registry.manage([stale_resolved, refire_stale])

    assert len(fanned) == 2
    assert fanned[1].state == AlertState.FIRING


def test_two_metrics_independent(
    alert_registry: AlertRegistry, fresh_warning: Alert, fresh_critical: Alert
):
    fanned = alert_registry.manage([fresh_warning, fresh_critical])

    assert len(fanned) == 2

    refanned = alert_registry.manage([fresh_warning])

    assert refanned == []


def test_duplicate_resolve(alert_registry: AlertRegistry, resolved: Alert):
    fanned = alert_registry.manage([resolved, resolved])

    assert len(fanned) == 1
