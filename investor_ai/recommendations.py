"""Rule-based BUY / SELL / HOLD recommendations for existing paper positions.

Same philosophy as rules.py: no AI, no external model. This module assigns a
fixed numeric weight to a small set of *directional* rules already defined in
rules.py (trend + momentum signals from the Week/Month/Year timeframes),
sums them into a score, and maps that score to an action and a suggested
position-size change. The rationale shown to the user is literally the same
rule messages already shown on the Ticker Analysis page -- nothing here is
generated text, it's arithmetic over rules that already exist.

Deliberately excluded from scoring:
  - Day-timeframe rules (too noisy for a position-sizing decision)
  - Informational-only rules (Bollinger breakout, volatility, P/E) -- these
    are shown as extra context, not used to push the score toward BUY/SELL

This is still not financial advice -- it doesn't know your tax situation,
diversification goals, risk tolerance, or overall financial picture. Amounts
are suggested as a percentage of your *current position size*, since the
app doesn't track cash balances.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from investor_ai import benchmarks, breakout, config, data, factor_model, indicators, rules, signals

# Weight each directional rule contributes to the recommendation score.
# Positive = bullish (leans toward BUY), negative = bearish (leans toward SELL).
SCORE_WEIGHTS: dict[str, float] = {
    "week_rsi_oversold": 1.5,
    "week_rsi_overbought": -1.5,
    "week_price_above_sma10": 0.5,
    "week_price_below_sma10": -0.5,
    "month_price_above_sma50": 1.0,
    "month_price_below_sma50": -1.0,
    "month_macd_bullish_cross": 1.0,
    "month_macd_bearish_cross": -1.0,
    "year_price_above_sma200": 1.0,
    "year_price_below_sma200": -1.0,
    "year_near_52w_low": 0.5,
    "year_near_52w_high": -0.5,
}

# Score thresholds and the position-size change suggested at each tier.
_BUY_TIERS = [(3.5, 30.0), (2.5, 20.0), (1.5, 10.0)]   # (min_score, suggested_pct)
_SELL_TIERS = [(3.5, 50.0), (2.5, 30.0), (1.5, 15.0)]  # (min_abs_score, suggested_pct)

# Portfolio concentration above this share of total value gets an extra note.
CONCENTRATION_WARNING_PCT = 40.0

# Score at or below which the rules lean bearish. Named because the exit
# logic needs the same line the SELL tiers use.
BEARISH_SCORE = -1.5


@dataclass
class PositionRecommendation:
    ticker: str
    action: str  # "BUY" | "SELL" | "EXIT" | "HOLD" | "NO_DATA"
    score: float
    suggested_pct: float | None       # % of current position size to add/trim
    suggested_shares: float | None
    suggested_dollars: float | None
    rationale: list[str] = field(default_factory=list)   # factors that drove the score
    context_notes: list[str] = field(default_factory=list)  # informational, non-scored


def _score_and_rationale(*signal_dicts_by_timeframe: tuple[str, dict]) -> tuple[float, list[str], list[str]]:
    """Runs rules.evaluate_rules for each (timeframe, signals) pair, splits the
    triggered rules into (scored rationale, unscored context), and sums weights.
    """
    score = 0.0
    rationale: list[str] = []
    context: list[str] = []

    for timeframe, signal_dict in signal_dicts_by_timeframe:
        if not signal_dict:
            continue
        for triggered in rules.evaluate_rules(timeframe, signal_dict):
            weight = SCORE_WEIGHTS.get(triggered.id)
            if weight is not None:
                score += weight
                rationale.append(triggered.message)
            elif triggered.severity != "neutral":
                context.append(triggered.message)

    return score, rationale, context


def _exit_reasons(score: float, portfolio_share_pct: float | None,
                  benchmark: dict | None) -> list[str]:
    """Why this position should be closed out rather than trimmed.

    An empty list means there is no exit case. The bar is deliberately
    higher than SELL's: trimming responds to price action, but closing a
    position means the holding itself has stopped earning its place, so it
    needs a standing reason on top of a bearish score -- either it has
    lagged a plain index fund over a real track record, or it is too small
    a slice to affect returns while still needing to be tracked.

    Kept separate from the score so it can never be reached by momentum
    alone: a fund can score badly for a fortnight without that saying
    anything about whether it deserves to be held.
    """
    reasons: list[str] = []
    benchmark = benchmark or {}
    lag = benchmark.get("outperformance_annualized_pct")
    years = benchmark.get("years_covered")
    fund_ann = benchmark.get("fund_annualized_return")
    bench_ann = benchmark.get("benchmark_annualized_return")

    # Only judge a fund on its record once it has one.
    if lag is not None and years is not None and years >= config.EXIT_MIN_YEARS:
        track_record = (
            f"Over ~{years:.1f} years it has returned {fund_ann:.1f}% annualized "
            f"against the {benchmarks.BENCHMARK_LABEL}'s {bench_ann:.1f}% -- "
            f"{abs(lag):.1f} points behind per year."
        ) if fund_ann is not None and bench_ann is not None else (
            f"Over ~{years:.1f} years it has trailed the {benchmarks.BENCHMARK_LABEL} "
            f"by {abs(lag):.1f} points per year."
        )

        if lag <= config.EXIT_SEVERE_LAG_PCT and score <= 0:
            reasons.append(
                f"{track_record} A plain index fund would have done better over the "
                "same window, and the current signals give no reason to expect that to turn."
            )
        elif lag <= config.EXIT_BENCHMARK_LAG_PCT and score <= BEARISH_SCORE:
            reasons.append(
                f"{track_record} That long-run lag plus currently bearish signals is the "
                "case for closing it rather than trimming."
            )

    if (portfolio_share_pct is not None
            and portfolio_share_pct < config.NEGLIGIBLE_POSITION_PCT
            and score <= BEARISH_SCORE):
        reasons.append(
            f"At {portfolio_share_pct:.1f}% of your portfolio it is too small to move your "
            "returns either way, while still being one more position to follow. "
            "Consolidating it into a holding you have conviction in costs you nothing in "
            "diversification."
        )

    return reasons


def _action_and_pct(score: float) -> tuple[str, float | None]:
    if score >= 1.5:
        for min_score, pct in _BUY_TIERS:
            if score >= min_score:
                return "BUY", pct
        return "BUY", _BUY_TIERS[-1][1]
    if score <= -1.5:
        abs_score = abs(score)
        for min_score, pct in _SELL_TIERS:
            if abs_score >= min_score:
                return "SELL", pct
        return "SELL", _SELL_TIERS[-1][1]
    return "HOLD", None


def score_technical(week_signals: dict, month_signals: dict, year_signals: dict) -> tuple[float, list[str], list[str]]:
    """Public entry point to the same technical scoring used for owned
    positions (trend + momentum rules, weighted per SCORE_WEIGHTS), usable
    for tickers you don't currently hold -- e.g. a screener.

    Returns (score, rationale, context_notes), same shape as the internal
    scorer used by recommend_for_position.
    """
    return _score_and_rationale(("week", week_signals), ("month", month_signals), ("year", year_signals))


def suggest_portfolio_additions(
    held_tickers: set[str] | list[str],
    max_candidates_per_category: int = 5,
    min_score: float = 1.5,
) -> list[dict]:
    """Return the best non-held tickers to consider adding to the portfolio.

    This is the same logic that used to live in the standalone ideal portfolio
    screener, but re-used directly in the recommendations flow so users get
    suggested additions alongside their current position advice.
    """
    held = set(held_tickers)
    universe = set(held)
    for category_key in data.MARKET_MOVER_CATEGORIES.values():
        movers_df = data.get_market_movers(category_key)
        if not movers_df.empty:
            universe.update(movers_df["ticker"].head(int(max_candidates_per_category)).tolist())

    suggestions: list[dict] = []
    for ticker in sorted(universe - held):
        daily_df = data.get_daily_history(ticker)
        if daily_df.empty:
            continue

        fundamentals = data.get_fundamentals(ticker)
        week_signals = signals.build_week_signals(daily_df)
        month_signals = signals.build_month_signals(daily_df)
        year_signals = signals.build_year_signals(daily_df, fundamentals)

        tech_score, tech_rationale, _ = score_technical(week_signals, month_signals, year_signals)
        factor_score, factor_rationale = factor_model.score_factors(
            fundamentals.get("market_cap"),
            fundamentals.get("price_to_book"),
        )

        combined_score = tech_score + factor_score
        if combined_score < min_score:
            continue

        volatility_series = indicators.historical_volatility(daily_df["Close"]).dropna()
        volatility = float(volatility_series.iloc[-1]) if not volatility_series.empty else None
        beta = fundamentals.get("beta")
        breakout_result = breakout.score_breakout(ticker, daily_df)

        suggestions.append(
            {
                "ticker": ticker,
                "combined_score": round(combined_score, 2),
                "verdict": "BUY" if combined_score >= 1.5 else "WATCH",
                "rationale": tech_rationale + factor_rationale,
                "beta": beta,
                "volatility": volatility,
                "breakout_score": breakout_result.score if breakout_result.has_data else None,
                "breakout_rationale": breakout_result.rationale if breakout_result.has_data else [],
            }
        )

    suggestions.sort(key=lambda item: item["combined_score"], reverse=True)
    return suggestions


def recommend_for_position(
    ticker: str,
    quantity: float,
    current_price: float | None,
    week_signals: dict,
    month_signals: dict,
    year_signals: dict,
    portfolio_share_pct: float | None = None,
    benchmark: dict | None = None,
) -> PositionRecommendation:
    """Build a recommendation for a single open position.

    portfolio_share_pct (optional): this position's market value as a % of
    total portfolio value. Used for the concentration note, and as one of
    the structural reasons a position can be closed outright -- it never
    affects the BUY/SELL score itself.

    benchmark (optional): the dict from benchmarks.compare_to_benchmark for
    this holding. Supplying it enables the EXIT verdict, which is how a
    fund that has quietly trailed a plain index fund for years gets
    surfaced -- something the price-action signals alone will never say.
    """
    if not (week_signals or month_signals or year_signals):
        return PositionRecommendation(
            ticker=ticker,
            action="NO_DATA",
            score=0.0,
            suggested_pct=None,
            suggested_shares=None,
            suggested_dollars=None,
            rationale=["Not enough price history to generate signals for this ticker yet."],
        )

    score, rationale, context = _score_and_rationale(
        ("week", week_signals), ("month", month_signals), ("year", year_signals)
    )
    action, suggested_pct = _action_and_pct(score)

    # An exit case overrides the tiered SELL: closing means all of it.
    exit_reasons = _exit_reasons(score, portfolio_share_pct, benchmark)
    if exit_reasons:
        action = "EXIT"
        suggested_pct = 100.0
        rationale.extend(exit_reasons)

    suggested_shares = None
    suggested_dollars = None
    if suggested_pct is not None:
        suggested_shares = round(quantity * suggested_pct / 100, 2)
        if current_price is not None:
            suggested_dollars = round(suggested_shares * current_price, 2)

    if portfolio_share_pct is not None and portfolio_share_pct >= CONCENTRATION_WARNING_PCT:
        context.append(
            f"This position is {portfolio_share_pct:.0f}% of your total paper portfolio value -- "
            "a significant concentration, worth weighing against your own risk tolerance regardless "
            "of the signals above."
        )

    if action == "EXIT":
        freed = f"~${suggested_dollars:,.2f}" if suggested_dollars is not None else "the proceeds"
        context.append(
            f"Closing frees {freed}. The Ideal Portfolio Screener below ranks candidates by the "
            "same rules if you want somewhere to redeploy it -- but note that selling may realise "
            "a taxable gain or loss, which none of these rules account for."
        )

    if not rationale:
        rationale = ["No strong trend or momentum signals in either direction right now."]

    return PositionRecommendation(
        ticker=ticker,
        action=action,
        score=round(score, 2),
        suggested_pct=suggested_pct,
        suggested_shares=suggested_shares,
        suggested_dollars=suggested_dollars,
        rationale=rationale,
        context_notes=context,
    )
