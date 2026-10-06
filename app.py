"""Entry point for the Website Load Testing Dashboard (Streamlit).

Run with:
    streamlit run app.py

Navigation is defined explicitly via ``st.navigation`` so the three pages share
a single Streamlit session (and therefore a single running test and database
connection).
"""

from __future__ import annotations

import logging

import streamlit as st

from pages import dashboard, settings as settings_page, test_history


def _configure_logging() -> None:
    """Configure structured logging that never records secrets.

    Only test lifecycle events, configuration (target, users, duration), errors,
    and stop reasons are logged. Request bodies, headers, cookies, and
    authorization material are never passed to the logger.
    """
    if logging.getLogger("loadtester").handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger("loadtester")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False


def main() -> None:
    st.set_page_config(
        page_title="Website Load Testing Dashboard",
        page_icon="📈",
        layout="wide",
    )
    _configure_logging()

    nav = st.navigation(
        [
            st.Page(dashboard.render, title="Dashboard", icon="📊", default=True),
            st.Page(test_history.render, title="Test History", icon="🗂"),
            st.Page(settings_page.render, title="Settings", icon="⚙️"),
        ]
    )
    nav.run()


if __name__ == "__main__":
    main()
