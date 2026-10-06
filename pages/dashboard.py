"""Dashboard page: configure, launch, monitor, and summarise a load test."""

from __future__ import annotations

import time

import streamlit as st
from pydantic import ValidationError

from core.test_manager import LoadTest
from core.validators import validate_url
from models.schemas import SafetyThresholds, TestConfig, TestResultStatus
from pages.common import (
    AUTH_STATEMENT,
    active_test,
    db,
    init_state,
    render_live_charts,
    render_metric_grid,
    settings_state,
)

_USER_PRESETS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000]
_DURATION_PRESETS = {
    "30 seconds": 30,
    "60 seconds": 60,
    "2 minutes": 120,
    "5 minutes": 300,
    "Custom": None,
}


def render() -> None:
    init_state()
    settings = settings_state()

    st.title("Website Load Testing Dashboard")
    st.caption("Authorized performance and stress testing")

    st.warning(
        "⚠️ **Only test systems you own or are explicitly authorized to test.** "
        "This tool measures capacity and automatically stops at configured safety "
        "thresholds. It is not designed to take a site offline.",
        icon="⚠️",
    )

    test = active_test()
    if test is not None and (test.is_running() or test.state.running):
        _render_running_view(test)
        return

    # If a test just finished, show its summary first.
    if test is not None and not test.is_running() and not test.state.running:
        _render_finished_view(test)

    _render_config_form(settings)


# --------------------------------------------------------------- config form
def _render_config_form(settings) -> None:
    st.subheader("Target")
    url = st.text_input(
        "Target URL",
        value="https://example.com",
        help="The deployed site you are authorized to test.",
    )
    allow_private = st.session_state.get("allow_private_targets", settings.allow_private_targets)
    if allow_private:
        st.info("Private/localhost targets are currently **enabled** (see Settings).")

    st.subheader("Test configuration")
    st.caption("Virtual users are simulated clients, not browser windows.")

    col1, col2 = st.columns(2)
    with col1:
        preset = st.selectbox(
            "Virtual users",
            options=[*_USER_PRESETS, "Custom"],
            index=3,
        )
        if preset == "Custom":
            users = st.number_input(
                "Custom virtual users",
                min_value=1,
                max_value=settings.max_users_hard_cap,
                value=min(100, settings.max_users_hard_cap),
                step=10,
            )
        else:
            users = int(preset)
        st.caption(f"Hard safety cap: {settings.max_users_hard_cap:,} users.")
        if users > settings.single_machine_recommended_max:
            st.warning(
                f"⚠️ {users:,} virtual users exceeds the ~{settings.single_machine_recommended_max:,} "
                "that a single machine can realistically generate. Past this point you are "
                "likely measuring **your own machine**, not the target. For tests this large, "
                "use the distributed Locust cluster (see the README / Advanced section) with "
                "multiple workers.",
                icon="⚠️",
            )

        spawn_rate = st.number_input(
            "Ramp-up (users added per second)",
            min_value=0.1,
            max_value=float(settings.max_users_hard_cap),
            value=float(settings.default_spawn_rate),
            step=1.0,
            help="Load increases gradually rather than all at once.",
        )

    with col2:
        duration_label = st.selectbox("Duration", options=list(_DURATION_PRESETS.keys()), index=1)
        if _DURATION_PRESETS[duration_label] is None:
            duration = st.number_input(
                "Custom duration (seconds)",
                min_value=1,
                max_value=settings.max_duration_hard_cap_s,
                value=min(60, settings.max_duration_hard_cap_s),
                step=10,
            )
        else:
            duration = _DURATION_PRESETS[duration_label]
        st.caption(f"Hard safety cap: {settings.max_duration_hard_cap_s:,}s.")

        timeout = st.number_input(
            "Per-request timeout (seconds)",
            min_value=1.0, max_value=120.0,
            value=float(settings.default_timeout_s), step=1.0,
        )

    st.subheader("Scenario")
    method = st.radio("HTTP method", options=["GET", "HEAD"], horizontal=True)
    paths_raw = st.text_area(
        "Authorized paths (one per line)",
        value="/\n/about\n/contact\n/products",
        help="Each path is requested against the target base URL.",
    )
    paths = [p.strip() for p in paths_raw.splitlines() if p.strip()]

    with st.expander("Safety thresholds (automatic stop conditions)"):
        th = st.session_state.thresholds
        tc = st.columns(2)
        err = tc[0].number_input("Max error rate (%)", 0.0, 100.0, th.max_error_rate_pct, 0.5)
        p95 = tc[1].number_input("Max P95 latency (ms)", 1.0, 60000.0, th.max_p95_latency_ms, 100.0)
        tc2 = st.columns(2)
        rl = tc2[0].number_input("Max HTTP 429 rate (%)", 0.0, 100.0, th.max_rate_limit_pct, 0.5)
        se = tc2[1].number_input("Max HTTP 5xx rate (%)", 0.0, 100.0, th.max_server_error_pct, 0.5)

    with st.expander("🧭 Advanced / Distributed Testing (for very large tests)"):
        st.markdown(
            f"""
**{settings.single_machine_recommended_max:,}+ virtual users from one laptop is not realistic.**
100,000 virtual users ≠ 100,000 Chrome windows — each virtual user is a
concurrent request loop, and a single machine runs out of CPU, sockets, and
file descriptors long before the target does.

For large authorized tests, scale out with a **Locust master + workers**
cluster (disabled by default, never auto-provisioned):

```
Local Dashboard → Load Controller (master) → Worker 1..N → Authorized Target
```

```bash
export LT_TARGET_URL={url or "https://your-target.example.com"}
export LT_PATHS=/,/about,/products
docker compose -f docker-compose.distributed.yml up --scale worker=8
# open the Locust UI at http://localhost:8089 and set users / spawn-rate / run-time
```

The local engine's connection pool is capped at
**{settings.max_connection_pool:,}** so large VU counts degrade gracefully
instead of crashing. See the README "Distributed testing architecture" section
for details.
"""
        )

    st.divider()
    authorized = st.checkbox(AUTH_STATEMENT)

    start = st.button("▶ Start load test", type="primary", disabled=not authorized)
    if not authorized:
        st.caption("You must confirm authorization before a test can start.")

    if start:
        _start_test(
            url=url,
            allow_private=allow_private,
            users=int(users),
            spawn_rate=float(spawn_rate),
            duration=int(duration),
            timeout=float(timeout),
            method=method,
            paths=paths,
            thresholds=SafetyThresholds(
                max_error_rate_pct=err,
                max_p95_latency_ms=p95,
                max_rate_limit_pct=rl,
                max_server_error_pct=se,
            ),
            authorized=authorized,
        )


