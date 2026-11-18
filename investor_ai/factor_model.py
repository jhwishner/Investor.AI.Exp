"""Fama-French-inspired factor scoring: size and book-to-market equity.

Fama & French (1992, "The Cross-Section of Expected Stock Returns") find
that market size (ME) and book-to-market equity (BE/ME) explain the
cross-section of average stock returns better than market beta --
historically, smaller-size and higher book-to-market (i.e. lower
price-to-book) stocks have earned higher average returns.

This module turns that into the same kind of fixed, inspectable rule this
app already uses everywhere else (see rules.py) -- it is NOT a replication
of the original paper's NYSE-decile breakpoints (those require the full
cross-section of the market to compute each period), just conventional
size/value buckets applied to one stock at a time. Consistent with the
rest of this app: no AI, no external model, every number traceable back to
a threshold in investor_ai/config.py.
"""

from __future__ import annotations

from investor_ai import config


def score_size(market_cap: float | None) -> tuple[float, str | None]:
    """Smaller companies have historically earned a "size premium" (Banz
    1981; Fama-French 1992). Returns (score, message); message is None if
    market_cap is unavailable.
    """
    if market_cap is None or market_cap <= 0:
        return 0.0, None
    if market_cap < config.SMALL_CAP_MAX:
        return (
            1.0,
            f"Small-cap (${market_cap / 1e9:.1f}B market cap) -- historically associated with "
            "higher average returns (the \"size effect\").",
        )
    if market_cap < config.MID_CAP_MAX:
        return 0.5, f"Mid-cap (${market_cap / 1e9:.1f}B market cap)."
    return (
        0.0,
        f"Large-cap (${market_cap / 1e9:.1f}B market cap) -- historically the weakest size-premium tier.",
    )


def score_value(price_to_book: float | None) -> tuple[float, str | None]:
    """Higher book-to-market equity (i.e. lower price-to-book) has
    historically earned a "value premium" (Fama-French 1992). Returns
    (score, message); message is None if price_to_book is unavailable.
    """
    if price_to_book is None or price_to_book <= 0:
        return 0.0, None
    book_to_market = 1 / price_to_book
    if price_to_book < config.VALUE_PB_MAX:
        return (
            1.0,
            f"Trading at {price_to_book:.1f}x book value (book-to-market {book_to_market:.2f}) -- "
            "in \"value\" territory, historically associated with higher average returns.",
        )
    if price_to_book < config.GROWTH_PB_MIN:
        return 0.0, f"Trading at {price_to_book:.1f}x book value -- neither clearly value nor growth."
    return (
        -0.5,
        f"Trading at {price_to_book:.1f}x book value -- in \"growth\"/expensive territory, "
        "historically the weaker end of the value premium.",
    )


def score_factors(market_cap: float | None, price_to_book: float | None) -> tuple[float, list[str]]:
    """Combined Fama-French-style factor score plus rationale messages for
    whichever of size/value are actually available for this ticker.

    Funds/ETFs typically have neither a meaningful market cap nor
    price-to-book in this sense -- both inputs are optional and missing
    data simply contributes zero to the score rather than being guessed at.
    """
    size_score, size_message = score_size(market_cap)
    value_score, value_message = score_value(price_to_book)
    rationale = [m for m in (size_message, value_message) if m]
    return size_score + value_score, rationale
