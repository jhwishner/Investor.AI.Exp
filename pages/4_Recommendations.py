"""Rule-based BUY / SELL / HOLD recommendations for your current paper positions.

Split into two subsections since the two kinds of holding are evaluated
differently:

  - Long-Term Holdings (Funds & ETFs): the same Day/Week/Month/Year signals
    PLUS a longer-term benchmark comparison against the S&P 500, since a
    diversified fund is best judged by whether it's keeping pace with the
    broad market over years, not by short-term technicals alone.
  - Individual Stocks: Day/Week/Month/Year signals only.

Every recommendation here is arithmetic over the same rules shown on the
Ticker Analysis page (trend, momentum, RSI) -- there is no AI model
generating this, and it is not personalized financial advice. It doesn't
know your taxes, fees, diversification goals, or risk tolerance.
"""

import streamlit as st

from investor_ai import (
    ai_assistant,
    benchmarks,
    breakout,
    config,
    data,
    factor_model,
    indicators,
    portfolio,
    recommendations,
    signals,
)
from live import enable_autorefresh, render_freshness_footer

user_id = st.session_state["user_id"]
enable_autorefresh(key="recommendations_autorefresh")
st.title("Recommendations")
render_freshness_footer()

# Tracks each ticker's last-seen action (BUY/SELL/HOLD/NO_DATA) across
# reruns -- including auto-refresh-triggered ones -- so we can flag when a
# position's call just changed since the last time this session saw it.
# Session-only: resets if the browser tab is closed or the app is restarted.
st.session_state.setdefault("previous_actions", {})

st.warning(
    "These are rule-based signals, not personalized financial advice. They're generated from "
    "fixed thresholds on trend and momentum indicators -- not an AI model, not a licensed advisor, "
    "and not aware of your taxes, fees, diversification goals, or risk tolerance. Always do your "
    "own research before acting."
)

portfolio.init_db()

risk_filter = st.selectbox("Filter by risk tag", options=["All"] + portfolio.list_risk_levels(user_id))
risk_filter = None if risk_filter == "All" else risk_filter

positions = portfolio.get_open_positions(user_id, risk_level=risk_filter)

if positions.empty:
    message = (
        "Your paper portfolio is empty. Head to **Manage Positions** to log a hypothetical trade first."
        if risk_filter is None
        else f"No open positions tagged **{risk_filter}**."
    )
    st.info(message)
    st.stop()

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()
    st.rerun()

current_prices = {t: data.get_current_price(t) for t in positions["ticker"]}
summary = portfolio.get_portfolio_summary(current_prices, user_id, risk_level=risk_filter)
total_value = summary["market_value"].sum(skipna=True)

# Generate portfolio summary for AI commentary
portfolio_summary_text = f"Portfolio with {len(positions)} positions (total value: ${total_value:,.0f}). "
portfolio_summary_text += "Holdings: " + ", ".join(positions["ticker"].tolist())

# Display AI Portfolio Summary with generated commentary (pass API key from secrets)
with st.expander("AI Portfolio Summary", icon=":material/auto_awesome:"):
    api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
    ai_summary = ai_assistant.generate_recommendation_summary(portfolio_summary_text, api_key=api_key)
    if ai_summary and "not configured" not in ai_summary.lower():
        st.markdown(ai_summary)
    else:
        st.info(ai_summary if ai_summary else "AI assistant is not yet configured. Set OPENAI_API_KEY or run a local Ollama model to enable this feature.")

_ACTION_STYLE = {
    "BUY": (st.success, "Consider adding"),
    "SELL": (st.warning, "Consider trimming"),
    "EXIT": (st.error, "Consider closing entirely"),
    "HOLD": (st.info, "Hold"),
    "NO_DATA": (st.info, "Not enough data"),
}


