"""Pydantic data models for configuration, runtime state, and test results.

These models are the single source of truth for validated configuration that
flows from the Streamlit UI into the load engine, and for the structured
results that are persisted to SQLite and exported.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Supported HTTP methods are intentionally limited. This tool is for measuring
# capacity, not for mutating a target, so only safe/idempotent reads are allowed.
SUPPORTED_METHODS = {"GET", "HEAD"}


class TestResultStatus(str, Enum):
    """Final verdict for a completed test."""

    PASSED = "PASSED"
    WARNING = "WARNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class StopReason(str, Enum):
    """Why a running test ended."""

    COMPLETED = "duration_reached"
    MANUAL = "manual_stop"
    ERROR_RATE = "error_rate_exceeded"
    P95_LATENCY = "p95_latency_exceeded"
    RATE_LIMIT = "rate_limit_responses_exceeded"
    SERVER_ERRORS = "server_error_responses_exceeded"
    ENGINE_ERROR = "engine_error"


HUMAN_READABLE_STOP_REASON = {
    StopReason.COMPLETED: "Test completed: the configured duration was reached.",
    StopReason.MANUAL: "Test stopped manually by the operator.",
    StopReason.ERROR_RATE: (
        "Test stopped automatically because the error rate exceeded the "
        "configured threshold."
    ),
    StopReason.P95_LATENCY: (
        "Test stopped automatically because P95 latency exceeded the "
        "configured threshold."
    ),
    StopReason.RATE_LIMIT: (
        "Test stopped automatically because the target returned too many "
        "HTTP 429 (rate limit) responses."
    ),
    StopReason.SERVER_ERRORS: (
        "Test stopped automatically because the target returned too many "
        "HTTP 5xx (server error) responses."
    ),
    StopReason.ENGINE_ERROR: "Test stopped because of an internal engine error.",
}


class SafetyThresholds(BaseModel):
    """Automatic stop conditions evaluated continuously while a test runs.

    Every threshold is a guardrail: the test halts as soon as one is breached
    so the tool measures capacity rather than driving a target into the ground.
    """

    max_error_rate_pct: float = Field(
        default=5.0, ge=0.0, le=100.0,
        description="Stop if the overall error rate exceeds this percentage.",
    )
    max_p95_latency_ms: float = Field(
        default=3000.0, ge=1.0,
        description="Stop if P95 response time exceeds this many milliseconds.",
    )
    max_rate_limit_pct: float = Field(
        default=2.0, ge=0.0, le=100.0,
        description="Stop if HTTP 429 responses exceed this percentage of requests.",
    )
    max_server_error_pct: float = Field(
        default=2.0, ge=0.0, le=100.0,
        description="Stop if HTTP 5xx responses exceed this percentage of requests.",
    )
    # A short grace period so a cold start / first few requests don't trip the
    # error-rate guard before any meaningful sample has been collected.
    min_requests_before_eval: int = Field(
        default=20, ge=1,
        description="Minimum number of completed requests before thresholds apply.",
    )


class TestConfig(BaseModel):
    """Fully validated configuration for a single load test run."""

    target_url: str = Field(..., description="Base target URL (http/https).")
    paths: list[str] = Field(
        default_factory=lambda: ["/"],
        description="Request paths appended to the base URL.",
    )
    method: str = Field(default="GET", description="HTTP method (GET or HEAD only).")
    virtual_users: int = Field(..., ge=1, description="Peak number of virtual users.")
    spawn_rate: float = Field(
        ..., gt=0.0, description="Virtual users added per second during ramp-up."
    )
    duration_seconds: int = Field(..., ge=1, description="Maximum test duration.")
    request_timeout_s: float = Field(
        default=10.0, gt=0.0, description="Per-request timeout in seconds."
    )
    allow_private_targets: bool = Field(
        default=False,
        description="Permit localhost / private / internal addresses (dev only).",
    )
    thresholds: SafetyThresholds = Field(default_factory=SafetyThresholds)
    authorized: bool = Field(
        default=False,
        description="Operator confirmed ownership/authorization of the target.",
    )

    @field_validator("method")
    @classmethod
    def _method_supported(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_METHODS:
            raise ValueError(
                f"Unsupported method '{value}'. Only {sorted(SUPPORTED_METHODS)} "
                "are allowed by this tool."
            )
        return normalized

    @field_validator("paths")
    @classmethod
    def _normalize_paths(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            path = raw.strip()
            if not path:
                continue
            if not path.startswith("/"):
                path = "/" + path
            if path not in cleaned:
                cleaned.append(path)
        return cleaned or ["/"]

    @model_validator(mode="after")
    def _fit_ramp_into_test(self) -> "TestConfig":
        # Ramp-up must leave time at peak load. Instead of rejecting the config,
        # speed the ramp up so it finishes within half of the test window.
        max_ramp_seconds = max(1.0, self.duration_seconds * 0.5)
        if self.virtual_users / self.spawn_rate > max_ramp_seconds:
            self.spawn_rate = math.ceil(self.virtual_users / max_ramp_seconds)
        return self


class LiveMetrics(BaseModel):
    """A point-in-time snapshot of a running (or finished) test."""

    active_users: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    requests_per_second: float = 0.0
    error_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    status_distribution: dict[str, int] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0


class TestSummary(BaseModel):
    """Persisted summary of a completed test (one row in the history table)."""

    id: Optional[int] = None
    target_url: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    max_users: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    requests_per_second: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate_pct: float
    result: TestResultStatus
    stop_reason: str

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)
