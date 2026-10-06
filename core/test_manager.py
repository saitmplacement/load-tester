"""Local load-test engine.

The engine runs entirely in-process on an asyncio event loop hosted in a
dedicated background thread, so the Streamlit UI thread can start a test, poll
live metrics, and stop the test without blocking.

Design principles enforced here:
  * Every test has a bounded duration *and* automatic stop conditions.
  * There are no infinite request loops — workers exit on the stop event, the
    deadline, or a breached safety threshold.
  * Shutdown is graceful: the stop event is set, workers finish their in-flight
    request, tasks are awaited with a timeout, and the HTTP client is closed.
  * Virtual users ramp up gradually at the configured spawn rate.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field

import httpx

from core.metrics import MetricsAggregator, evaluate_thresholds
from models.schemas import (
    HUMAN_READABLE_STOP_REASON,
    LiveMetrics,
    StopReason,
    TestConfig,
    TestResultStatus,
    TestSummary,
)

logger = logging.getLogger("loadtester.engine")

# How often the monitor loop samples metrics and evaluates safety thresholds.
_MONITOR_INTERVAL_S = 1.0
# Max time to wait for workers to finish after a stop is requested.
_SHUTDOWN_GRACE_S = 5.0


@dataclass
class TimeSeriesPoint:
    """One per-second sample used to drive the live charts."""

    t: float  # seconds since start
    rps: float
    p95_ms: float
    avg_ms: float
    error_rate_pct: float
    active_users: int
    total_requests: int


@dataclass
class EngineState:
    """Mutable, lock-guarded state shared between engine and UI threads."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = False
    active_users: int = 0
    stop_reason: StopReason | None = None
    history: list[TimeSeriesPoint] = field(default_factory=list)
    last_snapshot: LiveMetrics = field(default_factory=LiveMetrics)
    error_message: str = ""

    def set_active(self, n: int) -> None:
        with self._lock:
            self.active_users = n

    def get_active(self) -> int:
        with self._lock:
            return self.active_users

    def append_point(self, point: TimeSeriesPoint, snapshot: LiveMetrics) -> None:
        with self._lock:
            self.history.append(point)
            self.last_snapshot = snapshot

    def get_history(self) -> list[TimeSeriesPoint]:
        with self._lock:
            return list(self.history)


