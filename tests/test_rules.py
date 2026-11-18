"""Tests for the rule-based commentary engine -- ensures rules fire on the
right thresholds and degrade gracefully on missing signals."""

from investor_ai import rules


def test_week_rsi_overbought_triggers():
    triggered = rules.evaluate_rules("week", {"rsi_14": 75, "price": 100, "sma_10": 95})
    ids = [t.id for t in triggered]
    assert "week_rsi_overbought" in ids
    assert "week_rsi_oversold" not in ids


def test_week_rsi_oversold_triggers():
    triggered = rules.evaluate_rules("week", {"rsi_14": 25, "price": 100, "sma_10": 105})
    ids = [t.id for t in triggered]
    assert "week_rsi_oversold" in ids


def test_missing_signals_skip_rules_without_crashing():
    # No keys at all -- should return an empty list, not raise.
    triggered = rules.evaluate_rules("week", {})
    assert triggered == []


def test_unknown_timeframe_returns_empty():
    assert rules.evaluate_rules("decade", {"price": 100}) == []


def test_month_macd_bullish_crossover_triggers():
    triggered = rules.evaluate_rules(
        "month", {"macd_histogram": 0.5, "macd_histogram_prev": -0.1, "price": 100, "sma_50": 90}
    )
    ids = [t.id for t in triggered]
    assert "month_macd_bullish_cross" in ids


def test_year_pe_missing_vs_present():
    triggered_missing = rules.evaluate_rules("year", {"price": 100, "trailing_pe": None})
    ids_missing = [t.id for t in triggered_missing]
    assert "year_pe_missing" in ids_missing

    triggered_present = rules.evaluate_rules("year", {"price": 100, "trailing_pe": 22.5})
    ids_present = [t.id for t in triggered_present]
    assert "year_pe_present" in ids_present
    assert "year_pe_missing" not in ids_present


def test_message_formatting_uses_signal_values():
    triggered = rules.evaluate_rules("week", {"rsi_14": 72.3, "price": 100, "sma_10": 95})
    week_rsi_msg = next(t.message for t in triggered if t.id == "week_rsi_overbought")
    assert "72" in week_rsi_msg
