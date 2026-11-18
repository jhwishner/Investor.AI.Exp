"""Central configuration: file paths, cache lifetimes, and rule thresholds.

Keeping these in one place means tuning the app (e.g. changing what counts
as "overbought") never requires touching the fetch, indicator, or rule logic.
"""

from pathlib import Path

# --- Paths -----------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "portfolio.db"
LOG_PATH = LOG_DIR / "app.log"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --- Cache TTLs (seconds) ---------------------------------------------------
# This is an end-of-day research tool, not a real-time terminal -- TTLs are
# generous on purpose to avoid hammering Yahoo Finance on every Streamlit rerun.
# CACHE_TTL_DAILY is aligned to the 30-minute auto-refresh on the
# Recommendations/Portfolio/Ticker Analysis pages (see live.py) so each
# auto-refresh tick has a real chance of showing newly-fetched data.

CACHE_TTL_INTRADAY = 5 * 60        # 5 minutes
CACHE_TTL_DAILY = 30 * 60          # 30 minutes
CACHE_TTL_FUNDAMENTALS = 24 * 60 * 60  # 24 hours

# --- History window used for the daily fetch -------------------------------
# Week/Month/Year timeframes all slice this single fetch rather than issuing
# separate network calls. 2 years gives enough lookback for SMA(200).

DAILY_HISTORY_PERIOD = "2y"
INTRADAY_HISTORY_PERIOD = "5d"
INTRADAY_HISTORY_INTERVAL = "15m"

# --- Indicator parameters ---------------------------------------------------

RSI_WINDOW = 14
SMA_SHORT = 10
SMA_MEDIUM = 50
SMA_LONG = 200
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_WINDOW = 20
BOLLINGER_NUM_STD = 2
VOLATILITY_WINDOW = 20
VOLATILITY_TRADING_DAYS = 252
VOLUME_AVG_WINDOW = 20

# --- Rule thresholds ---------------------------------------------------------
# Centralized so tuning "what counts as overbought" doesn't require touching
# rules.py itself.

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
FIFTY_TWO_WEEK_PROXIMITY_PCT = 5.0       # within this % of 52w high/low
HIGH_VOLATILITY_ANNUALIZED_PCT = 40.0    # vs. broad-market baseline of ~15-20%
VOLUME_SPIKE_RATIO = 2.0                 # today's volume vs 20-day average
LARGE_DAILY_MOVE_PCT = 5.0               # single-day % move considered "large"

# --- Fama-French-inspired factor thresholds ----------------------------------
# Conventional size/value buckets applied to one stock at a time -- NOT the
# original paper's NYSE-decile breakpoints (those need the full market
# cross-section to compute). See investor_ai/factor_model.py.

SMALL_CAP_MAX = 2e9    # market cap below this = "small-cap"
MID_CAP_MAX = 10e9     # market cap below this (and above SMALL_CAP_MAX) = "mid-cap"
VALUE_PB_MAX = 1.0     # price-to-book below this = "value" territory
GROWTH_PB_MIN = 3.0    # price-to-book above this = "growth"/expensive territory

# --- Power/AI-infrastructure sector thresholds --------------------------------
# See investor_ai/power_sector.py -- inspired by "Power 2026" (Neel Somani),
# an educational primer on electricity markets and power trading.

NATGAS_TICKER = "NG=F"                  # Henry Hub natural gas futures, free via yfinance
NATGAS_MARGIN_PRESSURE_PCT = 10.0       # a monthly move at least this large is "notable"

# --- Closing a position outright ---------------------------------------------
# The difference between "trim" and "close entirely" is structural, not just
# a worse score: a position exits when the short-term signals are negative
# AND there is a standing reason to doubt the holding itself -- it has
# lagged a plain index fund over a real track record, or it is too small a
# slice to affect returns while still needing to be tracked.

EXIT_MIN_YEARS = 2.0              # too little history to judge a fund on
EXIT_BENCHMARK_LAG_PCT = -2.0     # annualized points behind the benchmark
EXIT_SEVERE_LAG_PCT = -4.0        # a lag this wide stands on its own
NEGLIGIBLE_POSITION_PCT = 2.0     # below this share of the portfolio it is clutter

# --- Misc --------------------------------------------------------------------

DISCLAIMER = (
    "This is a paper/educational tool, not financial advice. "
    "Data may be delayed or wrong -- verify anything important before acting on it."
)
