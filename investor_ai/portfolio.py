"""Virtual/paper portfolio: SQLite-backed transaction ledger and P&L math.

Design choice: an append-only ledger of BUY/SELL transactions, not a mutable
"positions" table. This correctly supports multiple buys/sells of the same
ticker over time, keeps the math auditable (every number can be traced back
to a row), and avoids read-modify-write races across Streamlit's
rerun-the-whole-script execution model.

Multi-user: every transaction belongs to exactly one account (see
investor_ai/auth.py), via the `user_id` column. Every function that reads or
writes transactions takes `user_id` as a required argument and scopes its
query by it -- there is deliberately no "give me everyone's data" function,
so a bug here fails closed (you see nothing) rather than open (you see
someone else's portfolio).

Cost basis is weighted-average (not FIFO/LIFO) -- this is a tracking tool,
not a tax-reporting tool. See README for that caveat.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from investor_ai.db import get_connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
    quantity REAL NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price >= 0),
    trade_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);
"""

# Sub-portfolio label (e.g. "Roth IRA", "Robinhood", "401k") a transaction is
# grouped under, distinct from `user_id` (which account/person logged in).
# One login can hold several of these; every transaction belongs to exactly
# one. Rows from before this feature existed -- and anyone who never bothers
# naming an account -- fall back to this single bucket.
DEFAULT_ACCOUNT = "General"

# Free-form risk tier (e.g. "Core", "Moonshot") a transaction is tagged
# with -- purely descriptive, orthogonal to `account`. Lets the same
# account hold both steady and speculative positions while still being
# filterable by intent (see get_open_positions' risk_level column).
DEFAULT_RISK_LEVEL = "Unspecified"


def init_db(db_path: str | None = None) -> None:
    """Create the transactions table if it doesn't already exist, and add the
    `user_id`/`account`/`risk_level` columns if this is a database from
    before those features existed. Idempotent either way.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(_SCHEMA)
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)")}
        if "user_id" not in existing_columns:
            conn.execute("ALTER TABLE transactions ADD COLUMN user_id INTEGER")
        if "account" not in existing_columns:
            conn.execute(
                f"ALTER TABLE transactions ADD COLUMN account TEXT NOT NULL DEFAULT '{DEFAULT_ACCOUNT}'"
            )
        if "risk_level" not in existing_columns:
            conn.execute(
                f"ALTER TABLE transactions ADD COLUMN risk_level TEXT NOT NULL DEFAULT '{DEFAULT_RISK_LEVEL}'"
            )
        conn.commit()
    finally:
        conn.close()


class InsufficientHoldingsError(ValueError):
    """Raised when a SELL would take a ticker's held quantity negative."""


class TransactionNotFoundError(ValueError):
    """Raised when deleting a transaction that doesn't exist, or doesn't
    belong to the requesting user -- deliberately the same error for both,
    so a caller can't use the error to fish for other users' transaction IDs.
    """


