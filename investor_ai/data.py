"""Market data fetch layer.

All functions here are defensive by design: yfinance can raise a wide variety
of network/HTTP/JSON errors (especially under Yahoo rate limiting), and can
also return an empty or partially-populated result without raising anything
at all. Every public function in this module therefore:

  - never raises -- callers always get back a well-defined "empty" result
    (empty DataFrame, empty dict, or a (False, message) tuple) on any failure
  - logs the underlying exception to logs/app.log for debugging
  - is wrapped in @st.cache_data so Streamlit's rerun-on-every-interaction
    behavior doesn't hammer Yahoo Finance with duplicate requests

Callers (UI pages) must treat an empty result as "no data available right
now" and must never render it as if it were a real, current value.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

from investor_ai import config

logging.basicConfig(
    filename=str(config.LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching price history...")
def get_daily_history(ticker: str, period: str = config.DAILY_HISTORY_PERIOD) -> pd.DataFrame:
    """Daily OHLCV history for a ticker.

    Reused by the Week/Month/Year timeframes via slicing so we only issue
    one network call per ticker per cache window, rather than one per
    timeframe. Returns an empty DataFrame (never raises) on any failure.
    """
    try:
        df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            logger.warning("get_daily_history(%s): empty result", ticker)
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        logger.exception("get_daily_history(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_INTRADAY, show_spinner="Fetching intraday data...")
def get_intraday_history(
    ticker: str,
    period: str = config.INTRADAY_HISTORY_PERIOD,
    interval: str = config.INTRADAY_HISTORY_INTERVAL,
) -> pd.DataFrame:
    """Intraday bars, used only for the Day timeframe's volume/momentum signals."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            logger.warning("get_intraday_history(%s): empty result", ticker)
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        logger.exception("get_intraday_history(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_FUNDAMENTALS, show_spinner="Fetching fundamentals...")
def get_fundamentals(ticker: str) -> dict:
    """Safe subset of yfinance's `.info` dict.

    yfinance's `.info` shape varies a lot by ticker (ETFs, indices, and
    foreign listings are often missing several keys) -- every field is read
    with `.get(..., None)` so a missing key never raises or silently
    produces a wrong-looking default like 0.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        logger.exception("get_fundamentals(%s) failed", ticker)
        return {}

    if not info:
        return {}

    return {
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "price_to_book": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "long_name": info.get("longName") or info.get("shortName"),
        "currency": info.get("currency"),
        "quote_type": info.get("quoteType"),
    }


_FUND_QUOTE_TYPES = {"ETF", "MUTUALFUND", "INDEX"}


def classify_asset_type(fundamentals: dict) -> str:
    """Buckets a position as 'fund' (ETF/mutual fund/index) or 'stock' (everything
    else, including when the type can't be determined).

    Pure function over an already-fetched fundamentals dict -- no I/O -- so it's
    independently testable and doesn't cost an extra network call.
    """
    quote_type = (fundamentals.get("quote_type") or "").upper()
    return "fund" if quote_type in _FUND_QUOTE_TYPES else "stock"


def validate_ticker(ticker: str) -> tuple[bool, str]:
    """Cheap existence check before a position can be logged.

    Not cached -- this is called on form submission, and we want a fresh
    answer rather than a stale "invalid" verdict for a ticker that just
    started trading.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return False, "Enter a ticker symbol."
    try:
        df = yf.Ticker(ticker).history(period="5d", interval="1d")
        if df is None or df.empty:
            return False, f"Couldn't find any recent price data for '{ticker}'. Check the symbol."
        return True, ""
    except Exception:
        logger.exception("validate_ticker(%s) failed", ticker)
        return False, f"Couldn't verify '{ticker}' right now (network or data issue). Try again shortly."


def get_current_price(ticker: str) -> float | None:
    """Most recent close price available, or None if unavailable.

    Built on top of get_daily_history (cached) rather than a separate
    network call, so callers can freely call this per-row in a table
    without multiplying network requests.
    """
    df = get_daily_history(ticker)
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


@st.cache_data(ttl=config.CACHE_TTL_INTRADAY, show_spinner="Fetching news...")
def get_news(ticker: str, limit: int = 8) -> list[dict]:
    """Recent headlines for a ticker via yfinance's `Ticker.news` (sourced from
    Yahoo Finance, free, no API key). This is an unofficial/undocumented
    endpoint on Yahoo's side -- like the rest of this module, any failure or
    shape change just yields an empty list rather than raising.

    Returns a list of {"title", "publisher", "link", "published"} dicts,
    newest first, already trimmed to `limit`.
    """
    try:
        raw_items = yf.Ticker(ticker).news or []
    except Exception:
        logger.exception("get_news(%s) failed", ticker)
        return []

    items = []
    for raw in raw_items[:limit]:
        content = raw.get("content", raw)  # yfinance has nested "content" in newer payloads
        title = content.get("title")
        if not title:
            continue
        link = (content.get("canonicalUrl") or content.get("clickThroughUrl") or {}).get("url")
        publisher = (content.get("provider") or {}).get("displayName")
        items.append(
            {
                "title": title,
                "publisher": publisher,
                "link": link,
                "published": content.get("pubDate"),
            }
        )
    return items


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching financial statements...")
def get_income_statement(ticker: str) -> pd.DataFrame:
    """Annual income statement (revenue, net income, EBITDA, etc.), free via
    yfinance. Empty DataFrame on any failure or if the ticker doesn't
    publish one (e.g. most ETFs/funds)."""
    try:
        df = yf.Ticker(ticker).income_stmt
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_income_statement(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching financial statements...")
def get_balance_sheet(ticker: str) -> pd.DataFrame:
    """Annual balance sheet (assets, liabilities, equity), free via yfinance."""
    try:
        df = yf.Ticker(ticker).balance_sheet
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_balance_sheet(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching financial statements...")
def get_cashflow(ticker: str) -> pd.DataFrame:
    """Annual cash flow statement, free via yfinance."""
    try:
        df = yf.Ticker(ticker).cashflow
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_cashflow(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching earnings history...")
def get_earnings_history(ticker: str) -> pd.DataFrame:
    """Past and next-scheduled EPS estimate vs. actual, free via yfinance
    (requires the `lxml` package -- see requirements.txt)."""
    try:
        df = yf.Ticker(ticker).earnings_dates
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_earnings_history(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching insider activity...")
def get_insider_transactions(ticker: str) -> pd.DataFrame:
    """Recent insider (officer/director) buy/sell transactions, free via
    yfinance/Yahoo Finance. Empty if unavailable for this ticker (common for
    ETFs/funds, which have no "insiders")."""
    try:
        df = yf.Ticker(ticker).insider_transactions
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_insider_transactions(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching institutional holders...")
def get_institutional_holders(ticker: str) -> pd.DataFrame:
    """Top institutional holders (funds, asset managers) and their stakes,
    free via yfinance/Yahoo Finance."""
    try:
        df = yf.Ticker(ticker).institutional_holders
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_institutional_holders(%s) failed", ticker)
        return pd.DataFrame()


@st.cache_data(ttl=config.CACHE_TTL_DAILY, show_spinner="Fetching ownership breakdown...")
def get_major_holders(ticker: str) -> pd.DataFrame:
    """Insider/institution ownership percentages, free via yfinance."""
    try:
        df = yf.Ticker(ticker).major_holders
        return df if df is not None else pd.DataFrame()
    except Exception:
        logger.exception("get_major_holders(%s) failed", ticker)
        return pd.DataFrame()


MARKET_MOVER_CATEGORIES = {
    "Top Gainers": "day_gainers",
    "Top Losers": "day_losers",
    "Most Active": "most_actives",
}


@st.cache_data(ttl=config.CACHE_TTL_INTRADAY, show_spinner="Fetching market movers...")
def get_market_movers(category: str, count: int = 25) -> pd.DataFrame:
    """A market-wide snapshot (not tied to your portfolio) via yfinance's
    screener, which calls the same public endpoint Yahoo Finance's own
    gainers/losers/most-active pages use -- free, no API key, but
    unofficial/undocumented, so treat it the same as any other yfinance data:
    it can go empty or change shape without warning.

    `category` must be one of MARKET_MOVER_CATEGORIES's values
    ("day_gainers", "day_losers", "most_actives"). Returns an empty
    DataFrame on any failure.
    """
    try:
        result = yf.screen(category, count=count)
        quotes = (result or {}).get("quotes") or []
        if not quotes:
            return pd.DataFrame()
        rows = [
            {
                "ticker": q.get("symbol"),
                "name": q.get("shortName") or q.get("longName"),
                "price": q.get("regularMarketPrice"),
                "change": q.get("regularMarketChange"),
                "change_pct": q.get("regularMarketChangePercent"),
                "volume": q.get("regularMarketVolume"),
                "market_cap": q.get("marketCap"),
                # Already present on the screener's quote payload when Yahoo
                # has it -- no extra per-ticker fetch needed to surface it.
                "beta": q.get("beta"),
            }
            for q in quotes
        ]
        return pd.DataFrame(rows)
    except Exception:
        logger.exception("get_market_movers(%s) failed", category)
        return pd.DataFrame()


def data_freshness_badge(df: pd.DataFrame) -> tuple[str, str]:
    """Returns (status, message) for the "Data as of ..." UI badge.

    status is one of "ok", "stale", "unavailable" -- callers map this to a
    color (green/yellow/red). This never guesses; it only describes what the
    DataFrame actually contains.
    """
    if df is None or df.empty:
        return "unavailable", "No data available right now."
    last_ts = df.index[-1]
    if hasattr(last_ts, "to_pydatetime"):
        last_ts = last_ts.to_pydatetime()
    age = datetime.now(last_ts.tzinfo) - last_ts if last_ts.tzinfo else datetime.now() - last_ts
    if age.days > 5:
        return "stale", f"Data as of {last_ts:%Y-%m-%d} -- may be several days old."
    return "ok", f"Data as of {last_ts:%Y-%m-%d %H:%M}"
