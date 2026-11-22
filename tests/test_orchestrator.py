"""
Tests for the multi-agent orchestrator: routing, schema validation, provider
failure fallback, deterministic operation, and user-data scoping.
"""

import os
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import Transaction
from src.orchestrator import Orchestrator, tool_detect_anomalies, tool_load_transactions
from src.services import create_user, get_default_account


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user_with_data(db):
    user = create_user(db, "orch_user", "orch@example.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)

    for i in range(5):
        db.add(Transaction(
            account_id=account.id,
            date=date(2026, 9, 1 + i),
            description=f"Purchase {i}",
            merchant="TestStore",
            category="Shopping",
            txn_type="Debit",
            amount=1000 + i * 500,
        ))
    db.commit()
    return user


# ── Orchestrator routing ──────────────────────────────────────────────── #

def test_orchestrator_success_with_db(db, user_with_data):
    orch = Orchestrator(db=db, user_id=user_with_data.id)
    result = orch.run("What did I spend in September 2026?", today=date(2026, 10, 1))
    assert result.success is True
    assert "matching_stats" in result.data
    assert result.data["matching_stats"].matching_transaction_count == 5


def test_orchestrator_success_with_csv():
    csv_path = os.path.join("data", "transactions.csv")
    if not os.path.exists(csv_path):
        pytest.skip("transactions.csv not available")
    orch = Orchestrator(csv_path=csv_path)
    result = orch.run("Show me all transactions")
    assert result.success is True


@patch("config.active_llm_provider", return_value=None)
def test_orchestrator_bad_query(_mock, db, user_with_data):
    orch = Orchestrator(db=db, user_id=user_with_data.id)
    result = orch.run("")
    assert result.success is False
    assert result.error != ""


def test_orchestrator_empty_dataset(db):
    user = create_user(db, "empty_orch", "empty_orch@example.com", "pass1234")
    db.commit()
    orch = Orchestrator(db=db, user_id=user.id)
    result = orch.run("Show transactions")
    # Empty dataset => may succeed with 0 matches or fail gracefully
    assert isinstance(result.success, bool)


# ── Deterministic fallback ────────────────────────────────────────────── #

@patch("config.active_llm_provider", return_value=None)
def test_orchestrator_works_without_api_keys(_mock, db, user_with_data):
    orch = Orchestrator(db=db, user_id=user_with_data.id)
    result = orch.run("Show my spending in September 2026", today=date(2026, 10, 1))
    assert result.success is True
    assert result.data["parse_method"] == "deterministic"


# ── Tool functions ────────────────────────────────────────────────────── #

def test_tool_load_from_db(db, user_with_data):
    df, report = tool_load_transactions(db, user_with_data.id)
    assert len(df) == 5
    assert report.valid_rows == 5


def test_tool_detect_anomalies_empty():
    import pandas as pd
    df = pd.DataFrame(columns=["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"])
    anomalies = tool_detect_anomalies(df)
    assert anomalies == []


# ── User-data isolation ───────────────────────────────────────────────── #

def test_orchestrator_user_isolation(db):
    user_a = create_user(db, "user_a", "a@example.com", "pass1234")
    user_b = create_user(db, "user_b", "b@example.com", "pass1234")
    db.commit()

    acct_a = get_default_account(db, user_a.id)
    acct_b = get_default_account(db, user_b.id)

    db.add(Transaction(
        account_id=acct_a.id, date=date(2026, 9, 1), description="A's txn",
        merchant="StoreA", category="Shopping", txn_type="Debit", amount=5000,
    ))
    db.add(Transaction(
        account_id=acct_b.id, date=date(2026, 9, 1), description="B's txn",
        merchant="StoreB", category="Shopping", txn_type="Debit", amount=9000,
    ))
    db.commit()

    orch_a = Orchestrator(db=db, user_id=user_a.id)
    result_a = orch_a.run("Show transactions from September 2026", today=date(2026, 10, 1))
    assert result_a.success is True
    df_a = result_a.data["matching_df"]
    assert all(df_a["merchant"] != "StoreB")

    orch_b = Orchestrator(db=db, user_id=user_b.id)
    result_b = orch_b.run("Show transactions from September 2026", today=date(2026, 10, 1))
    assert result_b.success is True
    df_b = result_b.data["matching_df"]
    assert all(df_b["merchant"] != "StoreA")
