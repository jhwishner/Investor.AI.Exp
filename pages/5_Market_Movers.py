"""Market-wide movers: top gainers, top losers, and most actively traded
tickers -- a snapshot of the whole market, independent of your paper
portfolio."""

import pandas as pd
import streamlit as st

from investor_ai import config, data
from live import enable_autorefresh, render_freshness_footer

enable_autorefresh(key="market_movers_autorefresh")
st.title("Market Movers")
render_freshness_footer()

st.caption(
    "A market-wide snapshot, independent of your paper portfolio. Sourced from Yahoo Finance's "
    "public screeners -- the same data behind Yahoo Finance's own gainers/losers pages -- free and "
    "with no API key, but unofficial and undocumented, so treat it the same as any other data in "
    "this app: verify anything important before acting on it."
)

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()
    st.rerun()

_DISPLAY_COLS = {
    "ticker": "Ticker",
    "name": "Name",
    "price": "Price",
    "change": "Change ($)",
    "change_pct": "Change (%)",
    "volume": "Volume",
    "market_cap": "Market Cap",
    "beta": "Beta",
}


def render_movers_table(category_key: str) -> None:
    df = data.get_market_movers(category_key)
    if df.empty:
        st.warning("Couldn't fetch this list right now -- try refreshing in a moment.")
        return
    display_df = df.copy()
    for col in ("price", "change", "change_pct"):
        display_df[col] = display_df[col].round(2)
    display_df["beta"] = pd.to_numeric(display_df["beta"], errors="coerce").round(2)
    st.dataframe(
        display_df.rename(columns=_DISPLAY_COLS),
        width="stretch",
        hide_index=True,
    )


tab_gainers, tab_losers, tab_active = st.tabs(list(data.MARKET_MOVER_CATEGORIES.keys()))

with tab_gainers:
    render_movers_table(data.MARKET_MOVER_CATEGORIES["Top Gainers"])

with tab_losers:
    render_movers_table(data.MARKET_MOVER_CATEGORIES["Top Losers"])

with tab_active:
    render_movers_table(data.MARKET_MOVER_CATEGORIES["Most Active"])

st.divider()
st.caption(config.DISCLAIMER)
