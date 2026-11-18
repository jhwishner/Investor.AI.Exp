"""Home: a dashboard of the user's current state, not a description of the app.

Design intent -- this page is opened repeatedly by someone who already knows
what the tool is, so it leads with their numbers and recent activity. The
"what is this" prose lives in a collapsed expander at the bottom: available
on demand, not re-read every visit.

Form choices follow the data's job rather than habit: headline figures are
stat tiles (a single value + delta), per-holding trend is a sparkline
(shape, not precise reading), and holdings are a table because seven-plus
rows each carrying meaning is a table's job, not a chart's.

Cost note: sparklines and the day/week performance figures reuse the same
cached daily history that pricing already needs, so the extra visual
density costs one additional network call (market movers), not one per
holding.
"""

from datetime import datetime

import streamlit as st

import wordmark_ivy
from investor_ai import config, data, portfolio

user_id = st.session_state["user_id"]
username = st.session_state.get("username", "")

portfolio.init_db()
positions = portfolio.get_open_positions(user_id)

SPARKLINE_DAYS = 30


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


# --- Hero --------------------------------------------------------------------
# Keyed so theme.py can style the title and fade the whole block out as it
# scrolls away, leaving the dashboard below.

# Site name top-left, like a masthead.
with st.container(key="ivy_brand"):
    st.markdown("<h1>Ivy Investments</h1>", unsafe_allow_html=True)

with st.container(key="ivy_hero"):
    # The greeting is the hero: composed server-side (type + ivy in one
    # image) rather than layered in the browser, because the vines are
    # positioned against measured glyph geometry and any drift between what
    # was measured and how the browser lays the text out would put them in
    # the wrong places. Real text is kept for screen readers.
    _greeting_text = f"{_greeting()}, {username}." if username else f"{_greeting()}."
    st.markdown(f'<p class="sr-only">{_greeting_text}</p>', unsafe_allow_html=True)

    with st.container(key="ivy_greeting"):
        _greet_png, _ = wordmark_ivy.hero_asset(_greeting_text, seed="greet", runners=4, scale=1.45)
        st.image(str(wordmark_ivy.STATIC_DIR / _greet_png), width="stretch")

    st.markdown('<p class="ivy-sub">Ivy Investments</p>', unsafe_allow_html=True)

    # Assets are content-hashed, so a text change orphans the old render.
    # Prune anything not currently referenced rather than letting static/
    # accumulate.
    wordmark_ivy._prune_stale_assets({_greet_png})

    with st.container(key="ivy_scrollcue"):
        st.caption("Scroll to enter")


# --- Empty state -------------------------------------------------------------

if positions.empty:
    st.space("small")
    with st.container(border=True):
        st.subheader("Your paper portfolio is empty")
        st.markdown(
            "Log a hypothetical trade and this page becomes your dashboard -- holdings, "
            "performance, and what changed since you last looked. Nothing here places a real "
            "trade or connects to a brokerage."
        )
        st.space("small")
        with st.container(horizontal=True):
            st.page_link(
                "pages/3_Manage_Positions.py",
                label="**Log your first trade**",
                icon=":material/edit_note:",
            )
            st.page_link(
                "pages/2_Ticker_Analysis.py",
                label="Look up a ticker first",
                icon=":material/query_stats:",
            )
    st.space("medium")
    st.caption(config.DISCLAIMER)
    st.stop()


# --- Data (one cached fetch per held ticker, reused throughout) ---------------

tickers = sorted(positions["ticker"].unique())
history = {t: data.get_daily_history(t) for t in tickers}
closes = {t: df["Close"] for t, df in history.items() if not df.empty}
current_prices = {t: (float(s.iloc[-1]) if not s.empty else None) for t, s in closes.items()}
for t in tickers:
    current_prices.setdefault(t, None)

summary = portfolio.get_portfolio_summary(current_prices, user_id)
performance = portfolio.get_portfolio_performance_by_timeframe(current_prices, closes, user_id)

total_value = summary["market_value"].sum(skipna=True)
total_cost = summary["cost_basis"].sum(skipna=True)
total_pl = total_value - total_cost
total_pl_pct = (total_pl / total_cost * 100) if total_cost else None

day = performance.get("day", {})
week = performance.get("week", {})


def _money(value) -> str:
    return f"${value:,.2f}" if value == value else "N/A"   # NaN-safe


# --- Headline stat tiles -----------------------------------------------------
# Each dashboard block is wrapped in a container keyed "reveal_*", which
# theme.py animates in as it scrolls into view.

with st.container(key="reveal_kpi"):
    st.caption(f"Paper portfolio &middot; as of {datetime.now():%b %d, %-I:%M %p}")
    kpi = st.columns(4)
    kpi[0].metric("Portfolio value", _money(total_value))
    kpi[1].metric(
        "Today",
        f"{day['change']:+,.2f}" if day.get("change") is not None else "N/A",
        f"{day['change_pct']:+.2f}%" if day.get("change_pct") is not None else None,
    )
    kpi[2].metric(
        "Unrealized P&L",
        _money(total_pl),
        f"{total_pl_pct:+.1f}%" if total_pl_pct is not None else None,
    )
    kpi[3].metric(
        "This week",
        f"{week['change']:+,.2f}" if week.get("change") is not None else "N/A",
        f"{week['change_pct']:+.2f}%" if week.get("change_pct") is not None else None,
    )

