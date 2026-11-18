"""Parser for Fidelity's transaction-history CSV export.

Fidelity has no public API for individuals to link a personal app to their
account, so the practical way to get real trades into this app's paper
ledger is: export transaction history from fidelity.com (Accounts & Trade >
Activity & Orders > Export), upload the CSV, and this module turns it into
BUY/SELL rows via investor_ai.portfolio.add_transaction.

Streamlit-free like the rest of investor_ai/ -- pages/3_Manage_Positions.py
owns the file uploader and result display.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from investor_ai import portfolio

# Fidelity's export uses these action phrases for actual buy/sell trades.
# Everything else (dividends, interest, transfers, journaled entries, fees)
# is intentionally left out -- this app's ledger only models BUY/SELL.
_SELL_MARKERS = ("YOU SOLD",)
_BUY_MARKERS = ("YOU BOUGHT", "REINVESTMENT")

_REQUIRED_COLUMNS = {"Run Date", "Account", "Action", "Symbol", "Quantity", "Price ($)"}


@dataclass
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    failed: list[str] = field(default_factory=list)


def _classify_action(action) -> str | None:
    # Real exports have blank/NaN Action cells (footer rows, disclaimer
    # text) -- pandas hands those through as raw floats (NaN), not strings.
    if not isinstance(action, str):
        return None
    action = action.upper()
    if any(marker in action for marker in _SELL_MARKERS):
        return "SELL"
    if any(marker in action for marker in _BUY_MARKERS):
        return "BUY"
    return None


def parse_fidelity_csv(file) -> pd.DataFrame:
    """Reads a Fidelity transaction-history export (path, bytes, or
    file-like object) and returns the actual BUY/SELL trade rows, normalized
    to this app's column names and sorted oldest-first -- so a later import
    step can apply BUYs before the SELLs that depend on them.

    Raises ValueError if the file doesn't look like a Fidelity transaction
    export (missing expected columns).
    """
    if isinstance(file, (bytes, bytearray)):
        file = io.BytesIO(file)

    df = pd.read_csv(file, skip_blank_lines=True, on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    if not _REQUIRED_COLUMNS.issubset(df.columns):
        missing = _REQUIRED_COLUMNS - set(df.columns)
        raise ValueError(
            "This doesn't look like a Fidelity transaction history export -- missing column(s): "
            f"{', '.join(sorted(missing))}."
        )

    trades = df.copy()
    trades["action"] = trades["Action"].map(_classify_action)
    trades = trades[trades["action"].notna()]

    trades["ticker"] = trades["Symbol"].astype(str).str.strip().str.upper()
    trades["account"] = trades["Account"].astype(str).str.strip()
    trades["quantity"] = pd.to_numeric(trades["Quantity"], errors="coerce").abs()
    trades["price"] = pd.to_numeric(
        trades["Price ($)"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    ).abs()
    trades["trade_date"] = pd.to_datetime(trades["Run Date"], errors="coerce")

    trades = trades[["trade_date", "account", "ticker", "action", "quantity", "price"]]
    trades = trades[
        trades["trade_date"].notna() & trades["ticker"].ne("") & (trades["quantity"] > 0) & trades["price"].notna()
    ]

    return trades.sort_values("trade_date").reset_index(drop=True)


def prepare_preview_dataframe(trades: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the rows that will be shown in the import preview."""
    if trades is None or trades.empty:
        return pd.DataFrame(columns=["trade_date", "account", "ticker", "action", "quantity", "price"])

    preview = trades.copy().reset_index(drop=True)
    required = ["trade_date", "account", "ticker", "action", "quantity", "price"]
    missing = [column for column in required if column not in preview.columns]
    if missing:
        raise ValueError(f"Preview rows are missing required fields: {', '.join(missing)}.")

    preview["trade_date"] = pd.to_datetime(preview["trade_date"], errors="coerce")
    preview["account"] = preview["account"].astype(str).str.strip()
    preview["ticker"] = preview["ticker"].astype(str).str.strip().str.upper()
    preview["action"] = preview["action"].astype(str).str.strip().str.upper()
    preview["quantity"] = pd.to_numeric(preview["quantity"], errors="coerce")
    preview["price"] = pd.to_numeric(preview["price"], errors="coerce")

    invalid_rows = (
        preview["trade_date"].isna()
        | preview["account"].eq("")
        | preview["ticker"].eq("")
        | ~preview["action"].isin(["BUY", "SELL"])
        | preview["quantity"].isna()
        | (preview["quantity"] <= 0)
        | preview["price"].isna()
        | (preview["price"] <= 0)
    )
    if invalid_rows.any():
        bad = preview.loc[invalid_rows, required].head(3).to_dict("records")
        detail = "; ".join(str(item) for item in bad) if bad else "unknown row"
        raise ValueError(f"Some import rows are invalid and need attention before importing: {detail}")

    return preview[required].sort_values("trade_date").reset_index(drop=True)


def import_transactions(trades: pd.DataFrame, user_id: int, db_path: str | None = None) -> ImportResult:
    """Applies parsed Fidelity trades to this user's ledger via
    portfolio.add_transaction. Rows that already exist (same ticker, action,
    quantity, price, date, and account) are skipped rather than duplicated,
    so re-uploading an overlapping export is safe. Rows that fail (e.g. a
    SELL that predates the corresponding BUY in this export) are recorded
    instead of aborting the rest of the batch.
    """
    result = ImportResult()
    existing = portfolio.list_transactions(user_id, db_path=db_path)

    for _, row in trades.iterrows():
        trade_date = row["trade_date"].date().isoformat()

        # Belt-and-suspenders against malformed rows reaching
        # portfolio.add_transaction (which assumes clean, validated input,
        # not raw spreadsheet data) -- a real-world export can still surface
        # a row that slipped past parse_fidelity_csv's own cleanup.
        if not isinstance(row["ticker"], str) or not row["ticker"] or not isinstance(row["account"], str) or not row["account"]:
            result.failed.append(f"{trade_date} {row['action']}: row has a missing ticker or account, skipped")
            continue

        is_duplicate = not existing.empty and (
            (existing["ticker"] == row["ticker"])
            & (existing["action"] == row["action"])
            & (existing["quantity"].round(4) == round(row["quantity"], 4))
            & (existing["price"].round(2) == round(row["price"], 2))
            & (existing["trade_date"] == trade_date)
            & (existing["account"] == row["account"])
        ).any()
        if is_duplicate:
            result.duplicates += 1
            continue

        try:
            portfolio.add_transaction(
                ticker=row["ticker"],
                action=row["action"],
                quantity=row["quantity"],
                price=row["price"],
                trade_date=trade_date,
                user_id=user_id,
                account=row["account"],
                notes="Imported from Fidelity",
                db_path=db_path,
            )
        except (portfolio.InsufficientHoldingsError, ValueError) as e:
            result.failed.append(f"{trade_date} {row['action']} {row['quantity']:g} {row['ticker']}: {e}")
        else:
            result.imported += 1
            # Keep the local view in sync so later rows in this same batch
            # see transactions just added (both for dedup and for holdings
            # checks inside add_transaction).
            existing = portfolio.list_transactions(user_id, db_path=db_path)

    return result
