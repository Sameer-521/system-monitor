import pytest
import statistics
from app.alerts.cpu_anomaly import CpuAnomalyAlert


@pytest.fixture()
def mock_processes():
    return [
        {
            "pid": 1,
            "name": "systemd",
            "username": "root",
            "cpu_percent": 0.0,
            "memory_percent": 0.1,
            "status": "sleeping",
        },
        {
            "pid": 451,
            "name": "sshd",
            "username": "root",
            "cpu_percent": 0.2,
            "memory_percent": 0.3,
            "status": "sleeping",
        },
        {
            "pid": 892,
            "name": "nginx",
            "username": "www-data",
            "cpu_percent": 1.5,
            "memory_percent": 2.1,
            "status": "sleeping",
        },
        {
            "pid": 893,
            "name": "nginx",
            "username": "www-data",
            "cpu_percent": 0.8,
            "memory_percent": 1.9,
            "status": "sleeping",
        },
        {
            "pid": 1204,
            "name": "postgres",
            "username": "postgres",
            "cpu_percent": 4.2,
            "memory_percent": 8.7,
            "status": "sleeping",
        },
        {
            "pid": 1205,
            "name": "postgres",
            "username": "postgres",
            "cpu_percent": 0.1,
            "memory_percent": 0.8,
            "status": "sleeping",
        },
        {
            "pid": 1206,
            "name": "postgres",
            "username": "postgres",
            "cpu_percent": 3.1,
            "memory_percent": 5.4,
            "status": "sleeping",
        },
        {
            "pid": 1572,
            "name": "redis-server",
            "username": "redis",
            "cpu_percent": 0.7,
            "memory_percent": 1.2,
            "status": "sleeping",
        },
        {
            "pid": 1893,
            "name": "python3",
            "username": "appuser",
            "cpu_percent": 12.4,
            "memory_percent": 6.3,
            "status": "running",
        },
        {
            "pid": 1894,
            "name": "python3",
            "username": "appuser",
            "cpu_percent": 0.0,
            "memory_percent": 0.2,
            "status": "sleeping",
        },
        {
            "pid": 2101,
            "name": "dockerd",
            "username": "root",
            "cpu_percent": 2.1,
            "memory_percent": 4.5,
            "status": "sleeping",
        },
        {
            "pid": 2345,
            "name": "containerd",
            "username": "root",
            "cpu_percent": 1.8,
            "memory_percent": 3.2,
            "status": "sleeping",
        },
        {
            "pid": 2789,
            "name": "celery",
            "username": "appuser",
            "cpu_percent": 5.6,
            "memory_percent": 3.8,
            "status": "sleeping",
        },
        {
            "pid": 2790,
            "name": "celery",
            "username": "appuser",
            "cpu_percent": 4.3,
            "memory_percent": 3.5,
            "status": "sleeping",
        },
        {
            "pid": 2791,
            "name": "celery",
            "username": "appuser",
            "cpu_percent": 6.1,
            "memory_percent": 3.9,
            "status": "running",
        },
        {
            "pid": 3120,
            "name": "java",
            "username": "appuser",
            "cpu_percent": 18.7,
            "memory_percent": 14.2,
            "status": "sleeping",
        },
        {
            "pid": 3456,
            "name": "node",
            "username": "appuser",
            "cpu_percent": 9.2,
            "memory_percent": 5.1,
            "status": "sleeping",
        },
        {
            "pid": 4012,
            "name": "rsyslogd",
            "username": "root",
            "cpu_percent": 0.3,
            "memory_percent": 0.4,
            "status": "sleeping",
        },
        {
            "pid": 4589,
            "name": "cron",
            "username": "root",
            "cpu_percent": 0.0,
            "memory_percent": 0.1,
            "status": "sleeping",
        },
        {
            "pid": 5120,
            "name": "bash",
            "username": "appuser",
            "cpu_percent": 0.0,
            "memory_percent": 0.2,
            "status": "sleeping",
        },
    ]


@pytest.fixture
def mock_baseline_buckets():
    return [
        4.0,
        5.0,
        4.5,
        5.5,
        4.0,
        6.0,
        4.5,
        5.5,
        4.0,
        5.0,
        4.5,
        6.0,
        5.0,
        4.5,
        5.5,
        4.0,
        5.0,
        6.0,
        4.5,
        5.0,
        4.0,
        5.5,
        4.5,
        5.0,
        6.0,
        4.5,
        5.0,
        4.0,
        5.5,
        5.0,
    ]


def test_cpu_anomaly_trigger_on_sustained_spike(mock_baseline_buckets):
    cpu_alert = CpuAnomalyAlert()
    cpu_alert.streak.value = 5
    baseline_buckets = mock_baseline_buckets
    new_usage = 35.0

    for val in baseline_buckets:
        cpu_alert.buffer.buckets.append(val)

    dummy_snapshot = {"cpu": {"usage_percentage": new_usage}}
    for _ in range(9):
        result = cpu_alert.evaluate(dummy_snapshot, timestamp=0.0)
        assert result == [], f"Expected no alert for partial bucket, got {result}"

    # current bucket full -> should trigger
    result = cpu_alert.evaluate(dummy_snapshot, timestamp=0.0)

    # verify
    median = statistics.median(cpu_alert.buffer.buckets)
    std = statistics.stdev(cpu_alert.buffer.buckets)
    z = abs(new_usage - median) / std

    assert len(result) == 1, f"Expected 1 alert, got {result}"
    fired = result[0]
    assert fired.metric == "cpu_anomaly"
    assert f"{z:.1f}σ" in fired.message
    assert f"{median:.1f}%" in fired.message
    assert cpu_alert.streak.value == 6
    print(f"OK — alert fired: {fired.message}")
    print(f"   median={median:.2f}, std={std:.3f}, z={z:.2f}")


def test_cpu_anomaly_no_trigger(mock_baseline_buckets):
    cpu_alert = CpuAnomalyAlert()
    cpu_alert.streak.value = 5
    baseline_buckets = mock_baseline_buckets
    new_usage = 4.0

    for val in baseline_buckets:
        cpu_alert.buffer.buckets.append(val)

    dummy_snapshot = {"cpu": {"usage_percentage": new_usage}}
    for _ in range(9):
        result = cpu_alert.evaluate(dummy_snapshot, timestamp=0.0)
        assert result == [], f"Expected no alert for partial bucket, got {result}"

    # current bucket full -> should not trigger
    result = cpu_alert.evaluate(dummy_snapshot, timestamp=0.0)

    # verify
    median = statistics.median(cpu_alert.buffer.buckets)
    std = statistics.stdev(cpu_alert.buffer.buckets)
    z = abs(new_usage - median) / std

    assert len(result) == 0, f"Expected 0 alert, got {result}"
    assert cpu_alert.streak_miss.value == 1
    print(f"   median={median:.2f}, std={std:.3f}, z={z:.2f}")