def get_position_quantity(
    ticker: str, user_id: int, account: str | None = None, db_path: str | None = None
) -> float:
    """Net quantity currently held for a ticker by this user (0 if none / fully
    sold). Pass `account` to scope this to a single sub-account instead of
    this user's combined holdings across all of their accounts.
    """
    conn = get_connection(db_path)
    try:
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN action='BUY' THEN quantity ELSE -quantity END), 0) AS net_qty
            FROM transactions WHERE ticker = ? AND user_id = ?
            """
        params = [ticker.upper(), user_id]
        if account:
            query += " AND account = ?"
            params.append(account.strip())
        row = conn.execute(query, params).fetchone()
        return float(row["net_qty"]) if row else 0.0
    finally:
        conn.close()


def add_transaction(
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    trade_date: str | date,
    user_id: int,
    notes: str = "",
    account: str = DEFAULT_ACCOUNT,
    risk_level: str = DEFAULT_RISK_LEVEL,
    db_path: str | None = None,
) -> int:
    """Log a BUY or SELL for the given user, under the given sub-account
    (e.g. "Roth IRA", "Robinhood"). Returns the new row's id.

    `account` is purely a user-chosen grouping label, not a security
    boundary -- unlike `user_id`, it is not used to restrict what a caller
    can see or sell against (holdings are still tracked per-user, across all
    of that user's accounts combined, since it's one real net worth).

    `risk_level` is a second, independent free-form label (e.g. "Core",
    "Moonshot") for tagging intent -- a single account can mix risk tiers,
    and a single tier can span accounts.

    Raises InsufficientHoldingsError if a SELL would take that user's
    position negative -- this is enforced here (not just in the UI) so the
    ledger can never end up in an inconsistent state regardless of caller.
    """
    ticker = ticker.strip().upper()
    action = action.strip().upper()
    account = account.strip() or DEFAULT_ACCOUNT
    risk_level = risk_level.strip() or DEFAULT_RISK_LEVEL
    if action not in ("BUY", "SELL"):
        raise ValueError(f"action must be 'BUY' or 'SELL', got {action!r}")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if price < 0:
        raise ValueError("price cannot be negative")

    if action == "SELL":
        # Scoped to this specific account, not the user's combined holdings
        # across all accounts -- otherwise a sell logged under one account
        # (e.g. "Robinhood") could be validated against shares that actually
        # live in a different one (e.g. "Roth IRA"), leaving that other
        # account's ledger in an inconsistent state.
        held = get_position_quantity(ticker, user_id, account, db_path)
        if quantity > held + 1e-9:
            raise InsufficientHoldingsError(
                f"Cannot sell {quantity} shares of {ticker} in '{account}'; only {held} are held there."
            )

    if isinstance(trade_date, date):
        trade_date = trade_date.isoformat()

    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO transactions
                (ticker, action, quantity, price, trade_date, notes, created_at, user_id, account, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                action,
                quantity,
                price,
                trade_date,
                notes,
                datetime.now(timezone.utc).isoformat(),
                user_id,
                account,
                risk_level,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete_transaction(transaction_id: int, user_id: int, db_path: str | None = None) -> None:
    """Deletes a transaction, but only if it belongs to `user_id`.

    Raises TransactionNotFoundError if the id doesn't exist or belongs to
    someone else -- callers should show a generic "not found" message either
    way, not distinguish the two (that distinction is exactly what would let
    someone probe for other users' transaction ids).
    """
    conn = get_connection(db_path)
    try:
        cur = conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id))
        conn.commit()
        if cur.rowcount == 0:
            raise TransactionNotFoundError(f"No transaction {transaction_id} found for this account.")
    finally:
        conn.close()


def delete_transactions(transaction_ids: list[int], user_id: int, db_path: str | None = None) -> int:
    """Deletes multiple transactions belonging to `user_id` in a single
    statement -- one DB round-trip instead of one per id. Rows that don't
    exist or belong to someone else are silently skipped (same fail-closed
    behavior as delete_transaction, just without raising for a partial
    match). Returns how many rows were actually deleted, so callers can
    compare it to len(transaction_ids) if they need to know about a partial
    delete.
    """
    if not transaction_ids:
        return 0
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" for _ in transaction_ids)
        cur = conn.execute(
            f"DELETE FROM transactions WHERE id IN ({placeholders}) AND user_id = ?",
            (*transaction_ids, user_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def claim_orphaned_transactions(user_id: int, db_path: str | None = None) -> int:
    """Assigns any legacy transactions with no owner (user_id IS NULL) to the
    given user. Returns how many rows were updated.

    Used exactly once per database, right after the very first account is
    ever created (see auth.create_user) -- migrates data logged before
    multi-user support existed forward to that first account, rather than
    orphaning or losing it.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.execute("UPDATE transactions SET user_id = ? WHERE user_id IS NULL", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_accounts(user_id: int, db_path: str | None = None) -> list[str]:
    """Every distinct sub-account name this user has logged a transaction
    under, alphabetically. Always returns at least [DEFAULT_ACCOUNT] so
    callers (e.g. the "add position" dropdown) always have something to
    show, even for a brand-new user with no transactions yet.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT account FROM transactions WHERE user_id = ? ORDER BY account COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        accounts = [row["account"] for row in rows]
        return accounts or [DEFAULT_ACCOUNT]
    finally:
        conn.close()


def list_risk_levels(user_id: int, db_path: str | None = None) -> list[str]:
    """Every distinct risk tag this user has logged a transaction under,
    alphabetically. Always returns at least [DEFAULT_RISK_LEVEL], mirroring
    list_accounts.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT risk_level FROM transactions WHERE user_id = ? ORDER BY risk_level COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        risk_levels = [row["risk_level"] for row in rows]
        return risk_levels or [DEFAULT_RISK_LEVEL]
    finally:
        conn.close()


def list_transactions(
    user_id: int, ticker: str | None = None, account: str | None = None, db_path: str | None = None
) -> pd.DataFrame:
    conn = get_connection(db_path)
    try:
        conditions = ["user_id = ?"]
        params: list = [user_id]
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker.strip().upper())
        if account:
            conditions.append("account = ?")
            params.append(account.strip())
        query = f"SELECT * FROM transactions WHERE {' AND '.join(conditions)} ORDER BY trade_date DESC, id DESC"
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def get_open_positions(
    user_id: int, account: str | None = None, risk_level: str | None = None, db_path: str | None = None
) -> pd.DataFrame:
    """Net quantity and weighted-average cost basis per (account, ticker)
    (BUYs only sold-down), for this user only. Pass `account` to restrict to
    a single sub-account; otherwise every one of this user's accounts is
    included, each ticker kept separate per account.

    Weighted-average cost basis: average price paid for currently-held
    shares, computed as (sum of BUY cost) / (sum of BUY quantity) -- SELLs
    reduce quantity but do not change the average cost of what remains.
    This is a simplification appropriate for tracking, not for tax lots.

    Also includes a `risk_level` column: since risk tags live on individual
    transactions (not positions), this is the tag of the most recent
    transaction in the group (by trade_date, then id) -- purely descriptive,
    it plays no part in the quantity/cost math above. Retag consistently for
    a given (account, ticker) if you want it to stay meaningful.

    Pass `risk_level` to keep only positions whose most-recent tag matches.
    Unlike `account` (a true partition of the ledger, safe to filter before
    aggregating), `risk_level` is filtered *after* quantity/cost is computed
    from the full transaction history -- otherwise a position built from
    transactions logged under different tags over time would show the wrong
    quantity depending on which tag you filtered by.
    """
    all_tx = list_transactions(user_id, account=account, db_path=db_path)
    if all_tx.empty:
        return pd.DataFrame(columns=["account", "ticker", "quantity", "avg_cost", "risk_level"])

    rows = []
    for (acct, ticker), group in all_tx.groupby(["account", "ticker"]):
        buys = group[group["action"] == "BUY"]
        sells = group[group["action"] == "SELL"]
        buy_qty = buys["quantity"].sum()
        sell_qty = sells["quantity"].sum()
        net_qty = buy_qty - sell_qty
        if net_qty <= 1e-9:
            continue
        avg_cost = (buys["quantity"] * buys["price"]).sum() / buy_qty if buy_qty > 0 else 0.0
        most_recent = group.sort_values(["trade_date", "id"]).iloc[-1]
        rows.append(
            {
                "account": acct,
                "ticker": ticker,
                "quantity": net_qty,
                "avg_cost": avg_cost,
                "risk_level": most_recent["risk_level"],
            }
        )

    positions = pd.DataFrame(rows, columns=["account", "ticker", "quantity", "avg_cost", "risk_level"])
    if risk_level:
        positions = positions[positions["risk_level"] == risk_level].reset_index(drop=True)
    return positions


def get_portfolio_summary(
    current_prices: dict[str, float | None],
    user_id: int,
    account: str | None = None,
    risk_level: str | None = None,
    db_path: str | None = None,
) -> pd.DataFrame:
    """This user's open positions enriched with market value and unrealized P&L.
    Pass `account` to restrict to a single sub-account, or `risk_level` to
    restrict to positions most recently tagged with that risk tier.

    current_prices maps ticker -> current price (or None if unavailable --
    those rows get NaN market value/P&L rather than a misleading number).
    """
    positions = get_open_positions(user_id, account=account, risk_level=risk_level, db_path=db_path)
    if positions.empty:
        return positions.assign(current_price=[], market_value=[], unrealized_pl=[], unrealized_pl_pct=[])

    positions = positions.copy()
    positions["current_price"] = positions["ticker"].map(lambda t: current_prices.get(t))
    positions["market_value"] = positions["quantity"] * positions["current_price"]
    positions["cost_basis"] = positions["quantity"] * positions["avg_cost"]
    positions["unrealized_pl"] = positions["market_value"] - positions["cost_basis"]
    positions["unrealized_pl_pct"] = (positions["unrealized_pl"] / positions["cost_basis"]) * 100
    return positions


# Trading-day lookback windows used for the portfolio-level Day/Week/Month/Year
# performance breakdown.
_TIMEFRAME_LOOKBACK_DAYS = {"day": 1, "week": 5, "month": 21, "year": 252}


def get_portfolio_performance_by_timeframe(
    current_prices: dict[str, float | None],
    price_history_lookup: dict[str, pd.Series],
    user_id: int,
    account: str | None = None,
    risk_level: str | None = None,
    db_path: str | None = None,
) -> dict[str, dict]:
    """This user's portfolio-level $ / % change over each timeframe. Pass
    `account` to restrict this to a single sub-account, or `risk_level` to
    restrict to positions most recently tagged with that risk tier.

    price_history_lookup maps ticker -> a Series of daily closes (as returned
    by data.get_daily_history(...)["Close"]) so this function does no
    network I/O itself.

    NOTE -- v1 approximation: this assumes *currently-held* quantities were
    held constant across each lookback window. It does not replay the full
    transaction history day-by-day, so a position bought mid-window will
    show a distorted "since" comparison. Good enough for a research/paper
    tool; flagged here and in the UI as a known simplification.
    """
    positions = get_open_positions(user_id, account=account, risk_level=risk_level, db_path=db_path)
    results: dict[str, dict] = {}

    for timeframe, lookback in _TIMEFRAME_LOOKBACK_DAYS.items():
        value_now = 0.0
        value_then = 0.0
        any_data = False

        for _, pos in positions.iterrows():
            ticker = pos["ticker"]
            qty = pos["quantity"]
            price_now = current_prices.get(ticker)
            history = price_history_lookup.get(ticker)

            if price_now is None or history is None or history.empty:
                continue

            idx = -1 - lookback
            if abs(idx) > len(history):
                price_then = float(history.iloc[0])
            else:
                price_then = float(history.iloc[idx])

            value_now += qty * price_now
            value_then += qty * price_then
            any_data = True

        if not any_data or value_then == 0:
            results[timeframe] = {"value_now": value_now, "value_then": None, "change": None, "change_pct": None}
        else:
            change = value_now - value_then
            results[timeframe] = {
                "value_now": value_now,
                "value_then": value_then,
                "change": change,
                "change_pct": (change / value_then) * 100,
            }

    return results
