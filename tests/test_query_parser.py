"""
Tests for the deterministic natural-language query parser
(src.query_parser.parse_deterministic) — the always-available fallback that
also backs the whole app when no LLM API key is configured.
"""

import pytest

from src.query_parser import InvalidQueryError, parse_deterministic


def test_main_example_query():
    q = parse_deterministic(
        "Show all transactions above ₹50,000 from last month and summarize my spending."
    )
    assert q.amount_threshold == 50000
    assert q.operator == "greater_than"
    assert q.date_range == "last_month"
    assert q.include_summary is True


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("transactions above ₹50,000", "greater_than"),
        ("transactions greater than ₹50,000", "greater_than"),
        ("transactions over ₹50,000", "greater_than"),
        ("transactions exceeding ₹50,000", "greater_than"),
        ("transactions below ₹50,000", "less_than"),
        ("transactions under ₹50,000", "less_than"),
        ("transactions at least ₹50,000", "greater_than_or_equal"),
        ("transactions at most ₹50,000", "less_than_or_equal"),
    ],
)
def test_operator_phrasing_variations(phrase, expected):
    q = parse_deterministic(phrase)
    assert q.operator == expected
    assert q.amount_threshold == 50000


@pytest.mark.parametrize(
    "phrase,expected_amount",
    [
        ("above ₹10,000", 10000),
        ("above ₹1 lakh", 100000),
        ("above 1.5 lakh", 150000),
        ("over 25000", 25000),
        ("above 50k", 50000),
        ("above 2 crore", 20000000),
    ],
)
def test_indian_currency_formats(phrase, expected_amount):
    q = parse_deterministic(phrase)
    assert q.amount_threshold == expected_amount


def test_show_transactions_above_20000():
    q = parse_deterministic("Show my transactions above ₹20,000.")
    assert q.amount_threshold == 20000
    assert q.operator == "greater_than"
    assert q.intent == "transaction_analysis"


def test_what_did_i_spend_last_month():
    q = parse_deterministic("What did I spend last month?")
    assert q.date_range == "last_month"
    assert q.intent == "spending_summary"
    assert q.transaction_type == "Debit"


def test_show_biggest_expenses():
    q = parse_deterministic("Show my biggest expenses.")
    assert q.intent == "top_expenses"
    assert q.sort_by == "amount_desc"


def test_category_spending_query():
    q = parse_deterministic("How much did I spend on shopping last month?")
    assert q.intent == "category_spending"
    assert q.category == "Shopping"
    assert q.date_range == "last_month"


def test_find_unusual_transactions():
    q = parse_deterministic("Find unusual transactions.")
    assert q.intent == "anomaly_detection"
    assert q.include_anomalies is True


def test_invalid_amount_raises_helpful_error():
    with pytest.raises(InvalidQueryError) as exc_info:
        parse_deterministic("Show transactions above xyz.")
    assert "amount" in exc_info.value.user_message.lower()


def test_empty_query_raises_helpful_error():
    with pytest.raises(InvalidQueryError):
        parse_deterministic("")


def test_query_with_no_amount_or_date_defaults_safely():
    q = parse_deterministic("Show my transactions")
    assert q.amount_threshold is None
    assert q.date_range == "all_time"


def test_this_week_and_last_week_variants():
    assert parse_deterministic("transactions this week").date_range == "this_week"
    assert parse_deterministic("transactions last week").date_range == "last_week"


def test_last_30_days_variant():
    q = parse_deterministic("show spending in the last 30 days")
    assert q.date_range == "last_30_days"
