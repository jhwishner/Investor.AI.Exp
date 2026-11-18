"""Portfolio overview: open positions, totals, and Day/Week/Month/Year performance."""

import streamlit as st

from investor_ai import config, data, portfolio
from live import enable_autorefresh, render_freshness_footer

user_id = st.session_state["user_id"]
enable_autorefresh(key="portfolio_autorefresh")
st.title("Portfolio Overview")
render_freshness_footer()

portfolio.init_db()

top_col1, top_col2 = st.columns([1, 2])
with top_col1:
    if st.button("Refresh prices", icon=":material/refresh:"):
        st.cache_data.clear()
        st.rerun()
with top_col2:
    risk_filter = st.selectbox(
        "Filter by risk tag",
        options=["All"] + portfolio.list_risk_levels(user_id),
        label_visibility="collapsed",
    )
risk_filter = None if risk_filter == "All" else risk_filter

positions = portfolio.get_open_positions(user_id, risk_level=risk_filter)

if positions.empty:
    message = (
        "Your paper portfolio is empty. Head to **Manage Positions** to log a hypothetical trade."
        if risk_filter is None
        else f"No open positions tagged **{risk_filter}**."
    )
    st.info(message)
    st.stop()

all_tickers = sorted(positions["ticker"].unique())
current_prices = {t: data.get_current_price(t) for t in all_tickers}
missing = [t for t, p in current_prices.items() if p is None]
if missing:
    st.warning(f"Couldn't fetch a current price for: {', '.join(missing)}. Those rows will show as N/A below.")

price_history_lookup = {t: data.get_daily_history(t)["Close"] for t in all_tickers}

_RENAME_COLS = {
    "ticker": "Ticker",
    "quantity": "Qty",
    "avg_cost": "Avg Cost",
    "current_price": "Current Price",
    "market_value": "Market Value",
    "cost_basis": "Cost Basis",
    "unrealized_pl": "Unrealized P&L ($)",
    "unrealized_pl_pct": "Unrealized P&L (%)",
    "risk_level": "Risk Tag",
}


def _render_positions_table(summary) -> None:
    display_df = summary.copy()
    for col in ["current_price", "market_value", "cost_basis", "unrealized_pl", "unrealized_pl_pct"]:
        display_df[col] = display_df[col].round(2)
    st.dataframe(
        display_df.drop(columns=["account"]).rename(columns=_RENAME_COLS),
        width="stretch",
        hide_index=True,
    )


def _render_totals(summary) -> None:
    total_value = summary["market_value"].sum(skipna=True)
    total_cost = summary["cost_basis"].sum(skipna=True)
    total_pl = total_value - total_cost
    total_pl_pct = (total_pl / total_cost * 100) if total_cost else None

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Value", f"${total_value:,.2f}")
    col2.metric(
        "Total Unrealized P&L", f"${total_pl:,.2f}", f"{total_pl_pct:+.1f}%" if total_pl_pct is not None else None
    )
    col3.metric("Positions", len(summary))


def _render_performance(account: str | None) -> None:
    performance = portfolio.get_portfolio_performance_by_timeframe(
        current_prices, price_history_lookup, user_id, account=account, risk_level=risk_filter
    )
    perf_cols = st.columns(4)
    for col, timeframe in zip(perf_cols, ["day", "week", "month", "year"]):
        result = performance.get(timeframe, {})
        change = result.get("change")
        change_pct = result.get("change_pct")
        if change is None:
            col.metric(timeframe.capitalize(), "N/A")
        else:
            col.metric(timeframe.capitalize(), f"${change:+,.2f}", f"{change_pct:+.1f}%")


overall_summary = portfolio.get_portfolio_summary(current_prices, user_id, risk_level=risk_filter)

st.subheader("All accounts combined")
_render_totals(overall_summary)

st.divider()

accounts = sorted(positions["account"].unique())
for account in accounts:
    st.subheader(account)
    account_summary = portfolio.get_portfolio_summary(current_prices, user_id, account=account, risk_level=risk_filter)

    st.markdown("**Open positions**")
    _render_positions_table(account_summary)
    _render_totals(account_summary)

    with st.expander("Performance by timeframe", icon=":material/trending_up:"):
        st.caption(
            "Each figure shows how this account's **currently-held** shares' total value has "
            "changed over that lookback window (1 trading day, ~5 trading days, ~21 trading days, "
            "~252 trading days), assuming today's exact quantities were held the whole time. "
            "**This is an approximation** -- if you bought a position partway through a window, "
            "the 'since' comparison won't exactly match your real cost basis for that period; for "
            "precise cost-basis P&L, use the Open Positions table above instead."
        )
        _render_performance(account)

    st.divider()

st.caption(config.DISCLAIMER)
