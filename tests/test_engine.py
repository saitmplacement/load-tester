"""End-to-end test of the load engine against a local HTTP server.

This verifies the full lifecycle: ramp-up, request execution, metric
collection, duration-based stop, and graceful shutdown — without touching any
external network.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.test_manager import LoadTest
from models.schemas import SafetyThresholds, TestConfig, TestResultStatus


class _QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:  # silence test server logging
        pass


@pytest.fixture()
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_short_run_completes_and_collects_metrics(local_server: str) -> None:
    config = TestConfig(
        target_url=local_server,
        paths=["/", "/about"],
        virtual_users=5,
        spawn_rate=5.0,
        duration_seconds=2,
        request_timeout_s=5.0,
        allow_private_targets=True,
        thresholds=SafetyThresholds(),
        authorized=True,
    )
    test = LoadTest(config, user_agent="pytest-agent/1.0")
    test.start()
    test.join(timeout=15)

    assert not test.is_running()
    snap = test.snapshot()
    assert snap.total_requests > 0
    assert snap.successful_requests == snap.total_requests  # local server never errors
    assert snap.error_rate_pct == 0.0

    summary = test.build_summary()
    assert summary.result == TestResultStatus.PASSED
    assert summary.total_requests == snap.total_requests
    assert "completed" in summary.stop_reason.lower()


def test_manual_stop(local_server: str) -> None:
    config = TestConfig(
        target_url=local_server,
        paths=["/"],
        virtual_users=3,
        spawn_rate=3.0,
        duration_seconds=30,
        allow_private_targets=True,
        authorized=True,
    )
    test = LoadTest(config)
    test.start()
    # Let it run briefly, then stop.
    test.join(timeout=2)
    test.stop()
    test.join(timeout=10)
    assert not test.is_running()
    summary = test.build_summary()
    assert summary.result == TestResultStatus.WARNING
    assert "manual" in summary.stop_reason.lower()
