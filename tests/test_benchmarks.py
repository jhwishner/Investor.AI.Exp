"""Tests for the long-term fund/ETF-vs-benchmark comparison logic."""

import pandas as pd
import pytest

from investor_ai import benchmarks


def _price_df(start, periods, start_price, end_price, freq="D"):
    """A simple straight-line price path from start_price to end_price."""
    index = pd.date_range(start, periods=periods, freq=freq)
    prices = [start_price + (end_price - start_price) * i / (periods - 1) for i in range(periods)]
    return pd.DataFrame({"Close": prices}, index=index)


def test_total_and_annualized_return_one_year_doubling():
    df = _price_df("2023-01-01", periods=366, start_price=100, end_price=200)
    total, annualized, years = benchmarks.compute_total_and_annualized_return(df)
    assert total == pytest.approx(100.0, rel=0.01)
    assert years == pytest.approx(1.0, rel=0.05)
    assert annualized == pytest.approx(100.0, rel=0.05)


def test_annualized_return_over_two_years():
    # Doubling over ~2 years -> annualized return should be well below the
    # 1-year figure (roughly sqrt(2)-1 ~= 41%, not 100%).
    df = _price_df("2022-01-01", periods=731, start_price=100, end_price=200)
    total, annualized, years = benchmarks.compute_total_and_annualized_return(df)
    assert total == pytest.approx(100.0, rel=0.01)
    assert years == pytest.approx(2.0, rel=0.05)
    assert annualized == pytest.approx(41.4, rel=0.1)


def test_empty_dataframe_returns_none():
    assert benchmarks.compute_total_and_annualized_return(pd.DataFrame()) == (None, None, None)


def test_compare_to_benchmark_outperformance():
    fund_df = _price_df("2022-01-01", periods=366, start_price=100, end_price=130)  # +30%
    bench_df = _price_df("2022-01-01", periods=366, start_price=100, end_price=110)  # +10%

    result = benchmarks.compare_to_benchmark(fund_df, bench_df)

    assert result["fund_total_return"] == pytest.approx(30.0, rel=0.01)
    assert result["benchmark_total_return"] == pytest.approx(10.0, rel=0.01)
    assert result["outperformance_annualized_pct"] > 0


def test_compare_to_benchmark_aligns_shorter_fund_history():
    # Benchmark has 5 years of history, fund only has the most recent 1 year --
    # the comparison should use only the overlapping (most recent) window.
    bench_df = _price_df("2019-01-01", periods=5 * 365, start_price=100, end_price=200)
    fund_df = _price_df("2023-01-01", periods=366, start_price=50, end_price=55)  # +10%

    result = benchmarks.compare_to_benchmark(fund_df, bench_df)

    assert result["years_covered"] == pytest.approx(1.0, rel=0.05)
    assert result["fund_total_return"] == pytest.approx(10.0, rel=0.01)
    # benchmark_total_return should reflect only its last ~1 year, not the full 5
    assert result["benchmark_total_return"] < 100.0


def test_compare_to_benchmark_empty_inputs():
    assert benchmarks.compare_to_benchmark(pd.DataFrame(), pd.DataFrame()) == {}


def test_compare_to_benchmark_no_overlap():
    fund_df = _price_df("2024-01-01", periods=366, start_price=100, end_price=110)
    bench_df = _price_df("2019-01-01", periods=366, start_price=100, end_price=110)  # ends before fund starts
    assert benchmarks.compare_to_benchmark(fund_df, bench_df) == {}
