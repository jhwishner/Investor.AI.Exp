"""Rule-based keyword sentiment scoring over news headlines.

Consistent with the rest of this app: no LLM, no external sentiment API --
just a fixed, inspectable keyword list, same spirit as rules.py. Good enough
to flag "mostly positive coverage" vs. "mostly negative coverage" at a
glance; not a substitute for actually reading the article.
"""

from __future__ import annotations

BULLISH_KEYWORDS = [
    "beat", "beats", "beating", "surge", "surges", "surging", "soar", "soars",
    "soaring", "rally", "rallies", "rallying", "upgrade", "upgraded",
    "outperform", "record high", "record profit", "record revenue",
    "strong demand", "raises guidance", "raises forecast", "raises outlook",
    "buyback", "expands", "expansion", "beats expectations", "wins",
    "approval", "approved", "breakthrough", "all-time high", "jumps", "jump",
]

BEARISH_KEYWORDS = [
    "miss", "misses", "missing", "plunge", "plunges", "plunging", "slump",
    "slumps", "slumping", "downgrade", "downgraded", "underperform",
    "cuts guidance", "cuts forecast", "cuts outlook", "warns", "warning",
    "lawsuit", "recall", "investigation", "layoffs", "job cuts", "bankruptcy",
    "delisted", "fraud", "decline", "declines", "falls", "falling", "drops",
    "dropping", "selloff", "sell-off", "tumbles", "tumbling",
]


def score_headline(text: str) -> tuple[str, int]:
    """Returns (label, score) for one headline.

    label is "bullish" / "bearish" / "neutral"; score is the count of
    matched bullish keywords minus matched bearish keywords in that headline
    (0 if no keywords matched, i.e. neutral).
    """
    lowered = (text or "").lower()
    bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in lowered)
    bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in lowered)
    score = bull_hits - bear_hits
    if score > 0:
        return "bullish", score
    if score < 0:
        return "bearish", score
    return "neutral", 0


def summarize_sentiment(headlines: list[str]) -> dict:
    """Aggregates per-headline sentiment across a list of headlines.

    Returns {"bullish": n, "bearish": n, "neutral": n, "overall": label}.
    "overall" is whichever of bullish/bearish has strictly more headlines;
    a tie (including an all-neutral list, or an empty list) is "neutral".
    """
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for headline in headlines:
        label, _ = score_headline(headline)
        counts[label] += 1

    if counts["bullish"] > counts["bearish"]:
        overall = "bullish"
    elif counts["bearish"] > counts["bullish"]:
        overall = "bearish"
    else:
        overall = "neutral"

    return {**counts, "overall": overall}
