"""Simple, self-contained username/password accounts.

No external identity provider (no "Sign in with Google") and no third-party
auth library -- consistent with the rest of this app never calling out to
anything beyond free market data. Passwords are hashed with PBKDF2-HMAC-SHA256
(stdlib `hashlib`, no extra dependency), a per-user random salt, and a high
iteration count; only the salt and hash are ever stored, never the password
itself.

This module only knows about accounts. It has no idea what a "position" or
"transaction" is -- see portfolio.py for that, which every function here
scopes by the user_id created/authenticated here.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone

from investor_ai import portfolio
from investor_ai.db import get_connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 8


class UsernameTakenError(ValueError):
    """Raised when signing up with a username that's already in use."""


class WeakCredentialsError(ValueError):
    """Raised when a username/password fails basic validation."""


def init_db(db_path: str | None = None) -> None:
    """Create the users table if it doesn't already exist. Idempotent.

    Also ensures the transactions table exists (portfolio.init_db) --
    create_user() can claim orphaned legacy transactions on the very first
    signup (see below), which requires that table to already be there. Pages
    call portfolio.init_db() too, but auth.init_db() can't rely on running
    after that -- require_login() is typically called before a page's own
    portfolio.init_db(), so this needs to be self-sufficient.
    """
    portfolio.init_db(db_path)

    conn = get_connection(db_path)
    try:
        conn.execute(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). Generates a new random salt if none given."""
    if salt is None:
        salt = os.urandom(16)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), hash_bytes.hex()


def _validate_credentials(username: str, password: str) -> None:
    if not username or not username.strip():
        raise WeakCredentialsError("Username can't be empty.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakCredentialsError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def create_user(username: str, password: str, db_path: str | None = None) -> int:
    """Creates a new account. Returns the new user's id.

    If this is the very first account ever created on this database, any
    pre-existing transactions with no owner (from before multi-user support
    existed) are automatically assigned to this new account -- see
    portfolio.claim_orphaned_transactions.

    Raises UsernameTakenError or WeakCredentialsError; never silently no-ops.
    """
    username = username.strip()
    _validate_credentials(username, password)

    conn = get_connection(db_path)
    try:
        existing_user_count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]

        salt_hex, hash_hex = _hash_password(password)
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_hex, salt_hex, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise UsernameTakenError(f"Username '{username}' is already taken.") from e
            raise

        new_user_id = int(cur.lastrowid)
    finally:
        conn.close()

    if existing_user_count == 0:
        portfolio.claim_orphaned_transactions(new_user_id, db_path=db_path)

    return new_user_id


def authenticate(username: str, password: str, db_path: str | None = None) -> int | None:
    """Returns the user's id if username/password match, else None."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, password_hash, salt FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    _, computed_hash = _hash_password(password, bytes.fromhex(row["salt"]))
    if hmac.compare_digest(computed_hash, row["password_hash"]):
        return int(row["id"])
    return None


def get_username(user_id: int, db_path: str | None = None) -> str | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["username"] if row else None
    finally:
        conn.close()
