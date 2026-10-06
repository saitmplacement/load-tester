"""FastAPI backend for the Website Load Testing Dashboard.

This exposes the shared in-process load engine (``core/``) over a small REST API
that the Next.js frontend consumes. A single active test is held in process,
since the tool is a single-operator local application.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.settings import get_settings
from core.database import HistoryDatabase, summaries_to_csv, summaries_to_json
from core.test_manager import LoadTest
from core.validators import split_target, validate_url
from models.schemas import SafetyThresholds, TestConfig, TestResultStatus

logger = logging.getLogger("loadtester.api")

settings = get_settings()
db = HistoryDatabase(settings.database_path)

app = FastAPI(title="Load Testing API", version="1.0.0")

# The Next.js dev server runs on :3000; allow it (and common local variants).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_PRESETS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000]
DURATION_PRESETS = [30, 60, 120, 300]


# --------------------------------------------------------------- active test
class _Controller:
    """Holds the single active/most-recent test and its persistence state."""

    def __init__(self) -> None:
        self.test: Optional[LoadTest] = None
        self.saved_id: Optional[int] = None

    def maybe_persist(self) -> None:
        """Persist a finished test exactly once."""
        if (
            self.test is not None
            and not self.test.is_running()
            and not self.test.state.running
            and self.saved_id is None
            and self.test.start_time is not None
            and self.test.snapshot().total_requests >= 0
        ):
            summary = self.test.build_summary()
            self.saved_id = db.save(summary)
            logger.info("Persisted finished test as history id=%s", self.saved_id)


controller = _Controller()


# ------------------------------------------------------------------ schemas
class ValidateRequest(BaseModel):
    url: str
    allow_private: bool = False


class StartRequest(BaseModel):
    target_url: str
    paths: list[str] = Field(default_factory=lambda: ["/"])
    method: str = "GET"
    virtual_users: int = 100
    spawn_rate: float = 10.0
    duration_seconds: int = 60
    request_timeout_s: float = 10.0
    allow_private_targets: bool = False
    authorized: bool = False
    max_error_rate_pct: float = 5.0
    max_p95_latency_ms: float = 3000.0
    max_rate_limit_pct: float = 2.0
    max_server_error_pct: float = 2.0


# -------------------------------------------------------------- serializers
def _snapshot_dict(test: LoadTest) -> dict:
    snap = test.snapshot()
    return {
        "activeUsers": snap.active_users,
        "totalRequests": snap.total_requests,
        "successfulRequests": snap.successful_requests,
        "failedRequests": snap.failed_requests,
        "requestsPerSecond": round(snap.requests_per_second, 2),
        "errorRatePct": round(snap.error_rate_pct, 2),
        "avgLatencyMs": round(snap.avg_latency_ms, 1),
        "minLatencyMs": round(snap.min_latency_ms, 1),
        "maxLatencyMs": round(snap.max_latency_ms, 1),
        "p50Ms": round(snap.p50_ms, 1),
        "p95Ms": round(snap.p95_ms, 1),
        "p99Ms": round(snap.p99_ms, 1),
        "statusDistribution": snap.status_distribution,
        "elapsedSeconds": round(snap.elapsed_seconds, 1),
    }


def _summary_dict(s) -> dict:
    return {
        "id": s.id,
        "targetUrl": s.target_url,
        "startTime": s.start_time.isoformat(),
        "endTime": s.end_time.isoformat(),
        "durationSeconds": round(s.duration_seconds, 1),
        "maxUsers": s.max_users,
        "totalRequests": s.total_requests,
        "successfulRequests": s.successful_requests,
        "failedRequests": s.failed_requests,
        "requestsPerSecond": round(s.requests_per_second, 2),
        "avgLatencyMs": round(s.avg_latency_ms, 1),
        "minLatencyMs": round(s.min_latency_ms, 1),
        "maxLatencyMs": round(s.max_latency_ms, 1),
        "p50Ms": round(s.p50_ms, 1),
        "p95Ms": round(s.p95_ms, 1),
        "p99Ms": round(s.p99_ms, 1),
        "errorRatePct": round(s.error_rate_pct, 2),
        "result": s.result.value,
        "stopReason": s.stop_reason,
    }


# -------------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/settings")
def api_settings() -> dict:
    return {
        "maxUsersHardCap": settings.max_users_hard_cap,
        "maxDurationHardCapS": settings.max_duration_hard_cap_s,
        "singleMachineRecommendedMax": settings.single_machine_recommended_max,
        "defaultMaxUsers": settings.default_max_users,
        "defaultDurationS": settings.default_duration_s,
        "defaultSpawnRate": settings.default_spawn_rate,
        "defaultTimeoutS": settings.default_timeout_s,
        "defaultErrorThresholdPct": settings.default_error_threshold_pct,
        "defaultP95ThresholdMs": settings.default_p95_threshold_ms,
        "allowPrivateTargets": settings.allow_private_targets,
        "databasePath": settings.database_path,
        "userPresets": USER_PRESETS,
        "durationPresets": DURATION_PRESETS,
    }


@app.post("/api/validate")
def api_validate(req: ValidateRequest) -> dict:
    result = validate_url(req.url, allow_private=req.allow_private)
    return {
        "ok": result.ok,
        "message": result.message,
        "normalizedUrl": result.normalized_url,
    }


@app.post("/api/tests")
def start_test(req: StartRequest) -> dict:
    if controller.test is not None and controller.test.is_running():
        raise HTTPException(status_code=409, detail="A test is already running.")

    if not req.authorized:
        raise HTTPException(
            status_code=400,
            detail="You must confirm authorization before starting a test.",
        )

    result = validate_url(req.target_url, allow_private=req.allow_private_targets)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message)

    users = settings.clamp_users(req.virtual_users)
    duration = settings.clamp_duration(req.duration_seconds)
    origin, paths = split_target(result.normalized_url, req.paths or ["/"])

    try:
        config = TestConfig(
            target_url=origin,
            paths=paths,
            method=req.method,
            virtual_users=users,
            spawn_rate=req.spawn_rate,
            duration_seconds=duration,
            request_timeout_s=req.request_timeout_s,
            allow_private_targets=req.allow_private_targets,
            authorized=req.authorized,
            thresholds=SafetyThresholds(
                max_error_rate_pct=req.max_error_rate_pct,
                max_p95_latency_ms=req.max_p95_latency_ms,
                max_rate_limit_pct=req.max_rate_limit_pct,
                max_server_error_pct=req.max_server_error_pct,
            ),
        )
    except Exception as exc:  # pydantic ValidationError -> 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    test = LoadTest(
        config,
        user_agent=settings.user_agent,
        connection_pool_cap=settings.max_connection_pool,
    )
    test.start()
    controller.test = test
    controller.saved_id = None

    clamped = {}
    if users != req.virtual_users:
        clamped["virtualUsers"] = users
    if duration != req.duration_seconds:
        clamped["durationSeconds"] = duration

    return {"running": True, "clamped": clamped, "config": {
        "targetUrl": config.target_url,
        "virtualUsers": config.virtual_users,
        "spawnRate": config.spawn_rate,
        "durationSeconds": config.duration_seconds,
        "method": config.method,
        "paths": config.paths,
    }}


@app.get("/api/tests/current")
def current_test() -> dict:
    test = controller.test
    if test is None:
        return {"exists": False}

    running = bool(test.is_running() or test.state.running)
    if not running:
        controller.maybe_persist()

    return {
        "exists": True,
        "running": running,
        "config": {
            "targetUrl": test.config.target_url,
            "virtualUsers": test.config.virtual_users,
            "spawnRate": test.config.spawn_rate,
            "durationSeconds": test.config.duration_seconds,
            "method": test.config.method,
            "paths": test.config.paths,
        },
        "metrics": _snapshot_dict(test),
        "history": [
            {
                "t": round(p.t, 1),
                "rps": round(p.rps, 2),
                "p95Ms": round(p.p95_ms, 1),
                "avgMs": round(p.avg_ms, 1),
                "errorRatePct": round(p.error_rate_pct, 2),
                "activeUsers": p.active_users,
            }
            for p in test.history()
        ],
        "result": None if running else test.result_status().value,
        "stopReason": None if running else test.stop_reason_text(),
        "savedId": controller.saved_id,
    }


@app.post("/api/tests/stop")
def stop_test() -> dict:
    test = controller.test
    if test is None or not test.is_running():
        raise HTTPException(status_code=400, detail="No test is currently running.")
    test.stop()
    return {"stopping": True}


@app.get("/api/history")
def list_history() -> list[dict]:
    return [_summary_dict(s) for s in db.list_all()]


@app.get("/api/history/export")
def export_history(format: str = "csv", id: Optional[int] = None) -> Response:
    if id is not None:
        summary = db.get(id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Test not found.")
        summaries = [summary]
        stem = f"load_test_{id}"
    else:
        summaries = db.list_all()
        stem = "load_test_history"

    if format == "json":
        body = summaries_to_json(summaries)
        media = "application/json"
        ext = "json"
    else:
        body = summaries_to_csv(summaries)
        media = "text/csv"
        ext = "csv"

    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{stem}.{ext}"'},
    )


@app.get("/api/history/{test_id}")
def get_history(test_id: int) -> dict:
    summary = db.get(test_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Test not found.")
    return _summary_dict(summary)


@app.delete("/api/history/{test_id}")
def delete_history(test_id: int) -> dict:
    if db.get(test_id) is None:
        raise HTTPException(status_code=404, detail="Test not found.")
    db.delete(test_id)
    return {"deleted": test_id}


@app.delete("/api/history")
def clear_history() -> dict:
    db.clear()
    return {"cleared": True}
