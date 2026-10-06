"""SQLite persistence for local test history.

A tiny, dependency-free data-access layer. The database lives entirely on the
local machine; no results ever leave the host. Each run is stored as a single
summary row.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from models.schemas import TestResultStatus, TestSummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    max_users INTEGER NOT NULL,
    total_requests INTEGER NOT NULL,
    successful_requests INTEGER NOT NULL,
    failed_requests INTEGER NOT NULL,
    requests_per_second REAL NOT NULL,
    avg_latency_ms REAL NOT NULL,
    min_latency_ms REAL NOT NULL,
    max_latency_ms REAL NOT NULL,
    p50_ms REAL NOT NULL,
    p95_ms REAL NOT NULL,
    p99_ms REAL NOT NULL,
    error_rate_pct REAL NOT NULL,
    result TEXT NOT NULL,
    stop_reason TEXT NOT NULL
);
"""

_COLUMNS = [
    "target_url", "start_time", "end_time", "duration_seconds", "max_users",
    "total_requests", "successful_requests", "failed_requests",
    "requests_per_second", "avg_latency_ms", "min_latency_ms", "max_latency_ms",
    "p50_ms", "p95_ms", "p99_ms", "error_rate_pct", "result", "stop_reason",
]


class HistoryDatabase:
    """Thin wrapper over a local SQLite file for storing test summaries."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def save(self, summary: TestSummary) -> int:
        """Insert a test summary and return its new row id."""
        values = (
            summary.target_url,
            summary.start_time.isoformat(),
            summary.end_time.isoformat(),
            summary.duration_seconds,
            summary.max_users,
            summary.total_requests,
            summary.successful_requests,
            summary.failed_requests,
            summary.requests_per_second,
            summary.avg_latency_ms,
            summary.min_latency_ms,
            summary.max_latency_ms,
            summary.p50_ms,
            summary.p95_ms,
            summary.p99_ms,
            summary.error_rate_pct,
            summary.result.value,
            summary.stop_reason,
        )
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        with self._connect() as conn:
            cur = conn.execute(
                f"INSERT INTO test_history ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
            return int(cur.lastrowid)

    def list_all(self) -> list[TestSummary]:
        """Return all stored summaries, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM test_history ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def get(self, test_id: int) -> TestSummary | None:
        """Return a single summary by id, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM test_history WHERE id = ?", (test_id,)
            ).fetchone()
        return self._row_to_summary(row) if row else None

    def delete(self, test_id: int) -> None:
        """Delete a single summary by id."""
        with self._connect() as conn:
            conn.execute("DELETE FROM test_history WHERE id = ?", (test_id,))

    def clear(self) -> None:
        """Delete all stored summaries."""
        with self._connect() as conn:
            conn.execute("DELETE FROM test_history")

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> TestSummary:
        return TestSummary(
            id=row["id"],
            target_url=row["target_url"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            duration_seconds=row["duration_seconds"],
            max_users=row["max_users"],
            total_requests=row["total_requests"],
            successful_requests=row["successful_requests"],
            failed_requests=row["failed_requests"],
            requests_per_second=row["requests_per_second"],
            avg_latency_ms=row["avg_latency_ms"],
            min_latency_ms=row["min_latency_ms"],
            max_latency_ms=row["max_latency_ms"],
            p50_ms=row["p50_ms"],
            p95_ms=row["p95_ms"],
            p99_ms=row["p99_ms"],
            error_rate_pct=row["error_rate_pct"],
            result=TestResultStatus(row["result"]),
            stop_reason=row["stop_reason"],
        )


def summaries_to_csv(summaries: list[TestSummary]) -> str:
    """Serialize a list of summaries to CSV text."""
    buffer = io.StringIO()
    fieldnames = ["id", *_COLUMNS]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for s in summaries:
        data = s.model_dump()
        data["start_time"] = s.start_time.isoformat()
        data["end_time"] = s.end_time.isoformat()
        data["result"] = s.result.value
        writer.writerow({k: data.get(k) for k in fieldnames})
    return buffer.getvalue()


def summaries_to_json(summaries: list[TestSummary]) -> str:
    """Serialize a list of summaries to JSON text."""
    return json.dumps(
        [json.loads(s.model_dump_json()) for s in summaries], indent=2
    )
