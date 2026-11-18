"""Quantitative indicator formulas.

Every function here is a pure function over a pandas Series/DataFrame --
no I/O, no Streamlit, no side effects. That makes them independently
testable (see tests/test_indicators.py) and easy to point at when
explaining "what does this mean" to a new investor: the formula IS the
explanation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from investor_ai import config


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average: the plain average of the last `window` closes."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average: like SMA but weights recent prices more heavily."""
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, window: int = config.RSI_WINDOW) -> pd.Series:
    """Relative Strength Index (Wilder smoothing), 0-100.

    Above ~70 is conventionally "overbought" (may be due for a pullback);
    below ~30 is conventionally "oversold" (may be due for a bounce).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing is an EMA with alpha = 1/window
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    # Where avg_loss is 0 (straight-up move), RSI is 100 by convention.
    result = result.where(avg_loss != 0, 100.0)
    return result


def macd(
    series: pd.Series,
    fast: int = config.MACD_FAST,
    slow: int = config.MACD_SLOW,
    signal: int = config.MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, and histogram.

    The MACD line crossing above its signal line is a classic bullish
    trend-change signal; crossing below is bearish.
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    series: pd.Series,
    window: int = config.BOLLINGER_WINDOW,
    num_std: float = config.BOLLINGER_NUM_STD,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Upper band, middle band (SMA), lower band.

    Bands widen/narrow with recent volatility. Price pushing outside a band
    signals an unusually strong move relative to its recent range.
    """
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def historical_volatility(
    series: pd.Series,
    window: int = config.VOLATILITY_WINDOW,
    trading_days: int = config.VOLATILITY_TRADING_DAYS,
) -> pd.Series:
    """Annualized historical volatility (%) from the stdev of daily log returns."""
    log_returns = np.log(series / series.shift(1))
    rolling_std = log_returns.rolling(window=window, min_periods=window).std()
    return rolling_std * np.sqrt(trading_days) * 100


def momentum(series: pd.Series, window: int) -> pd.Series:
    """Percent change over the last `window` periods."""
    return series.pct_change(periods=window) * 100


def volume_ratio(volume: pd.Series, window: int = config.VOLUME_AVG_WINDOW) -> pd.Series:
    """Current volume divided by its trailing `window`-period average.

    A ratio well above 1.0 signals unusually heavy trading interest.
    """
    avg_volume = volume.rolling(window=window, min_periods=window).mean()
    return volume / avg_volume.replace(0, np.nan)


def fifty_two_week_range_position(series: pd.Series) -> dict:
    """Where the latest price sits within its trailing 52-week high/low range.

    Returns dict with high, low, latest, pct_from_high, pct_from_low (all
    None if there isn't enough history yet).
    """
    window = series.tail(252)
    if window.empty:
        return {"high": None, "low": None, "latest": None, "pct_from_high": None, "pct_from_low": None}
    high = float(window.max())
    low = float(window.min())
    latest = float(series.iloc[-1])
    pct_from_high = (latest - high) / high * 100 if high else None
    pct_from_low = (latest - low) / low * 100 if low else None
    return {
        "high": high,
        "low": low,
        "latest": latest,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
    }
