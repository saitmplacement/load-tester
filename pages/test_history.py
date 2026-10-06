"""Test History page: browse, inspect, export, and delete past runs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.database import summaries_to_csv, summaries_to_json
from pages.common import db, init_state


def render() -> None:
    init_state()
    st.title("Test History")
    st.caption("Previous load tests stored locally in SQLite.")

    summaries = db().list_all()
    if not summaries:
        st.info("No tests have been run yet. Start one from the Dashboard.")
        return

    # Overview table.
    rows = []
    for s in summaries:
        rows.append(
            {
                "ID": s.id,
                "Target": s.target_url,
                "Started": s.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Duration (s)": round(s.duration_seconds, 1),
                "Peak users": s.max_users,
                "Requests": s.total_requests,
                "RPS": round(s.requests_per_second, 1),
                "P95 (ms)": round(s.p95_ms, 0),
                "Error %": round(s.error_rate_pct, 2),
                "Result": s.result.value,
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Export all.
    exp = st.columns(2)
    exp[0].download_button(
        "⬇ Export all (CSV)",
        data=summaries_to_csv(summaries),
        file_name="load_test_history.csv",
        mime="text/csv",
    )
    exp[1].download_button(
        "⬇ Export all (JSON)",
        data=summaries_to_json(summaries),
        file_name="load_test_history.json",
        mime="application/json",
    )

    st.divider()
    st.subheader("Inspect a test")
    ids = [s.id for s in summaries]
    selected = st.selectbox("Select test ID", options=ids)
    summary = db().get(int(selected)) if selected is not None else None
    if summary is None:
        return

    detail = st.columns(4)
    detail[0].metric("Result", summary.result.value)
    detail[1].metric("Total requests", f"{summary.total_requests:,}")
    detail[2].metric("Requests/sec", f"{summary.requests_per_second:,.1f}")
    detail[3].metric("Error rate", f"{summary.error_rate_pct:.2f}%")

    detail2 = st.columns(4)
    detail2[0].metric("P50", f"{summary.p50_ms:.0f} ms")
    detail2[1].metric("P95", f"{summary.p95_ms:.0f} ms")
    detail2[2].metric("P99", f"{summary.p99_ms:.0f} ms")
    detail2[3].metric("Max", f"{summary.max_latency_ms:.0f} ms")

    st.caption(f"Stop reason: {summary.stop_reason}")

    act = st.columns(3)
    act[0].download_button(
        "⬇ This test (CSV)",
        data=summaries_to_csv([summary]),
        file_name=f"load_test_{summary.id}.csv",
        mime="text/csv",
    )
    act[1].download_button(
        "⬇ This test (JSON)",
        data=summaries_to_json([summary]),
        file_name=f"load_test_{summary.id}.json",
        mime="application/json",
    )
    if act[2].button("🗑 Delete this record", type="secondary"):
        db().delete(int(summary.id))
        st.success(f"Deleted test #{summary.id}.")
        st.rerun()