def _start_test(**kwargs) -> None:
    settings = settings_state()
    result = validate_url(kwargs["url"], allow_private=kwargs["allow_private"])
    if not result.ok:
        st.error(result.message)
        return

    users = settings.clamp_users(kwargs["users"])
    duration = settings.clamp_duration(kwargs["duration"])
    if users != kwargs["users"]:
        st.warning(f"Virtual users clamped to the hard cap: {users:,}.")
    if duration != kwargs["duration"]:
        st.warning(f"Duration clamped to the hard cap: {duration:,}s.")

    try:
        config = TestConfig(
            target_url=result.normalized_url,
            paths=kwargs["paths"] or ["/"],
            method=kwargs["method"],
            virtual_users=users,
            spawn_rate=kwargs["spawn_rate"],
            duration_seconds=duration,
            request_timeout_s=kwargs["timeout"],
            allow_private_targets=kwargs["allow_private"],
            thresholds=kwargs["thresholds"],
            authorized=kwargs["authorized"],
        )
    except ValidationError as exc:
        st.error("Configuration error:\n\n" + "\n".join(
            f"- {e['msg']}" for e in exc.errors()
        ))
        return

    test = LoadTest(
        config,
        user_agent=settings.user_agent,
        connection_pool_cap=settings.max_connection_pool,
    )
    test.start()
    st.session_state.active_test = test
    st.session_state.last_summary_id = None
    st.rerun()


# ------------------------------------------------------------- running view
def _render_running_view(test: LoadTest) -> None:
    st.subheader("Test running")
    cfg = test.config
    st.caption(f"Target: {cfg.target_url}  ·  Peak users: {cfg.virtual_users:,}  ·  "
               f"Duration: {cfg.duration_seconds}s")

    if st.button("⏹ STOP TEST", type="primary"):
        test.stop()
        st.info("Stop requested — workers are shutting down gracefully…")

    snap = test.snapshot()
    progress = min(snap.elapsed_seconds / cfg.duration_seconds, 1.0)
    st.progress(progress, text=f"Elapsed {snap.elapsed_seconds:.0f}s / {cfg.duration_seconds}s")

    render_metric_grid(snap)
    st.divider()
    render_live_charts(test.history())

    # Auto-refresh the live view roughly once per second.
    if test.is_running() or test.state.running:
        time.sleep(1.0)
        st.rerun()
    else:
        st.rerun()


# ------------------------------------------------------------ finished view
def _render_finished_view(test: LoadTest) -> None:
    summary = test.build_summary()

    # Persist exactly once per completed test.
    if st.session_state.last_summary_id is None:
        new_id = db().save(summary)
        st.session_state.last_summary_id = new_id

    badge = {
        TestResultStatus.PASSED: "✅ PASSED",
        TestResultStatus.WARNING: "⚠️ WARNING",
        TestResultStatus.STOPPED: "🛑 STOPPED",
        TestResultStatus.FAILED: "❌ FAILED",
    }[summary.result]

    st.subheader("Test summary")
    st.markdown(f"### Result: {badge}")
    st.info(test.stop_reason_text())

    c = st.columns(4)
    c[0].metric("Target", summary.target_url)
    c[1].metric("Duration", f"{summary.duration_seconds:.0f} s")
    c[2].metric("Peak users", f"{summary.max_users:,}")
    c[3].metric("Total requests", f"{summary.total_requests:,}")

    c2 = st.columns(4)
    c2[0].metric("Requests/sec", f"{summary.requests_per_second:,.1f}")
    c2[1].metric("Avg latency", f"{summary.avg_latency_ms:.0f} ms")
    c2[2].metric("P95", f"{summary.p95_ms:.0f} ms")
    c2[3].metric("Error rate", f"{summary.error_rate_pct:.2f}%")

    render_live_charts(test.history())

    if st.button("Configure a new test"):
        st.session_state.active_test = None
        st.session_state.last_summary_id = None
        st.rerun()
    st.divider()
