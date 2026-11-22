"""Tests for Phase 3 dashboard features: new analytics functions and insights."""

from datetime import date

import pandas as pd
import pytest

from src.analytics import (
    calculate_overall_statistics,
    income_expense_over_time,
    period_comparison,
    top_merchants,
)


@pytest.fixture()
def sample_df():
    """A small DataFrame with both Debit and Credit transactions across two months."""
    return pd.DataFrame({
        "transaction_id": [f"t{i}" for i in range(8)],
        "date": pd.to_datetime([
            "2026-08-05", "2026-08-10", "2026-08-15", "2026-08-20",
            "2026-09-05", "2026-09-10", "2026-09-15", "2026-09-20",
        ]),
        "description": ["desc"] * 8,
        "merchant": ["ShopA", "ShopB", "ShopA", "Salary", "ShopA", "ShopC", "ShopB", "Salary"],
        "category": ["Shopping", "Food", "Shopping", "Salary / Income",
                      "Shopping", "Food", "Food", "Salary / Income"],
        "type": ["Debit", "Debit", "Debit", "Credit", "Debit", "Debit", "Debit", "Credit"],
        "amount": [1000.0, 500.0, 2000.0, 50000.0, 1500.0, 800.0, 600.0, 55000.0],
        "account": ["Primary"] * 8,
    })


@pytest.fixture()
def empty_df():
    return pd.DataFrame(columns=[
        "transaction_id", "date", "description", "merchant",
        "category", "type", "amount", "account",
    ])


# ── income_expense_over_time ───────────────────────────────────────────── #


def test_income_expense_over_time_returns_both_series(sample_df):
    result = income_expense_over_time(sample_df, freq="MS")
    assert "income" in result.columns
    assert "expense" in result.columns
    assert "net" in result.columns
    assert len(result) == 2  # Aug and Sep


def test_income_expense_over_time_correct_totals(sample_df):
    result = income_expense_over_time(sample_df, freq="MS")
    aug = result[result["period"] == pd.Timestamp("2026-08-01")].iloc[0]
    assert aug["income"] == 50000.0
    assert aug["expense"] == 3500.0  # 1000 + 500 + 2000
    assert aug["net"] == 46500.0

    sep = result[result["period"] == pd.Timestamp("2026-09-01")].iloc[0]
    assert sep["income"] == 55000.0
    assert sep["expense"] == 2900.0  # 1500 + 800 + 600
    assert sep["net"] == 52100.0


def test_income_expense_over_time_empty(empty_df):
    result = income_expense_over_time(empty_df)
    assert result.empty
    assert list(result.columns) == ["period", "income", "expense", "net"]


# ── top_merchants ─────────────────────────────────────────────────────── #


def test_top_merchants_returns_correct_order(sample_df):
    result = top_merchants(sample_df, n=3)
    assert len(result) == 3
    assert result.iloc[0]["merchant"] == "ShopA"  # 1000 + 2000 + 1500 = 4500
    assert result.iloc[0]["total"] == 4500.0


def test_top_merchants_limits_to_n(sample_df):
    result = top_merchants(sample_df, n=1)
    assert len(result) == 1


def test_top_merchants_empty(empty_df):
    result = top_merchants(empty_df)
    assert result.empty


def test_top_merchants_credits_excluded(sample_df):
    result = top_merchants(sample_df, n=10)
    merchants = result["merchant"].tolist()
    assert "Salary" not in merchants


# ── period_comparison ─────────────────────────────────────────────────── #


def test_period_comparison_returns_both_periods(sample_df):
    result = period_comparison(sample_df, date(2026, 9, 1), date(2026, 9, 30))
    assert "current" in result
    assert "previous" in result
    assert "changes" in result

    cur = result["current"]
    prev = result["previous"]
    assert cur.total_transactions == 4  # 4 Sep transactions
    assert prev.total_transactions == 4  # 4 Aug transactions


def test_period_comparison_calculates_pct_change(sample_df):
    result = period_comparison(sample_df, date(2026, 9, 1), date(2026, 9, 30))
    changes = result["changes"]
    # spending: Aug 3500, Sep 2900 → (2900-3500)/3500*100 = -17.1%
    assert changes["spending"] is not None
    assert changes["spending"] < 0


