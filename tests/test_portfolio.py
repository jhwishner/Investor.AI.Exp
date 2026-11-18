"""CRUD, P&L, and multi-tenant isolation tests for portfolio.py, using a real
temp-file SQLite DB.

NOTE: use a temp *file* path, not ':memory:' -- portfolio.py opens a fresh
connection per call, and a plain ':memory:' database is destroyed as soon as
the connection that created it closes.
"""

import pytest

from investor_ai import portfolio

USER = 1
OTHER_USER = 2


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_portfolio.db")
    portfolio.init_db(db_path=path)
    return path


def test_init_db_is_idempotent(db_path):
    portfolio.init_db(db_path=db_path)  # calling twice should not raise
    assert portfolio.list_transactions(USER, db_path=db_path).empty


def test_add_and_list_transaction(db_path):
    tx_id = portfolio.add_transaction("aapl", "BUY", 10, 150.0, "2024-01-01", USER, db_path=db_path)
    assert tx_id > 0
    txs = portfolio.list_transactions(USER, db_path=db_path)
    assert len(txs) == 1
    assert txs.iloc[0]["ticker"] == "AAPL"  # ticker is normalized to uppercase
    assert txs.iloc[0]["action"] == "BUY"


def test_sell_more_than_held_raises(db_path):
    portfolio.add_transaction("AAPL", "BUY", 5, 100.0, "2024-01-01", USER, db_path=db_path)
    with pytest.raises(portfolio.InsufficientHoldingsError):
        portfolio.add_transaction("AAPL", "SELL", 10, 110.0, "2024-01-02", USER, db_path=db_path)


