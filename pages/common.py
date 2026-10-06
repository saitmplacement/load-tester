"""Shared Streamlit helpers: session state, database access, and Plotly charts."""

from __future__ import annotations

import streamlit as st

from config.settings import Settings, get_settings
from core.database import HistoryDatabase
from core.test_manager import LoadTest, TimeSeriesPoint
from models.schemas import LiveMetrics, SafetyThresholds

AUTH_STATEMENT = (
    "I confirm that I own this website or have explicit authorization to "
    "perform load testing against it."
)


def init_state() -> None:
    """Initialise session state shared across all pages (idempotent)."""
    if "settings" not in st.session_state:
        st.session_state.settings = get_settings()
    if "db" not in st.session_state:
        st.session_state.db = HistoryDatabase(st.session_state.settings.database_path)
    if "active_test" not in st.session_state:
        st.session_state.active_test = None  # type: ignore[assignment]
    if "last_summary_id" not in st.session_state:
        st.session_state.last_summary_id = None
    if "thresholds" not in st.session_state:
        s = st.session_state.settings
        st.session_state.thresholds = SafetyThresholds(
            max_error_rate_pct=s.default_error_threshold_pct,
            max_p95_latency_ms=s.default_p95_threshold_ms,
        )


def settings_state() -> Settings:
    return st.session_state.settings


def db() -> HistoryDatabase:
    return st.session_state.db


def active_test() -> LoadTest | None:
    return st.session_state.active_test


# --------------------------------------------------------------------- charts
try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None  # type: ignore


def _line_chart(points: list[TimeSeriesPoint], attr: str, title: str, y_title: str):
    """Build a simple time-series line chart from history points."""
    fig = go.Figure()
    xs = [p.t for p in points]
    ys = [getattr(p, attr) for p in points]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=title, line={"width": 2}))
    fig.update_layout(
        title=title,
        xaxis_title="Elapsed (s)",
        yaxis_title=y_title,
        height=260,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
    )
    return fig


def render_live_charts(points: list[TimeSeriesPoint]) -> None:
    """Render the six live charts in a 2x3 grid."""
    if go is None:
        st.warning("Plotly is not installed; charts are unavailable.")
        return
    if not points:
        st.info("Waiting for the first metrics sample…")
        return

    row1 = st.columns(3)
    with row1[0]:
        st.plotly_chart(_line_chart(points, "rps", "Requests / sec", "req/s"),
                        use_container_width=True)
    with row1[1]:
        st.plotly_chart(_line_chart(points, "avg_ms", "Avg response time", "ms"),
                        use_container_width=True)
    with row1[2]:
        st.plotly_chart(_line_chart(points, "p95_ms", "P95 latency", "ms"),
                        use_container_width=True)

    row2 = st.columns(3)
    with row2[0]:
        st.plotly_chart(_line_chart(points, "error_rate_pct", "Error rate", "%"),
                        use_container_width=True)
    with row2[1]:
        st.plotly_chart(_line_chart(points, "active_users", "Active virtual users", "users"),
                        use_container_width=True)
    with row2[2]:
        _render_status_chart()


def _render_status_chart() -> None:
    """Render an HTTP status-code distribution bar chart from the latest snapshot."""
    test = active_test()
    if test is None:
        st.info("No status data yet.")
        return
    snap = test.snapshot()
    dist = snap.status_distribution
    if not dist:
        st.info("No status data yet.")
        return
    labels = list(dist.keys())
    values = list(dist.values())
    labels = [("transport-error" if l == "0" else l) for l in labels]
    fig = go.Figure(go.Bar(x=labels, y=values))
    fig.update_layout(
        title="HTTP status distribution",
        xaxis_title="Status code",
        yaxis_title="Count",
        height=260,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
    )
    st.plotly_chart(fig, use_container_width=True)


def render_metric_grid(snap: LiveMetrics) -> None:
    """Render the live numeric metric tiles."""
    row1 = st.columns(4)
    row1[0].metric("Active users", f"{snap.active_users:,}")
    row1[1].metric("Requests/sec", f"{snap.requests_per_second:,.1f}")
    row1[2].metric("Total requests", f"{snap.total_requests:,}")
    row1[3].metric("Error rate", f"{snap.error_rate_pct:.2f}%")

    row2 = st.columns(4)
    row2[0].metric("Successful", f"{snap.successful_requests:,}")
    row2[1].metric("Failed", f"{snap.failed_requests:,}")
    row2[2].metric("Avg latency", f"{snap.avg_latency_ms:.0f} ms")
    row2[3].metric("Max latency", f"{snap.max_latency_ms:.0f} ms")

    row3 = st.columns(4)
    row3[0].metric("P50", f"{snap.p50_ms:.0f} ms")
    row3[1].metric("P95", f"{snap.p95_ms:.0f} ms")
    row3[2].metric("P99", f"{snap.p99_ms:.0f} ms")
    row3[3].metric("Min latency", f"{snap.min_latency_ms:.0f} ms")
