"""Sanity tests for the pure indicator functions -- no network, no Streamlit."""

import numpy as np
import pandas as pd
import pytest

from investor_ai import indicators


def _make_series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))


def test_sma_matches_hand_computed_average():
    series = _make_series([1, 2, 3, 4, 5])
    result = indicators.sma(series, window=3)
    # last value should be avg(3,4,5) = 4
    assert result.iloc[-1] == pytest.approx(4.0)
    # first two entries have insufficient window -> NaN
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])


def test_ema_is_defined_from_first_point():
    series = _make_series([1, 2, 3, 4, 5])
    result = indicators.ema(series, span=3)
    assert not pd.isna(result.iloc[0])
    assert len(result) == len(series)


def test_rsi_stays_within_0_100():
    rng = np.random.default_rng(42)
    values = 100 + np.cumsum(rng.normal(0, 1, size=100))
    series = _make_series(values)
    result = indicators.rsi(series, window=14).dropna()
    assert not result.empty
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_rsi_is_100_on_straight_uptrend():
    # Strictly increasing series -> no losses at all -> RSI should be 100
    series = _make_series(list(range(1, 30)))
    result = indicators.rsi(series, window=14).dropna()
    assert not result.empty
    assert result.iloc[-1] == pytest.approx(100.0)


def test_macd_histogram_is_difference_of_lines():
    rng = np.random.default_rng(1)
    values = 100 + np.cumsum(rng.normal(0, 1, size=60))
    series = _make_series(values)
    macd_line, signal_line, histogram = indicators.macd(series)
    diff = macd_line - signal_line
    pd.testing.assert_series_equal(histogram, diff, check_names=False)


def test_bollinger_bands_upper_above_lower():
    rng = np.random.default_rng(2)
    values = 100 + np.cumsum(rng.normal(0, 1, size=60))
    series = _make_series(values)
    upper, mid, lower = indicators.bollinger_bands(series)
    valid = upper.dropna().index
    assert (upper[valid] >= mid[valid]).all()
    assert (mid[valid] >= lower[valid]).all()


def test_historical_volatility_nonnegative():
    rng = np.random.default_rng(3)
    values = 100 + np.cumsum(rng.normal(0, 1, size=60))
    series = _make_series(values)
    vol = indicators.historical_volatility(series).dropna()
    assert not vol.empty
    assert (vol >= 0).all()


def test_momentum_percent_change():
    series = _make_series([100, 100, 100, 100, 110])
    result = indicators.momentum(series, window=4)
    assert result.iloc[-1] == pytest.approx(10.0)


def test_volume_ratio_above_one_on_spike():
    volumes = _make_series([100] * 20 + [500])
    result = indicators.volume_ratio(volumes, window=20)
    assert result.iloc[-1] == pytest.approx(5.0, rel=0.2)


def test_fifty_two_week_range_position():
    values = list(range(1, 253))  # steadily increasing, so high == latest
    series = _make_series(values)
    info = indicators.fifty_two_week_range_position(series)
    assert info["high"] == pytest.approx(252)
    assert info["latest"] == pytest.approx(252)
    assert info["pct_from_high"] == pytest.approx(0.0)
