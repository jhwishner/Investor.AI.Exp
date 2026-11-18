"""Tests for the self-contained username/password account system."""

import pytest

from investor_ai import auth, portfolio


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_auth.db")
    auth.init_db(db_path=path)
    portfolio.init_db(db_path=path)
    return path


def test_create_user_and_authenticate(db_path):
    user_id = auth.create_user("alice", "correct-horse", db_path=db_path)
    assert user_id > 0
    assert auth.authenticate("alice", "correct-horse", db_path=db_path) == user_id


def test_authenticate_wrong_password_fails(db_path):
    auth.create_user("alice", "correct-horse", db_path=db_path)
    assert auth.authenticate("alice", "wrong-password", db_path=db_path) is None


def test_authenticate_unknown_username_fails(db_path):
    assert auth.authenticate("nobody", "whatever123", db_path=db_path) is None


def test_username_is_case_insensitive(db_path):
    user_id = auth.create_user("Alice", "correct-horse", db_path=db_path)
    assert auth.authenticate("alice", "correct-horse", db_path=db_path) == user_id
    assert auth.authenticate("ALICE", "correct-horse", db_path=db_path) == user_id


def test_duplicate_username_raises(db_path):
    auth.create_user("alice", "correct-horse", db_path=db_path)
    with pytest.raises(auth.UsernameTakenError):
        auth.create_user("alice", "different-password", db_path=db_path)


def test_duplicate_username_case_insensitive_raises(db_path):
    auth.create_user("alice", "correct-horse", db_path=db_path)
    with pytest.raises(auth.UsernameTakenError):
        auth.create_user("ALICE", "different-password", db_path=db_path)


def test_short_password_rejected(db_path):
    with pytest.raises(auth.WeakCredentialsError):
        auth.create_user("bob", "short", db_path=db_path)


def test_empty_username_rejected(db_path):
    with pytest.raises(auth.WeakCredentialsError):
        auth.create_user("   ", "a-fine-password", db_path=db_path)


def test_password_is_never_stored_in_plaintext(db_path):
    from investor_ai.db import get_connection

    auth.create_user("alice", "correct-horse", db_path=db_path)
    conn = get_connection(db_path)
    row = conn.execute("SELECT password_hash FROM users WHERE username = 'alice'").fetchone()
    conn.close()
    assert "correct-horse" not in row["password_hash"]


def test_get_username(db_path):
    user_id = auth.create_user("alice", "correct-horse", db_path=db_path)
    assert auth.get_username(user_id, db_path=db_path) == "alice"
    assert auth.get_username(999999, db_path=db_path) is None


def test_first_signup_claims_orphaned_legacy_transactions(db_path):
    # Simulate pre-multi-user data: a transaction with no owner.
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", user_id=1, db_path=db_path)
    from investor_ai.db import get_connection

    conn = get_connection(db_path)
    conn.execute("UPDATE transactions SET user_id = NULL")
    conn.commit()
    conn.close()

    first_user_id = auth.create_user("alice", "correct-horse", db_path=db_path)

    assert len(portfolio.list_transactions(first_user_id, db_path=db_path)) == 1


def test_second_signup_does_not_claim_orphaned_data(db_path):
    portfolio.add_transaction("AAPL", "BUY", 10, 100.0, "2024-01-01", user_id=1, db_path=db_path)
    from investor_ai.db import get_connection

    conn = get_connection(db_path)
    conn.execute("UPDATE transactions SET user_id = NULL")
    conn.commit()
    conn.close()

    first_user_id = auth.create_user("alice", "correct-horse", db_path=db_path)
    second_user_id = auth.create_user("bob", "another-password", db_path=db_path)

    # The legacy data went to whoever signed up first, not the second account.
    assert len(portfolio.list_transactions(first_user_id, db_path=db_path)) == 1
    assert portfolio.list_transactions(second_user_id, db_path=db_path).empty