st.space("small")


# --- Holdings, with a 30-day sparkline per row -------------------------------

with st.container(key="reveal_holdings"):
    st.subheader("Your holdings")

    holdings = summary.copy()
    holdings["trend"] = holdings["ticker"].map(
        lambda t: closes[t].tail(SPARKLINE_DAYS).tolist() if t in closes else []
    )
    holdings = holdings.sort_values("market_value", ascending=False, na_position="last")

    st.dataframe(
        holdings[
            ["ticker", "trend", "account", "risk_level", "quantity",
             "avg_cost", "current_price", "market_value", "unrealized_pl", "unrealized_pl_pct"]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", pinned=True),
            "trend": st.column_config.LineChartColumn(f"{SPARKLINE_DAYS}-day trend", width="small"),
            "account": st.column_config.TextColumn("Account"),
            "risk_level": st.column_config.TextColumn("Risk tag"),
            "quantity": st.column_config.NumberColumn("Qty", format="%.4g"),
            "avg_cost": st.column_config.NumberColumn("Avg cost", format="$%.2f"),
            "current_price": st.column_config.NumberColumn("Price", format="$%.2f"),
            "market_value": st.column_config.NumberColumn("Value", format="$%.2f"),
            "unrealized_pl": st.column_config.NumberColumn("P&L", format="$%+.2f"),
            "unrealized_pl_pct": st.column_config.NumberColumn("P&L %", format="%+.1f%%"),
        },
    )

    missing = [t for t, price in current_prices.items() if price is None]
    if missing:
        st.caption(f"No current price available for {', '.join(missing)} -- those rows show as N/A.")

st.space("small")


# --- Recent activity + market snapshot ---------------------------------------

reveal_lower = st.container(key="reveal_activity")
activity_col, market_col = reveal_lower.columns(2)

with activity_col:
    st.subheader("Recent activity")
    transactions = portfolio.list_transactions(user_id).head(6)
    if transactions.empty:
        st.caption("No transactions logged yet.")
    else:
        with st.container(border=True):
            for _, tx in transactions.iterrows():
                icon = ":material/trending_up:" if tx["action"] == "BUY" else ":material/trending_down:"
                st.markdown(
                    f"{icon} **{tx['action']} {tx['quantity']:g} {tx['ticker']}** "
                    f"@ ${tx['price']:,.2f}"
                )
                st.caption(f"{tx['trade_date']} &middot; {tx['account']}")
    st.page_link(
        "pages/3_Manage_Positions.py", label="Log a trade", icon=":material/add:"
    )

with market_col:
    st.subheader("Market today")
    movers = data.get_market_movers(data.MARKET_MOVER_CATEGORIES["Top Gainers"])
    if movers.empty:
        st.caption("Market movers aren't available right now.")
    else:
        with st.container(border=True):
            st.caption("Top gainers")
            st.dataframe(
                movers[["ticker", "price", "change_pct"]].head(5),
                width="stretch",
                hide_index=True,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker"),
                    "price": st.column_config.NumberColumn("Price", format="$%.2f"),
                    "change_pct": st.column_config.NumberColumn("Change", format="%+.2f%%"),
                },
            )
    st.page_link(
        "pages/5_Market_Movers.py", label="See all movers", icon=":material/trending_up:"
    )

st.space("small")


# --- Quick actions ------------------------------------------------------------

with st.container(key="reveal_actions"):
    st.subheader("Jump back in")
    with st.container(horizontal=True):
        st.page_link("pages/2_Ticker_Analysis.py", label="Analyze a ticker", icon=":material/query_stats:")
        st.page_link("pages/4_Recommendations.py", label="Recommendations", icon=":material/lightbulb:")
        st.page_link("pages/1_Portfolio.py", label="Full portfolio", icon=":material/account_balance_wallet:")
        st.page_link("pages/6_Power_and_AI_Infrastructure.py", label="Power & AI watchlist", icon=":material/bolt:")

st.space("medium")

with st.expander("About this tool", icon=":material/info:"):
    st.markdown(
        "A **paper-trading research tool**: it fetches free market data, computes standard "
        "quantitative signals (moving averages, RSI, MACD, volatility, valuation ratios, and "
        "more), and turns those signals into plain-English commentary using fixed rules -- "
        "**no AI-generated text, no external API calls**. Every explanation you see is a "
        "template filled in with real numbers, so you can always trace a statement back to the "
        "exact rule and threshold that produced it.\n\n"
        "Nothing here places a real trade or connects to a brokerage. Positions are hypothetical "
        "and stored locally."
    )

st.caption(config.DISCLAIMER)
