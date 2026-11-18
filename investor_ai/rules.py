"""Rule-based commentary engine.

This is the "intelligence" of the app -- but it's entirely rule-based, not
generative. Each Rule pairs a condition (a function over a signals dict)
with a message template. No LLM, no external API: the wording is fixed at
write-time and only the numbers plugged into it change.

Rules are data (a list per timeframe), not nested if/else in UI code, so
adding or tuning a rule never requires touching app.py or the pages/.

Signal dict keys expected per timeframe (all optional -- a missing/None
value simply means rules depending on it are skipped, never crashes):

  day:   pct_change, volume_ratio, current_price
  week:  rsi_14, momentum_5d, momentum_10d, price, sma_10
  month: price, sma_50, macd_histogram, macd_histogram_prev, bb_upper, bb_lower
  year:  price, sma_200, pct_from_high, pct_from_low, volatility_annualized,
         trailing_pe, dividend_yield
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from investor_ai import config


@dataclass
class Rule:
    id: str
    timeframe: str  # "day" | "week" | "month" | "year"
    priority: int  # lower = evaluated/shown first
    condition: Callable[[dict], bool]
    message_template: str
    explanation_key: str
    severity: str  # "bullish" | "bearish" | "neutral" | "info"


@dataclass
class TriggeredRule:
    id: str
    message: str
    severity: str
    explanation_key: str


def _has(signals: dict, *keys: str) -> bool:
    """True only if every key is present and not None (avoids KeyError/TypeError in conditions)."""
    return all(signals.get(k) is not None for k in keys)


# --- Day rules ---------------------------------------------------------------

_DAY_RULES = [
    Rule(
        id="day_volume_spike_up",
        timeframe="day",
        priority=1,
        condition=lambda s: _has(s, "volume_ratio", "pct_change")
        and s["volume_ratio"] >= config.VOLUME_SPIKE_RATIO
        and s["pct_change"] > 0,
        message_template=(
            "Volume is running {volume_ratio:.1f}x its 20-day average alongside a "
            "{pct_change:+.1f}% move -- unusually heavy buying interest today."
        ),
        explanation_key="volume",
        severity="bullish",
    ),
    Rule(
        id="day_volume_spike_down",
        timeframe="day",
        priority=1,
        condition=lambda s: _has(s, "volume_ratio", "pct_change")
        and s["volume_ratio"] >= config.VOLUME_SPIKE_RATIO
        and s["pct_change"] < 0,
        message_template=(
            "Volume is running {volume_ratio:.1f}x its 20-day average alongside a "
            "{pct_change:+.1f}% move -- unusually heavy selling pressure today."
        ),
        explanation_key="volume",
        severity="bearish",
    ),
    Rule(
        id="day_large_move",
        timeframe="day",
        priority=2,
        condition=lambda s: _has(s, "pct_change") and abs(s["pct_change"]) >= config.LARGE_DAILY_MOVE_PCT,
        message_template=(
            "A {pct_change:+.1f}% single-day move is a large swing -- worth checking for "
            "recent news before reacting."
        ),
        explanation_key="momentum",
        severity="info",
    ),
    Rule(
        id="day_neutral",
        timeframe="day",
        priority=99,
        condition=lambda s: _has(s, "pct_change"),
        message_template="Today's move ({pct_change:+.1f}%) and volume look within their normal recent range.",
        explanation_key="volume",
        severity="neutral",
    ),
]

# --- Week rules ---------------------------------------------------------------

_WEEK_RULES = [
    Rule(
        id="week_rsi_overbought",
        timeframe="week",
        priority=1,
        condition=lambda s: _has(s, "rsi_14") and s["rsi_14"] >= config.RSI_OVERBOUGHT,
        message_template="RSI is {rsi_14:.0f} (overbought), suggesting near-term pullback risk on the week horizon.",
        explanation_key="rsi",
        severity="bearish",
    ),
    Rule(
        id="week_rsi_oversold",
        timeframe="week",
        priority=1,
        condition=lambda s: _has(s, "rsi_14") and s["rsi_14"] <= config.RSI_OVERSOLD,
        message_template="RSI is {rsi_14:.0f} (oversold), suggesting the recent decline may be overdone.",
        explanation_key="rsi",
        severity="bullish",
    ),
    Rule(
        id="week_price_above_sma10",
        timeframe="week",
        priority=3,
        condition=lambda s: _has(s, "price", "sma_10") and s["price"] > s["sma_10"],
        message_template="Price is above its 10-day average -- short-term trend is up.",
        explanation_key="sma",
        severity="bullish",
    ),
    Rule(
        id="week_price_below_sma10",
        timeframe="week",
        priority=3,
        condition=lambda s: _has(s, "price", "sma_10") and s["price"] < s["sma_10"],
        message_template="Price is below its 10-day average -- short-term trend is down.",
        explanation_key="sma",
        severity="bearish",
    ),
    Rule(
        id="week_rsi_neutral",
        timeframe="week",
        priority=99,
        condition=lambda s: _has(s, "rsi_14"),
        message_template="RSI is {rsi_14:.0f} -- neither overbought nor oversold.",
        explanation_key="rsi",
        severity="neutral",
    ),
]

# --- Month rules ---------------------------------------------------------------

_MONTH_RULES = [
    Rule(
        id="month_price_above_sma50",
        timeframe="month",
        priority=2,
        condition=lambda s: _has(s, "price", "sma_50") and s["price"] > s["sma_50"],
        message_template="Price is trading above its 50-day average, consistent with a medium-term uptrend.",
        explanation_key="sma",
        severity="bullish",
    ),
    Rule(
        id="month_price_below_sma50",
        timeframe="month",
        priority=2,
        condition=lambda s: _has(s, "price", "sma_50") and s["price"] < s["sma_50"],
        message_template="Price is trading below its 50-day average, consistent with a medium-term downtrend.",
        explanation_key="sma",
        severity="bearish",
    ),
    Rule(
        id="month_macd_bullish_cross",
        timeframe="month",
        priority=1,
        condition=lambda s: _has(s, "macd_histogram", "macd_histogram_prev")
        and s["macd_histogram_prev"] <= 0
        and s["macd_histogram"] > 0,
        message_template="MACD just crossed bullish -- momentum is shifting upward.",
        explanation_key="macd",
        severity="bullish",
    ),
    Rule(
        id="month_macd_bearish_cross",
        timeframe="month",
        priority=1,
        condition=lambda s: _has(s, "macd_histogram", "macd_histogram_prev")
        and s["macd_histogram_prev"] >= 0
        and s["macd_histogram"] < 0,
        message_template="MACD just crossed bearish -- momentum is shifting downward.",
        explanation_key="macd",
        severity="bearish",
    ),
    Rule(
        id="month_bollinger_upper_breakout",
        timeframe="month",
        priority=3,
        condition=lambda s: _has(s, "price", "bb_upper") and s["price"] > s["bb_upper"],
        message_template="Price is trading above its upper Bollinger Band -- an unusually strong recent move.",
        explanation_key="bollinger",
        severity="info",
    ),
    Rule(
        id="month_bollinger_lower_breakout",
        timeframe="month",
        priority=3,
        condition=lambda s: _has(s, "price", "bb_lower") and s["price"] < s["bb_lower"],
        message_template="Price is trading below its lower Bollinger Band -- an unusually sharp recent decline.",
        explanation_key="bollinger",
        severity="info",
    ),
]

# --- Year rules ---------------------------------------------------------------

_YEAR_RULES = [
    Rule(
        id="year_price_above_sma200",
        timeframe="year",
        priority=2,
        condition=lambda s: _has(s, "price", "sma_200") and s["price"] > s["sma_200"],
        message_template="Price is above its 200-day average, consistent with a longer-term uptrend.",
        explanation_key="sma_crossover",
        severity="bullish",
    ),
    Rule(
        id="year_price_below_sma200",
        timeframe="year",
        priority=2,
        condition=lambda s: _has(s, "price", "sma_200") and s["price"] < s["sma_200"],
        message_template="Price is below its 200-day average, consistent with a longer-term downtrend.",
        explanation_key="sma_crossover",
        severity="bearish",
    ),
    Rule(
        id="year_near_52w_high",
        timeframe="year",
        priority=3,
        condition=lambda s: _has(s, "pct_from_high") and abs(s["pct_from_high"]) <= config.FIFTY_TWO_WEEK_PROXIMITY_PCT,
        message_template="Price is within {pct_from_high:.1f}% of its 52-week high -- near the top of its yearly range.",
        explanation_key="fifty_two_week",
        severity="info",
    ),
    Rule(
        id="year_near_52w_low",
        timeframe="year",
        priority=3,
        condition=lambda s: _has(s, "pct_from_low") and abs(s["pct_from_low"]) <= config.FIFTY_TWO_WEEK_PROXIMITY_PCT,
        message_template="Price is within {pct_from_low:.1f}% of its 52-week low -- near the bottom of its yearly range.",
        explanation_key="fifty_two_week",
        severity="info",
    ),
    Rule(
        id="year_high_volatility",
        timeframe="year",
        priority=4,
        condition=lambda s: _has(s, "volatility_annualized")
        and s["volatility_annualized"] >= config.HIGH_VOLATILITY_ANNUALIZED_PCT,
        message_template=(
            "Annualized volatility is {volatility_annualized:.0f}%, notably higher than the broader "
            "market's typical ~15-20% -- expect bigger price swings in both directions."
        ),
        explanation_key="volatility",
        severity="info",
    ),
    Rule(
        id="year_pe_missing",
        timeframe="year",
        priority=5,
        condition=lambda s: s.get("trailing_pe") is None,
        message_template="No trailing P/E is available -- often means the company isn't currently profitable.",
        explanation_key="pe_ratio",
        severity="info",
    ),
    Rule(
        id="year_pe_present",
        timeframe="year",
        priority=5,
        condition=lambda s: _has(s, "trailing_pe"),
        message_template="Trailing P/E is {trailing_pe:.1f} -- only meaningful compared against similar companies.",
        explanation_key="pe_ratio",
        severity="info",
    ),
]

RULES_BY_TIMEFRAME: dict[str, list[Rule]] = {
    "day": _DAY_RULES,
    "week": _WEEK_RULES,
    "month": _MONTH_RULES,
    "year": _YEAR_RULES,
}


def evaluate_rules(timeframe: str, signals: dict) -> list[TriggeredRule]:
    """Evaluate all rules for a timeframe against a signals dict.

    Rules whose condition raises (e.g. unexpected type) are skipped rather
    than crashing the page -- a missing signal should degrade gracefully,
    never take down the UI.
    """
    rules = RULES_BY_TIMEFRAME.get(timeframe, [])
    triggered: list[TriggeredRule] = []

    for rule in sorted(rules, key=lambda r: r.priority):
        try:
            if not rule.condition(signals):
                continue
            message = rule.message_template.format(**signals)
        except Exception:
            continue
        triggered.append(
            TriggeredRule(
                id=rule.id,
                message=message,
                severity=rule.severity,
                explanation_key=rule.explanation_key,
            )
        )

    return triggered
