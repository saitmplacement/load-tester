"""Tests for metric aggregation, percentiles, and threshold detection."""

from __future__ import annotations

from core.metrics import MetricsAggregator, evaluate_thresholds, percentile
from models.schemas import LiveMetrics, SafetyThresholds, StopReason


def test_percentile_basic() -> None:
    data = sorted(float(x) for x in range(1, 101))  # 1..100
    assert percentile(data, 50) == 50.5 or abs(percentile(data, 50) - 50.5) < 1.0
    assert percentile(data, 0) == 1.0
    assert percentile(data, 100) == 100.0
    assert percentile([], 95) == 0.0


def test_percentile_single_value() -> None:
    assert percentile([42.0], 95) == 42.0


def test_aggregator_counts_and_latency() -> None:
    agg = MetricsAggregator()
    agg.record(200, 100.0, True)
    agg.record(200, 200.0, True)
    agg.record(500, 300.0, False)
    agg.record(0, 50.0, False)  # transport error

    snap = agg.snapshot(active_users=3)
    assert snap.total_requests == 4
    assert snap.successful_requests == 2
    assert snap.failed_requests == 2
    assert snap.active_users == 3
    assert snap.error_rate_pct == 50.0
    assert snap.min_latency_ms == 50.0
    assert snap.max_latency_ms == 300.0
    assert snap.status_distribution == {"0": 1, "200": 2, "500": 1}
    assert abs(snap.avg_latency_ms - 162.5) < 1e-6


def test_aggregator_tracks_rate_limit_and_server_errors() -> None:
    agg = MetricsAggregator()
    agg.record(429, 10.0, False)
    agg.record(503, 10.0, False)
    agg.record(502, 10.0, False)
    agg.record(200, 10.0, True)
    assert agg.rate_limit_count == 1
    assert agg.server_error_count == 2


def _metrics(**kwargs) -> LiveMetrics:
    base = dict(total_requests=1000, error_rate_pct=0.0, p95_ms=100.0)
    base.update(kwargs)
    return LiveMetrics(**base)


def test_thresholds_not_evaluated_before_min_requests() -> None:
    th = SafetyThresholds(min_requests_before_eval=50)
    m = _metrics(total_requests=10, error_rate_pct=100.0, p95_ms=99999.0)
    assert evaluate_thresholds(m, th, 10, 10) is None


def test_error_rate_threshold() -> None:
    th = SafetyThresholds(max_error_rate_pct=5.0)
    m = _metrics(error_rate_pct=6.0)
    assert evaluate_thresholds(m, th, 0, 0) == StopReason.ERROR_RATE


def test_p95_threshold() -> None:
    th = SafetyThresholds(max_p95_latency_ms=3000.0)
    m = _metrics(p95_ms=3500.0)
    assert evaluate_thresholds(m, th, 0, 0) == StopReason.P95_LATENCY


def test_rate_limit_threshold() -> None:
    th = SafetyThresholds(max_rate_limit_pct=2.0)
    m = _metrics(total_requests=1000)
    # 30 of 1000 = 3% > 2%
    assert evaluate_thresholds(m, th, 30, 0) == StopReason.RATE_LIMIT


def test_server_error_threshold() -> None:
    th = SafetyThresholds(max_server_error_pct=2.0)
    m = _metrics(total_requests=1000)
    assert evaluate_thresholds(m, th, 0, 30) == StopReason.SERVER_ERRORS


def test_thresholds_pass_when_healthy() -> None:
    th = SafetyThresholds()
    m = _metrics(error_rate_pct=1.0, p95_ms=500.0)
    assert evaluate_thresholds(m, th, 1, 1) is None


def test_error_rate_checked_before_latency() -> None:
    # Both breached; error-rate takes precedence per evaluation order.
    th = SafetyThresholds(max_error_rate_pct=5.0, max_p95_latency_ms=3000.0)
    m = _metrics(error_rate_pct=10.0, p95_ms=9999.0)
    assert evaluate_thresholds(m, th, 0, 0) == StopReason.ERROR_RATE
