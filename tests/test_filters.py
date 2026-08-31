"""
Tests for deterministic filtering (src.filters), including the strict
boundary behavior required by the spec: "above ₹50,000" means amount > 50000
(strictly greater than), not >=.
"""

from datetime import date

import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

from src.date_utils import resolve_date_range
from src.filters import apply_filters
from src.validators import StructuredQuery


_COLUMNS = ["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"]


def _make_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_amount_above_threshold_is_strictly_greater_than():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=50001, account="Primary"),
            dict(transaction_id="T2", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=50000, account="Primary"),
            dict(transaction_id="T3", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=49999, account="Primary"),
        ]
    )
    query = StructuredQuery(intent="transaction_analysis", amount_threshold=50000, operator="greater_than", date_range="all_time")
    outcome = apply_filters(df, query)

    ids = set(outcome.filtered_df["transaction_id"])
    assert ids == {"T1"}, f"Expected only T1 (50,001) to be included, got {ids}"


def test_amount_at_least_threshold_includes_equal_value():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=50000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=49999, account="Primary"),
        ]
    )
    query = StructuredQuery(amount_threshold=50000, operator="greater_than_or_equal", date_range="all_time")
    outcome = apply_filters(df, query)
    assert set(outcome.filtered_df["transaction_id"]) == {"T1"}


def test_below_threshold_operator():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=1000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=100000, account="Primary"),
        ]
    )
    query = StructuredQuery(amount_threshold=5000, operator="less_than", date_range="all_time")
    outcome = apply_filters(df, query)
    assert set(outcome.filtered_df["transaction_id"]) == {"T1"}


def test_category_filter_is_case_insensitive():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=1000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-10", description="d", merchant="M", category="Travel", type="Debit", amount=1000, account="Primary"),
        ]
    )
    query = StructuredQuery(category="shopping", date_range="all_time")
    outcome = apply_filters(df, query)
    assert set(outcome.filtered_df["transaction_id"]) == {"T1"}


def test_last_month_is_computed_dynamically_relative_to_today():
    """'last month' must always resolve to the calendar month before whatever
    'today' is — never a hard-coded month/year.
    """
    fake_today = date(2026, 8, 31)
    start, end, label = resolve_date_range("last_month", today=fake_today)
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 31)
    assert label == "July 2026"

    # And it should shift correctly for a different "today", including a
    # year boundary.
    fake_today_jan = date(2027, 1, 15)
    start2, end2, label2 = resolve_date_range("last_month", today=fake_today_jan)
    assert start2 == date(2026, 12, 1)
    assert end2 == date(2026, 12, 31)
    assert label2 == "December 2026"


def test_this_month_caps_at_today_not_month_end():
    fake_today = date(2026, 8, 15)
    start, end, _ = resolve_date_range("this_month", today=fake_today)
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 15)  # not Aug 31 — no future data assumed


def test_last_30_days_window():
    fake_today = date(2026, 8, 31)
    start, end, _ = resolve_date_range("last_30_days", today=fake_today)
    assert (end - start).days == 29
    assert end == fake_today


def test_all_time_returns_no_date_bounds():
    start, end, label = resolve_date_range("all_time")
    assert start is None and end is None
    assert label == "All Time"


def test_empty_dataframe_does_not_raise():
    df = _make_df([])
    query = StructuredQuery(amount_threshold=50000, operator="greater_than", date_range="all_time")
    outcome = apply_filters(df, query)
    assert outcome.filtered_df.empty


def test_top_n_and_sort():
    rows = [
        dict(transaction_id=f"T{i}", date="2026-07-10", description="d", merchant="M", category="Shopping", type="Debit", amount=amt, account="Primary")
        for i, amt in enumerate([1000, 5000, 20000, 3000, 90000])
    ]
    df = _make_df(rows)
    query = StructuredQuery(intent="top_expenses", top_n=2, date_range="all_time")
    outcome = apply_filters(df, query)
    assert list(outcome.filtered_df["amount"]) == [90000, 20000]
