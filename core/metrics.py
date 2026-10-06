"""Metrics collection, percentile computation, and threshold evaluation.

The aggregator is designed to be cheap to update on the hot path (one record
per request) and cheap to snapshot from the UI thread. Exact counters are kept
for every request; latency samples are held in a bounded reservoir so memory
stays flat even under long, high-throughput runs while percentile estimates
remain statistically sound.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field

from models.schemas import LiveMetrics, SafetyThresholds, StopReason

# Upper bound on retained latency samples. Beyond this, reservoir sampling keeps
# a uniform random sample of all observed latencies.
_RESERVOIR_SIZE = 200_000


def percentile(sorted_values: list[float], pct: float) -> float:
    """Return the ``pct`` percentile of an already-sorted list.

    Uses linear interpolation between closest ranks. Returns 0.0 for an empty
    list. ``pct`` is expressed as 0-100.
    """
    if not sorted_values:
        return 0.0
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[int(rank)]
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


@dataclass
class _RequestRecord:
    status_code: int  # 0 means transport/connection error (no HTTP response)
    latency_ms: float
    success: bool
    timestamp: float


@dataclass
class MetricsAggregator:
    """Thread-safe accumulator of per-request results."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    total: int = 0
    successful: int = 0
    failed: int = 0
    status_counts: dict[int, int] = field(default_factory=dict)
    _latency_sum: float = 0.0
    _latency_min: float = math.inf
    _latency_max: float = 0.0
    _reservoir: list[float] = field(default_factory=list)
    _seen_latencies: int = 0
    _start_monotonic: float = field(default_factory=time.monotonic)
    rate_limit_count: int = 0  # HTTP 429
    server_error_count: int = 0  # HTTP 5xx

    def record(
        self, status_code: int, latency_ms: float, success: bool
    ) -> None:
        """Record a single completed (or failed) request."""
        with self._lock:
            self.total += 1
            if success:
                self.successful += 1
            else:
                self.failed += 1

            self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1
            if status_code == 429:
                self.rate_limit_count += 1
            elif 500 <= status_code <= 599:
                self.server_error_count += 1

            self._latency_sum += latency_ms
            self._latency_min = min(self._latency_min, latency_ms)
            self._latency_max = max(self._latency_max, latency_ms)

            # Reservoir sampling keeps memory bounded on long runs.
            self._seen_latencies += 1
            if len(self._reservoir) < _RESERVOIR_SIZE:
                self._reservoir.append(latency_ms)
            else:
                j = random.randint(0, self._seen_latencies - 1)
                if j < _RESERVOIR_SIZE:
                    self._reservoir[j] = latency_ms

    def snapshot(self, active_users: int = 0) -> LiveMetrics:
        """Return a consistent :class:`LiveMetrics` view of current state."""
        with self._lock:
            elapsed = max(time.monotonic() - self._start_monotonic, 1e-9)
            latencies = sorted(self._reservoir)
            avg = self._latency_sum / self.total if self.total else 0.0
            error_rate = (self.failed / self.total * 100.0) if self.total else 0.0
            return LiveMetrics(
                active_users=active_users,
                total_requests=self.total,
                successful_requests=self.successful,
                failed_requests=self.failed,
                requests_per_second=self.total / elapsed,
                error_rate_pct=error_rate,
                avg_latency_ms=avg,
                min_latency_ms=0.0 if self._latency_min is math.inf else self._latency_min,
                max_latency_ms=self._latency_max,
                p50_ms=percentile(latencies, 50),
                p95_ms=percentile(latencies, 95),
                p99_ms=percentile(latencies, 99),
                status_distribution={str(k): v for k, v in sorted(self.status_counts.items())},
                elapsed_seconds=elapsed,
            )


def evaluate_thresholds(
    metrics: LiveMetrics,
    thresholds: SafetyThresholds,
    rate_limit_count: int,
    server_error_count: int,
) -> StopReason | None:
    """Return a :class:`StopReason` if any safety threshold is breached.

    Returns ``None`` when the test may continue. Thresholds are not evaluated
    until a minimum sample of requests has been collected, so transient startup
    spikes do not trip a guard prematurely.
    """
    if metrics.total_requests < thresholds.min_requests_before_eval:
        return None

    if metrics.error_rate_pct > thresholds.max_error_rate_pct:
        return StopReason.ERROR_RATE

    if metrics.p95_ms > thresholds.max_p95_latency_ms:
        return StopReason.P95_LATENCY

    total = metrics.total_requests
    if (rate_limit_count / total * 100.0) > thresholds.max_rate_limit_pct:
        return StopReason.RATE_LIMIT

    if (server_error_count / total * 100.0) > thresholds.max_server_error_pct:
        return StopReason.SERVER_ERRORS

    return None
