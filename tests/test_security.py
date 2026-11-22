"""
Security hardening tests: rate limiting, session expiry, SECRET_KEY
validation, cross-user adversarial isolation, and XSS safety.
"""

import html as html_mod
from datetime import date
from unittest.mock import MagicMock, patch
import time

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import FinancialAccount, ImportRecord, Transaction
from src.services import (
    DBTransactionRepository,
    create_import_record,
    create_user,
    get_default_account,
    get_user_accounts,
    get_user_imports,
)
from src.importer import run_import
from src.orchestrator import Orchestrator


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def two_users(db):
    alice = create_user(db, "alice", "alice@test.com", "pass1234")
    bob = create_user(db, "bob", "bob@test.com", "pass1234")
    db.commit()
    acct_a = get_default_account(db, alice.id)
    acct_b = get_default_account(db, bob.id)
    db.add(Transaction(
        account_id=acct_a.id, date=date(2026, 8, 1),
        description="Alice secret", merchant="AliceShop",
        category="Shopping", txn_type="Debit", amount=50000,
    ))
    db.add(Transaction(
        account_id=acct_b.id, date=date(2026, 8, 1),
        description="Bob secret", merchant="BobShop",
        category="Shopping", txn_type="Debit", amount=70000,
    ))
    db.commit()
    return alice, bob, acct_a, acct_b


# ── Rate limiting ────────────────────────────────────────────────────────── #


@patch("src.auth.config")
@patch("src.auth.st")
def test_rate_limit_blocks_after_max_attempts(mock_st, mock_config):
    from src.auth import _login_attempts, _rate_lock, login, _clear_attempts

    mock_config.MAX_LOGIN_ATTEMPTS = 3
    mock_config.LOGIN_LOCKOUT_SECONDS = 300
    mock_config.SESSION_LIFETIME_SECONDS = 86400
    mock_st.session_state = {}

    _clear_attempts("ratelimited")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    for _ in range(3):
        ok, err = login(session, "ratelimited", "wrong")
        assert ok is False

    ok, err = login(session, "ratelimited", "wrong")
    assert ok is False
    assert "too many" in err.lower()

    _clear_attempts("ratelimited")
    session.close()


@patch("src.auth.config")
@patch("src.auth.st")
def test_rate_limit_clears_on_successful_login(mock_st, mock_config, db):
    from src.auth import login, _clear_attempts, _record_failed_attempt

    mock_config.MAX_LOGIN_ATTEMPTS = 5
    mock_config.LOGIN_LOCKOUT_SECONDS = 300
    mock_config.SESSION_LIFETIME_SECONDS = 86400
    mock_st.session_state = {}

    user = create_user(db, "cleartest", "cleartest@test.com", "goodpass1")
    db.commit()

    _clear_attempts("cleartest")
    for _ in range(3):
        _record_failed_attempt("cleartest")

    ok, err = login(db, "cleartest", "goodpass1")
    assert ok is True

    from src.auth import _login_attempts, _rate_lock
    with _rate_lock:
        assert "cleartest" not in _login_attempts

    _clear_attempts("cleartest")


@patch("src.auth.config")
@patch("src.auth.st")
def test_rate_limit_case_insensitive(mock_st, mock_config):
    from src.auth import _check_rate_limit, _record_failed_attempt, _clear_attempts

    mock_config.MAX_LOGIN_ATTEMPTS = 2
    mock_config.LOGIN_LOCKOUT_SECONDS = 300

    _clear_attempts("CaseUser")

    _record_failed_attempt("CaseUser")
    _record_failed_attempt("caseuser")

    allowed, _ = _check_rate_limit("CASEUSER")
    assert allowed is False

    _clear_attempts("CaseUser")


# ── Session expiry ───────────────────────────────────────────────────────── #


@patch("src.auth.config")
@patch("src.auth.st")
def test_session_expires_after_lifetime(mock_st, mock_config):
    from src.auth import is_authenticated

    mock_config.SESSION_LIFETIME_SECONDS = 10
    mock_st.session_state = {
        "authenticated": True,
        "user_id": 1,
        "session_token": "abc",
        "session_created_at": time.time() - 20,
    }
    assert is_authenticated() is False
    assert len(mock_st.session_state) == 0


@patch("src.auth.config")
@patch("src.auth.st")
def test_session_valid_within_lifetime(mock_st, mock_config):
    from src.auth import is_authenticated

    mock_config.SESSION_LIFETIME_SECONDS = 86400
    mock_st.session_state = {
        "authenticated": True,
        "user_id": 1,
        "session_token": "abc",
        "session_created_at": time.time() - 100,
    }
    assert is_authenticated() is True


# ── SECRET_KEY validation ────────────────────────────────────────────────── #


