"""Tests for SQLite persistence and export helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from core.database import HistoryDatabase, summaries_to_csv, summaries_to_json
from models.schemas import TestResultStatus, TestSummary


def _summary(target: str = "https://example.com") -> TestSummary:
    now = datetime.now(timezone.utc)
    return TestSummary(
        target_url=target,
        start_time=now,
        end_time=now,
        duration_seconds=60.0,
        max_users=100,
        total_requests=1000,
        successful_requests=990,
        failed_requests=10,
        requests_per_second=16.6,
        avg_latency_ms=120.0,
        min_latency_ms=10.0,
        max_latency_ms=800.0,
        p50_ms=100.0,
        p95_ms=400.0,
        p99_ms=700.0,
        error_rate_pct=1.0,
        result=TestResultStatus.PASSED,
        stop_reason="Test completed.",
    )


def test_save_and_retrieve(tmp_path) -> None:
    db = HistoryDatabase(str(tmp_path / "h.db"))
    new_id = db.save(_summary())
    assert new_id > 0

    fetched = db.get(new_id)
    assert fetched is not None
    assert fetched.target_url == "https://example.com"
    assert fetched.total_requests == 1000
    assert fetched.result == TestResultStatus.PASSED


def test_list_newest_first_and_delete(tmp_path) -> None:
    db = HistoryDatabase(str(tmp_path / "h.db"))
    id1 = db.save(_summary("https://a.example.com"))
    id2 = db.save(_summary("https://b.example.com"))

    all_rows = db.list_all()
    assert [r.id for r in all_rows] == [id2, id1]  # newest first

    db.delete(id1)
    assert db.get(id1) is None
    assert len(db.list_all()) == 1


def test_clear(tmp_path) -> None:
    db = HistoryDatabase(str(tmp_path / "h.db"))
    db.save(_summary())
    db.save(_summary())
    db.clear()
    assert db.list_all() == []


def test_csv_and_json_export(tmp_path) -> None:
    db = HistoryDatabase(str(tmp_path / "h.db"))
    db.save(_summary())
    rows = db.list_all()

    csv_text = summaries_to_csv(rows)
    assert "target_url" in csv_text
    assert "https://example.com" in csv_text

    json_text = summaries_to_json(rows)
    assert "https://example.com" in json_text
    assert "PASSED" in json_text
