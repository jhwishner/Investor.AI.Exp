"""Breakout scoring: which tickers look "coiled" for a large short-term move.

Same philosophy as the rest of this package -- fixed rules, fixed weights,
every number traceable back to a threshold. No model is fitted here and no
AI generates the wording.

WHAT THIS DOES AND DOESN'T CLAIM
--------------------------------
It scores how likely a ticker is to move *a lot*, not which direction. The
inputs (unusual volume, recent momentum, a tight volatility band, closing
strength) are associated with volatility expansion. Volatility is
two-sided: the same conditions precede large drops as large rallies. Treat
a high score as "worth reading the news on this one", not as a buy signal.

That distinction is why `backtest()` reports the rate of large *falls*
alongside large rises. A screen that selects volatile stocks will show a
high "hit rate" of +10% moves even with zero predictive skill, purely
because volatile stocks have fatter tails in both directions -- so the up
rate alone cannot distinguish skill from having simply picked volatile
names. The gap between the two rates is the part that would indicate a
directional edge, and it is usually close to zero. Expect that.

Indicator math is reused from investor_ai.indicators rather than
reimplemented, so there is exactly one RSI/Bollinger/volume implementation
in the codebase.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from investor_ai import config, indicators

# How much each component contributes to the composite score. These are a
# judgment call about which conditions best precede volatility expansion --
# they are NOT fitted to historical returns, deliberately: weights tuned on
# the same history you then backtest are how a screen ends up looking
# predictive without being predictive.
COMPONENT_WEIGHTS: dict[str, float] = {
    "volume_anomaly": 0.30,
    "momentum": 0.25,
    "volatility_squeeze": 0.20,
    "closing_strength": 0.15,
    "rsi_runway": 0.10,
}

# Component calibration.
VOLUME_RATIO_FOR_MAX = 4.0        # volume this many x its average scores 1.0
MOMENTUM_PCT_FOR_MAX = 25.0       # a ~1-month gain this large scores 1.0
MOMENTUM_WINDOW = 21              # trading days (~1 month)
SQUEEZE_LOOKBACK = 120            # bandwidth percentile is taken over this window
RSI_SWEET_SPOT = 60.0             # trending but not exhausted
RSI_SWEET_SPOT_HALF_WIDTH = 40.0  # RSI this far from the sweet spot scores 0
CLOSING_STRENGTH_DAYS = 5

# Minimum bars needed before a score means anything (the 120-bar squeeze
# percentile is the binding constraint).
MIN_BARS = 140


@dataclass
class BreakoutScore:
    ticker: str
    score: float                                     # 0-100 composite
    components: dict[str, float] = field(default_factory=dict)   # each 0-100
    rationale: list[str] = field(default_factory=list)
    has_data: bool = True


def _clip01(x: float) -> float:
    if x is None or not np.isfinite(x):
        return 0.0
    return float(min(1.0, max(0.0, x)))


def _volume_anomaly(df: pd.DataFrame) -> tuple[float, str | None]:
    """Latest volume against its own trailing average. Unusual participation
    tends to lead price."""
    ratio = indicators.volume_ratio(df["Volume"], window=config.VOLUME_AVG_WINDOW).dropna()
    if ratio.empty:
        return 0.0, None
    latest = float(ratio.iloc[-1])
    score = _clip01((latest - 1.0) / (VOLUME_RATIO_FOR_MAX - 1.0))
    if latest >= config.VOLUME_SPIKE_RATIO:
        return score, f"Volume is {latest:.1f}x its {config.VOLUME_AVG_WINDOW}-day average -- unusual participation."
    return score, None


def _momentum(df: pd.DataFrame) -> tuple[float, str | None]:
    """Recent price momentum. Short-horizon momentum is one of the few
    widely-replicated anomalies, though it reverses sharply and without
    warning."""
    mom = indicators.momentum(df["Close"], window=MOMENTUM_WINDOW).dropna()
    if mom.empty:
        return 0.0, None
    latest = float(mom.iloc[-1])
    score = _clip01(latest / MOMENTUM_PCT_FOR_MAX)
    if latest >= MOMENTUM_PCT_FOR_MAX / 2:
        return score, f"Up {latest:.1f}% over the last ~{MOMENTUM_WINDOW} trading days."
    return score, None


def _volatility_squeeze(df: pd.DataFrame) -> tuple[float, str | None]:
    """Bollinger bandwidth at the low end of its own recent range.

    Quiet periods tend to be followed by loud ones. NOTE the direction:
    a TIGHT band scores HIGH. (An earlier draft of this logic inverted the
    percentile and rewarded stocks whose volatility had already expanded --
    the opposite of the intent, so the direction is asserted in the tests.)
    """
    upper, mid, lower = indicators.bollinger_bands(df["Close"], window=config.BOLLINGER_WINDOW)
    width = ((upper - lower) / mid).dropna()
    if len(width) < 60:
        return 0.0, None
    window = width.tail(SQUEEZE_LOOKBACK)
    current = float(width.iloc[-1])
    # Fraction of the recent window BELOW the current reading -> a tight
    # band sits near the bottom, giving a low percentile and a high score.
    percentile = float((window < current).mean())
    score = _clip01(1.0 - percentile)
    if percentile <= 0.20:
        return score, (f"Bollinger bandwidth is in the tightest {percentile * 100:.0f}% of its recent range -- "
                       "a quiet period, which historically tends to precede a louder one.")
    return score, None


def _closing_strength(df: pd.DataFrame) -> tuple[float, str | None]:
    """Where price closes inside each day's range, averaged over recent days.
    Persistent closes near the high indicate buyers absorbing supply."""
    recent = df.tail(CLOSING_STRENGTH_DAYS)
    span = (recent["High"] - recent["Low"]).replace(0, np.nan)
    position = ((recent["Close"] - recent["Low"]) / span).mean()
    if position is None or not np.isfinite(position):
        return 0.5, None
    score = _clip01(float(position))
    if score >= 0.70:
        return score, (f"Closing in the top {score * 100:.0f}% of its daily range on average "
                       f"over the last {CLOSING_STRENGTH_DAYS} sessions.")
    return score, None


def _rsi_runway(df: pd.DataFrame) -> tuple[float, str | None]:
    """RSI near the sweet spot: trending, but with room left before the
    conventional overbought zone."""
    rsi = indicators.rsi(df["Close"], window=config.RSI_WINDOW).dropna()
    if rsi.empty:
        return 0.5, None
    latest = float(rsi.iloc[-1])
    score = _clip01(1.0 - abs(latest - RSI_SWEET_SPOT) / RSI_SWEET_SPOT_HALF_WIDTH)
    if latest >= config.RSI_OVERBOUGHT:
        return score, f"RSI is {latest:.0f} -- already extended, less runway before the overbought zone."
    return score, None


_COMPONENTS = {
    "volume_anomaly": _volume_anomaly,
    "momentum": _momentum,
    "volatility_squeeze": _volatility_squeeze,
    "closing_strength": _closing_strength,
    "rsi_runway": _rsi_runway,
}


def score_breakout(ticker: str, daily_df: pd.DataFrame) -> BreakoutScore:
    """Composite 0-100 "likely to move a lot soon" score for one ticker.

    Never raises: too little history (or an empty frame from the data layer)
    returns has_data=False with a zero score, matching how the rest of the
    app treats missing data.
    """
    if daily_df is None or daily_df.empty or len(daily_df) < MIN_BARS:
        return BreakoutScore(
            ticker=ticker,
            score=0.0,
            has_data=False,
            rationale=[f"Needs at least {MIN_BARS} trading days of history to score; not enough available."],
        )

    total = 0.0
    components: dict[str, float] = {}
    rationale: list[str] = []
    for name, fn in _COMPONENTS.items():
        value, message = fn(daily_df)
        components[name] = round(value * 100, 1)
        total += COMPONENT_WEIGHTS[name] * value
        if message:
            rationale.append(message)

    if not rationale:
        rationale.append("No individual component stands out right now; nothing unusual in volume, trend, or range.")

    return BreakoutScore(
        ticker=ticker,
        score=round(total * 100, 1),
        components=components,
        rationale=rationale,
    )


# --- Backtest ---------------------------------------------------------------


@dataclass
class BacktestResult:
    picks: int
    hold_days: int
    big_move_pct: float
    model_mean_return_pct: float
    random_mean_return_pct: float
    model_up_rate: float       # share of picks that gained >= big_move_pct
    model_down_rate: float     # share that fell >= big_move_pct  <-- the honest half
    random_up_rate: float
    random_down_rate: float
    model_worst_pct: float
    verdict: str

    @property
    def model_directional_edge(self) -> float:
        """Up-rate minus down-rate. This -- not the up rate alone -- is the
        part that would indicate the screen picks direction rather than
        merely picking volatility."""
        return self.model_up_rate - self.model_down_rate

    @property
    def random_directional_edge(self) -> float:
        return self.random_up_rate - self.random_down_rate


def _align(histories: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Restrict every ticker to the trading days they all share.

    Without this, walking a positional index `i` across separately-fetched
    frames silently compares different calendar dates whenever one ticker
    is missing a session (halt, late listing, different venue calendar).
    """
    usable = {t: df for t, df in histories.items()
              if df is not None and not df.empty and "Close" in df}
    if not usable:
        return {}
    common = None
    for df in usable.values():
        common = df.index if common is None else common.intersection(df.index)
    if common is None or len(common) == 0:
        return {}
    return {t: df.loc[common] for t, df in usable.items()}


