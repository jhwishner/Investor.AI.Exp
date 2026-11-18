"""Tests for the rule-based BUY/SELL/HOLD recommendation engine."""

from investor_ai import recommendations


def test_strongly_bullish_signals_produce_buy():
    week = {"rsi_14": 25, "price": 100, "sma_10": 105}  # oversold, below sma10 (mixed but rsi dominates)
    month = {"price": 110, "sma_50": 100, "macd_histogram": 0.5, "macd_histogram_prev": -0.2}
    year = {"price": 110, "sma_200": 95, "pct_from_low": 3.0}

    rec = recommendations.recommend_for_position("AAPL", 10, 110.0, week, month, year)

    assert rec.action == "BUY"
    assert rec.suggested_pct is not None
    assert rec.suggested_shares == round(10 * rec.suggested_pct / 100, 2)
    assert rec.suggested_dollars == round(rec.suggested_shares * 110.0, 2)
    assert len(rec.rationale) > 0


def test_strongly_bearish_signals_produce_sell():
    week = {"rsi_14": 78, "price": 90, "sma_10": 95}
    month = {"price": 85, "sma_50": 100, "macd_histogram": -0.5, "macd_histogram_prev": 0.2}
    year = {"price": 85, "sma_200": 100, "pct_from_high": 2.0}

    rec = recommendations.recommend_for_position("XYZ", 20, 85.0, week, month, year)

    assert rec.action == "SELL"
    assert rec.suggested_pct is not None
    assert rec.suggested_shares is not None
    assert rec.suggested_shares <= 20  # can't suggest selling more than held


def test_mixed_signals_produce_hold():
    week = {"rsi_14": 50, "price": 100, "sma_10": 100}
    month = {"price": 100, "sma_50": 100}
    year = {"price": 100, "sma_200": 100}

    rec = recommendations.recommend_for_position("MIX", 5, 100.0, week, month, year)

    assert rec.action == "HOLD"
    assert rec.suggested_pct is None
    assert rec.suggested_shares is None


def test_no_signals_returns_no_data():
    rec = recommendations.recommend_for_position("NEWIPO", 1, None, {}, {}, {})
    assert rec.action == "NO_DATA"
    assert rec.suggested_pct is None


def test_higher_score_produces_larger_tier():
    # Maximal bullish stack: oversold + above sma10 + above sma50 + bullish macd
    # + above sma200 + near 52w low
    week = {"rsi_14": 20, "price": 105, "sma_10": 100}
    month = {"price": 110, "sma_50": 100, "macd_histogram": 0.5, "macd_histogram_prev": -0.1}
    year = {"price": 110, "sma_200": 90, "pct_from_low": 2.0}

    rec = recommendations.recommend_for_position("STRONG", 10, 110.0, week, month, year)
    assert rec.action == "BUY"
    assert rec.suggested_pct == 30.0  # top tier given the stacked bullish score


def test_concentration_note_added_above_threshold():
    week, month, year = {"rsi_14": 50, "price": 100, "sma_10": 100}, {"price": 100, "sma_50": 100}, {"price": 100, "sma_200": 100}
    rec = recommendations.recommend_for_position(
        "BIG", 10, 100.0, week, month, year, portfolio_share_pct=55.0
    )
    assert any("55%" in note for note in rec.context_notes)


def test_no_concentration_note_below_threshold():
    week, month, year = {"rsi_14": 50, "price": 100, "sma_10": 100}, {"price": 100, "sma_50": 100}, {"price": 100, "sma_200": 100}
    rec = recommendations.recommend_for_position(
        "SMALL", 10, 100.0, week, month, year, portfolio_share_pct=10.0
    )
    assert not any("total paper portfolio value" in note for note in rec.context_notes)


# --- EXIT: close the position outright ---------------------------------------
#
# The bar is deliberately higher than SELL's. Trimming responds to price
# action; closing says the holding has stopped earning its place, so it
# needs a standing structural reason on top of a bearish score. These tests
# pin both halves -- that the reasons do fire, and that a bad fortnight
# alone never reaches EXIT.

# Real signal shapes -- the same dicts signals.build_*_signals produce.
BEARISH = (
    {"rsi_14": 78, "price": 90, "sma_10": 95},
    {"price": 85, "sma_50": 100, "macd_histogram": -0.5, "macd_histogram_prev": 0.2},
    {"price": 85, "sma_200": 100, "pct_from_high": 2.0},
)
BULLISH = (
    {"rsi_14": 25, "price": 105, "sma_10": 100},
    {"price": 110, "sma_50": 100, "macd_histogram": 0.5, "macd_histogram_prev": -0.2},
    {"price": 110, "sma_200": 95, "pct_from_low": 3.0},
)
NEUTRAL = (
    {"rsi_14": 50, "price": 100, "sma_10": 100},
    {"price": 100, "sma_50": 100},
    {"price": 100, "sma_200": 100},
)


def _lagging(years=4.0, lag=-5.0, fund=4.0, bench=9.0):
    return {"years_covered": years, "outperformance_annualized_pct": lag,
            "fund_annualized_return": fund, "benchmark_annualized_return": bench}


