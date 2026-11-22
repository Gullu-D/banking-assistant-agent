"""Currency and number formatting utilities."""

from __future__ import annotations

import config

_CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "GBP": "£",
    "USD": "$",
    "EUR": "€",
}


def _symbol(currency: str | None) -> str:
    if currency and currency.upper() in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[currency.upper()]
    return config.CURRENCY_SYMBOL


def format_inr(amount: float, currency: str | None = None) -> str:
    """Format a number with the appropriate currency symbol.

    INR uses Indian digit grouping (1,25,000).
    Other currencies use standard Western grouping (125,000).
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return f"{_symbol(currency)}0"
    negative = amount < 0
    amount = abs(amount)
    sign = "-" if negative else ""
    sym = _symbol(currency)

    if currency and currency.upper() != "INR":
        formatted = f"{amount:,.0f}"
        return f"{sign}{sym}{formatted}"

    int_part = f"{amount:,.0f}".replace(",", "")
    if len(int_part) <= 3:
        formatted = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3
    return f"{sign}{sym}{formatted}"
