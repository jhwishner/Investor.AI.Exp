"""Entrypoint / router.

Since the app moved from the auto-discovered pages/ directory to an
explicit st.navigation call (needed for a top nav bar with grouped
sections, rather than a flat sidebar list), this file no longer renders a
page itself -- it's shared chrome around every page: page config, theme,
the login gate (which also renders the top app-bar), and navigation. Each
page file underneath reads `st.session_state["user_id"]` directly rather
than calling require_login() again.
"""

import streamlit as st

from auth_ui import require_login
from theme import apply_theme

st.set_page_config(page_title="Ivy Investments", page_icon=":material/insights:", layout="wide")

pages = {
    "": [st.Page("home.py", title="Home", icon=":material/insights:", default=True)],
    "Research": [
        st.Page("pages/2_Ticker_Analysis.py", title="Ticker analysis", icon=":material/query_stats:"),
        st.Page("pages/5_Market_Movers.py", title="Market movers", icon=":material/trending_up:"),
        st.Page("pages/6_Power_and_AI_Infrastructure.py", title="Power & AI infrastructure", icon=":material/bolt:"),
    ],
    "Manage": [
        st.Page("pages/3_Manage_Positions.py", title="Manage positions", icon=":material/edit_note:"),
        st.Page("pages/1_Portfolio.py", title="Portfolio", icon=":material/account_balance_wallet:"),
    ],
    "Insights": [
        st.Page("pages/4_Recommendations.py", title="Recommendations", icon=":material/lightbulb:"),
    ],
}

# st.navigation must register the pages (and renders the top-nav bar as a
# side effect) before require_login()'s app-bar can page_link("home.py", ..)
# -- Streamlit only recognizes page paths that have already been declared.
nav = st.navigation(pages, position="top")

# Theme after navigation, not before: each page grows its own ivy from its
# identity (see vines.py), and the current page is only known once
# st.navigation has resolved it. url_path is stable per page and empty for
# the default page, so fall back to a fixed key for that one.
apply_theme(nav.url_path or "home")

require_login()
nav.run()