def _rec(signals_tuple, share=20.0, benchmark=None):
    return recommendations.recommend_for_position(
        "TEST", 10, 50.0, *signals_tuple, portfolio_share_pct=share, benchmark=benchmark)


def test_fund_lagging_benchmark_for_years_is_an_exit():
    """The case the feature exists for: an ETF that has quietly trailed a
    plain index fund for years while the owner kept holding it."""
    rec = _rec(BEARISH, benchmark=_lagging())
    assert rec.action == "EXIT"
    assert rec.suggested_pct == 100.0
    assert rec.suggested_shares == 10
    assert any("points behind per year" in r for r in rec.rationale)


def test_exit_suggests_the_whole_position_not_a_tier():
    rec = _rec(BEARISH, benchmark=_lagging())
    assert rec.suggested_shares == 10       # every share, not a SELL tier
    assert rec.suggested_dollars == 500.0


def test_negligible_position_with_bearish_signals_is_an_exit():
    """Over-diversification: too small to matter, still one more thing to track."""
    rec = _rec(BEARISH, share=0.8)
    assert rec.action == "EXIT"
    assert any("too small to move your returns" in r for r in rec.rationale)


def test_bad_signals_alone_never_reach_exit():
    """Without a structural reason a bearish score is a trim, not a close.
    This is the guard against a fund being dumped over a bad fortnight."""
    rec = _rec(BEARISH, share=25.0)
    assert rec.action == "SELL"
    assert rec.suggested_pct < 100.0


def test_short_track_record_is_not_enough_to_exit():
    """A fund needs a real record before its record is used against it."""
    rec = _rec(BEARISH, benchmark=_lagging(years=1.0, lag=-8.0))
    assert rec.action == "SELL"


def test_mild_lag_is_not_an_exit():
    rec = _rec(BEARISH, benchmark=_lagging(lag=-0.5))
    assert rec.action == "SELL"


def test_outperforming_fund_is_never_exited():
    rec = _rec(BEARISH, benchmark=_lagging(lag=+3.0, fund=12.0, bench=9.0))
    assert rec.action == "SELL"


def test_bullish_signals_beat_a_moderate_lag():
    """A moderate lag only exits alongside bearish signals; if the fund is
    currently working, that is not the moment to close it."""
    rec = _rec(BULLISH, benchmark=_lagging(lag=-2.5))
    assert rec.action != "EXIT"


def test_severe_lag_exits_even_on_neutral_signals():
    """A wide enough long-run gap stands on its own -- it just must not be
    actively bullish."""
    rec = _rec(NEUTRAL, benchmark=_lagging(lag=-6.0))
    assert rec.action == "EXIT"


def test_severe_lag_still_defers_to_bullish_signals():
    rec = _rec(BULLISH, benchmark=_lagging(lag=-6.0))
    assert rec.action != "EXIT"


def test_exit_points_at_redeployment_and_flags_tax():
    """The user asked to be told to put the money somewhere better; the tax
    consequence of doing so is not something these rules model, so it is
    stated rather than glossed over."""
    rec = _rec(BEARISH, benchmark=_lagging())
    notes = " ".join(rec.context_notes)
    assert "Ideal Portfolio Screener" in notes
    assert "taxable" in notes


def test_missing_benchmark_data_is_handled():
    for benchmark in (None, {}, {"years_covered": 3.0, "outperformance_annualized_pct": None}):
        assert _rec(BEARISH, share=30.0, benchmark=benchmark).action == "SELL"


def test_suggest_portfolio_additions_returns_non_held_candidates(monkeypatch):
    class DummyBreakout:
        has_data = True
        score = 80
        rationale = ["Breakout rationale"]

    monkeypatch.setattr(recommendations, "score_technical", lambda *args, **kwargs: (3.0, ["tech reason"], []))
    monkeypatch.setattr(recommendations.factor_model, "score_factors", lambda *args, **kwargs: (2.0, ["factor reason"]))
    monkeypatch.setattr(recommendations.breakout, "score_breakout", lambda *args, **kwargs: DummyBreakout())
    monkeypatch.setattr(recommendations.data, "MARKET_MOVER_CATEGORIES", {"gainers": "gainers"})
    monkeypatch.setattr(recommendations.data, "get_market_movers", lambda category: __import__("pandas").DataFrame({"ticker": ["AAPL", "MSFT", "NVDA"]}))
    monkeypatch.setattr(recommendations.data, "get_daily_history", lambda ticker, period=None: __import__("pandas").DataFrame({"Close": [100.0, 101.0, 102.0]}))
    monkeypatch.setattr(recommendations.data, "get_fundamentals", lambda ticker: {})

    suggestions = recommendations.suggest_portfolio_additions({"MSFT"}, max_candidates_per_category=2)

    assert any(item["ticker"] == "AAPL" for item in suggestions)
    assert all(item["ticker"] != "MSFT" for item in suggestions)
    assert suggestions[0]["combined_score"] >= 4.0


def test_exit_never_fires_without_data():
    rec = recommendations.recommend_for_position("T", 5, 10.0, {}, {}, {}, benchmark=_lagging())
    assert rec.action == "NO_DATA"
