"""
Specialist agent functions for the Banking Assistant Agent.

Each agent receives a pre-filtered DataFrame (user-scoped, date-filtered)
and a StructuredQuery, and returns a ToolResult with deterministic
financial analysis.  The LLM is never called here — all figures come
from Pandas/NumPy calculations.

Agents:
  - agent_trend_analysis:    Spending/income trends over time.
  - agent_period_comparison: Current vs previous period comparison.
  - agent_merchant_analysis: Top merchants by spending.
  - agent_income_analysis:   Income/credit transaction breakdown.
  - agent_cashflow_analysis: Net cash flow and savings rate.
  - agent_budget_analysis:   Expense-to-income ratios and category budgets.
  - agent_insights:          Automatic pattern detection and highlights.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.analytics import (
    income_expense_over_time,
    period_comparison,
    top_merchants,
)
from src.anomaly_detector import detect_anomalies
from src.formatting import format_inr
from src.tool_result import ToolResult
from src.validators import StructuredQuery


def agent_trend_analysis(df: pd.DataFrame, query: StructuredQuery, *, currency: str | None = None) -> ToolResult:
    """Analyze spending/income trends over time."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available to analyze trends.",
            "agent": "trend_analysis",
        })

    fmt = lambda amt: format_inr(amt, currency)
    ie = income_expense_over_time(df, freq="MS")
    top_m = top_merchants(df, n=5)

    lines = []
    if not ie.empty and len(ie) >= 2:
        latest = ie.iloc[-1]
        prev = ie.iloc[-2]
        lines.append(
            f"In {latest['period'].strftime('%B %Y')}, you spent {fmt(latest['expense'])} "
            f"and earned {fmt(latest['income'])} (net: {fmt(latest['net'])})."
        )
        if prev["expense"] > 0:
            pct = (latest["expense"] - prev["expense"]) / prev["expense"] * 100
            direction = "up" if pct > 0 else "down"
            lines.append(
                f"Spending was {direction} {abs(pct):.1f}% compared to "
                f"{prev['period'].strftime('%B %Y')} ({fmt(prev['expense'])})."
            )
    elif not ie.empty:
        row = ie.iloc[0]
        lines.append(
            f"In {row['period'].strftime('%B %Y')}, you spent {fmt(row['expense'])} "
            f"and earned {fmt(row['income'])}."
        )
        lines.append("Only one month of data is available, so trend analysis is limited.")

    if not top_m.empty:
        top3 = top_m.head(3)
        merchant_parts = [f"{r['merchant']} ({fmt(r['total'])})" for _, r in top3.iterrows()]
        lines.append(f"Top merchants by spending: {', '.join(merchant_parts)}.")

    return ToolResult(success=True, data={
        "direct_answer": " ".join(lines) if lines else "Not enough data to identify spending trends.",
        "agent": "trend_analysis",
        "ie_data": ie,
        "top_merchants": top_m,
    })


def agent_period_comparison(df: pd.DataFrame, query: StructuredQuery, today: date, *, currency: str | None = None) -> ToolResult:
    """Compare current period against previous equivalent period."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available for comparison.",
            "agent": "period_comparison",
        })

    from src.date_utils import resolve_date_range
    start, end, label = resolve_date_range(query.date_range, today)
    if start is None or end is None:
        start = df["date"].min().date() if hasattr(df["date"].min(), "date") else today
        end = today
        label = "All Time"

    comp = period_comparison(df, start, end)
    cur = comp["current"]
    prev = comp["previous"]
    changes = comp["changes"]

    fmt = lambda amt: format_inr(amt, currency)
    lines = [f"**{label}** vs previous equivalent period "
             f"({comp['prev_start'].strftime('%b %d')} – {comp['prev_end'].strftime('%b %d, %Y')}):"]

    lines.append(f"Spending: {fmt(cur.total_spending)}")
    if changes["spending"] is not None:
        lines[-1] += f" ({changes['spending']:+.1f}% vs prior)"

    lines.append(f"Income: {fmt(cur.total_income)}")
    if changes["income"] is not None:
        lines[-1] += f" ({changes['income']:+.1f}% vs prior)"

    lines.append(f"Net cash flow: {fmt(cur.net_cash_flow)}")
    lines.append(f"Transactions: {cur.total_transactions}")
    if changes["transactions"] is not None:
        lines[-1] += f" ({changes['transactions']:+.1f}% vs prior)"

    if prev.total_transactions == 0:
        lines.append("Note: no transactions found in the prior period for comparison.")

    return ToolResult(success=True, data={
        "direct_answer": " ".join(lines),
        "agent": "period_comparison",
        "comparison": comp,
    })


def agent_merchant_analysis(df: pd.DataFrame, query: StructuredQuery, *, currency: str | None = None) -> ToolResult:
    """Analyze spending by merchant."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available to analyze merchants.",
            "agent": "merchant_analysis",
        })

    spend = df[df["type"] == "Debit"]
    if spend.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No spending transactions found.",
            "agent": "merchant_analysis",
        })

    fmt = lambda amt: format_inr(amt, currency)
    top_m = top_merchants(spend, n=10)
    total_spend = spend["amount"].sum()
    lines = [f"Your top merchants by spending (out of {fmt(total_spend)} total):"]
    for i, (_, row) in enumerate(top_m.iterrows(), 1):
        pct = row["total"] / total_spend * 100 if total_spend > 0 else 0
        lines.append(f"{i}. {row['merchant']}: {fmt(row['total'])} ({pct:.1f}%) — {int(row['count'])} transactions")

    unique_merchants = spend["merchant"].nunique()
    lines.append(f"\nYou transacted with {unique_merchants} different merchants in total.")

    return ToolResult(success=True, data={
        "direct_answer": "\n".join(lines),
        "agent": "merchant_analysis",
        "top_merchants": top_m,
    })


