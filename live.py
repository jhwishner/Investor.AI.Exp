"""Shared "live feel" helpers: auto-refresh + a last-checked timestamp.

Kept at the project root alongside theme.py -- pure UI glue, not business
logic, so it stays out of investor_ai/.

Only wired into the "watching" pages (Recommendations, Portfolio, Ticker
Analysis) -- deliberately NOT on Manage Positions, so an auto-refresh can
never interrupt someone mid-form.
"""

from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# 30 minutes -- matches investor_ai.config.CACHE_TTL_DAILY, so each tick has
# a real chance of surfacing newly-fetched data rather than replaying an
# identical cached value.
AUTOREFRESH_INTERVAL_MS = 30 * 60 * 1000


def enable_autorefresh(key: str) -> None:
    """Triggers a Streamlit rerun on a timer. Call once near the top of a page."""
    st_autorefresh(interval=AUTOREFRESH_INTERVAL_MS, key=key)


def render_freshness_footer() -> None:
    """A small "this page checks itself automatically" indicator."""
    st.caption(f"Auto-refreshing every 30 minutes -- last checked {datetime.now():%-I:%M:%S %p}")
