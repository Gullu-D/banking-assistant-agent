"""
Phase 6 regression tests: import rollback, email validation, negative amounts,
and edge cases found during the risk-based audit.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import FinancialAccount, ImportRecord, Transaction
from src.services import create_user, get_default_account
from src.importer import run_import, _parse_amount
from src.auth import register


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user_and_account(db):
    user = create_user(db, "phase6user", "phase6@example.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)
    return user, account


# ── Import savepoint rollback ──────────────────────────────────────────── #


def test_import_failure_does_not_leave_partial_transactions(db, user_and_account):
    """If transaction insertion fails, the import record should be marked
    'failed' and no partial transactions should be committed."""
    user, account = user_and_account

    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02"],
        "amount": ["5000", "3000"],
        "merchant": ["Amazon", "Flipkart"],
    })

    # Monkey-patch Transaction to fail on second add
    original_init = Transaction.__init__
    call_count = [0]

    def failing_init(self, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("Simulated DB error")
        original_init(self, **kwargs)

    with patch.object(Transaction, "__init__", failing_init):
        result = run_import(db, user.id, account.id, df, "fail.csv", "csv")
    db.commit()

    assert result.success is False
    assert "simulated" in result.error.lower()

    # No transactions should exist — the savepoint rolled them back
    txns = db.scalars(
        select(Transaction).where(Transaction.account_id == account.id)
    ).all()
    assert len(txns) == 0

    # The import record should exist with "failed" status
    rec = db.scalars(
        select(ImportRecord).where(ImportRecord.user_id == user.id)
    ).first()
    assert rec is not None
    assert rec.status == "failed"


def test_import_success_commits_all_transactions(db, user_and_account):
    """Normal import should commit all transactions atomically."""
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "amount": ["1000", "2000", "3000"],
        "merchant": ["A", "B", "C"],
        "txn_type": ["Debit", "Credit", "Debit"],
    })
    result = run_import(db, user.id, account.id, df, "good.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 3

    txns = db.scalars(
        select(Transaction).where(Transaction.account_id == account.id)
    ).all()
    assert len(txns) == 3


# ── Negative amount handling ───────────────────────────────────────────── #


def test_negative_amounts_inferred_type_from_sign(db, user_and_account):
    """When no explicit type column exists, negative amounts are imported
    as Debit with the absolute value, not skipped."""
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "amount": ["5000", "-500", "3000"],
        "merchant": ["A", "Refund", "B"],
    })
    result = run_import(db, user.id, account.id, df, "negatives.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 3
    assert result.rows_skipped == 0
    assert any("negative" in w.lower() for w in result.warnings)
    assert any("absolute value" in w.lower() for w in result.warnings)


def test_negative_amounts_skipped_when_type_column_present(db, user_and_account):
    """When an explicit type column exists, negative amounts are skipped."""
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "amount": ["5000", "-500", "3000"],
        "merchant": ["A", "Refund", "B"],
        "type": ["Debit", "Credit", "Debit"],
    })
    result = run_import(db, user.id, account.id, df, "negatives_typed.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 2
    assert result.rows_skipped == 1
    assert any("negative" in w.lower() for w in result.warnings)


def test_parse_amount_negative():
    assert _parse_amount("-500") == -500.0


# ── Email validation ──────────────────────────────────────────────────── #


@patch("src.auth.st")
def test_register_rejects_email_without_domain(mock_st, db):
    mock_st.session_state = {}
    ok, err = register(db, "validuser", "user@", "password123")
    assert ok is False
    assert "email" in err.lower()


@patch("src.auth.st")
def test_register_rejects_email_without_tld(mock_st, db):
    mock_st.session_state = {}
    ok, err = register(db, "validuser", "user@domain", "password123")
    assert ok is False
    assert "email" in err.lower()


@patch("src.auth.st")
def test_register_accepts_valid_email(mock_st, db):
    mock_st.session_state = {}
    ok, err = register(db, "validuser", "user@domain.com", "password123")
    db.commit()
    assert ok is True


@patch("src.auth.st")
def test_register_rejects_empty_email(mock_st, db):
    mock_st.session_state = {}
    ok, err = register(db, "validuser", "", "password123")
    assert ok is False


@patch("src.auth.st")
def test_register_rejects_email_with_spaces(mock_st, db):
    mock_st.session_state = {}
    ok, err = register(db, "validuser", "user @domain.com", "password123")
    assert ok is False


# ── Empty user experience ─────────────────────────────────────────────── #


def test_new_user_has_empty_transactions(db, user_and_account):
    from src.services import DBTransactionRepository

    user, account = user_and_account
    repo = DBTransactionRepository(db, user.id)
    result_df, report = repo.load()
    assert len(result_df) == 0
    assert report.valid_rows == 0


def test_analytics_on_empty_df():
    from src.analytics import (
        calculate_overall_statistics,
        calculate_matching_statistics,
        calculate_category_breakdown,
    )

    empty = pd.DataFrame(columns=["date", "amount", "type", "merchant", "category", "transaction_id"])
    stats = calculate_overall_statistics(empty)
    assert stats.total_transactions == 0
    assert stats.total_spending == 0.0

    matching = calculate_matching_statistics(empty)
    assert matching.matching_transaction_count == 0

    breakdown = calculate_category_breakdown(empty)
    assert breakdown == []


def test_anomaly_detection_on_empty_df():
    from src.anomaly_detector import detect_anomalies

    empty = pd.DataFrame(columns=["date", "amount", "type", "merchant", "category", "transaction_id"])
    assert detect_anomalies(empty) == []


# ── Period comparison edge cases ──────────────────────────────────────── #


def test_period_comparison_no_prior_data():
    from src.analytics import period_comparison

    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-07-01", "2026-07-15", "2026-07-30"]),
        "amount": [1000.0, 2000.0, 3000.0],
        "type": ["Debit", "Debit", "Credit"],
        "merchant": ["A", "B", "C"],
        "category": ["Shopping", "Food & Dining", "Salary / Income"],
        "transaction_id": ["T1", "T2", "T3"],
    })
    result = period_comparison(df, date(2026, 7, 1), date(2026, 7, 31))
    assert result["previous"].total_transactions == 0
    assert result["changes"]["spending"] is None


def test_period_comparison_zero_income():
    from src.analytics import period_comparison

    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-06-15", "2026-07-15"]),
        "amount": [500.0, 1000.0],
        "type": ["Debit", "Debit"],
        "merchant": ["A", "B"],
        "category": ["Shopping", "Shopping"],
        "transaction_id": ["T1", "T2"],
    })
    result = period_comparison(df, date(2026, 7, 1), date(2026, 7, 31))
    assert result["changes"]["income"] is None
