"""Single-ticker deep dive across Day / Week / Month / Year timeframes."""

import pandas as pd
import streamlit as st

from investor_ai import ai_assistant, config, data, indicators, portfolio, rules, sentiment, signals, templates
from live import enable_autorefresh, render_freshness_footer

user_id = st.session_state["user_id"]
enable_autorefresh(key="ticker_analysis_autorefresh")
st.title("Ticker Analysis")
render_freshness_footer()

_SEVERITY_TO_ST = {
    "bullish": st.success,
    "bearish": st.warning,
    "info": st.info,
    "neutral": st.info,
}


def render_rule_commentary(timeframe: str, signal_dict: dict) -> None:
    if not signal_dict:
        st.warning("Not enough price history to compute signals for this timeframe yet.")
        return

    triggered = rules.evaluate_rules(timeframe, signal_dict)
    if not triggered:
        st.info("No specific signals triggered for this timeframe right now.")
        return

    for t in triggered:
        renderer = _SEVERITY_TO_ST.get(t.severity, st.info)
        renderer(t.message)
        with st.expander("What does this mean?", icon=":material/help:"):
            st.markdown(templates.EXPLANATIONS.get(t.explanation_key, "No explanation available."))


# --- Ticker picker -----------------------------------------------------------

portfolio.init_db()
portfolio_tickers = sorted(portfolio.get_open_positions(user_id)["ticker"].tolist())

col1, col2 = st.columns([2, 1])
with col1:
    typed_ticker = st.text_input("Look up any ticker", placeholder="e.g. AAPL, MSFT, SPY").strip().upper()
with col2:
    picked_ticker = st.selectbox("...or pick from your portfolio", options=[""] + portfolio_tickers)

ticker = typed_ticker or picked_ticker

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()
    st.rerun()

if not ticker:
    st.stop()

is_valid, message = data.validate_ticker(ticker)
if not is_valid:
    st.error(message)
    st.stop()

daily_df = data.get_daily_history(ticker)
fundamentals = data.get_fundamentals(ticker)

status, freshness_message = data.data_freshness_badge(daily_df)
badge = {"ok": st.success, "stale": st.warning, "unavailable": st.error}[status]
badge(freshness_message)

if daily_df.empty:
    st.stop()

st.subheader(fundamentals.get("long_name") or ticker)

