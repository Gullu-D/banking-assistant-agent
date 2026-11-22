"""
Deterministic financial analytics.

Every number produced here comes from plain pandas/numpy arithmetic — no LLM
involvement. These functions are the single source of truth for all totals,
averages, and breakdowns shown in the UI and handed to the summarizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

import config
from src.validators import CategoryBreakdownItem


def _safe_float(value) -> float:
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return 0.0
    return float(value)


@dataclass
class OverallStatistics:
    total_transactions: int = 0
    total_spending: float = 0.0
    total_income: float = 0.0
    net_cash_flow: float = 0.0
    average_transaction: float = 0.0
    largest_transaction: float = 0.0
    smallest_transaction: float = 0.0


@dataclass
class MatchingStatistics:
    matching_transaction_count: int = 0
    matching_total_amount: float = 0.0
    matching_average_amount: float = 0.0
    matching_largest_amount: float = 0.0
    matching_smallest_amount: float = 0.0


def calculate_overall_statistics(df: pd.DataFrame) -> OverallStatistics:
    """Compute overall statistics for a (typically period-scoped) dataframe.

    `total_spending` sums Debit transactions; `total_income` sums Credit
    transactions. `average/largest/smallest transaction` are computed across
    ALL transactions in `df` regardless of type.
    """
    if df.empty:
        return OverallStatistics()

    debit_mask = df["type"] == "Debit"
    credit_mask = df["type"] == "Credit"

    total_spending = _safe_float(df.loc[debit_mask, "amount"].sum())
    total_income = _safe_float(df.loc[credit_mask, "amount"].sum())

    return OverallStatistics(
        total_transactions=int(len(df)),
        total_spending=total_spending,
        total_income=total_income,
        net_cash_flow=_safe_float(total_income - total_spending),
        average_transaction=_safe_float(df["amount"].mean()),
        largest_transaction=_safe_float(df["amount"].max()),
        smallest_transaction=_safe_float(df["amount"].min()),
    )


def calculate_matching_statistics(filtered_df: pd.DataFrame) -> MatchingStatistics:
    """Compute statistics for the transactions that matched the user's filters."""
    if filtered_df.empty:
        return MatchingStatistics()

    return MatchingStatistics(
        matching_transaction_count=int(len(filtered_df)),
        matching_total_amount=_safe_float(filtered_df["amount"].sum()),
        matching_average_amount=_safe_float(filtered_df["amount"].mean()),
        matching_largest_amount=_safe_float(filtered_df["amount"].max()),
        matching_smallest_amount=_safe_float(filtered_df["amount"].min()),
    )


def calculate_category_breakdown(filtered_df: pd.DataFrame, spending_only: bool = True) -> list[CategoryBreakdownItem]:
    """Compute per-category transaction count, total amount, and % of spending.

    By default only Debit (spending) transactions contribute, so percentages
    are relative to total spending rather than mixing in income/transfers.
    """
    if filtered_df.empty:
        return []

    scope = filtered_df[filtered_df["type"] == "Debit"] if spending_only else filtered_df
    if scope.empty:
        return []

    total = scope["amount"].sum()
    if total <= 0:
        return []

    grouped = (
        scope.groupby("category", dropna=False)["amount"]
        .agg(transaction_count="count", total_amount="sum")
        .reset_index()
    )
    grouped["percentage_of_spending"] = (grouped["total_amount"] / total * 100).round(2)
    grouped = grouped.sort_values("total_amount", ascending=False)

    return [
        CategoryBreakdownItem(
            category=row["category"],
            transaction_count=int(row["transaction_count"]),
            total_amount=_safe_float(row["total_amount"]),
            percentage_of_spending=_safe_float(row["percentage_of_spending"]),
        )
        for _, row in grouped.iterrows()
    ]


def spending_over_time(filtered_df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Return a daily/weekly/monthly time series of spending (Debit only) for charting."""
    if filtered_df.empty:
        return pd.DataFrame(columns=["period", "amount"])

    spend = filtered_df[filtered_df["type"] == "Debit"].copy()
    if spend.empty:
        return pd.DataFrame(columns=["period", "amount"])

    spend = spend.set_index("date")
    series = spend["amount"].resample(freq).sum().reset_index()
    series.columns = ["period", "amount"]
    return series


def income_expense_over_time(df: pd.DataFrame, freq: str = "MS") -> pd.DataFrame:
    """Return a time series with income, expense, and net columns per period."""
    if df.empty:
        return pd.DataFrame(columns=["period", "income", "expense", "net"])

    tmp = df.copy()
    tmp = tmp.set_index("date")

    expense = tmp.loc[tmp["type"] == "Debit", "amount"].resample(freq).sum()
    income = tmp.loc[tmp["type"] == "Credit", "amount"].resample(freq).sum()

    combined = pd.DataFrame({"income": income, "expense": expense}).fillna(0)
    combined["net"] = combined["income"] - combined["expense"]
    combined = combined.reset_index().rename(columns={"date": "period"})
    return combined


def top_merchants(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return top-n merchants by total spending (Debit only)."""
    if df.empty:
        return pd.DataFrame(columns=["merchant", "total", "count"])

    spend = df[df["type"] == "Debit"]
    if spend.empty:
        return pd.DataFrame(columns=["merchant", "total", "count"])

    grouped = (
        spend.groupby("merchant")["amount"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("total", ascending=False)
        .head(n)
    )
    return grouped


def period_comparison(
    df: pd.DataFrame,
    current_start: date,
    current_end: date,
) -> dict:
    """Compare current period stats against the equivalent previous period.

    Previous period is the same number of days immediately before current_start.
    Returns dict with current/previous OverallStatistics and pct changes.
    """
    from datetime import timedelta

    days = (current_end - current_start).days + 1
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    cur_mask = (df["date"] >= pd.Timestamp(current_start)) & (df["date"] <= pd.Timestamp(current_end))
    prev_mask = (df["date"] >= pd.Timestamp(prev_start)) & (df["date"] <= pd.Timestamp(prev_end))

    cur_stats = calculate_overall_statistics(df[cur_mask])
    prev_stats = calculate_overall_statistics(df[prev_mask])

    def pct_change(cur: float, prev: float) -> float | None:
        if prev == 0:
            return None
        return round((cur - prev) / prev * 100, 1)

    return {
        "current": cur_stats,
        "previous": prev_stats,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "changes": {
            "spending": pct_change(cur_stats.total_spending, prev_stats.total_spending),
            "income": pct_change(cur_stats.total_income, prev_stats.total_income),
            "net_cash_flow": pct_change(cur_stats.net_cash_flow, prev_stats.net_cash_flow),
            "transactions": pct_change(cur_stats.total_transactions, prev_stats.total_transactions),
        },
    }
