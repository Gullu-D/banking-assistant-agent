"""
Tests for the transaction data-loading pipeline (src.data_loader).

Covers: valid loading, missing file, corrupt CSV, missing columns, empty
dataset, invalid dates/amounts/types, row skipping, and LoadReport accuracy.
"""

import os
import textwrap

import pandas as pd
import pytest

from src.data_loader import (
    DatasetCorruptedError,
    DatasetNotFoundError,
    EmptyDatasetError,
    LoadReport,
    MissingColumnsError,
    TransactionRepository,
)


@pytest.fixture()
def valid_csv(tmp_path):
    p = tmp_path / "txns.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-07-01,Salary credit,Company,Salary / Income,Credit,90000,Primary
        T2,2026-07-02,Rent,Landlord,Rent,Debit,35000,Primary
        T3,2026-07-03,Groceries,BigBasket,Groceries,Debit,1500.50,Primary
    """))
    return str(p)


@pytest.fixture()
def dirty_csv(tmp_path):
    p = tmp_path / "dirty.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-07-01,Good row,Amazon,Shopping,Debit,5000,Primary
        T2,not-a-date,Bad date,Amazon,Shopping,Debit,3000,Primary
        T3,2026-07-02,Bad amount,Amazon,Shopping,Debit,xyz,Primary
        T4,2026-07-03,Bad type,Amazon,Shopping,InvalidType,2000,Primary
        T5,2026-07-04,,,,Debit,1000,Primary
    """))
    return str(p)


def test_valid_csv_loads_correctly(valid_csv):
    repo = TransactionRepository(valid_csv)
    df, report = repo.load()

    assert len(df) == 3
    assert report.valid_rows == 3
    assert report.total_rows_skipped == 0
    assert not report.has_issues()
    assert list(df.columns) == [
        "transaction_id", "date", "description", "merchant",
        "category", "type", "amount", "account",
    ]
    assert df["amount"].dtype == float
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_valid_csv_is_sorted_by_date(valid_csv):
    repo = TransactionRepository(valid_csv)
    df, _ = repo.load()
    dates = list(df["date"])
    assert dates == sorted(dates)


def test_missing_file_raises_dataset_not_found(tmp_path):
    repo = TransactionRepository(str(tmp_path / "nonexistent.csv"))
    with pytest.raises(DatasetNotFoundError) as exc_info:
        repo.load()
    assert "not found" in exc_info.value.user_message.lower()


def test_empty_file_raises_empty_dataset(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    repo = TransactionRepository(str(p))
    with pytest.raises(EmptyDatasetError):
        repo.load()


def test_header_only_csv_raises_empty_dataset(tmp_path):
    p = tmp_path / "header_only.csv"
    p.write_text("transaction_id,date,description,merchant,category,type,amount,account\n")
    repo = TransactionRepository(str(p))
    with pytest.raises(EmptyDatasetError):
        repo.load()


def test_missing_columns_raises_error(tmp_path):
    p = tmp_path / "bad_cols.csv"
    p.write_text("id,date,amount\nT1,2026-07-01,100\n")
    repo = TransactionRepository(str(p))
    with pytest.raises(MissingColumnsError) as exc_info:
        repo.load()
    assert "transaction_id" in exc_info.value.user_message


def test_corrupt_csv_raises_error(tmp_path):
    p = tmp_path / "corrupt.csv"
    p.write_bytes(b"\x00\x01\x02\xff\xfe" * 100)
    repo = TransactionRepository(str(p))
    with pytest.raises((DatasetCorruptedError, EmptyDatasetError)):
        repo.load()


def test_dirty_csv_skips_bad_rows_and_reports(dirty_csv):
    repo = TransactionRepository(dirty_csv)
    df, report = repo.load()

    assert report.total_rows_in_file == 5
    assert report.has_issues()
    assert report.rows_with_invalid_date >= 1
    assert report.rows_with_invalid_amount >= 1
    assert report.total_rows_skipped > 0
    assert len(report.warnings) > 0
    assert report.valid_rows == len(df)
    assert len(df) >= 1


def test_negative_amounts_are_excluded(tmp_path):
    p = tmp_path / "neg.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-07-01,Good,M,Shopping,Debit,500,Primary
        T2,2026-07-02,Negative,M,Shopping,Debit,-100,Primary
    """))
    repo = TransactionRepository(str(p))
    df, report = repo.load()
    assert len(df) == 1
    assert report.rows_with_invalid_amount == 1


def test_currency_symbols_stripped_from_amounts(tmp_path):
    p = tmp_path / "currency.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-07-01,Salary,Company,Salary / Income,Credit,"₹1,25,000",Primary
    """), encoding="utf-8")
    repo = TransactionRepository(str(p))
    df, _ = repo.load()
    assert df.iloc[0]["amount"] == 125000.0


def test_missing_description_gets_placeholder(tmp_path):
    p = tmp_path / "no_desc.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-07-01,,Amazon,Shopping,Debit,5000,Primary
    """))
    repo = TransactionRepository(str(p))
    df, _ = repo.load()
    assert df.iloc[0]["description"] == "Transaction"


def test_load_report_properties():
    r = LoadReport(total_rows_in_file=10, valid_rows=7)
    assert r.total_rows_skipped == 3
    assert r.has_issues()

    r2 = LoadReport(total_rows_in_file=5, valid_rows=5)
    assert r2.total_rows_skipped == 0
    assert not r2.has_issues()