def _verdict(model_edge: float, random_edge: float, model_up: float, random_up: float) -> str:
    """Fixed-rule interpretation -- template text, same as the rest of the app."""
    lifted_volatility = model_up > random_up + 0.02
    edge_gap = model_edge - random_edge

    if edge_gap > 0.05:
        head = ("The screen's large gains outpaced its large losses by more than the random baseline did. "
                "That is what a directional edge would look like -- but on a single universe and a "
                "short history it is just as consistent with luck. Re-run it on a different period "
                "before believing it.")
    elif edge_gap < -0.05:
        head = ("The screen's large losses outpaced its large gains by more than the random baseline did -- "
                "i.e. picks moved a lot and, on this sample, more often downward.")
    else:
        head = ("No directional edge: large gains and large losses came out roughly balanced, "
                "the same as picking at random from this universe.")

    if lifted_volatility:
        tail = (" The screen did raise the rate of big moves in BOTH directions, which means it is "
                "successfully selecting volatile stocks. That is a real property, but on its own it "
                "is not an ability to predict which way they go.")
    else:
        tail = " The screen did not meaningfully raise the rate of big moves versus random selection."
    return head + tail


def backtest(
    histories: dict[str, pd.DataFrame],
    hold_days: int = 10,
    big_move_pct: float = 10.0,
    top_n: int = 5,
    warmup_bars: int = MIN_BARS,
    seed: int = 42,
) -> BacktestResult | None:
    """Walk-forward test of the screen against random selection.

    At each test date the score is computed from data available up to and
    including that bar; the position is then entered at the NEXT bar's close
    and held `hold_days`. That one-bar delay matters -- scoring and entering
    on the same close assumes a fill at a price you could only act on after
    seeing it.

    Returns None if there isn't enough shared history to run a single
    window. Costs and slippage are NOT modelled; on thinly-traded names a
    round trip can eat a meaningful part of these numbers.
    """
    aligned = _align(histories)
    if len(aligned) < top_n * 2:
        return None
    length = len(next(iter(aligned.values())))
    last_start = length - hold_days - 2
    if last_start <= warmup_bars:
        return None

    rng = random.Random(seed)
    model_returns: list[float] = []
    random_returns: list[float] = []

    for i in range(warmup_bars, last_start, hold_days):
        scored: list[tuple[str, float, float]] = []
        for ticker, df in aligned.items():
            result = score_breakout(ticker, df.iloc[: i + 1])
            if not result.has_data:
                continue
            entry = float(df["Close"].iloc[i + 1])       # next bar's close
            exit_ = float(df["Close"].iloc[i + 1 + hold_days])
            if entry <= 0 or not np.isfinite(entry) or not np.isfinite(exit_):
                continue
            scored.append((ticker, result.score, (exit_ / entry - 1.0) * 100.0))
        if len(scored) < top_n * 2:
            continue
        scored.sort(key=lambda row: row[1], reverse=True)
        model_returns.extend(r for _, _, r in scored[:top_n])
        random_returns.extend(r for _, _, r in rng.sample(scored, top_n))

    if not model_returns:
        return None

    model = np.asarray(model_returns)
    baseline = np.asarray(random_returns)
    model_up = float((model >= big_move_pct).mean())
    model_down = float((model <= -big_move_pct).mean())
    random_up = float((baseline >= big_move_pct).mean())
    random_down = float((baseline <= -big_move_pct).mean())

    return BacktestResult(
        picks=int(model.size),
        hold_days=hold_days,
        big_move_pct=big_move_pct,
        model_mean_return_pct=round(float(model.mean()), 2),
        random_mean_return_pct=round(float(baseline.mean()), 2),
        model_up_rate=model_up,
        model_down_rate=model_down,
        random_up_rate=random_up,
        random_down_rate=random_down,
        model_worst_pct=round(float(model.min()), 2),
        verdict=_verdict(model_up - model_down, random_up - random_down, model_up, random_up),
    )
