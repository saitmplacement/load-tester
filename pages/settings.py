"""Settings page: adjust default test parameters and safety behaviour.

Hard safety caps (maximum users / maximum duration) are deliberately read-only
here — they are the outer safety envelope and can only be changed via
environment variables in ``.env``.
"""

from __future__ import annotations

import streamlit as st

from models.schemas import SafetyThresholds
from pages.common import db, init_state, settings_state


def render() -> None:
    init_state()
    settings = settings_state()

    st.title("Settings")
    st.caption("Defaults and safety behaviour for this local installation.")

    st.subheader("Default test parameters")
    c = st.columns(2)
    default_timeout = c[0].number_input(
        "Default request timeout (s)", 1.0, 120.0, float(settings.default_timeout_s), 1.0
    )
    default_duration = c[1].number_input(
        "Default duration (s)", 1, settings.max_duration_hard_cap_s,
        min(settings.default_duration_s, settings.max_duration_hard_cap_s), 10
    )
    c2 = st.columns(2)
    default_users = c2[0].number_input(
        "Default max users", 1, settings.max_users_hard_cap,
        min(settings.default_max_users, settings.max_users_hard_cap), 10
    )
    default_spawn = c2[1].number_input(
        "Default ramp-up (users/sec)", 0.1, float(settings.max_users_hard_cap),
        float(settings.default_spawn_rate), 1.0
    )

    st.subheader("Default safety thresholds")
    c3 = st.columns(2)
    err = c3[0].number_input(
        "Error-rate threshold (%)", 0.0, 100.0,
        float(st.session_state.thresholds.max_error_rate_pct), 0.5
    )
    p95 = c3[1].number_input(
        "P95 latency threshold (ms)", 1.0, 60000.0,
        float(st.session_state.thresholds.max_p95_latency_ms), 100.0
    )
    c4 = st.columns(2)
    rl = c4[0].number_input(
        "HTTP 429 threshold (%)", 0.0, 100.0,
        float(st.session_state.thresholds.max_rate_limit_pct), 0.5
    )
    se = c4[1].number_input(
        "HTTP 5xx threshold (%)", 0.0, 100.0,
        float(st.session_state.thresholds.max_server_error_pct), 0.5
    )

    st.subheader("Target policy")
    allow_private = st.toggle(
        "Allow private / localhost / internal targets (development only)",
        value=st.session_state.get("allow_private_targets", settings.allow_private_targets),
        help="When off, loopback and private network addresses are blocked.",
    )

    st.subheader("Storage")
    st.text_input("Database location", value=settings.database_path, disabled=True)
    st.caption("Change the database path via LT_DATABASE_PATH in your .env file.")

    st.divider()
    st.subheader("Hard safety caps (read-only)")
    hc = st.columns(2)
    hc[0].metric("Max users hard cap", f"{settings.max_users_hard_cap:,}")
    hc[1].metric("Max duration hard cap", f"{settings.max_duration_hard_cap_s:,} s")
    st.caption(
        "These outer limits protect the target and your machine. Change them only "
        "via LT_MAX_USERS_HARD_CAP / LT_MAX_DURATION_HARD_CAP_S in .env."
    )

    if st.button("💾 Apply settings (this session)", type="primary"):
        settings.default_timeout_s = float(default_timeout)
        settings.default_duration_s = int(default_duration)
        settings.default_max_users = int(default_users)
        settings.default_spawn_rate = float(default_spawn)
        st.session_state.thresholds = SafetyThresholds(
            max_error_rate_pct=err,
            max_p95_latency_ms=p95,
            max_rate_limit_pct=rl,
            max_server_error_pct=se,
        )
        st.session_state.allow_private_targets = bool(allow_private)
        st.success("Settings applied for this session.")

    st.divider()
    with st.expander("Danger zone"):
        st.caption("Permanently delete all locally stored test history.")
        if st.button("🗑 Clear all test history"):
            db().clear()
            st.success("All test history cleared.")