def render_position_card(row, fundamentals: dict, show_benchmark: bool) -> None:
    ticker = row["ticker"]
    quantity = row["quantity"]
    current_price = current_prices.get(ticker)
    market_value = row["market_value"]
    portfolio_share_pct = (market_value / total_value * 100) if total_value and market_value == market_value else None

    # Fund/ETF positions fetch a longer history (needed for the benchmark
    # comparison below); individual stocks use the app's normal 2y window.
    period = benchmarks.LONG_TERM_HISTORY_PERIOD if show_benchmark else config.DAILY_HISTORY_PERIOD
    daily_df = data.get_daily_history(ticker, period=period)

    week_signals = signals.build_week_signals(daily_df)
    month_signals = signals.build_month_signals(daily_df)
    year_signals = signals.build_year_signals(daily_df, fundamentals)

    # Computed before the recommendation, not just for the display block
    # below: a long-run lag against the benchmark is one of the things that
    # turns a trim into a close-it-out.
    comparison = {}
    if show_benchmark:
        benchmark_df = data.get_daily_history(
            benchmarks.BENCHMARK_TICKER, period=benchmarks.LONG_TERM_HISTORY_PERIOD
        )
        comparison = benchmarks.compare_to_benchmark(daily_df, benchmark_df)

    rec = recommendations.recommend_for_position(
        ticker, quantity, current_price, week_signals, month_signals, year_signals,
        portfolio_share_pct, benchmark=comparison,
    )

    previous_actions = st.session_state["previous_actions"]
    previous_action = previous_actions.get(ticker)
    changed = previous_action is not None and previous_action != rec.action
    previous_actions[ticker] = rec.action

    with st.container(border=True):
        header_col, action_col = st.columns([3, 2])
        with header_col:
            st.subheader(ticker)
            st.caption(f"{quantity:g} shares held @ avg cost ${row['avg_cost']:.2f}")
        with action_col:
            renderer, label = _ACTION_STYLE[rec.action]
            if rec.action == "EXIT":
                exit_text = f"**{label}** (all {quantity:g} shares"
                if rec.suggested_dollars is not None:
                    exit_text += f", ~${rec.suggested_dollars:,.2f}"
                renderer(exit_text + ")")
            elif rec.action in ("BUY", "SELL") and rec.suggested_pct is not None:
                shares_text = f" (~{rec.suggested_shares:g} shares"
                if rec.suggested_dollars is not None:
                    shares_text += f", ~${rec.suggested_dollars:,.2f}"
                shares_text += ")"
                renderer(f"**{label} ~{rec.suggested_pct:.0f}% of position**{shares_text}")
            else:
                renderer(f"**{label}**")
            if changed:
                prev_label = _ACTION_STYLE[previous_action][1]
                st.caption(f"\U0001F501 Changed from \"{prev_label}\" since your last check")

        st.markdown("**Day / Week / Month / Year signals:**")
        for reason in rec.rationale:
            st.markdown(f"- {reason}")

        if rec.context_notes:
            with st.expander("Additional context", icon=":material/info:"):
                for note in rec.context_notes:
                    st.markdown(f"- {note}")

        if show_benchmark:
            st.markdown(f"**Longer-term benchmark vs. {benchmarks.BENCHMARK_LABEL}:**")
            if not comparison:
                st.caption("Not enough long-term price history yet to compare against a benchmark.")
            else:
                years = comparison["years_covered"]
                fund_ann = comparison["fund_annualized_return"]
                bench_ann = comparison["benchmark_annualized_return"]
                outperf = comparison["outperformance_annualized_pct"]

                b1, b2, b3 = st.columns(3)
                b1.metric(f"{ticker} (annualized, ~{years:.1f}y)", f"{fund_ann:.1f}%" if fund_ann is not None else "N/A")
                b2.metric(f"{benchmarks.BENCHMARK_LABEL} (annualized)", f"{bench_ann:.1f}%" if bench_ann is not None else "N/A")
                b3.metric("Difference (annualized)", f"{outperf:+.1f} pts" if outperf is not None else "N/A")

                if outperf is not None:
                    if outperf >= 1.0:
                        st.caption(f"Outpacing the {benchmarks.BENCHMARK_LABEL} over this window.")
                    elif outperf <= -1.0:
                        st.caption(f"Lagging the {benchmarks.BENCHMARK_LABEL} over this window -- worth asking why you hold this vs. a plain index fund.")
                    else:
                        st.caption(f"Tracking roughly in line with the {benchmarks.BENCHMARK_LABEL} over this window.")


# --- Classify positions into fund/ETF vs. individual stock -----------------

fund_rows = []
stock_rows = []
fundamentals_by_ticker: dict[str, dict] = {}

for _, row in summary.iterrows():
    fundamentals = data.get_fundamentals(row["ticker"])
    fundamentals_by_ticker[row["ticker"]] = fundamentals
    if data.classify_asset_type(fundamentals) == "fund":
        fund_rows.append(row)
    else:
        stock_rows.append(row)

st.subheader("Long-Term Holdings (Funds & ETFs)")
st.caption(
    "Diversified holdings like ETFs, index funds, and mutual funds -- evaluated on the same "
    f"Day/Week/Month/Year signals below, plus how they've performed against the {benchmarks.BENCHMARK_LABEL} "
    "over the longer term."
)
if not fund_rows:
    st.caption("No fund/ETF/mutual fund positions detected in your current portfolio.")
else:
    for row in fund_rows:
        render_position_card(row, fundamentals_by_ticker[row["ticker"]], show_benchmark=True)

st.divider()

st.subheader("Individual Stocks")
st.caption("Single-company positions -- evaluated on Day/Week/Month/Year technical and momentum signals.")
if not stock_rows:
    st.caption("No individual stock positions detected in your current portfolio.")
else:
    for row in stock_rows:
        render_position_card(row, fundamentals_by_ticker[row["ticker"]], show_benchmark=False)

st.divider()

st.subheader("Suggested additions for this portfolio")
st.caption(
    "Highest-scoring names beyond your current holdings, using the same technical and factor rules as "
    "the rest of the recommendation page. This keeps the screener in context instead of forcing a separate "
    "screening step each time you want a fresh idea."
)

suggestions = recommendations.suggest_portfolio_additions(positions["ticker"].tolist(), max_candidates_per_category=5)
if not suggestions:
    st.caption("No strong additions are showing up right now based on your current holdings and the Market Movers list.")
