"""Power/AI-infrastructure sector watchlist and educational context.

Inspired by "Power 2026: Electricity Pricing in the Age of AI" (Neel Somani,
power2026.ai) -- a free primer on electricity markets and power trading,
whose central thesis is that AI data-center demand is a structural tailwind
for efficient natural-gas generation and grid infrastructure. See
investor_ai/power_sector.py for exactly what is (and isn't) implemented
from that book, and why.
"""

import pandas as pd
import streamlit as st

from investor_ai import config, data, indicators, power_sector, recommendations, signals
from live import enable_autorefresh, render_freshness_footer

enable_autorefresh(key="power_sector_autorefresh")
st.title("Power & AI Infrastructure")
render_freshness_footer()

st.caption(
    "A curated watchlist inspired by \"Power 2026: Electricity Pricing in the Age of AI\" (Neel "
    "Somani, power2026.ai) -- a free educational primer on electricity markets. That book's core "
    "thesis: AI data-center demand is a structural tailwind for efficient natural-gas generation "
    "and grid infrastructure. **This is a thematic watchlist, not a real electricity-market trading "
    "tool** -- the book's actual pricing math (spark spread, locational marginal price, basis "
    "trades) needs live electricity-market data with no free equivalent to yfinance. The one "
    "simplification below that free data does support: tracking Henry Hub natural gas futures as a "
    "rough margin proxy for gas-fired power producers."
)

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()
    st.rerun()

# --- Natural gas price context ------------------------------------------------

st.subheader("Natural gas price trend")

natgas_df = data.get_daily_history(config.NATGAS_TICKER)
if natgas_df.empty:
    st.warning("Couldn't fetch natural gas futures data right now.")
    natgas_direction, natgas_message = "neutral", None
else:
    close = natgas_df["Close"]
    current_price = float(close.iloc[-1])
    month_momentum = indicators.momentum(close, window=21)
    pct_change_month = (
        float(month_momentum.iloc[-1])
        if not month_momentum.empty and pd.notna(month_momentum.iloc[-1])
        else None
    )

    col1, col2 = st.columns(2)
    col1.metric("Henry Hub Natural Gas (NG=F)", f"${current_price:.2f}/MMBtu")
    col2.metric("~1-month change", f"{pct_change_month:+.1f}%" if pct_change_month is not None else "N/A")

    natgas_direction, natgas_message = power_sector.score_natural_gas_trend(pct_change_month)

_NATGAS_RENDERER = {"pressure": st.warning, "tailwind": st.success, "neutral": st.info}
if natgas_message:
    _NATGAS_RENDERER[natgas_direction](natgas_message)
else:
    st.caption("No notable monthly move in natural gas prices right now.")

with st.expander("Book concepts glossary", icon=":material/menu_book:"):
    for term, explanation in power_sector.BOOK_GLOSSARY.items():
        st.markdown(f"**{term.replace('_', ' ').title()}** -- {explanation}")

st.divider()

# --- Curated watchlist ---------------------------------------------------------

st.subheader("Watchlist")
st.caption(
    "Spans the parts of the AI-power supply chain the book discusses: regulated utilities, "
    "independent power producers, turbine manufacturers, natural gas producers, and data-center "
    "power/hosting plays. Not exhaustive, and not a recommendation to buy any of these -- "
    "informational signals only, using the same rule-based trend/momentum engine as the rest of "
    "this app."
)

_SIGNAL_RENDERER = {"bullish": st.success, "bearish": st.warning, "neutral": st.info}

for entry in power_sector.POWER_SECTOR_WATCHLIST:
    ticker = entry["ticker"]
    daily_df = data.get_daily_history(ticker)
    if daily_df.empty:
        continue
    fundamentals = data.get_fundamentals(ticker)
    week_signals = signals.build_week_signals(daily_df)
    month_signals = signals.build_month_signals(daily_df)
    year_signals = signals.build_year_signals(daily_df, fundamentals)

    tech_score, tech_rationale, _ = recommendations.score_technical(week_signals, month_signals, year_signals)
    if tech_score >= 1.5:
        overall = "bullish"
    elif tech_score <= -1.5:
        overall = "bearish"
    else:
        overall = "neutral"

    with st.container(border=True):
        header_col, signal_col = st.columns([3, 2])
        with header_col:
            st.subheader(f"{ticker} -- {fundamentals.get('long_name') or ticker}")
            st.caption(entry["category"])
        with signal_col:
            _SIGNAL_RENDERER[overall](f"**Signals: {overall.capitalize()}** (score {tech_score:+.1f})")

        for reason in tech_rationale:
            st.markdown(f"- {reason}")
        if not tech_rationale:
            st.caption("No strong trend or momentum signals in either direction right now.")

        if entry["gas_exposed"] and natgas_message:
            st.markdown(f"- {natgas_message}")

st.divider()
st.caption(config.DISCLAIMER)
