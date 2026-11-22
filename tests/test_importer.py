"""
Tests for CSV/XLSX import pipeline: file reading, validation, column mapping,
duplicate detection, import execution, and rollback on failure.

Uses an in-memory SQLite database.
"""

import io
import textwrap
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import FinancialAccount, Transaction
from src.services import create_user, get_default_account
from src.importer import (
    ImportResult,
    auto_map_columns,
    apply_column_mapping,
    detect_file_type,
    read_upload,
    run_import,
    _parse_date,
    _parse_amount,
    _parse_type,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user_and_account(db):
    user = create_user(db, "importer", "importer@example.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)
    return user, account


def _csv_bytes(text: str) -> bytes:
    return textwrap.dedent(text).strip().encode("utf-8")


# ── File type detection ───────────────────────────────────────────────── #

def test_detect_csv():
    assert detect_file_type("data.csv") == "csv"


def test_detect_xlsx():
    assert detect_file_type("report.xlsx") == "xlsx"


def test_detect_unsupported():
    assert detect_file_type("script.py") is None
    assert detect_file_type("noext") is None


# ── File reading ──────────────────────────────────────────────────────── #

def test_read_valid_csv():
    data = _csv_bytes("""
        date,amount,merchant
        2026-01-01,5000,Amazon
        2026-01-02,3000,Flipkart
    """)
    df, err = read_upload(data, "test.csv")
    assert err == ""
    assert df is not None
    assert len(df) == 2


def test_read_empty_file():
    df, err = read_upload(b"", "empty.csv")
    assert df is None
    assert "empty" in err.lower()


def test_read_unsupported_type():
    df, err = read_upload(b"data", "file.json")
    assert df is None
    assert "unsupported" in err.lower()


def test_read_oversized_file():
    data = b"x" * (11 * 1024 * 1024)
    df, err = read_upload(data, "big.csv")
    assert df is None
    assert "limit" in err.lower()


def test_read_malformed_csv():
    df, err = read_upload(b"\x00\x01\xff\xfe", "bad.csv")
    assert df is None or err != ""


# ── Column mapping ────────────────────────────────────────────────────── #

def test_auto_map_standard_columns():
    df = pd.DataFrame(columns=["Date", "Amount", "Merchant", "Category", "Type"])
    mapping = auto_map_columns(df)
    assert mapping["Date"] == "date"
    assert mapping["Amount"] == "amount"
    assert mapping["Type"] == "txn_type"


def test_auto_map_alternate_names():
    df = pd.DataFrame(columns=["transaction_date", "amt", "payee", "desc"])
    mapping = auto_map_columns(df)
    assert mapping["transaction_date"] == "date"
    assert mapping["amt"] == "amount"
    assert mapping["payee"] == "merchant"
    assert mapping["desc"] == "description"


def test_apply_column_mapping():
    df = pd.DataFrame({"Trans Date": ["2026-01-01"], "Value": [5000]})
    result = apply_column_mapping(df, {"Trans Date": "date", "Value": "amount"})
    assert "date" in result.columns
    assert "amount" in result.columns


# ── Value parsing ─────────────────────────────────────────────────────── #

def test_parse_date_valid():
    assert _parse_date("2026-07-15") == date(2026, 7, 15)
    assert _parse_date("15/07/2026") == date(2026, 7, 15)


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None
    assert _parse_date(None) is None


def test_parse_amount_valid():
    assert _parse_amount("5000") == 5000.0
    assert _parse_amount("₹1,25,000") == 125000.0
    assert _parse_amount("Rs. 500.50") == 500.5


def test_parse_amount_invalid():
    assert _parse_amount("abc") is None
    assert _parse_amount(None) is None


def test_parse_type():
    assert _parse_type("debit") == "Debit"
    assert _parse_type("credit") == "Credit"
    assert _parse_type("unknown") == "Debit"
    assert _parse_type(None) == "Debit"


# ── Import execution ─────────────────────────────────────────────────── #

def test_import_valid_csv(db, user_and_account):
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "amount": ["5000", "3000", "7000"],
        "merchant": ["Amazon", "Flipkart", "Swiggy"],
        "category": ["Shopping", "Shopping", "Food & Dining"],
        "txn_type": ["Debit", "Debit", "Debit"],
        "description": ["Order 1", "Order 2", "Dinner"],
    })
    result = run_import(db, user.id, account.id, df, "test.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 3
    assert result.rows_skipped == 0
    assert result.rows_duplicate == 0

    txns = db.scalars(select(Transaction).where(Transaction.account_id == account.id)).all()
    assert len(txns) == 3


def test_import_skips_invalid_rows(db, user_and_account):
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01", "invalid-date", "2026-07-03"],
        "amount": ["5000", "3000", "not-a-number"],
        "merchant": ["A", "B", "C"],
    })
    result = run_import(db, user.id, account.id, df, "test.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 1
    assert result.rows_skipped == 2


def test_import_detects_duplicates(db, user_and_account):
    user, account = user_and_account

    db.add(Transaction(
        account_id=account.id,
        date=date(2026, 7, 1),
        description="Existing",
        merchant="Amazon",
        category="Shopping",
        txn_type="Debit",
        amount=5000.0,
    ))
    db.commit()

    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02"],
        "amount": ["5000", "3000"],
        "merchant": ["Amazon", "Flipkart"],
        "txn_type": ["Debit", "Debit"],
    })
    result = run_import(db, user.id, account.id, df, "test.csv", "csv")
    db.commit()

    assert result.rows_duplicate == 1
    assert result.rows_imported == 1