else:
    _SCREENER_VERDICT_STYLE = {
        "BUY": st.success,
        "SELL": st.warning,
        "AVOID": st.warning,
        "HOLD": st.info,
        "NEUTRAL": st.info,
        "WATCH": st.info,
    }
    for result in suggestions[:8]:
        with st.container(border=True):
            header_col, verdict_col = st.columns([3, 2])
            with header_col:
                st.subheader(result["ticker"])
                detail_bits = []
                if result["beta"] is not None:
                    detail_bits.append(f"Beta {result['beta']:.2f}")
                if result["volatility"] is not None:
                    detail_bits.append(f"Volatility {result['volatility']:.0f}%/yr (annualized)")
                if result.get("breakout_score") is not None:
                    detail_bits.append(f"Breakout {result['breakout_score']:.0f}/100")
                if detail_bits:
                    st.caption(" | ".join(detail_bits))
            with verdict_col:
                _SCREENER_VERDICT_STYLE[result["verdict"]](
                    f"**{result['verdict']}** (score {result['combined_score']:+.1f})"
                )

            for reason in result["rationale"]:
                st.markdown(f"- {reason}")

            if result.get("breakout_rationale"):
                with st.expander(
                    f"Why the breakout score is {result['breakout_score']:.0f}", icon=":material/bolt:"
                ):
                    for reason in result["breakout_rationale"]:
                        st.markdown(f"- {reason}")
                    st.caption(
                        "Direction-agnostic: these conditions precede large moves either way. "
                        "A high score means 'worth reading the news on', not 'about to go up'."
                    )

st.divider()

st.subheader("Does the breakout score actually work?")
st.caption(
    "A walk-forward test on the same universe: at each historical date, score every ticker using "
    "only data available then, take the top 5, enter at the *next* bar's close, and hold. The "
    "comparison is against picking 5 tickers at random from the same universe -- so it measures "
    "the ranking, not the universe. Costs and slippage are not modelled."
)

backtest_col1, backtest_col2 = st.columns(2)
with backtest_col1:
    backtest_hold_days = st.number_input(
        "Holding period (trading days)", min_value=3, max_value=40, value=10, step=1
    )
with backtest_col2:
    backtest_big_move = st.number_input(
        "What counts as a big move (%)", min_value=3.0, max_value=40.0, value=10.0, step=1.0
    )

if st.button("Run backtest", icon=":material/science:"):
    held_tickers = set(positions["ticker"])
    universe = set(held_tickers)
    for category_key in data.MARKET_MOVER_CATEGORIES.values():
        movers_df = data.get_market_movers(category_key)
        if not movers_df.empty:
            universe.update(movers_df["ticker"].head(int(candidates_per_category)).tolist())

    with st.spinner(f"Replaying history for {len(universe)} tickers..."):
        histories = {t: data.get_daily_history(t) for t in sorted(universe)}
        backtest_result = breakout.backtest(
            histories,
            hold_days=int(backtest_hold_days),
            big_move_pct=float(backtest_big_move),
        )
    st.session_state["breakout_backtest"] = backtest_result

if "breakout_backtest" in st.session_state:
    result = st.session_state["breakout_backtest"]
    if result is None:
        st.warning(
            "Not enough shared price history across the universe to run a single window. "
            "Try again when more tickers have a couple of years of data."
        )
    else:
        st.caption(f"{result.picks} picks, {result.hold_days}-day holds.")

        big = result.big_move_pct
        row1 = st.columns(2)
        row1[0].metric("Screen -- average return", f"{result.model_mean_return_pct:+.2f}%")
        row1[1].metric(
            "Random pick -- average return",
            f"{result.random_mean_return_pct:+.2f}%",
            delta=f"{result.model_mean_return_pct - result.random_mean_return_pct:+.2f} pts vs screen",
            delta_color="off",
        )

        st.markdown("**Both tails, side by side:**")
        row2 = st.columns(4)
        row2[0].metric(f"Screen: gained ≥{big:.0f}%", f"{result.model_up_rate:.1%}")
        row2[1].metric(f"Screen: fell ≥{big:.0f}%", f"{result.model_down_rate:.1%}")
        row2[2].metric(f"Random: gained ≥{big:.0f}%", f"{result.random_up_rate:.1%}")
        row2[3].metric(f"Random: fell ≥{big:.0f}%", f"{result.random_down_rate:.1%}")

        row3 = st.columns(2)
        row3[0].metric(
            "Screen -- directional edge",
            f"{result.model_directional_edge:+.1%}",
            help="Large-gain rate minus large-loss rate. This, not the gain rate alone, is what "
            "would show the screen picks direction rather than merely picking volatility.",
        )
        row3[1].metric("Random -- directional edge", f"{result.random_directional_edge:+.1%}")

        st.info(result.verdict, icon=":material/balance:")
        st.caption(
            f"Worst single pick: {result.model_worst_pct:+.1f}%. "
            "One universe over one period is a small sample -- treat a positive result as a "
            "reason to test further, not as a validated edge."
        )

st.divider()
st.caption(config.DISCLAIMER)
