"""Longer-term benchmark comparison for fund/ETF-style holdings.

Individual stocks get evaluated on Day/Week/Month/Year technical signals
(see signals.py + rules.py). Long-term, diversified holdings (ETFs, mutual
funds, index funds) are better evaluated against a broad-market benchmark
over multi-year windows -- a fund being "up" doesn't mean much on its own;
what matters is whether it kept pace with the market it's meant to track or
compete with.

Pure functions over price-history DataFrames -- no I/O, no Streamlit.
"""

from __future__ import annotations

import pandas as pd

BENCHMARK_TICKER = "SPY"
BENCHMARK_LABEL = "S&P 500 (SPY)"

# Long-term comparisons fetch this much history (see data.get_daily_history's
# `period` argument, which the Recommendations page passes explicitly for
# fund/ETF positions instead of the default 2y used elsewhere).
LONG_TERM_HISTORY_PERIOD = "5y"


def compute_total_and_annualized_return(
    df: pd.DataFrame,
) -> tuple[float | None, float | None, float | None]:
    """Total % return and annualized % return from the first to the last close
    in `df`, plus the number of years that window actually covers.

    Returns (None, None, None) if there isn't enough data to compute a return.
    Annualized return is None (but total return still returned) if the window
    covers less than a day.
    """
    if df.empty or len(df) < 2:
        return None, None, None

    first_close = float(df["Close"].iloc[0])
    last_close = float(df["Close"].iloc[-1])
    if first_close <= 0:
        return None, None, None

    years = (df.index[-1] - df.index[0]).days / 365.25
    total_return = (last_close / first_close - 1) * 100

    if years <= 0:
        return total_return, None, years

    annualized = ((1 + total_return / 100) ** (1 / years) - 1) * 100
    return total_return, annualized, years


def compare_to_benchmark(fund_df: pd.DataFrame, benchmark_df: pd.DataFrame) -> dict:
    """Compares a fund/ETF's return to a benchmark's return over the SAME
    window -- the benchmark series is sliced to start no earlier than the
    fund's own earliest available data, so a fund with only 2 years of
    history is compared against the benchmark's matching 2-year window, not
    a full 5 years.

    Returns {} if there isn't enough overlapping data to make a fair
    comparison (e.g. brand-new fund, or missing benchmark data).
    """
    if fund_df.empty or benchmark_df.empty:
        return {}

    start = fund_df.index[0]
    aligned_benchmark = benchmark_df[benchmark_df.index >= start]
    if aligned_benchmark.empty:
        return {}

    fund_total, fund_annualized, years = compute_total_and_annualized_return(fund_df)
    bench_total, bench_annualized, _ = compute_total_and_annualized_return(aligned_benchmark)

    if fund_total is None or bench_total is None:
        return {}

    outperformance = None
    if fund_annualized is not None and bench_annualized is not None:
        outperformance = fund_annualized - bench_annualized

    return {
        "years_covered": years,
        "fund_total_return": fund_total,
        "fund_annualized_return": fund_annualized,
        "benchmark_total_return": bench_total,
        "benchmark_annualized_return": bench_annualized,
        "outperformance_annualized_pct": outperformance,
    }