def test_import_wrong_account_denied(db, user_and_account):
    user, account = user_and_account
    df = pd.DataFrame({"date": ["2026-07-01"], "amount": ["100"]})
    result = run_import(db, user.id, 99999, df, "test.csv", "csv")
    assert result.success is False
    assert "access denied" in result.error.lower()


def test_import_empty_after_validation(db, user_and_account):
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["not-a-date"],
        "amount": ["not-a-number"],
    })
    result = run_import(db, user.id, account.id, df, "test.csv", "csv")
    assert result.success is False
    assert "no valid rows" in result.error.lower()


def test_import_all_duplicates(db, user_and_account):
    user, account = user_and_account

    db.add(Transaction(
        account_id=account.id,
        date=date(2026, 7, 1),
        merchant="Amazon",
        category="Shopping",
        txn_type="Debit",
        amount=5000.0,
        description="Existing",
    ))
    db.commit()

    df = pd.DataFrame({
        "date": ["2026-07-01"],
        "amount": ["5000"],
        "merchant": ["Amazon"],
        "txn_type": ["Debit"],
    })
    result = run_import(db, user.id, account.id, df, "re-import.csv", "csv")
    db.commit()

    assert result.success is True
    assert result.rows_imported == 0
    assert result.rows_duplicate == 1


def test_import_creates_import_record(db, user_and_account):
    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-07-01"],
        "amount": ["1000"],
        "merchant": ["Test"],
    })
    result = run_import(db, user.id, account.id, df, "tracked.csv", "csv")
    db.commit()
    assert result.import_id is not None


# ── Imported data feeds analytics pipeline ────────────────────────────── #

def test_imported_data_appears_in_db_repo(db, user_and_account):
    from src.services import DBTransactionRepository

    user, account = user_and_account
    df = pd.DataFrame({
        "date": ["2026-08-01", "2026-08-02"],
        "amount": ["2500", "7500"],
        "merchant": ["Zomato", "BigBasket"],
        "category": ["Food & Dining", "Groceries"],
        "txn_type": ["Debit", "Debit"],
    })
    run_import(db, user.id, account.id, df, "pipeline.csv", "csv")
    db.commit()

    repo = DBTransactionRepository(db, user.id)
    result_df, report = repo.load()
    assert len(result_df) == 2
    assert report.valid_rows == 2
    assert set(result_df["merchant"]) == {"Zomato", "BigBasket"}
