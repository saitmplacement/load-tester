"""Tests for configuration validation and safety clamping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings
from models.schemas import SafetyThresholds, TestConfig


def _valid_config(**overrides) -> TestConfig:
    data = dict(
        target_url="https://example.com",
        paths=["/", "/about"],
        method="GET",
        virtual_users=100,
        spawn_rate=10.0,
        duration_seconds=60,
    )
    data.update(overrides)
    return TestConfig(**data)


def test_valid_config_builds() -> None:
    cfg = _valid_config()
    assert cfg.virtual_users == 100
    assert cfg.paths == ["/", "/about"]


def test_paths_are_normalized_and_deduplicated() -> None:
    cfg = _valid_config(paths=["about", "/about", "contact", ""])
    assert cfg.paths == ["/about", "/contact"]


def test_empty_paths_default_to_root() -> None:
    cfg = _valid_config(paths=[])
    assert cfg.paths == ["/"]


def test_unsupported_method_rejected() -> None:
    for bad in ["POST", "DELETE", "PUT", "PATCH"]:
        with pytest.raises(ValidationError):
            _valid_config(method=bad)


def test_head_method_allowed() -> None:
    assert _valid_config(method="head").method == "HEAD"


def test_zero_users_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_config(virtual_users=0)


def test_ramp_longer_than_duration_rejected() -> None:
    # 1000 users at 1/sec = 1000s ramp, but only 60s duration.
    with pytest.raises(ValidationError):
        _valid_config(virtual_users=1000, spawn_rate=1.0, duration_seconds=60)


def test_settings_clamp_users_and_duration() -> None:
    s = Settings(max_users_hard_cap=500, max_duration_hard_cap_s=300)
    assert s.clamp_users(100000) == 500
    assert s.clamp_users(50) == 50
    assert s.clamp_users(0) == 1
    assert s.clamp_duration(99999) == 300
    assert s.clamp_duration(30) == 30


def test_threshold_defaults_are_conservative() -> None:
    th = SafetyThresholds()
    assert th.max_error_rate_pct == 5.0
    assert th.max_p95_latency_ms == 3000.0
    assert th.min_requests_before_eval >= 1
