"""
Tests for transaction categorization (src.categorizer).

Covers: canonical normalization, alias mapping, keyword inference from
merchant/description, "Other" fallback, and DataFrame-level categorization.
"""

import pandas as pd

from src.categorizer import (
    categorize_transactions,
    infer_category_from_text,
    normalize_category,
)


def test_canonical_categories_normalize_to_themselves():
    assert normalize_category("Shopping") == "Shopping"
    assert normalize_category("Food & Dining") == "Food & Dining"
    assert normalize_category("Salary / Income") == "Salary / Income"
    assert normalize_category("ATM / Cash Withdrawal") == "ATM / Cash Withdrawal"


def test_normalization_is_case_insensitive():
    assert normalize_category("shopping") == "Shopping"
    assert normalize_category("TRAVEL") == "Travel"
    assert normalize_category("rent") == "Rent"


def test_known_aliases_map_correctly():
    assert normalize_category("grocery") == "Groceries"
    assert normalize_category("restaurant") == "Food & Dining"
    assert normalize_category("medical") == "Healthcare"
    assert normalize_category("upi") == "Transfers"
    assert normalize_category("salary") == "Salary / Income"
    assert normalize_category("atm") == "ATM / Cash Withdrawal"
    assert normalize_category("misc") == "Other"


def test_unrecognized_category_returns_none():
    assert normalize_category("completely_unknown_category") is None
    assert normalize_category("") is None


def test_infer_from_merchant_keywords():
    assert infer_category_from_text("Swiggy", "") == "Food & Dining"
    assert infer_category_from_text("BigBasket", "") == "Groceries"
    assert infer_category_from_text("Amazon", "") == "Shopping"
    assert infer_category_from_text("Uber", "") == "Travel"
    assert infer_category_from_text("Netflix", "") == "Entertainment"
    assert infer_category_from_text("Zerodha", "") == "Investments"
    assert infer_category_from_text("ATM Withdrawal", "") == "ATM / Cash Withdrawal"


def test_infer_from_description_keywords():
    assert infer_category_from_text("Unknown", "Salary credit") == "Salary / Income"
    assert infer_category_from_text("Unknown", "Electricity bill") == "Utilities"
    assert infer_category_from_text("Unknown", "UPI transfer to friend") == "Transfers"


def test_infer_falls_back_to_other():
    assert infer_category_from_text("Random Vendor", "Some random thing") == "Other"
    assert infer_category_from_text("", "") == "Other"


_COLUMNS = ["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"]


def _make_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_categorize_normalizes_known_categories():
    df = _make_df([
        dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M",
             category="shopping", type="Debit", amount=1000, account="Primary"),
    ])
    result = categorize_transactions(df)
    assert result.iloc[0]["category"] == "Shopping"


def test_categorize_infers_missing_categories():
    df = _make_df([
        dict(transaction_id="T1", date="2026-07-01", description="d", merchant="Swiggy",
             category="unknown_garbage", type="Debit", amount=500, account="Primary"),
    ])
    result = categorize_transactions(df)
    assert result.iloc[0]["category"] == "Food & Dining"


def test_categorize_empty_df():
    df = _make_df([])
    result = categorize_transactions(df)
    assert result.empty
