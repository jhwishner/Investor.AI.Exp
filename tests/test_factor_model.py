"""Tests for the Fama-French-inspired size/value factor scoring (pure logic, no network)."""

from investor_ai import factor_model


def test_small_cap_scores_positive():
    score, message = factor_model.score_size(1e9)
    assert score == 1.0
    assert "Small-cap" in message


def test_mid_cap_scores_half():
    score, message = factor_model.score_size(5e9)
    assert score == 0.5
    assert "Mid-cap" in message


def test_large_cap_scores_zero():
    score, message = factor_model.score_size(50e9)
    assert score == 0.0
    assert "Large-cap" in message


def test_missing_market_cap_is_neutral_with_no_message():
    assert factor_model.score_size(None) == (0.0, None)


def test_value_stock_scores_positive():
    score, message = factor_model.score_value(0.8)
    assert score == 1.0
    assert "value" in message.lower()


def test_growth_stock_scores_negative():
    score, message = factor_model.score_value(5.0)
    assert score == -0.5
    assert "growth" in message.lower()


def test_neutral_price_to_book_scores_zero():
    score, message = factor_model.score_value(2.0)
    assert score == 0.0
    assert message is not None


def test_missing_or_invalid_price_to_book_is_neutral_with_no_message():
    assert factor_model.score_value(None) == (0.0, None)
    assert factor_model.score_value(0) == (0.0, None)
    assert factor_model.score_value(-1.0) == (0.0, None)


def test_score_factors_combines_size_and_value():
    score, rationale = factor_model.score_factors(market_cap=1e9, price_to_book=0.8)
    assert score == 2.0
    assert len(rationale) == 2


def test_score_factors_handles_missing_data_gracefully():
    score, rationale = factor_model.score_factors(market_cap=None, price_to_book=None)
    assert score == 0.0
    assert rationale == []
