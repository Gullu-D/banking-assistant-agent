"""
Tests for the Indian currency formatting helper (app.format_inr).
"""

import pytest

from src.formatting import format_inr


@pytest.mark.parametrize(
    "amount,expected",
    [
        (0, "₹0"),
        (999, "₹999"),
        (1000, "₹1,000"),
        (10000, "₹10,000"),
        (100000, "₹1,00,000"),
        (125000, "₹1,25,000"),
        (1250000, "₹12,50,000"),
        (12500000, "₹1,25,00,000"),
        (50001, "₹50,001"),
    ],
)
def test_indian_digit_grouping(amount, expected):
    assert format_inr(amount) == expected


def test_negative_amount():
    result = format_inr(-125000)
    assert result.startswith("-₹")
    assert "1,25,000" in result


def test_float_amount_rounds():
    result = format_inr(1234.56)
    assert result == "₹1,235"


def test_invalid_input_returns_zero():
    assert format_inr("not_a_number") == "₹0"
    assert format_inr(None) == "₹0"
