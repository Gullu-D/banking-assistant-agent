"""
Tests for deterministic financial analytics (src.analytics) — totals must be
mathematically correct against hand-computed known values.
"""

import pandas as pd

from src.analytics import (
    calculate_category_breakdown,
    calculate_matching_statistics,
    calculate_overall_statistics,
)


_COLUMNS = ["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"]


def _make_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_overall_statistics_known_values():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M", category="Salary / Income", type="Credit", amount=90000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-02", description="d", merchant="M", category="Rent", type="Debit", amount=35000, account="Primary"),
            dict(transaction_id="T3", date="2026-07-03", description="d", merchant="M", category="Shopping", type="Debit", amount=15000, account="Primary"),
        ]
    )
    stats = calculate_overall_statistics(df)
    assert stats.total_transactions == 3
    assert stats.total_spending == 50000  # 35000 + 15000
    assert stats.total_income == 90000
    assert stats.net_cash_flow == 40000  # 90000 - 50000
    assert stats.largest_transaction == 90000
    assert stats.smallest_transaction == 15000
    assert stats.average_transaction == (90000 + 35000 + 15000) / 3


def test_overall_statistics_empty_df():
    df = _make_df([])
    stats = calculate_overall_statistics(df)
    assert stats.total_transactions == 0
    assert stats.total_spending == 0
    assert stats.net_cash_flow == 0


def test_matching_statistics_known_values():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M", category="Shopping", type="Debit", amount=60000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-02", description="d", merchant="M", category="Travel", type="Debit", amount=80000, account="Primary"),
        ]
    )
    stats = calculate_matching_statistics(df)
    assert stats.matching_transaction_count == 2
    assert stats.matching_total_amount == 140000
    assert stats.matching_average_amount == 70000
    assert stats.matching_largest_amount == 80000
    assert stats.matching_smallest_amount == 60000


def test_category_breakdown_percentages_sum_to_100():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M", category="Shopping", type="Debit", amount=125000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-02", description="d", merchant="M", category="Education", type="Debit", amount=95000, account="Primary"),
            dict(transaction_id="T3", date="2026-07-03", description="d", merchant="M", category="Travel", type="Debit", amount=80000, account="Primary"),
            dict(transaction_id="T4", date="2026-07-04", description="d", merchant="M", category="Other", type="Debit", amount=50000, account="Primary"),
        ]
    )
    breakdown = calculate_category_breakdown(df)
    total_pct = sum(item.percentage_of_spending for item in breakdown)
    assert 99.9 <= total_pct <= 100.1

    shopping = next(item for item in breakdown if item.category == "Shopping")
    assert shopping.total_amount == 125000
    assert shopping.transaction_count == 1
    # 125000 / 350000 = ~35.71%
    assert 35.0 <= shopping.percentage_of_spending <= 36.0


def test_category_breakdown_excludes_income_by_default():
    df = _make_df(
        [
            dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M", category="Salary / Income", type="Credit", amount=90000, account="Primary"),
            dict(transaction_id="T2", date="2026-07-02", description="d", merchant="M", category="Shopping", type="Debit", amount=10000, account="Primary"),
        ]
    )
    breakdown = calculate_category_breakdown(df)
    categories = {item.category for item in breakdown}
    assert "Salary / Income" not in categories
    assert categories == {"Shopping"}


def test_category_breakdown_empty_df():
    df = _make_df([])
    assert calculate_category_breakdown(df) == []