def agent_income_analysis(df: pd.DataFrame, query: StructuredQuery, *, currency: str | None = None) -> ToolResult:
    """Analyze income/credit transactions."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available to analyze income.",
            "agent": "income_analysis",
        })

    income = df[df["type"] == "Credit"]
    if income.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No income/credit transactions found in your data.",
            "agent": "income_analysis",
        })

    total_income = income["amount"].sum()
    avg_income = income["amount"].mean()
    count = len(income)

    fmt = lambda amt: format_inr(amt, currency)
    lines = [f"Total income: {fmt(total_income)} from {count} credit transactions."]
    lines.append(f"Average credit transaction: {fmt(avg_income)}.")

    ie = income_expense_over_time(df, freq="MS")
    if not ie.empty and len(ie) >= 2:
        latest = ie.iloc[-1]
        lines.append(f"Most recent month ({latest['period'].strftime('%B %Y')}): {fmt(latest['income'])} income.")

    by_cat = income.groupby("category")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    if not by_cat.empty:
        top = by_cat.head(3)
        cat_parts = [f"{cat}: {fmt(row['sum'])} ({int(row['count'])} txns)" for cat, row in top.iterrows()]
        lines.append(f"Top income sources: {', '.join(cat_parts)}.")

    return ToolResult(success=True, data={
        "direct_answer": " ".join(lines),
        "agent": "income_analysis",
    })


def agent_cashflow_analysis(df: pd.DataFrame, query: StructuredQuery, *, currency: str | None = None) -> ToolResult:
    """Analyze net cash flow position."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available to analyze cash flow.",
            "agent": "cashflow_analysis",
        })

    total_income = df[df["type"] == "Credit"]["amount"].sum() if not df[df["type"] == "Credit"].empty else 0
    total_expense = df[df["type"] == "Debit"]["amount"].sum() if not df[df["type"] == "Debit"].empty else 0
    net = total_income - total_expense

    fmt = lambda amt: format_inr(amt, currency)
    lines = [
        f"Cash flow summary:",
        f"Total income: {fmt(total_income)}",
        f"Total expenses: {fmt(total_expense)}",
        f"Net cash flow: {fmt(net)}",
    ]

    if total_income > 0:
        savings_rate = (net / total_income) * 100
        lines.append(f"Savings rate: {savings_rate:.1f}% of income.")
        if savings_rate < 0:
            lines.append("Warning: your expenses exceed your income in this period.")
        elif savings_rate < 10:
            lines.append("Your savings rate is low. Consider reviewing discretionary spending.")
        elif savings_rate > 30:
            lines.append("Strong savings rate. You're retaining a healthy portion of your income.")

    ie = income_expense_over_time(df, freq="MS")
    if not ie.empty and len(ie) >= 2:
        positive_months = (ie["net"] > 0).sum()
        total_months = len(ie)
        lines.append(f"Positive cash flow months: {positive_months} out of {total_months}.")

    return ToolResult(success=True, data={
        "direct_answer": " ".join(lines),
        "agent": "cashflow_analysis",
        "ie_data": ie if not ie.empty else None,
    })


