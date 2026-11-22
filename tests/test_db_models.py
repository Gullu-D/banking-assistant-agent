"""
Smoke tests for the database layer: models, services, DB-backed repository.

Uses an in-memory SQLite database so nothing touches disk.
"""

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import FinancialAccount, ImportRecord, Transaction, User
from src.services import (
    DBTransactionRepository,
    authenticate_user,
    create_import_record,
    create_user,
    get_default_account,
    get_user_by_email,
    get_user_by_username,
    hash_password,
    verify_password,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


# ── Password hashing ────────────────────────────────────────────────────── #

def test_hash_and_verify():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


# ── User CRUD ───────────────────────────────────────────────────────────── #

def test_create_user_and_default_account(db):
    user = create_user(db, "alice", "alice@example.com", "pass")
    db.commit()

    assert user.id is not None
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert user.is_active is True

    acct = get_default_account(db, user.id)
    assert acct is not None
    assert acct.name == "Primary"


def test_get_user_by_username(db):
    create_user(db, "bob", "bob@example.com", "pass")
    db.commit()
    assert get_user_by_username(db, "bob") is not None
    assert get_user_by_username(db, "nobody") is None


def test_get_user_by_email(db):
    create_user(db, "carol", "Carol@Example.COM", "pass")
    db.commit()
    assert get_user_by_email(db, "carol@example.com") is not None


def test_authenticate_user(db):
    create_user(db, "dave", "dave@example.com", "s3cret")
    db.commit()
    assert authenticate_user(db, "dave", "s3cret") is not None
    assert authenticate_user(db, "dave", "wrong") is None
    assert authenticate_user(db, "nobody", "s3cret") is None


def test_duplicate_username_rejected(db):
    create_user(db, "dup", "dup1@example.com", "p")
    db.commit()
    with pytest.raises(Exception):
        create_user(db, "dup", "dup2@example.com", "p")
        db.commit()


# ── DB Transaction Repository ──────────────────────────────────────────── #

def test_db_repo_empty(db):
    user = create_user(db, "empty_user", "empty@example.com", "p")
    db.commit()
    repo = DBTransactionRepository(db, user.id)
    df, report = repo.load()
    assert len(df) == 0
    assert report.valid_rows == 0


def test_db_repo_returns_dataframe(db):
    user = create_user(db, "txn_user", "txn@example.com", "p")
    db.commit()
    acct = get_default_account(db, user.id)

    for i in range(3):
        db.add(Transaction(
            account_id=acct.id,
            date=date(2026, 7, 1 + i),
            description=f"Txn {i}",
            merchant="Amazon",
            category="Shopping",
            txn_type="Debit",
            amount=1000 + i * 100,
        ))
    db.commit()

    repo = DBTransactionRepository(db, user.id)
    df, report = repo.load()

    assert len(df) == 3
    assert report.valid_rows == 3
    assert list(df.columns) == [
        "transaction_id", "date", "description", "merchant",
        "category", "type", "amount", "account",
    ]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["amount"].tolist() == [1000.0, 1100.0, 1200.0]


# ── Import record ──────────────────────────────────────────────────────── #

def test_create_import_record(db):
    user = create_user(db, "imp_user", "imp@example.com", "p")
    db.commit()
    rec = create_import_record(db, user.id, "data.csv", "csv")
    db.commit()
    assert rec.id is not None
    assert rec.status == "pending"


# ── Model relationships ─────────────────────────────────────────────────── #

def test_user_cascade_deletes_accounts(db):
    user = create_user(db, "cascade", "cascade@example.com", "p")
    db.commit()
    uid = user.id
    db.delete(user)
    db.commit()
    assert get_default_account(db, uid) is None
