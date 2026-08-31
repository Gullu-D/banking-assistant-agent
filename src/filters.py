"""
Deterministic transaction filtering.

ALL filtering (date range, amount threshold, category, transaction type) is
performed here using plain pandas boolean masks. The LLM never filters data
directly — it only ever produces a StructuredQuery, which this module
executes mechanically and reproducibly.
"""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.date_utils import resolve_date_range
from src.validators import StructuredQuery

_OPERATORS = {
    "greater_than": lambda s, v: s > v,
    "greater_than_or_equal": lambda s, v: s >= v,
    "less_than": lambda s, v: s < v,
    "less_than_or_equal": lambda s, v: s <= v,
    "equal": lambda s, v: s == v,
}


@dataclass
class FilterOutcome:
    filtered_df: pd.DataFrame
    period_start: Optional[date]
    period_end: Optional[date]
    period_label: str
    applied_amount_filter: bool
    applied_category_filter: bool


def apply_filters(df: pd.DataFrame, query: StructuredQuery, today: Optional[date] = None) -> FilterOutcome:
    """Apply date range, amount threshold, category, and type filters.

    `df` must already be the cleaned/validated transaction dataframe from
    TransactionRepository (with a proper datetime64 `date` column and a
    numeric `amount` column).
    """
    working = df.copy()

    # --- Date range filter -------------------------------------------------
    start, end, label = resolve_date_range(
        query.date_range,
        today=today,
        custom_start=query.custom_start_date,
        custom_end=query.custom_end_date,
    )
    if start is not None and end is not None:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        working = working[(working["date"] >= start_ts) & (working["date"] <= end_ts)]

    # --- Amount threshold filter --------------------------------------------
    applied_amount_filter = False
    if query.amount_threshold is not None and query.operator is not None:
        op_fn = _OPERATORS.get(query.operator)
        if op_fn is not None:
            working = working[op_fn(working["amount"], query.amount_threshold)]
            applied_amount_filter = True

    # --- Category filter -----------------------------------------------------
    applied_category_filter = False
    if query.category:
        working = working[working["category"].str.casefold() == query.category.casefold()]
        applied_category_filter = True

    # --- Transaction type filter ----------------------------------------------
    if query.transaction_type:
        working = working[working["type"] == query.transaction_type]

    # --- Sorting / top_n -------------------------------------------------------
    sort_by = query.sort_by
    if sort_by is None and query.intent == "top_expenses":
        sort_by = "amount_desc"

    if sort_by == "amount_desc":
        working = working.sort_values("amount", ascending=False)
    elif sort_by == "amount_asc":
        working = working.sort_values("amount", ascending=True)
    elif sort_by == "date_desc":
        working = working.sort_values("date", ascending=False)
    elif sort_by == "date_asc":
        working = working.sort_values("date", ascending=True)
    else:
        working = working.sort_values("date", ascending=False)

    if query.top_n:
        working = working.head(query.top_n)

    working = working.reset_index(drop=True)

    return FilterOutcome(
        filtered_df=working,
        period_start=start,
        period_end=end,
        period_label=label,
        applied_amount_filter=applied_amount_filter,
        applied_category_filter=applied_category_filter,
    )
