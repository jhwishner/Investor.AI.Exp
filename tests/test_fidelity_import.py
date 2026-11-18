"""Tests for the Fidelity CSV import parser and ledger-application step."""

import io

import pytest

from investor_ai import fidelity_import, portfolio

USER = 1

_HEADER = "Run Date,Account,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date"


def _csv(*rows: str) -> io.BytesIO:
    return io.BytesIO(("\n".join((_HEADER, *rows))).encode())


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_fidelity_import.db")
    portfolio.init_db(db_path=path)
    return path


def test_parse_extracts_only_buy_sell_rows():
    csv_file = _csv(
        "01/15/2026,Z123,YOU BOUGHT COMMON STOCK,AAPL,APPLE INC,Cash,10,150.00,0,0,0,-1500.00,01/17/2026",
        "01/16/2026,Z123,DIVIDEND RECEIVED,AAPL,APPLE INC,Cash,,,,,,5.00,01/16/2026",
        "01/20/2026,Z123,YOU SOLD COMMON STOCK,AAPL,APPLE INC,Cash,-4,160.00,0,0,0,640.00,01/22/2026",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)
    assert list(trades["action"]) == ["BUY", "SELL"]
    assert list(trades["ticker"]) == ["AAPL", "AAPL"]
    assert list(trades["quantity"]) == [10, 4]  # SELL quantity normalized to positive
    assert list(trades["price"]) == [150.0, 160.0]
    assert list(trades["account"]) == ["Z123", "Z123"]


def test_parse_sorts_oldest_first():
    csv_file = _csv(
        "02/01/2026,Z123,YOU SOLD COMMON STOCK,MSFT,MICROSOFT,Cash,-2,300.00,0,0,0,600.00,02/03/2026",
        "01/01/2026,Z123,YOU BOUGHT COMMON STOCK,MSFT,MICROSOFT,Cash,5,280.00,0,0,0,-1400.00,01/03/2026",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)
    assert list(trades["trade_date"].dt.month) == [1, 2]


def test_parse_rejects_non_fidelity_csv():
    csv_file = io.BytesIO(b"foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        fidelity_import.parse_fidelity_csv(csv_file)


def test_parse_ignores_blank_action_rows():
    # Real exports have trailing footer/disclaimer rows with a blank Action
    # cell, which pandas reads as NaN (a float) rather than an empty string.
    csv_file = _csv(
        "01/15/2026,Z123,YOU BOUGHT COMMON STOCK,AAPL,APPLE INC,Cash,10,150.00,0,0,0,-1500.00,01/17/2026",
        ",,,,,,,,,,,,",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)
    assert len(trades) == 1
    assert trades.iloc[0]["ticker"] == "AAPL"


def test_import_applies_buy_then_sell(db_path):
    csv_file = _csv(
        "01/01/2026,Z123,YOU BOUGHT COMMON STOCK,AAPL,APPLE INC,Cash,10,150.00,0,0,0,-1500.00,01/03/2026",
        "01/10/2026,Z123,YOU SOLD COMMON STOCK,AAPL,APPLE INC,Cash,-4,160.00,0,0,0,640.00,01/12/2026",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)
    result = fidelity_import.import_transactions(trades, USER, db_path=db_path)

    assert result.imported == 2
    assert result.duplicates == 0
    assert result.failed == []

    positions = portfolio.get_open_positions(USER, db_path=db_path)
    row = positions[positions["ticker"] == "AAPL"].iloc[0]
    assert row["quantity"] == pytest.approx(6)


def test_import_skips_duplicates_on_reupload(db_path):
    csv_file = _csv("01/01/2026,Z123,YOU BOUGHT COMMON STOCK,AAPL,APPLE INC,Cash,10,150.00,0,0,0,-1500.00,01/03/2026")
    trades = fidelity_import.parse_fidelity_csv(csv_file)

    first = fidelity_import.import_transactions(trades, USER, db_path=db_path)
    assert first.imported == 1

    second = fidelity_import.import_transactions(trades, USER, db_path=db_path)
    assert second.imported == 0
    assert second.duplicates == 1


def test_import_records_failure_without_aborting_batch(db_path):
    # A SELL with no prior BUY in the ledger should fail gracefully, not
    # raise out of import_transactions.
    csv_file = _csv(
        "01/01/2026,Z123,YOU SOLD COMMON STOCK,AAPL,APPLE INC,Cash,-4,160.00,0,0,0,640.00,01/03/2026",
        "01/02/2026,Z123,YOU BOUGHT COMMON STOCK,MSFT,MICROSOFT,Cash,5,280.00,0,0,0,-1400.00,01/04/2026",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)
    result = fidelity_import.import_transactions(trades, USER, db_path=db_path)

    assert result.imported == 1  # MSFT buy succeeds
    assert len(result.failed) == 1  # AAPL sell fails
    assert "AAPL" in result.failed[0]


def test_prepare_preview_dataframe_normalizes_values():
    csv_file = _csv(
        "01/15/2026, z123 ,YOU BOUGHT COMMON STOCK,aapl,APPLE INC,Cash,10,150.00,0,0,0,-1500.00,01/17/2026",
    )
    trades = fidelity_import.parse_fidelity_csv(csv_file)

    preview = fidelity_import.prepare_preview_dataframe(trades)

    assert list(preview.columns) == ["trade_date", "account", "ticker", "action", "quantity", "price"]
    assert preview.iloc[0]["account"] == "z123"
    assert preview.iloc[0]["ticker"] == "AAPL"
    assert preview.iloc[0]["quantity"] == 10
    assert preview.iloc[0]["price"] == 150.0


def test_prepare_preview_dataframe_accepts_fractional_quantities():
    fractional = __import__("pandas").DataFrame(
        [{
            "trade_date": "2026-01-15",
            "account": "Roth IRA",
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 0.042,
            "price": 150.0,
        }, {
            "trade_date": "2026-01-16",
            "account": "Roth IRA",
            "ticker": "MSFT",
            "action": "SELL",
            "quantity": 0.5,
            "price": 250.0,
        }]
    )

    preview = fidelity_import.prepare_preview_dataframe(fractional)

    assert list(preview["quantity"]) == [0.042, 0.5]


def test_prepare_preview_dataframe_rejects_invalid_rows():
    invalid = __import__("pandas").DataFrame(
        [{
            "trade_date": "2026-01-15",
            "account": "",
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 0,
            "price": 150.0,
        }]
    )

    with pytest.raises(ValueError, match="account|quantity|price"):
        fidelity_import.prepare_preview_dataframe(invalid)
