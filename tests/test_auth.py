"""
Tests for authentication: registration, login, logout, session management,
password hashing, and input validation.

Uses an in-memory SQLite database so nothing touches disk.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.services import (
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_username,
    hash_password,
    verify_password,
)
from src.auth import register, login, logout, is_authenticated, get_current_user_id


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


# ── Password hashing ──────────────────────────────────────────────────── #

def test_password_hash_is_not_plaintext():
    h = hash_password("MyP@ssw0rd!")
    assert h != "MyP@ssw0rd!"
    assert len(h) > 20


def test_verify_correct_password():
    h = hash_password("correct-horse")
    assert verify_password("correct-horse", h) is True


def test_verify_wrong_password():
    h = hash_password("correct-horse")
    assert verify_password("wrong-horse", h) is False


def test_different_passwords_produce_different_hashes():
    h1 = hash_password("password1")
    h2 = hash_password("password2")
    assert h1 != h2


def test_same_password_produces_different_hashes_due_to_salt():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


# ── Registration ──────────────────────────────────────────────────────── #

def test_register_success(db):
    ok, err = register(db, "testuser", "test@example.com", "password123")
    db.commit()
    assert ok is True
    assert err == ""
    assert get_user_by_username(db, "testuser") is not None


def test_register_duplicate_username(db):
    create_user(db, "taken", "taken1@example.com", "pass1234")
    db.commit()
    ok, err = register(db, "taken", "taken2@example.com", "pass1234")
    assert ok is False
    assert "already taken" in err.lower()


def test_register_duplicate_email(db):
    create_user(db, "user1", "same@example.com", "pass1234")
    db.commit()
    ok, err = register(db, "user2", "same@example.com", "pass1234")
    assert ok is False
    assert "email" in err.lower()


def test_register_short_username(db):
    ok, err = register(db, "ab", "short@example.com", "password123")
    assert ok is False
    assert "3 characters" in err


def test_register_invalid_username_chars(db):
    ok, err = register(db, "bad user!", "bad@example.com", "password123")
    assert ok is False
    assert "letters" in err.lower()


def test_register_invalid_email(db):
    ok, err = register(db, "valid_user", "not-an-email", "password123")
    assert ok is False
    assert "email" in err.lower()


def test_register_short_password(db):
    ok, err = register(db, "validuser", "valid@example.com", "short")
    assert ok is False
    assert "8 characters" in err


# ── Login ─────────────────────────────────────────────────────────────── #

def test_authenticate_valid_credentials(db):
    create_user(db, "alice", "alice@example.com", "hunter2!!")
    db.commit()
    user = authenticate_user(db, "alice", "hunter2!!")
    assert user is not None
    assert user.username == "alice"


def test_authenticate_wrong_password(db):
    create_user(db, "bob", "bob@example.com", "correct")
    db.commit()
    assert authenticate_user(db, "bob", "wrong") is None


def test_authenticate_nonexistent_user(db):
    assert authenticate_user(db, "nobody", "anything") is None


def test_authenticate_inactive_user(db):
    user = create_user(db, "inactive", "inactive@example.com", "pass1234")
    user.is_active = False
    db.commit()
    assert authenticate_user(db, "inactive", "pass1234") is None


# ── Session management ────────────────────────────────────────────────── #

@patch("src.auth.st")
def test_login_sets_session_state(mock_st, db):
    mock_st.session_state = {}
    create_user(db, "sessuser", "sess@example.com", "password123")
    db.commit()
    ok, err = login(db, "sessuser", "password123")
    assert ok is True
    assert mock_st.session_state["authenticated"] is True
    assert mock_st.session_state["user_id"] is not None
    assert mock_st.session_state["username"] == "sessuser"
    assert len(mock_st.session_state["session_token"]) == 64


@patch("src.auth.st")
def test_login_wrong_creds_no_session(mock_st, db):
    mock_st.session_state = {}
    ok, err = login(db, "nobody", "wrong")
    assert ok is False
    assert "authenticated" not in mock_st.session_state


@patch("src.auth.st")
def test_logout_clears_session(mock_st):
    mock_st.session_state = {
        "authenticated": True,
        "user_id": 1,
        "username": "test",
        "session_token": "abc",
        "other_key": "other_value",
    }
    logout()
    assert len(mock_st.session_state) == 0


@patch("src.auth.st")
def test_is_authenticated_checks_all_keys(mock_st):
    mock_st.session_state = {}
    assert is_authenticated() is False

    mock_st.session_state = {"authenticated": True}
    assert is_authenticated() is False

    mock_st.session_state = {"authenticated": True, "user_id": 1, "session_token": "abc"}
    assert is_authenticated() is True


@patch("src.auth.st")
def test_get_current_user_id_returns_none_when_not_authenticated(mock_st):
    mock_st.session_state = {}
    assert get_current_user_id() is None
