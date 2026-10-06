"""Locust entry point for the optional distributed load-testing mode.

The default local mode uses the in-process asyncio engine (see
``core/test_manager.py``). This Locust file exists for *large, authorized*
tests that a single machine cannot generate on its own — it is driven through a
Locust master/worker cluster (see the Distributed Testing section of the
README and ``docker-compose.distributed.yml``).

Run locally (web UI):
    LT_TARGET_URL=https://example.com locust -f loadtest/locustfile.py

Run headless with a hard stop:
    LT_TARGET_URL=https://example.com \\
    locust -f loadtest/locustfile.py --headless \\
           -u 100 -r 10 --run-time 60s --stop-timeout 10

Only GET/HEAD tasks are defined. This file never issues mutating requests.
"""

from __future__ import annotations

import logging

try:
    from locust import HttpUser, between, events, task
except ImportError as exc:  # pragma: no cover - locust is an optional extra
    raise SystemExit(
        "Locust is not installed. Install the distributed extra with "
        "`pip install locust` to use distributed mode."
    ) from exc

from loadtest.scenarios import scenario_from_env

logger = logging.getLogger("loadtester.locust")

_SCENARIO = scenario_from_env()

# Thresholds for the optional automatic-stop hook (percent / milliseconds).
_MAX_ERROR_RATE_PCT = 5.0
_MIN_REQUESTS_BEFORE_EVAL = 50


class AuthorizedTargetUser(HttpUser):
    """A virtual user that issues safe reads against authorized paths."""

    host = _SCENARIO.base_url
    # A small think-time keeps each user realistic rather than hammering flat-out.
    wait_time = between(0.5, 2.0)

    @task
    def hit_path(self) -> None:
        # Rotate through configured paths; weighting could be added here.
        for path in _SCENARIO.paths:
            name = path  # group stats by path, not by full URL
            self.client.request(_SCENARIO.method, path, name=name)


@events.quitting.add_listener
def _enforce_quality_gate(environment, **_kwargs) -> None:
    """Exit non-zero if the run breached the error-rate gate (useful in CI)."""
    stats = environment.stats.total
    if stats.num_requests < _MIN_REQUESTS_BEFORE_EVAL:
        return
    error_rate = (stats.num_failures / stats.num_requests) * 100.0
    if error_rate > _MAX_ERROR_RATE_PCT:
        logger.error(
            "Error rate %.2f%% exceeded gate of %.2f%%", error_rate, _MAX_ERROR_RATE_PCT
        )
        environment.process_exit_code = 1
