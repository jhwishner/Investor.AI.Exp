"""Tests for the rule-based keyword sentiment scorer (pure logic, no network)."""

from investor_ai import sentiment


def test_bullish_headline_scores_positive():
    label, score = sentiment.score_headline("Company beats earnings expectations, stock surges to record high")
    assert label == "bullish"
    assert score > 0


def test_bearish_headline_scores_negative():
    label, score = sentiment.score_headline("Company misses earnings, shares plunge amid investigation")
    assert label == "bearish"
    assert score < 0


def test_neutral_headline_with_no_keywords():
    label, score = sentiment.score_headline("Company to report quarterly results next Tuesday")
    assert label == "neutral"
    assert score == 0


def test_empty_or_none_text_is_neutral():
    assert sentiment.score_headline("") == ("neutral", 0)
    assert sentiment.score_headline(None) == ("neutral", 0)


def test_summarize_sentiment_counts_each_label():
    headlines = [
        "Stock surges after beating expectations",
        "Shares plunge on weak guidance",
        "Company to hold annual meeting next month",
    ]
    summary = sentiment.summarize_sentiment(headlines)
    assert summary["bullish"] == 1
    assert summary["bearish"] == 1
    assert summary["neutral"] == 1


def test_summarize_sentiment_overall_majority_wins():
    headlines = [
        "Stock surges after beating expectations",
        "Shares rally on record profit",
        "Company misses guidance",
    ]
    summary = sentiment.summarize_sentiment(headlines)
    assert summary["overall"] == "bullish"


def test_summarize_sentiment_tie_is_neutral():
    headlines = ["Stock surges after beating expectations", "Shares plunge on weak guidance"]
    summary = sentiment.summarize_sentiment(headlines)
    assert summary["overall"] == "neutral"


def test_summarize_sentiment_empty_list_is_neutral():
    summary = sentiment.summarize_sentiment([])
    assert summary == {"bullish": 0, "bearish": 0, "neutral": 0, "overall": "neutral"}
