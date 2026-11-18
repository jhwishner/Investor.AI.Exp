"""Shared SQLite connection helper, used by both portfolio.py and auth.py --
they're separate tables in the same physical database file
(config.DB_PATH), so both go through the same connection logic.
"""

from __future__ import annotations

import sqlite3

from investor_ai import config


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection to the given DB file (defaults to config.DB_PATH).

    Every public function in portfolio.py/auth.py opens and closes its own
    short-lived connection -- this fits Streamlit's rerun-the-whole-script
    model, where there's no natural place to hold a long-lived connection
    object open.

    In tests, pass a real temporary file path (e.g. pytest's tmp_path), not
    ':memory:' -- a plain ':memory:' database only lives as long as the
    single connection that created it, so it would appear empty on every
    subsequent call in this connection-per-call design.
    """
    path = db_path or str(config.DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