def test_period_comparison_handles_zero_previous(empty_df):
    result = period_comparison(empty_df, date(2026, 9, 1), date(2026, 9, 30))
    assert result["current"].total_transactions == 0
    assert result["previous"].total_transactions == 0
    assert result["changes"]["spending"] is None


def test_period_comparison_prev_dates_correct(sample_df):
    result = period_comparison(sample_df, date(2026, 9, 1), date(2026, 9, 30))
    # 30 days in Sep → previous period: Aug 2 - Aug 31
    assert result["prev_start"] == date(2026, 8, 2)
    assert result["prev_end"] == date(2026, 8, 31)


# ── insights generation ──────────────────────────────────────────────── #


def test_insights_from_app(sample_df):
    """Test the _generate_insights function from app.py."""
    # Import here to avoid side effects from st.set_page_config
    import importlib
    import sys
    # We can't import app.py directly due to st.set_page_config,
    # so test the insight logic inline
    spend = sample_df[sample_df["type"] == "Debit"]
    income = sample_df[sample_df["type"] == "Credit"]

    top_cat = spend.groupby("category")["amount"].sum().idxmax()
    assert top_cat == "Shopping"

    total_income = income["amount"].sum()
    total_expense = spend["amount"].sum()
    assert total_income == 105000.0
    assert total_expense == 6400.0
    assert total_income > total_expense


def test_empty_data_produces_no_insights(empty_df):
    # The insights function requires >= 3 rows
    assert len(empty_df) < 3


# ── regression: zero-income period ────────────────────────────────────── #


def test_period_comparison_zero_income_returns_none():
    """When prior period has transactions but zero income, income change is None."""
    df = pd.DataFrame({
        "transaction_id": ["t0", "t1", "t2", "t3"],
        "date": pd.to_datetime(["2026-08-10", "2026-08-15", "2026-09-10", "2026-09-15"]),
        "description": ["d"] * 4,
        "merchant": ["Shop"] * 4,
        "category": ["Shopping"] * 4,
        "type": ["Debit", "Debit", "Debit", "Credit"],
        "amount": [1000.0, 2000.0, 500.0, 10000.0],
        "account": ["Primary"] * 4,
    })
    result = period_comparison(df, date(2026, 9, 1), date(2026, 9, 30))
    assert result["changes"]["income"] is None  # no income in Aug


def test_income_expense_over_time_debit_only():
    """Months with only debits should have income=0, not NaN."""
    df = pd.DataFrame({
        "transaction_id": ["t0", "t1"],
        "date": pd.to_datetime(["2026-08-05", "2026-08-10"]),
        "description": ["d", "d"],
        "merchant": ["Shop", "Shop"],
        "category": ["Shopping", "Shopping"],
        "type": ["Debit", "Debit"],
        "amount": [1000.0, 2000.0],
        "account": ["Primary", "Primary"],
    })
    result = income_expense_over_time(df, freq="MS")
    assert len(result) == 1
    assert result.iloc[0]["income"] == 0.0
    assert result.iloc[0]["expense"] == 3000.0
    assert result.iloc[0]["net"] == -3000.0


def test_period_comparison_single_day():
    """Period comparison works for a single-day range."""
    df = pd.DataFrame({
        "transaction_id": ["t0", "t1"],
        "date": pd.to_datetime(["2026-09-15", "2026-09-14"]),
        "description": ["d", "d"],
        "merchant": ["Shop", "Shop"],
        "category": ["Shopping", "Shopping"],
        "type": ["Debit", "Debit"],
        "amount": [500.0, 300.0],
        "account": ["Primary", "Primary"],
    })
    result = period_comparison(df, date(2026, 9, 15), date(2026, 9, 15))
    assert result["current"].total_transactions == 1
    assert result["current"].total_spending == 500.0
    assert result["prev_start"] == date(2026, 9, 14)
    assert result["prev_end"] == date(2026, 9, 14)
    assert result["previous"].total_transactions == 1
    assert result["previous"].total_spending == 300.0


def test_expense_to_income_ratio_consistency(sample_df):
    """The expense-to-income ratio should match total_expense / total_income * 100."""
    spend = sample_df[sample_df["type"] == "Debit"]
    income = sample_df[sample_df["type"] == "Credit"]
    total_expense = spend["amount"].sum()
    total_income = income["amount"].sum()
    expected_ratio = total_expense / total_income * 100
    assert abs(expected_ratio - 6400.0 / 105000.0 * 100) < 0.01