def agent_budget_analysis(df: pd.DataFrame, query: StructuredQuery, *, currency: str | None = None) -> ToolResult:
    """Analyze spending patterns for budget-related questions."""
    if df.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No transactions available for budget analysis.",
            "agent": "budget_analysis",
        })

    spend = df[df["type"] == "Debit"]
    income = df[df["type"] == "Credit"]
    if spend.empty:
        return ToolResult(success=True, data={
            "direct_answer": "No spending transactions found.",
            "agent": "budget_analysis",
        })

    total_spend = spend["amount"].sum()
    total_income = income["amount"].sum() if not income.empty else 0

    fmt = lambda amt: format_inr(amt, currency)
    lines = [f"Budget analysis based on your transaction data:"]
    lines.append(f"Total spending: {fmt(total_spend)}")

    if total_income > 0:
        ratio = total_spend / total_income * 100
        lines.append(f"Expense-to-income ratio: {ratio:.0f}%")
        if ratio > 100:
            lines.append(f"You are spending more than you earn by {fmt(total_spend - total_income)}.")
        elif ratio > 80:
            lines.append("Your spending is high relative to income. Consider reducing discretionary expenses.")
        else:
            lines.append(f"You're keeping spending within {ratio:.0f}% of income. Net savings: {fmt(total_income - total_spend)}.")

    by_cat = spend.groupby("category")["amount"].sum().sort_values(ascending=False)
    if not by_cat.empty:
        top5 = by_cat.head(5)
        lines.append("\nTop spending categories:")
        for cat, amt in top5.items():
            pct = amt / total_spend * 100 if total_spend > 0 else 0
            lines.append(f"  • {cat}: {fmt(amt)} ({pct:.0f}%)")

    monthly = spend.set_index("date").resample("MS")["amount"].sum()
    if len(monthly) >= 2:
        avg_monthly = monthly.mean()
        latest = monthly.iloc[-1]
        lines.append(f"\nAverage monthly spending: {fmt(avg_monthly)}")
        if latest > avg_monthly * 1.2:
            lines.append(f"Current month ({fmt(latest)}) is above your monthly average.")

    return ToolResult(success=True, data={
        "direct_answer": "\n".join(lines),
        "agent": "budget_analysis",
    })


def agent_insights(df: pd.DataFrame, *, currency: str | None = None) -> ToolResult:
    """Generate deterministic insights from the user's data."""
    if df.empty or len(df) < 3:
        return ToolResult(success=True, data={
            "direct_answer": "Not enough transaction data to generate insights yet.",
            "agent": "insights",
        })

    fmt = lambda amt: format_inr(amt, currency)
    spend = df[df["type"] == "Debit"]
    income = df[df["type"] == "Credit"]
    lines = []

    if not spend.empty:
        top_cat = spend.groupby("category")["amount"].sum()
        cat_name = top_cat.idxmax()
        cat_amt = top_cat.max()
        total_spend = spend["amount"].sum()
        pct = cat_amt / total_spend * 100 if total_spend > 0 else 0
        lines.append(f"Your largest spending category is {cat_name} at {fmt(cat_amt)} ({pct:.0f}% of total spending).")

    total_income = income["amount"].sum() if not income.empty else 0
    total_expense = spend["amount"].sum() if not spend.empty else 0
    if total_income > 0 and total_expense > 0:
        ratio = total_expense / total_income * 100
        lines.append(f"Your expense-to-income ratio is {ratio:.0f}%. "
                      f"Net cash flow: {fmt(total_income - total_expense)}.")
        if ratio > 100:
            lines.append("Note: expenses exceed income based on imported transactions. "
                          "This may not include all income sources.")

    if not spend.empty:
        freq = spend["merchant"].value_counts()
        if freq.iloc[0] >= 3:
            lines.append(f"Most frequent merchant: {freq.index[0]} ({freq.iloc[0]} transactions).")

    anomalies = detect_anomalies(df, currency=currency)
    if anomalies:
        lines.append(f"{len(anomalies)} potentially unusual transactions detected "
                      f"(statistical patterns, not fraud detection).")

    return ToolResult(success=True, data={
        "direct_answer": " ".join(lines) if lines else "Not enough data to generate meaningful insights.",
        "agent": "insights",
    })