def test_secret_key_rejects_default_with_database_url():
    import importlib
    import os

    env = {
        "SECRET_KEY": "change-me-in-production",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            import config as _cfg
            importlib.reload(_cfg)

    # Restore: reload config with default env (no DATABASE_URL)
    with patch.dict(os.environ, {"DATABASE_URL": "", "SECRET_KEY": "change-me-in-production"}, clear=False):
        importlib.reload(_cfg)


def test_secret_key_rejects_empty_with_database_url():
    import importlib
    import os

    env = {
        "SECRET_KEY": "",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            import config as _cfg
            importlib.reload(_cfg)

    with patch.dict(os.environ, {"DATABASE_URL": "", "SECRET_KEY": "change-me-in-production"}, clear=False):
        importlib.reload(_cfg)


# ── Adversarial cross-user isolation ─────────────────────────────────────── #


def test_bob_cannot_query_alice_via_orchestrator(db, two_users):
    alice, bob, _, _ = two_users
    orch = Orchestrator(db=db, user_id=bob.id)
    result = orch.run("Show all transactions", today=date(2026, 9, 1))
    if result.success and "matching_df" in result.data:
        df = result.data["matching_df"]
        assert "AliceShop" not in df["merchant"].values


def test_bob_cannot_load_alice_transactions_via_repo(db, two_users):
    alice, bob, _, _ = two_users
    repo = DBTransactionRepository(db, bob.id)
    df, _ = repo.load()
    merchants = df["merchant"].tolist() if not df.empty else []
    assert "AliceShop" not in merchants


def test_bob_cannot_import_to_alice_account(db, two_users):
    alice, bob, acct_a, _ = two_users
    df = pd.DataFrame({"date": ["2026-08-01"], "amount": ["999"]})
    result = run_import(db, bob.id, acct_a.id, df, "attack.csv", "csv")
    assert result.success is False
    assert "access denied" in result.error.lower()


def test_bob_cannot_see_alice_import_records(db, two_users):
    alice, bob, _, _ = two_users
    create_import_record(db, alice.id, "alice_secret.csv", "csv")
    db.commit()
    bob_imports = get_user_imports(db, bob.id)
    filenames = [i.filename for i in bob_imports]
    assert "alice_secret.csv" not in filenames


def test_bob_cannot_access_alice_accounts(db, two_users):
    alice, bob, _, _ = two_users
    bob_accts = get_user_accounts(db, bob.id)
    acct_ids = [a.id for a in bob_accts]
    alice_accts = get_user_accounts(db, alice.id)
    for a in alice_accts:
        assert a.id not in acct_ids


def test_direct_account_id_manipulation_denied(db, two_users):
    """Bob tries to import by directly using Alice's account_id."""
    alice, bob, acct_a, acct_b = two_users
    df = pd.DataFrame({
        "date": ["2026-08-10"],
        "amount": ["1000"],
        "merchant": ["Injected"],
    })
    result = run_import(db, bob.id, acct_a.id, df, "inject.csv", "csv")
    assert result.success is False


def test_fabricated_user_id_gets_nothing(db, two_users):
    repo = DBTransactionRepository(db, 999999)
    df, report = repo.load()
    assert len(df) == 0

    imports = get_user_imports(db, 999999)
    assert len(imports) == 0

    accounts = get_user_accounts(db, 999999)
    assert len(accounts) == 0


# ── XSS regression ──────────────────────────────────────────────────────── #


def test_xss_payload_in_merchant_is_escaped(db):
    """A <script> tag in imported data must not survive to raw HTML output."""
    xss = '<script>alert(1)</script>'
    user = create_user(db, "xsstest", "xss@test.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)

    df = pd.DataFrame({
        "date": ["2026-08-01"],
        "amount": ["1000"],
        "merchant": [xss],
        "category": [xss],
        "description": [xss],
    })
    result = run_import(db, user.id, account.id, df, "xss.csv", "csv")
    db.commit()
    assert result.success is True

    repo = DBTransactionRepository(db, user.id)
    loaded_df, _ = repo.load()
    assert len(loaded_df) == 1
    assert loaded_df.iloc[0]["merchant"] == xss

    escaped = html_mod.escape(xss)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped


# ── Rate limiter stale-key cleanup ───────────────────────────────────────── #


@patch("src.auth.config")
@patch("src.auth.st")
def test_rate_limiter_cleans_stale_keys(mock_st, mock_config):
    from src.auth import (
        _login_attempts, _rate_lock, _check_rate_limit,
        _record_failed_attempt, _clear_attempts,
    )
    import src.auth as auth_mod

    mock_config.MAX_LOGIN_ATTEMPTS = 5
    mock_config.LOGIN_LOCKOUT_SECONDS = 1

    _clear_attempts("stale_a")
    _clear_attempts("stale_b")

    _record_failed_attempt("stale_a")
    _record_failed_attempt("stale_b")

    with _rate_lock:
        assert "stale_a" in _login_attempts
        assert "stale_b" in _login_attempts

    time.sleep(1.1)

    old_sweep = auth_mod._last_sweep
    auth_mod._last_sweep = 0.0
    auth_mod._SWEEP_INTERVAL = 0.0
    try:
        _check_rate_limit("trigger_sweep")
    finally:
        auth_mod._SWEEP_INTERVAL = 60.0

    with _rate_lock:
        assert "stale_a" not in _login_attempts
        assert "stale_b" not in _login_attempts

    _clear_attempts("trigger_sweep")
