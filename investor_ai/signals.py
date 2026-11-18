"""Combines data.py + indicators.py into the per-timeframe signal dicts
consumed by rules.evaluate_rules(...).

This is the glue layer between "raw price history" and "named numbers a
rule can check a threshold against." Kept separate from both data.py (fetch)
and rules.py (thresholds/wording) so each stays focused and testable.
"""

from __future__ import annotations

import pandas as pd

from investor_ai import config, indicators


def build_day_signals(intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> dict:
    """Signals for the Day timeframe.

    Uses intraday bars for the current price/volume and the prior daily
    close for the day-over-day % change, since intraday history alone
    doesn't reliably include yesterday's official close.
    """
    if intraday_df.empty or daily_df.empty or len(daily_df) < 2:
        return {}

    current_price = float(intraday_df["Close"].iloc[-1])
    prior_close = float(daily_df["Close"].iloc[-2])
    pct_change = (current_price - prior_close) / prior_close * 100 if prior_close else None

    vol_ratio_series = indicators.volume_ratio(intraday_df["Volume"], window=min(config.VOLUME_AVG_WINDOW, len(intraday_df)))
    volume_ratio = float(vol_ratio_series.iloc[-1]) if not vol_ratio_series.empty and pd.notna(vol_ratio_series.iloc[-1]) else None

    return {
        "current_price": current_price,
        "pct_change": pct_change,
        "volume_ratio": volume_ratio,
    }


def build_week_signals(daily_df: pd.DataFrame) -> dict:
    """Signals for the Week timeframe, sliced from the shared daily history."""
    if daily_df.empty or len(daily_df) < config.RSI_WINDOW + 1:
        return {}

    close = daily_df["Close"]
    rsi_series = indicators.rsi(close, window=config.RSI_WINDOW)
    sma10_series = indicators.sma(close, window=config.SMA_SHORT)
    mom5_series = indicators.momentum(close, window=5)
    mom10_series = indicators.momentum(close, window=10)

    def last_valid(series: pd.Series) -> float | None:
        return float(series.iloc[-1]) if not series.empty and pd.notna(series.iloc[-1]) else None

    return {
        "price": float(close.iloc[-1]),
        "rsi_14": last_valid(rsi_series),
        "sma_10": last_valid(sma10_series),
        "momentum_5d": last_valid(mom5_series),
        "momentum_10d": last_valid(mom10_series),
    }


def build_month_signals(daily_df: pd.DataFrame) -> dict:
    """Signals for the Month timeframe, sliced from the shared daily history."""
    if daily_df.empty or len(daily_df) < config.SMA_MEDIUM:
        return {}

    close = daily_df["Close"]
    sma50_series = indicators.sma(close, window=config.SMA_MEDIUM)
    macd_line, macd_signal, macd_hist = indicators.macd(close)
    bb_upper, bb_mid, bb_lower = indicators.bollinger_bands(close)

    def last_valid(series: pd.Series, offset: int = 0) -> float | None:
        idx = -1 - offset
        if len(series) <= abs(idx) - 1 or pd.isna(series.iloc[idx]):
            return None
        return float(series.iloc[idx])

    return {
        "price": float(close.iloc[-1]),
        "sma_50": last_valid(sma50_series),
        "macd_histogram": last_valid(macd_hist),
        "macd_histogram_prev": last_valid(macd_hist, offset=1),
        "bb_upper": last_valid(bb_upper),
        "bb_lower": last_valid(bb_lower),
    }


def build_year_signals(daily_df: pd.DataFrame, fundamentals: dict) -> dict:
    """Signals for the Year timeframe: combines price history with fundamentals."""
    if daily_df.empty:
        return {}

    close = daily_df["Close"]
    signals: dict = {"price": float(close.iloc[-1])}

    if len(close) >= config.SMA_LONG:
        sma200_series = indicators.sma(close, window=config.SMA_LONG)
        if pd.notna(sma200_series.iloc[-1]):
            signals["sma_200"] = float(sma200_series.iloc[-1])

    range_info = indicators.fifty_two_week_range_position(close)
    if range_info["pct_from_high"] is not None:
        signals["pct_from_high"] = range_info["pct_from_high"]
        signals["pct_from_low"] = range_info["pct_from_low"]
        signals["fifty_two_week_high"] = range_info["high"]
        signals["fifty_two_week_low"] = range_info["low"]

    if len(close) >= config.VOLATILITY_WINDOW + 1:
        vol_series = indicators.historical_volatility(close)
        if pd.notna(vol_series.iloc[-1]):
            signals["volatility_annualized"] = float(vol_series.iloc[-1])

    signals["trailing_pe"] = fundamentals.get("trailing_pe")
    signals["dividend_yield"] = fundamentals.get("dividend_yield")
    signals["sector"] = fundamentals.get("sector")
    signals["beta"] = fundamentals.get("beta")

    return signals
