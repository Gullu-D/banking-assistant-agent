"""
Transaction categorization.

- Validates/normalizes categories already present in the dataset against the
  canonical category list (case-insensitive matching, common synonyms).
- Infers a category deterministically (via merchant/description keyword
  rules) for any transaction whose category is missing or unrecognized.

The LLM is never allowed to silently invent a category. If AI-assisted
categorization is used in the future, its output must still be validated
against `config.VALID_CATEGORIES` here before being accepted.
"""

from __future__ import annotations

import re

import pandas as pd

import config

logger = config.get_logger(__name__)

# Canonical category -> accepted synonyms/aliases (lower-cased).
_CATEGORY_ALIASES: dict[str, str] = {}
for canonical in config.VALID_CATEGORIES:
    _CATEGORY_ALIASES[canonical.lower()] = canonical

_CATEGORY_ALIASES.update(
    {
        "food": "Food & Dining",
        "dining": "Food & Dining",
        "restaurant": "Food & Dining",
        "restaurants": "Food & Dining",
        "grocery": "Groceries",
        "shop": "Shopping",
        "shopping online": "Shopping",
        "e-commerce": "Shopping",
        "ecommerce": "Shopping",
        "travel & transport": "Travel",
        "transport": "Travel",
        "transportation": "Travel",
        "cab": "Travel",
        "flights": "Travel",
        "housing": "Rent",
        "bills": "Utilities",
        "bill payment": "Utilities",
        "electricity": "Utilities",
        "internet": "Utilities",
        "medical": "Healthcare",
        "health": "Healthcare",
        "hospital": "Healthcare",
        "pharmacy": "Healthcare",
        "school": "Education",
        "tuition": "Education",
        "movies": "Entertainment",
        "movie": "Entertainment",
        "subscription": "Entertainment",
        "subscriptions": "Entertainment",
        "investment": "Investments",
        "mutual fund": "Investments",
        "stocks": "Investments",
        "sip": "Investments",
        "transfer": "Transfers",
        "upi": "Transfers",
        "neft": "Transfers",
        "imps": "Transfers",
        "salary": "Salary / Income",
        "income": "Salary / Income",
        "payroll": "Salary / Income",
        "freelance": "Freelance",
        "freelancing": "Freelance",
        "contract work": "Freelance",
        "interest": "Interest",
        "bank interest": "Interest",
        "savings interest": "Interest",
        "refund": "Refund",
        "cashback": "Refund",
        "return": "Refund",
        "atm": "ATM / Cash Withdrawal",
        "cash withdrawal": "ATM / Cash Withdrawal",
        "cash": "ATM / Cash Withdrawal",
        "other": "Other",
        "misc": "Other",
        "miscellaneous": "Other",
    }
)

# Keyword rules used to INFER a category from merchant/description text when
# the source category is missing or unrecognized. Order matters: first match
# wins, so more specific patterns are listed before generic ones.
_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"salary|payroll", re.I), "Salary / Income"),
    (re.compile(r"rent|landlord|lease", re.I), "Rent"),
    (re.compile(r"electricity|water dept|broadband|fiber|wifi|utility|utilit(y|ies)", re.I), "Utilities"),
    (re.compile(r"atm|cash withdrawal", re.I), "ATM / Cash Withdrawal"),
    (re.compile(r"hospital|pharmacy|clinic|health|medical|doctor|lab", re.I), "Healthcare"),
    (re.compile(r"school|college|university|course|tuition|udemy|coursera|byju", re.I), "Education"),
    (re.compile(r"netflix|spotify|cinema|movie|bookmyshow|pvr|prime video|hotstar", re.I), "Entertainment"),
    (re.compile(r"zerodha|groww|mutual fund|sip|stocks|equity|investment", re.I), "Investments"),
    (re.compile(r"upi|neft|imps|fund transfer|transfer to", re.I), "Transfers"),
    (re.compile(r"swiggy|zomato|restaurant|cafe|food|dining|barbeque|pizza", re.I), "Food & Dining"),
    (re.compile(r"bigbasket|dmart|grocery|supermarket|reliance fresh|more supermarket", re.I), "Groceries"),
    (re.compile(r"flight|indigo|makemytrip|irctc|hotel|oyo|uber|ola|cab|train", re.I), "Travel"),
    (re.compile(r"amazon|flipkart|myntra|electronics|croma|digital|lifestyle|mall|store", re.I), "Shopping"),
]


def normalize_category(raw_value: str) -> str | None:
    """Map a raw category string to a canonical category, or None if unrecognized."""
    if not raw_value:
        return None
    key = str(raw_value).strip().lower()
    return _CATEGORY_ALIASES.get(key)


def infer_category_from_text(merchant: str, description: str) -> str:
    """Deterministically infer a category using merchant/description keywords.

    Falls back to "Other" if nothing matches — never returns an invented
    category outside the canonical list.
    """
    haystack = f"{merchant or ''} {description or ''}"
    for pattern, category in _KEYWORD_RULES:
        if pattern.search(haystack):
            return category
    return "Other"


def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with a validated/normalized `category` column.

    - Known categories (including recognized synonyms) are normalized to the
      canonical spelling.
    - Missing or unrecognized categories are inferred deterministically from
      merchant + description text, falling back to "Other".
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    normalized = out["category"].apply(normalize_category)

    needs_inference = normalized.isna()
    n_inferred = int(needs_inference.sum())

    if n_inferred:
        inferred_values = out.loc[needs_inference].apply(
            lambda row: infer_category_from_text(row.get("merchant", ""), row.get("description", "")),
            axis=1,
        )
        normalized.loc[needs_inference] = inferred_values
        logger.info("Inferred category for %d transaction(s) with missing/unrecognized categories", n_inferred)

    out["category"] = normalized
    return out