class LoadTest:
    """Controls the lifecycle of a single load test.

    Usage::

        test = LoadTest(config)
        test.start()
        ...  # poll test.snapshot() from the UI
        test.stop()           # optional manual stop
        test.join()           # wait for completion
        summary = test.build_summary()
    """

    def __init__(self, config: TestConfig, user_agent: str = "load-tester/1.0") -> None:
        self.config = config
        self.user_agent = user_agent
        self.metrics = MetricsAggregator()
        self.state = EngineState()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._stop_requested = threading.Event()
        self._manual_stop = False
        self.start_time = None
        self.end_time = None

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        """Start the test in a background thread."""
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Test is already running.")
        self.start_time = TestSummary.utcnow()
        self.state.running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request a graceful manual stop."""
        self._manual_stop = True
        self._stop_requested.set()
        if self._loop and self._stop_event and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def join(self, timeout: float | None = None) -> None:
        """Block until the test thread finishes."""
        if self._thread:
            self._thread.join(timeout)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def snapshot(self) -> LiveMetrics:
        """Return current live metrics (safe to call from any thread)."""
        return self.metrics.snapshot(active_users=self.state.get_active())

    def history(self) -> list[TimeSeriesPoint]:
        return self.state.get_history()

    # ----------------------------------------------------------- internals
    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Load engine crashed")
            self.state.stop_reason = StopReason.ENGINE_ERROR
            self.state.error_message = str(exc)
        finally:
            self.state.running = False
            self.end_time = TestSummary.utcnow()

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        if self._stop_requested.is_set():
            self._stop_event.set()

        limits = httpx.Limits(
            max_connections=self.config.virtual_users * 2,
            max_keepalive_connections=self.config.virtual_users,
        )
        timeout = httpx.Timeout(self.config.request_timeout_s)
        headers = {"User-Agent": self.user_agent}

        deadline = time.monotonic() + self.config.duration_seconds
        worker_tasks: list[asyncio.Task] = []

        async with httpx.AsyncClient(
            base_url=self.config.target_url,
            limits=limits,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            spawner = asyncio.create_task(
                self._spawn_workers(client, worker_tasks, deadline)
            )
            monitor = asyncio.create_task(self._monitor(deadline))

            # Wait until the deadline passes or a stop is requested.
            await self._wait_for_stop(deadline)

            # ---- graceful shutdown ----
            self._stop_event.set()
            spawner.cancel()
            monitor.cancel()
            for t in (spawner, monitor):
                try:
                    await t
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

            if worker_tasks:
                await asyncio.wait(worker_tasks, timeout=_SHUTDOWN_GRACE_S)
                for t in worker_tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Finalise stop reason.
        if self.state.stop_reason is None:
            self.state.stop_reason = (
                StopReason.MANUAL if self._manual_stop else StopReason.COMPLETED
            )
        self.state.set_active(0)

    async def _wait_for_stop(self, deadline: float) -> None:
        """Return when the deadline is reached or a stop event fires."""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=min(remaining, 0.5))
            except asyncio.TimeoutError:
                continue

    async def _spawn_workers(
        self,
        client: httpx.AsyncClient,
        worker_tasks: list[asyncio.Task],
        deadline: float,
    ) -> None:
        """Gradually launch virtual users at the configured spawn rate."""
        assert self._stop_event is not None
        target = self.config.virtual_users
        spawn_rate = self.config.spawn_rate
        spawned = 0
        # Spawn in small time slices for a smooth ramp.
        slice_interval = 0.25  # seconds
        per_slice = max(1, int(round(spawn_rate * slice_interval)))

        while spawned < target and not self._stop_event.is_set():
            batch = min(per_slice, target - spawned)
            for _ in range(batch):
                worker_tasks.append(
                    asyncio.create_task(self._worker(client, deadline))
                )
            spawned += batch
            self.state.set_active(spawned)
            await asyncio.sleep(slice_interval)

    async def _worker(self, client: httpx.AsyncClient, deadline: float) -> None:
        """A single virtual user: repeatedly requests a path until stop/deadline."""
        assert self._stop_event is not None
        paths = self.config.paths
        method = self.config.method
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            path = random.choice(paths)
            started = time.perf_counter()
            try:
                resp = await client.request(method, path)
                latency_ms = (time.perf_counter() - started) * 1000.0
                success = resp.status_code < 400
                self.metrics.record(resp.status_code, latency_ms, success)
            except httpx.TimeoutException:
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.metrics.record(0, latency_ms, False)
            except httpx.HTTPError:
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.metrics.record(0, latency_ms, False)
            except Exception:  # noqa: BLE001 - never let a worker kill the loop
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.metrics.record(0, latency_ms, False)

    async def _monitor(self, deadline: float) -> None:
        """Sample metrics every second and enforce safety thresholds."""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await asyncio.sleep(_MONITOR_INTERVAL_S)
            snap = self.metrics.snapshot(active_users=self.state.get_active())
            point = TimeSeriesPoint(
                t=snap.elapsed_seconds,
                rps=snap.requests_per_second,
                p95_ms=snap.p95_ms,
                avg_ms=snap.avg_latency_ms,
                error_rate_pct=snap.error_rate_pct,
                active_users=snap.active_users,
                total_requests=snap.total_requests,
            )
            self.state.append_point(point, snap)

            reason = evaluate_thresholds(
                snap,
                self.config.thresholds,
                self.metrics.rate_limit_count,
                self.metrics.server_error_count,
            )
            if reason is not None:
                self.state.stop_reason = reason
                logger.warning("Auto-stop triggered: %s", reason.value)
                self._stop_event.set()
                return

    # ----------------------------------------------------------- results
    def stop_reason_text(self) -> str:
        reason = self.state.stop_reason or StopReason.COMPLETED
        base = HUMAN_READABLE_STOP_REASON.get(reason, reason.value)
        if reason == StopReason.ENGINE_ERROR and self.state.error_message:
            return f"{base} ({self.state.error_message})"
        return base

    def result_status(self) -> TestResultStatus:
        """Derive a PASS/WARNING/STOPPED/FAILED verdict from the final state."""
        reason = self.state.stop_reason or StopReason.COMPLETED
        if reason == StopReason.ENGINE_ERROR:
            return TestResultStatus.FAILED
        if reason in {
            StopReason.ERROR_RATE,
            StopReason.P95_LATENCY,
            StopReason.RATE_LIMIT,
            StopReason.SERVER_ERRORS,
        }:
            return TestResultStatus.STOPPED
        if reason == StopReason.MANUAL:
            return TestResultStatus.WARNING

        # Completed normally: decide PASS vs WARNING on soft criteria.
        snap = self.snapshot()
        th = self.config.thresholds
        if (
            snap.error_rate_pct > th.max_error_rate_pct * 0.5
            or snap.p95_ms > th.max_p95_latency_ms * 0.8
        ):
            return TestResultStatus.WARNING
        return TestResultStatus.PASSED

    def build_summary(self) -> TestSummary:
        """Assemble the persistable summary for this run."""
        snap = self.snapshot()
        start = self.start_time or TestSummary.utcnow()
        end = self.end_time or TestSummary.utcnow()
        return TestSummary(
            target_url=self.config.target_url,
            start_time=start,
            end_time=end,
            duration_seconds=(end - start).total_seconds(),
            max_users=self.config.virtual_users,
            total_requests=snap.total_requests,
            successful_requests=snap.successful_requests,
            failed_requests=snap.failed_requests,
            requests_per_second=snap.requests_per_second,
            avg_latency_ms=snap.avg_latency_ms,
            min_latency_ms=snap.min_latency_ms,
            max_latency_ms=snap.max_latency_ms,
            p50_ms=snap.p50_ms,
            p95_ms=snap.p95_ms,
            p99_ms=snap.p99_ms,
            error_rate_pct=snap.error_rate_pct,
            result=self.result_status(),
            stop_reason=self.stop_reason_text(),
        )
