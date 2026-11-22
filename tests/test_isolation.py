"""
Cross-user isolation tests: verify that one user cannot access another user's
accounts, transactions, or import records.
"""

from datetime import date

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

import pandas as pd


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
    alice = create_user(db, "alice", "alice@example.com", "pass1234")
    bob = create_user(db, "bob", "bob@example.com", "pass1234")
    db.commit()

    acct_alice = get_default_account(db, alice.id)
    acct_bob = get_default_account(db, bob.id)

    db.add(Transaction(
        account_id=acct_alice.id, date=date(2026, 7, 1),
        description="Alice buys", merchant="AliceStore",
        category="Shopping", txn_type="Debit", amount=10000,
    ))
    db.add(Transaction(
        account_id=acct_bob.id, date=date(2026, 7, 1),
        description="Bob buys", merchant="BobStore",
        category="Shopping", txn_type="Debit", amount=20000,
    ))
    db.commit()
    return alice, bob


def test_db_repo_only_returns_own_transactions(db, two_users):
    alice, bob = two_users

    repo_a = DBTransactionRepository(db, alice.id)
    df_a, _ = repo_a.load()
    assert len(df_a) == 1
    assert df_a.iloc[0]["merchant"] == "AliceStore"

    repo_b = DBTransactionRepository(db, bob.id)
    df_b, _ = repo_b.load()
    assert len(df_b) == 1
    assert df_b.iloc[0]["merchant"] == "BobStore"


def test_user_accounts_isolated(db, two_users):
    alice, bob = two_users
    alice_accts = get_user_accounts(db, alice.id)
    bob_accts = get_user_accounts(db, bob.id)
    assert all(a.user_id == alice.id for a in alice_accts)
    assert all(a.user_id == bob.id for a in bob_accts)


def test_import_to_other_users_account_denied(db, two_users):
    alice, bob = two_users
    bob_acct = get_default_account(db, bob.id)
    df = pd.DataFrame({"date": ["2026-07-01"], "amount": ["100"]})
    result = run_import(db, alice.id, bob_acct.id, df, "test.csv", "csv")
    assert result.success is False
    assert "access denied" in result.error.lower()


def test_import_records_isolated(db, two_users):
    alice, bob = two_users
    create_import_record(db, alice.id, "alice.csv", "csv")
    create_import_record(db, bob.id, "bob.csv", "csv")
    db.commit()

    alice_imports = get_user_imports(db, alice.id)
    bob_imports = get_user_imports(db, bob.id)
    assert all(i.user_id == alice.id for i in alice_imports)
    assert all(i.user_id == bob.id for i in bob_imports)
    assert len(alice_imports) == 1
    assert len(bob_imports) == 1


def test_nonexistent_user_gets_no_data(db, two_users):
    repo = DBTransactionRepository(db, 99999)
    df, report = repo.load()
    assert len(df) == 0
