"""Tests for the pure (non-network) parts of data.py."""

from investor_ai import data


def test_classify_etf_as_fund():
    assert data.classify_asset_type({"quote_type": "ETF"}) == "fund"


def test_classify_mutualfund_as_fund():
    assert data.classify_asset_type({"quote_type": "MUTUALFUND"}) == "fund"


def test_classify_index_as_fund():
    assert data.classify_asset_type({"quote_type": "INDEX"}) == "fund"


def test_classify_equity_as_stock():
    assert data.classify_asset_type({"quote_type": "EQUITY"}) == "stock"


def test_classify_lowercase_quote_type():
    assert data.classify_asset_type({"quote_type": "etf"}) == "fund"


def test_classify_missing_quote_type_defaults_to_stock():
    assert data.classify_asset_type({}) == "stock"
    assert data.classify_asset_type({"quote_type": None}) == "stock"
