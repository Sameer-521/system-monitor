import pytest

from app.alerts.cpu_anomaly import CpuAnomalyAlert
from app.alerts.high_cpu_usage import HighCpuUsage
from app.alerts.high_iowait import HighIowait
from app.alerts.high_load_avg import HighLoadAvg
from app.alerts.registry import AlertRegistry
from app.models.alert import Alert, AlertCategory, AlertLevel, AlertState, AlertTier


def _firing_alert(metric: str = "cpu_usage") -> Alert:
    return Alert(
        metric=metric,
        severity=AlertLevel.WARNING,
        message="test alert",
        state=AlertState.FIRING,
    )


class _Evaluator:
    name: str = "test_alert"
    category: AlertCategory = AlertCategory.CPU
    tier: AlertTier = AlertTier.CORE

    def __init__(self, alerts: list[Alert] | None = None) -> None:
        self.alerts = alerts if alerts is not None else [_firing_alert()]

    def evaluate(self, snapshot: dict) -> list[Alert]:
        return list(self.alerts)


class _MissingName:
    category = AlertCategory.CPU
    tier = AlertTier.CORE

    def evaluate(self, snapshot: dict) -> list[Alert]:
        return []


class _BlankName:
    name = "   "
    category = AlertCategory.CPU
    tier = AlertTier.CORE

    def evaluate(self, snapshot: dict) -> list[Alert]:
        return []


class _StringCategory:
    name = "test_alert"
    category = "cpu"
    tier = AlertTier.CORE

    def evaluate(self, snapshot: dict) -> list[Alert]:
        return []


class _StringTier:
    name = "test_alert"
    category = AlertCategory.CPU
    tier = "core"

    def evaluate(self, snapshot: dict) -> list[Alert]:
        return []


def test_accepts_classified_evaluator():
    registry = AlertRegistry([_Evaluator()])

    assert len(registry.evaluators) == 1


def test_rejects_evaluator_missing_name():
    with pytest.raises(ValueError, match="missing alert classification metadata: name"):
        AlertRegistry([_MissingName()])  # type: ignore[arg-type]


def test_rejects_blank_name():
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        AlertRegistry([_BlankName()])  # type: ignore[arg-type]


def test_rejects_string_category():
    with pytest.raises(ValueError, match="category must be an AlertCategory"):
        AlertRegistry([_StringCategory()])  # type: ignore[arg-type]


def test_rejects_string_tier():
    with pytest.raises(ValueError, match="tier must be an AlertTier"):
        AlertRegistry([_StringTier()])  # type: ignore[arg-type]


def test_failed_register_does_not_add_evaluator():
    registry = AlertRegistry([])

    with pytest.raises(ValueError, match="missing alert classification"):
        registry.register(_MissingName())  # type: ignore[arg-type]

    assert registry.evaluators == []


def test_evaluate_stamps_classification_on_emitted_alerts():
    registry = AlertRegistry([_Evaluator()])
    emitted = registry.evaluate({})

    assert len(emitted) == 1
    assert emitted[0].name == "test_alert"
    assert emitted[0].category == AlertCategory.CPU
    assert emitted[0].tier == AlertTier.CORE
    assert registry.alerts_store["cpu_usage"]["content"].name == "test_alert"


def test_builtin_cpu_evaluators_classified():
    registry = AlertRegistry([CpuAnomalyAlert(), HighLoadAvg(), HighCpuUsage(), HighIowait()])

    assert [e.name for e in registry.evaluators] == [
        "cpu_anomaly",
        "high_load_average",
        "high_cpu_usage",
        "high_iowait",
    ]
    assert all(e.category == AlertCategory.CPU for e in registry.evaluators)
    assert all(e.tier == AlertTier.CORE for e in registry.evaluators)