_SENTIMENT_TAG = {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral"}
_SENTIMENT_RENDERER = {"bullish": st.success, "bearish": st.warning, "neutral": st.info}

with st.expander("Recent news & sentiment", icon=":material/newspaper:"):
    news_items = data.get_news(ticker)
    if not news_items:
        st.caption("No recent news found for this ticker.")
    else:
        headlines = [item["title"] for item in news_items]
        news_summary = sentiment.summarize_sentiment(headlines)
        _SENTIMENT_RENDERER[news_summary["overall"]](
            f"Overall headline tone: **{_SENTIMENT_TAG[news_summary['overall']]}** "
            f"({news_summary['bullish']} bullish / {news_summary['neutral']} neutral / "
            f"{news_summary['bearish']} bearish of {len(headlines)} recent headlines)"
        )
        for item in news_items:
            label, _ = sentiment.score_headline(item["title"])
            st.markdown(f"**[{_SENTIMENT_TAG[label]}]** {item['title']}")
            source_line = item.get("publisher") or "Unknown source"
            if item.get("link"):
                st.caption(f"{source_line} -- [Read more]({item['link']})")
            else:
                st.caption(source_line)
        with st.expander("What does this mean?", icon=":material/help:"):
            st.markdown(
                "Each headline is scanned for a fixed list of bullish words (e.g. \"beats\", "
                "\"surges\", \"upgrade\") and bearish words (e.g. \"misses\", \"plunges\", "
                "\"downgrade\"). **This is not AI-generated sentiment** -- it's simple keyword "
                "matching, the same rule-based approach as the rest of this app's commentary. "
                "Treat it as a rough at-a-glance signal, not a substitute for reading the actual "
                "articles."
            )

tab_day, tab_week, tab_month, tab_year = st.tabs(["Day", "Week", "Month", "Year"])

with tab_day:
    intraday_df = data.get_intraday_history(ticker)
    if intraday_df.empty:
        st.warning("Intraday data isn't available for this ticker right now (markets may be closed).")
    else:
        st.line_chart(intraday_df["Close"])
        day_signals = signals.build_day_signals(intraday_df, daily_df)
        render_rule_commentary("day", day_signals)

with tab_week:
    week_close = daily_df["Close"].tail(60)
    sma10 = indicators.sma(daily_df["Close"], config.SMA_SHORT).tail(60)
    chart_df = pd.DataFrame({"Close": week_close, "SMA(10)": sma10})
    st.line_chart(chart_df)

    rsi_series = indicators.rsi(daily_df["Close"]).tail(60)
    st.caption("RSI(14)")
    st.line_chart(rsi_series)

    week_signals = signals.build_week_signals(daily_df)
    render_rule_commentary("week", week_signals)

with tab_month:
    month_close = daily_df["Close"].tail(120)
    sma50 = indicators.sma(daily_df["Close"], config.SMA_MEDIUM).tail(120)
    bb_upper, bb_mid, bb_lower = indicators.bollinger_bands(daily_df["Close"])
    chart_df = pd.DataFrame(
        {
            "Close": month_close,
            "SMA(50)": sma50,
            "BB Upper": bb_upper.tail(120),
            "BB Lower": bb_lower.tail(120),
        }
    )
    st.line_chart(chart_df)

    macd_line, macd_signal_line, macd_hist = indicators.macd(daily_df["Close"])
    st.caption("MACD line vs. signal line")
    st.line_chart(pd.DataFrame({"MACD": macd_line.tail(120), "Signal": macd_signal_line.tail(120)}))

    month_signals = signals.build_month_signals(daily_df)
    render_rule_commentary("month", month_signals)

with tab_year:
    sma200 = indicators.sma(daily_df["Close"], config.SMA_LONG)
    chart_df = pd.DataFrame({"Close": daily_df["Close"], "SMA(200)": sma200})
    st.line_chart(chart_df)

    year_signals = signals.build_year_signals(daily_df, fundamentals)
    render_rule_commentary("year", year_signals)

    st.subheader("Fundamentals")
    fcol1, fcol2, fcol3 = st.columns(3)
    fcol1.metric("Trailing P/E", f"{fundamentals.get('trailing_pe'):.1f}" if fundamentals.get("trailing_pe") else "N/A")
    dy = fundamentals.get("dividend_yield")
    fcol2.metric("Dividend Yield", f"{dy * 100:.2f}%" if dy else "N/A")
    fcol3.metric("Beta", f"{fundamentals.get('beta'):.2f}" if fundamentals.get("beta") else "N/A")
    st.caption(f"Sector: {fundamentals.get('sector') or 'N/A'}  |  Industry: {fundamentals.get('industry') or 'N/A'}")

    # AI-generated market commentary
    with st.expander("AI Commentary", icon=":material/auto_awesome:"):
        # Build market context from latest signals
        market_context_parts = []
        latest_close = daily_df["Close"].iloc[-1] if not daily_df.empty else None
        prev_close = daily_df["Close"].iloc[-2] if len(daily_df) > 1 else None
        if latest_close and prev_close:
            pct_change = ((latest_close - prev_close) / prev_close) * 100
            market_context_parts.append(f"Latest price: ${latest_close:.2f} ({pct_change:+.2f}%)")
        
        # Add signal summary from the year tab
        year_signals = signals.build_year_signals(daily_df, fundamentals)
        if year_signals:
            triggered = rules.evaluate_rules("year", year_signals)
            if triggered:
                signal_summary = "; ".join([t.message for t in triggered[:3]])
                market_context_parts.append(f"Signals: {signal_summary}")
        
        market_context = " | ".join(market_context_parts) if market_context_parts else "Market analysis in progress."
        
        # Generate and display AI commentary (pass API key from secrets)
        api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
        commentary = ai_assistant.generate_market_commentary(ticker, market_context, api_key=api_key)
        if commentary and "not configured" not in commentary.lower():
            st.markdown(commentary)
        else:
            st.info(commentary if commentary else "AI assistant is not yet configured. Set OPENAI_API_KEY or run a local Ollama model to enable this feature.")

    with st.expander("Financial statements (annual)", icon=":material/description:"):
        income_stmt = data.get_income_statement(ticker)
        balance_sheet = data.get_balance_sheet(ticker)
        cashflow = data.get_cashflow(ticker)

        if income_stmt.empty and balance_sheet.empty and cashflow.empty:
            st.caption(
                "No financial statements available for this ticker "
                "(common for ETFs, mutual funds, and indices)."
            )
        else:
            fin_tab1, fin_tab2, fin_tab3 = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])
            with fin_tab1:
                st.dataframe(income_stmt, width="stretch") if not income_stmt.empty else st.caption("Not available.")
            with fin_tab2:
                st.dataframe(balance_sheet, width="stretch") if not balance_sheet.empty else st.caption("Not available.")
            with fin_tab3:
                st.dataframe(cashflow, width="stretch") if not cashflow.empty else st.caption("Not available.")

    with st.expander("Earnings history", icon=":material/calendar_today:"):
        earnings_history = data.get_earnings_history(ticker)
        if earnings_history.empty:
            st.caption("No earnings history available for this ticker.")
        else:
            st.dataframe(earnings_history, width="stretch")

    with st.expander("Ownership: insiders & institutions", icon=":material/groups:"):
        major_holders = data.get_major_holders(ticker)
        institutional_holders = data.get_institutional_holders(ticker)
        insider_transactions = data.get_insider_transactions(ticker)

        if major_holders.empty and institutional_holders.empty and insider_transactions.empty:
            st.caption(
                "No ownership data available for this ticker (common for ETFs, mutual funds, "
                "and indices)."
            )
        else:
            if not major_holders.empty:
                st.caption("Ownership breakdown")
                st.dataframe(major_holders, width="stretch")
            if not institutional_holders.empty:
                st.caption("Top institutional holders")
                st.dataframe(institutional_holders, width="stretch")
            if not insider_transactions.empty:
                st.caption("Recent insider transactions")
                display_cols = [
                    c
                    for c in ["Start Date", "Insider", "Position", "Text", "Shares", "Value", "Ownership"]
                    if c in insider_transactions.columns
                ]
                st.dataframe(insider_transactions[display_cols], width="stretch", hide_index=True)

st.divider()
st.caption(config.DISCLAIMER)
