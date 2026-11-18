"""Tests for the breakout screen.

The two that matter most:

  * test_volatility_squeeze_scores_tight_bands_higher -- the original
    version of this signal was inverted (it rewarded stocks whose
    volatility had already expanded, the opposite of the intent). The
    direction is pinned here so it cannot silently flip back.

  * the backtest tests -- specifically that a large-gain rate is reported
    alongside a large-loss rate, since the up rate alone cannot distinguish
    "picks direction" from "picks volatile stocks".
"""

import numpy as np
import pandas as pd
import pytest

from investor_ai import breakout


def _frame(closes, volumes=None, high_mult=1.01, low_mult=0.99):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * high_mult,
            "Low": closes * low_mult,
            "Close": closes,
            "Volume": np.full(n, 1_000_000.0) if volumes is None else np.asarray(volumes, dtype=float),
        },
        index=pd.bdate_range("2023-01-02", periods=n),
    )


def _random_walk(n, sigma, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    return start + np.cumsum(rng.normal(0, sigma, n))


# --- the previously-inverted signal ----------------------------------------


def test_volatility_squeeze_scores_tight_bands_higher():
    """A quiet, tight band must score HIGHER than one that has already
    blown out. This is the regression that motivated the module."""
    base = _random_walk(200, sigma=2.0, seed=1)
    tight = np.concatenate([base, base[-1] + np.cumsum(np.full(60, 0.01))])
    wide = np.concatenate([base, base[-1] + np.cumsum(np.random.default_rng(2).normal(0, 6.0, 60))])

    tight_score, _ = breakout._volatility_squeeze(_frame(tight))
    wide_score, _ = breakout._volatility_squeeze(_frame(wide))

    assert tight_score > wide_score
    assert tight_score > 0.7   # a genuine squeeze should score near the top
    assert wide_score < 0.3


def test_volatility_squeeze_is_bounded():
    for seed in range(5):
        score, _ = breakout._volatility_squeeze(_frame(_random_walk(260, 1.5, seed)))
        assert 0.0 <= score <= 1.0


# --- individual components --------------------------------------------------


def test_volume_anomaly_rewards_a_spike():
    closes = _random_walk(200, 1.0, seed=3)
    quiet = _frame(closes)
    spiky_volumes = np.full(200, 1_000_000.0)
    spiky_volumes[-1] = 5_000_000.0
    spiky = _frame(closes, volumes=spiky_volumes)

    assert breakout._volume_anomaly(spiky)[0] > breakout._volume_anomaly(quiet)[0]
    assert breakout._volume_anomaly(spiky)[1] is not None  # spike is explained to the user


def test_momentum_rewards_recent_gains():
    flat = _frame(np.full(200, 100.0))
    rising = _frame(np.concatenate([np.full(170, 100.0), np.linspace(100, 135, 30)]))
    assert breakout._momentum(rising)[0] > breakout._momentum(flat)[0]


def test_closing_strength_rewards_closes_near_the_high():
    n = 200
    closes = np.full(n, 100.0)
    strong = pd.DataFrame(
        {"Open": closes, "High": closes * 1.001, "Low": closes * 0.95,
         "Close": closes, "Volume": np.full(n, 1e6)},
        index=pd.bdate_range("2023-01-02", periods=n),
    )
    weak = pd.DataFrame(
        {"Open": closes, "High": closes * 1.05, "Low": closes * 0.999,
         "Close": closes, "Volume": np.full(n, 1e6)},
        index=pd.bdate_range("2023-01-02", periods=n),
    )
    assert breakout._closing_strength(strong)[0] > breakout._closing_strength(weak)[0]


def test_rsi_runway_peaks_in_the_sweet_spot_not_at_extremes():
    straight_up = _frame(np.linspace(100, 400, 220))     # RSI pinned near 100
    score, _ = breakout._rsi_runway(straight_up)
    assert score < 0.6   # extended, not "runway"


# --- composite --------------------------------------------------------------


def test_score_is_zero_to_one_hundred_and_components_reported():
    result = breakout.score_breakout("TEST", _frame(_random_walk(260, 1.5, seed=9)))
    assert result.has_data
    assert 0.0 <= result.score <= 100.0
    assert set(result.components) == set(breakout.COMPONENT_WEIGHTS)
    assert all(0.0 <= v <= 100.0 for v in result.components.values())
    assert result.rationale


def test_weights_sum_to_one():
    """Otherwise the composite silently stops being a 0-100 scale."""
    assert sum(breakout.COMPONENT_WEIGHTS.values()) == pytest.approx(1.0)


def test_insufficient_history_is_flagged_not_raised():
    result = breakout.score_breakout("SHORT", _frame(_random_walk(40, 1.0)))
    assert result.has_data is False
    assert result.score == 0.0


def test_empty_frame_is_handled():
    """The data layer returns an empty DataFrame on any failure, so this
    path is reachable in normal operation."""
    for empty in (pd.DataFrame(), None):
        result = breakout.score_breakout("NODATA", empty)
        assert result.has_data is False
        assert result.score == 0.0


def test_score_is_deterministic():
    df = _frame(_random_walk(260, 1.5, seed=11))
    assert breakout.score_breakout("X", df).score == breakout.score_breakout("X", df).score


# --- alignment --------------------------------------------------------------


def test_align_restricts_to_shared_dates():
    a = _frame(_random_walk(100, 1.0, seed=1))
    b = _frame(_random_walk(100, 1.0, seed=2)).drop(index=_frame(_random_walk(100, 1.0)).index[50])
    aligned = breakout._align({"A": a, "B": b})
    assert len(aligned["A"]) == len(aligned["B"])
    assert aligned["A"].index.equals(aligned["B"].index)
    # the dropped session is gone from BOTH, so positional walks stay in step
    assert len(aligned["A"]) == 99


def test_align_drops_empty_frames():
    good = _frame(_random_walk(100, 1.0))
    aligned = breakout._align({"GOOD": good, "EMPTY": pd.DataFrame(), "NONE": None})
    assert set(aligned) == {"GOOD"}


# --- backtest ---------------------------------------------------------------


def _universe(n_tickers=14, n_bars=420, seed=0):
    rng = np.random.default_rng(seed)
    return {
        f"T{i}": _frame(
            _random_walk(n_bars, sigma=rng.uniform(0.5, 3.0), seed=int(rng.integers(0, 10_000))),
            volumes=rng.lognormal(13, 0.6, n_bars),
        )
        for i in range(n_tickers)
    }


def test_backtest_reports_both_tails():
    """The whole point: an up-rate without a down-rate can't tell skill from
    volatility selection."""
    result = breakout.backtest(_universe(), hold_days=10, big_move_pct=10.0)
    assert result is not None
    assert 0.0 <= result.model_up_rate <= 1.0
    assert 0.0 <= result.model_down_rate <= 1.0
    assert 0.0 <= result.random_up_rate <= 1.0
    assert 0.0 <= result.random_down_rate <= 1.0
    assert result.picks > 0


def test_directional_edge_is_up_minus_down():
    result = breakout.backtest(_universe(), hold_days=10)
    assert result.model_directional_edge == pytest.approx(
        result.model_up_rate - result.model_down_rate
    )
    assert result.random_directional_edge == pytest.approx(
        result.random_up_rate - result.random_down_rate
    )


def test_backtest_on_pure_noise_shows_no_directional_edge():
    """Random walks have no predictable direction by construction, so the
    screen must not appear to find one. If this ever fails, something in
    the pipeline is leaking future information."""
    result = breakout.backtest(_universe(n_tickers=16, n_bars=500, seed=5), hold_days=10)
    assert result is not None
    assert abs(result.model_directional_edge) < 0.25


def test_backtest_is_reproducible():
    universe = _universe(seed=3)
    a = breakout.backtest(universe, seed=7)
    b = breakout.backtest(universe, seed=7)
    assert a.model_mean_return_pct == b.model_mean_return_pct
    assert a.random_mean_return_pct == b.random_mean_return_pct


def test_backtest_returns_none_without_enough_history():
    assert breakout.backtest(_universe(n_tickers=14, n_bars=150)) is None
    assert breakout.backtest({"ONLY": _frame(_random_walk(400, 1.0))}) is None


def test_backtest_enters_on_the_bar_after_scoring_not_the_scoring_bar():
    """Pin the exact entry price.

    Every ticker is identical and strictly increasing, so whichever five the
    screen picks, the realised return of a window is fully determined by the
    entry bar. That lets the expected mean be computed independently here
    for BOTH conventions -- entering at the scoring bar's close vs the next
    bar's close -- and asserted against the right one. Scoring and entering
    on the same close assumes a fill at a price you only learn after the
    close prints, so it would flatter every result.
    """
    n_bars, hold = 420, 10
    closes = 100.0 + np.arange(n_bars, dtype=float)      # strictly increasing
    universe = {f"R{i}": _frame(closes) for i in range(12)}

    result = breakout.backtest(universe, hold_days=hold)
    assert result is not None

    last_start = n_bars - hold - 2
    starts = range(breakout.MIN_BARS, last_start, hold)
    # Round exactly as the implementation does, so this is an equality test
    # rather than a tolerance that could mask a one-bar shift.
    expected_next_bar = round(float(np.mean([(closes[i + 1 + hold] / closes[i + 1] - 1) * 100 for i in starts])), 2)
    expected_same_bar = round(float(np.mean([(closes[i + hold] / closes[i] - 1) * 100 for i in starts])), 2)

    assert expected_next_bar != expected_same_bar, "test data must distinguish the two conventions"
    assert result.model_mean_return_pct == expected_next_bar
    assert result.model_mean_return_pct != expected_same_bar


def test_verdict_mentions_volatility_when_both_tails_lift():
    text = breakout._verdict(model_edge=0.0, random_edge=0.0, model_up=0.30, random_up=0.10)
    assert "volatile" in text.lower()
    assert "not an ability to predict" in text.lower()