def test_weighted_average_cost_basis(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.add_transaction("AAPL", "BUY", 10, 120.0, "2024-01-02", USER, db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    row = positions[positions["ticker"] == "AAPL"].iloc[0]
    assert row["quantity"] == pytest.approx(20)
    assert row["avg_cost"] == pytest.approx(110.0)  # (10*100 + 10*120) / 20


def test_sell_reduces_quantity_but_not_avg_cost(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.add_transaction("AAPL", "SELL", 4, 150.0, "2024-01-05", USER, db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    row = positions[positions["ticker"] == "AAPL"].iloc[0]
    assert row["quantity"] == pytest.approx(6)
    assert row["avg_cost"] == pytest.approx(100.0)


def test_fully_sold_position_excluded_from_open_positions(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.add_transaction("AAPL", "SELL", 10, 120.0, "2024-01-02", USER, db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    assert positions.empty


def test_delete_transaction(db_path):
    tx_id = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.delete_transaction(tx_id, USER, db_path=db_path)
    assert portfolio.list_transactions(USER, db_path=db_path).empty


def test_delete_nonexistent_transaction_raises(db_path):
    with pytest.raises(portfolio.TransactionNotFoundError):
        portfolio.delete_transaction(9999, USER, db_path=db_path)


def test_delete_transactions_bulk(db_path):
    id1 = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    id2 = portfolio.add_transaction("MSFT", "BUY", 5, 200.0, "2024-01-02", USER, db_path=db_path)
    id3 = portfolio.add_transaction("GOOG", "BUY", 2, 300.0, "2024-01-03", USER, db_path=db_path)

    deleted = portfolio.delete_transactions([id1, id2], USER, db_path=db_path)

    assert deleted == 2
    remaining = portfolio.list_transactions(USER, db_path=db_path)
    assert len(remaining) == 1
    assert remaining.iloc[0]["id"] == id3


def test_delete_transactions_ignores_other_users_rows(db_path):
    mine = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    theirs = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", OTHER_USER, db_path=db_path)

    deleted = portfolio.delete_transactions([mine, theirs], USER, db_path=db_path)

    assert deleted == 1  # only the row belonging to USER is removed
    assert not portfolio.list_transactions(OTHER_USER, db_path=db_path).empty


def test_delete_transactions_empty_list_is_noop(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    assert portfolio.delete_transactions([], USER, db_path=db_path) == 0
    assert len(portfolio.list_transactions(USER, db_path=db_path)) == 1


def test_portfolio_summary_computes_pl(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    summary = portfolio.get_portfolio_summary({"AAPL": 150.0}, USER, db_path=db_path)
    row = summary.iloc[0]
    assert row["market_value"] == pytest.approx(1500.0)
    assert row["cost_basis"] == pytest.approx(1000.0)
    assert row["unrealized_pl"] == pytest.approx(500.0)
    assert row["unrealized_pl_pct"] == pytest.approx(50.0)


def test_portfolio_summary_handles_missing_price(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    summary = portfolio.get_portfolio_summary({"AAPL": None}, USER, db_path=db_path)
    row = summary.iloc[0]
    assert row["market_value"] != row["market_value"]  # NaN != NaN -- confirms no fake number shown


def test_invalid_action_raises(db_path):
    with pytest.raises(ValueError):
        portfolio.add_transaction("AAPL", "HOLD", 1, 100.0, "2024-01-01", USER, db_path=db_path)


def test_risk_level_defaults_to_unspecified(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    assert positions.iloc[0]["risk_level"] == portfolio.DEFAULT_RISK_LEVEL


def test_risk_level_is_stored_and_listed(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, risk_level="Moonshot", db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    assert positions.iloc[0]["risk_level"] == "Moonshot"
    assert "Moonshot" in portfolio.list_risk_levels(USER, db_path=db_path)


def test_risk_level_reflects_most_recent_transaction(db_path):
    portfolio.add_transaction("AAPL", "BUY", 5, 100.0, "2024-01-01", USER, risk_level="Core", db_path=db_path)
    portfolio.add_transaction("AAPL", "BUY", 5, 110.0, "2024-01-05", USER, risk_level="Moonshot", db_path=db_path)
    positions = portfolio.get_open_positions(USER, db_path=db_path)
    row = positions[positions["ticker"] == "AAPL"].iloc[0]
    assert row["risk_level"] == "Moonshot"
    assert row["quantity"] == pytest.approx(10)  # quantity/cost math is unaffected by the tag


def test_get_open_positions_filters_by_risk_level(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, risk_level="Core", db_path=db_path)
    portfolio.add_transaction("TSLA", "BUY", 2, 200.0, "2024-01-01", USER, risk_level="Moonshot", db_path=db_path)

    core_only = portfolio.get_open_positions(USER, risk_level="Core", db_path=db_path)
    assert list(core_only["ticker"]) == ["AAPL"]

    moonshot_only = portfolio.get_open_positions(USER, risk_level="Moonshot", db_path=db_path)
    assert list(moonshot_only["ticker"]) == ["TSLA"]


def test_risk_level_filter_uses_full_history_for_quantity(db_path):
    # A position tagged inconsistently over time should still report its
    # TRUE net quantity when filtered by its current (most recent) tag --
    # filtering must not silently drop the earlier, differently-tagged BUY
    # from the quantity math.
    portfolio.add_transaction("AAPL", "BUY", 5, 100.0, "2024-01-01", USER, risk_level="Core", db_path=db_path)
    portfolio.add_transaction("AAPL", "BUY", 5, 110.0, "2024-01-05", USER, risk_level="Moonshot", db_path=db_path)

    filtered = portfolio.get_open_positions(USER, risk_level="Moonshot", db_path=db_path)
    assert filtered.iloc[0]["quantity"] == pytest.approx(10)

    # And the stale tag no longer matches anything, since the position's
    # current tag is whatever the most recent transaction set it to.
    assert portfolio.get_open_positions(USER, risk_level="Core", db_path=db_path).empty


def test_portfolio_summary_filters_by_risk_level(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, risk_level="Core", db_path=db_path)
    portfolio.add_transaction("TSLA", "BUY", 2, 200.0, "2024-01-01", USER, risk_level="Moonshot", db_path=db_path)
    summary = portfolio.get_portfolio_summary({"AAPL": 100.0, "TSLA": 200.0}, USER, risk_level="Moonshot", db_path=db_path)
    assert list(summary["ticker"]) == ["TSLA"]


def test_zero_quantity_raises(db_path):
    with pytest.raises(ValueError):
        portfolio.add_transaction("AAPL", "BUY", 0, 100.0, "2024-01-01", USER, db_path=db_path)


# --- Multi-tenant isolation --------------------------------------------------


def test_users_cannot_see_each_others_transactions(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.add_transaction("MSFT", "BUY", 5, 300.0, "2024-01-01", OTHER_USER, db_path=db_path)

    user_txs = portfolio.list_transactions(USER, db_path=db_path)
    other_txs = portfolio.list_transactions(OTHER_USER, db_path=db_path)

    assert set(user_txs["ticker"]) == {"AAPL"}
    assert set(other_txs["ticker"]) == {"MSFT"}


def test_open_positions_scoped_per_user(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    portfolio.add_transaction("AAPL", "BUY", 3, 90.0, "2024-01-01", OTHER_USER, db_path=db_path)

    user_positions = portfolio.get_open_positions(USER, db_path=db_path)
    other_positions = portfolio.get_open_positions(OTHER_USER, db_path=db_path)

    assert user_positions.iloc[0]["quantity"] == pytest.approx(10)
    assert other_positions.iloc[0]["quantity"] == pytest.approx(3)


def test_sell_validation_does_not_count_other_users_holdings(db_path):
    # OTHER_USER holds 100 shares -- USER holds none. USER selling even 1
    # share should fail on USER's own (empty) position, not succeed by
    # accidentally summing across both users' holdings.
    portfolio.add_transaction("AAPL", "BUY", 100, 100.0, "2024-01-01", OTHER_USER, db_path=db_path)
    with pytest.raises(portfolio.InsufficientHoldingsError):
        portfolio.add_transaction("AAPL", "SELL", 1, 100.0, "2024-01-02", USER, db_path=db_path)


def test_cannot_delete_another_users_transaction(db_path):
    tx_id = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    with pytest.raises(portfolio.TransactionNotFoundError):
        portfolio.delete_transaction(tx_id, OTHER_USER, db_path=db_path)
    # And it should still exist, untouched, for the rightful owner.
    assert len(portfolio.list_transactions(USER, db_path=db_path)) == 1


# --- Sub-accounts (e.g. "Roth IRA", "Robinhood") ----------------------------


def test_transactions_default_to_general_account(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)
    txs = portfolio.list_transactions(USER, db_path=db_path)
    assert txs.iloc[0]["account"] == portfolio.DEFAULT_ACCOUNT


def test_list_accounts_returns_general_by_default(db_path):
    assert portfolio.list_accounts(USER, db_path=db_path) == [portfolio.DEFAULT_ACCOUNT]


def test_list_accounts_returns_distinct_accounts_used(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, account="Roth IRA", db_path=db_path)
    portfolio.add_transaction("MSFT", "BUY", 5, 300.0, "2024-01-01", USER, account="Robinhood", db_path=db_path)
    assert portfolio.list_accounts(USER, db_path=db_path) == ["Robinhood", "Roth IRA"]


def test_same_ticker_kept_separate_across_accounts(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, account="Roth IRA", db_path=db_path)
    portfolio.add_transaction("AAPL", "BUY", 3, 90.0, "2024-01-01", USER, account="Robinhood", db_path=db_path)

    all_positions = portfolio.get_open_positions(USER, db_path=db_path)
    assert len(all_positions) == 2

    roth_positions = portfolio.get_open_positions(USER, account="Roth IRA", db_path=db_path)
    assert roth_positions.iloc[0]["quantity"] == pytest.approx(10)

    robinhood_positions = portfolio.get_open_positions(USER, account="Robinhood", db_path=db_path)
    assert robinhood_positions.iloc[0]["quantity"] == pytest.approx(3)


def test_sell_validation_is_scoped_to_the_account_being_sold_from(db_path):
    # 10 shares live in Roth IRA; Robinhood holds none of this ticker. Selling
    # from Robinhood should fail even though the user's combined AAPL
    # holdings (across both accounts) would technically cover it.
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, account="Roth IRA", db_path=db_path)
    with pytest.raises(portfolio.InsufficientHoldingsError):
        portfolio.add_transaction(
            "AAPL", "SELL", 1, 110.0, "2024-01-02", USER, account="Robinhood", db_path=db_path
        )


def test_claim_orphaned_transactions(db_path):
    # Simulate a pre-multi-user database: insert a transaction with no
    # user_id, exactly as a legacy row would look after the schema migration.
    tx_id = portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", USER, db_path=db_path)

    from investor_ai.db import get_connection

    conn = get_connection(db_path)
    conn.execute("UPDATE transactions SET user_id = NULL WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()

    assert portfolio.list_transactions(USER, db_path=db_path).empty  # orphaned, not visible to anyone yet

    claimed_count = portfolio.claim_orphaned_transactions(OTHER_USER, db_path=db_path)
    assert claimed_count == 1
    assert len(portfolio.list_transactions(OTHER_USER, db_path=db_path)) == 1
    assert portfolio.list_transactions(USER, db_path=db_path).empty
