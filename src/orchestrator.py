"""
Multi-agent orchestration foundation.

Wraps the existing deterministic pipeline modules (analytics, anomaly
detection, summarizer) as typed "tools" that an orchestrator can dispatch.
The orchestrator routes a user's natural-language query to one or more tools,
enforcing user-data scope on every call.

Design:
  - Each tool is a plain function with a typed input/output.
  - Financial arithmetic is always deterministic (Pandas/NumPy).
  - An LLM may interpret queries or explain verified results; it never
    invents authoritative figures.
  - Without API keys, everything falls back to deterministic mode.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

import config
from src.analytics import (
    MatchingStatistics,
    calculate_category_breakdown,
    calculate_matching_statistics,
    calculate_overall_statistics,
    spending_over_time,
)
from src.anomaly_detector import detect_anomalies
from src.categorizer import categorize_transactions
from src.data_loader import LoadReport, TransactionDataError, TransactionRepository
from src.filters import FilterOutcome, apply_filters
from src.formatting import format_inr
from src.query_parser import InvalidQueryError, parse_query
from src.services import DBTransactionRepository
from src.summarizer import generate_summary
from src.validators import AnalysisSummaryInput, AnomalyRecord, CategoryBreakdownItem, StructuredQuery

# Specialist agents — each is a separate module function.
from src.agents import (  # noqa: E402
    agent_budget_analysis,
    agent_cashflow_analysis,
    agent_income_analysis,
    agent_insights,
    agent_merchant_analysis,
    agent_period_comparison,
    agent_trend_analysis,
)

logger = config.get_logger(__name__)


from src.tool_result import ToolResult  # shared with src.agents


def tool_load_transactions(
    db: Session | None, user_id: int | None, csv_path: str | None = None
) -> tuple[pd.DataFrame, LoadReport]:
    if db and user_id:
        repo = DBTransactionRepository(db, user_id)
    else:
        repo = TransactionRepository(csv_path)
    return repo.load()


def tool_analyze_transactions(
    df: pd.DataFrame, query: StructuredQuery, today: date | None = None
) -> dict:
    today = today or date.today()
    categorized = categorize_transactions(df)

    period_query = query.model_copy(
        update={
            "amount_threshold": None,
            "operator": None,
            "category": None,
            "transaction_type": None,
            "top_n": None,
            "sort_by": None,
        }
    )
    period_outcome = apply_filters(categorized, period_query, today=today)
    matching_outcome = apply_filters(categorized, query, today=today)

    overall_stats = calculate_overall_statistics(period_outcome.filtered_df)
    matching_stats = calculate_matching_statistics(matching_outcome.filtered_df)
    category_breakdown = calculate_category_breakdown(matching_outcome.filtered_df)
    time_series = spending_over_time(matching_outcome.filtered_df)

    return {
        "period_outcome": period_outcome,
        "matching_outcome": matching_outcome,
        "overall_stats": overall_stats,
        "matching_stats": matching_stats,
        "category_breakdown": category_breakdown,
        "time_series": time_series,
    }


def tool_detect_anomalies(df: pd.DataFrame, *, currency: str | None = None) -> list[AnomalyRecord]:
    return detect_anomalies(df, currency=currency)


def tool_generate_summary(
    analysis: dict,
    query: StructuredQuery,
    query_description: str,
    *,
    currency: str | None = None,
) -> tuple[str, str]:
    matching_outcome = analysis["matching_outcome"]
    overall_stats = analysis["overall_stats"]
    matching_stats = analysis["matching_stats"]

    summary_input = AnalysisSummaryInput(
        period_label=matching_outcome.period_label,
        period_start=matching_outcome.period_start,
        period_end=matching_outcome.period_end,
        query_description=query_description,
        total_transactions_overall=overall_stats.total_transactions,
        total_spending_overall=overall_stats.total_spending,
        total_income_overall=overall_stats.total_income,
        net_cash_flow_overall=overall_stats.net_cash_flow,
        matching_transaction_count=matching_stats.matching_transaction_count,
        matching_total_amount=matching_stats.matching_total_amount,
        matching_average_amount=matching_stats.matching_average_amount,
        matching_largest_amount=matching_stats.matching_largest_amount,
        matching_smallest_amount=matching_stats.matching_smallest_amount,
        category_breakdown=analysis["category_breakdown"],
        anomalies=analysis.get("anomalies", []),
    )

    if query.include_summary:
        return generate_summary(summary_input, currency=currency)
    return "", "skipped"


class Orchestrator:
    """Routes user queries through the deterministic pipeline.

    When a DB session and user_id are provided, transactions come from the
    database (user-scoped). Otherwise falls back to CSV for backward
    compatibility and testing.
    """

    def __init__(
        self,
        db: Session | None = None,
        user_id: int | None = None,
        csv_path: str | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.csv_path = csv_path

    def _resolve_currency(self) -> str | None:
        """Look up the user's primary account currency, if available."""
        if not self.db or not self.user_id:
            return None
        from src.services import get_default_account
        acct = get_default_account(self.db, self.user_id)
        return acct.currency if acct else None

    def run(self, raw_query: str, today: date | None = None,
            context: ConversationContext | None = None) -> ToolResult:
        today = today or date.today()
        currency = self._resolve_currency()

        try:
            query, parse_method = parse_query(raw_query)
        except InvalidQueryError as exc:
            return ToolResult(success=False, error=exc.user_message)
        except Exception:
            logger.exception("Query parse error")
            return ToolResult(success=False, error="Could not understand the question.")

        if context:
            query = context.resolve_follow_up(query)

        # Expense-focused intents should only show Debit transactions
        _expense_intents = {"top_expenses", "spending_summary", "category_spending"}
        if query.intent in _expense_intents and not query.transaction_type:
            query = query.model_copy(update={"transaction_type": "Debit"})

        try:
            df, load_report = tool_load_transactions(self.db, self.user_id, self.csv_path)
        except TransactionDataError as exc:
            return ToolResult(success=False, error=exc.user_message)
        except Exception:
            logger.exception("Transaction load error")
            return ToolResult(success=False, error="Failed to load transactions.")

        # Route to specialized agents for new intents
        _agent_intents = {"trend_analysis", "period_comparison", "insights_query",
                          "merchant_analysis", "income_analysis", "cashflow_analysis", "budget_query"}
        if query.intent in _agent_intents:
            # Apply date filter so agents respect the parsed date range
            from src.date_utils import resolve_date_range
            start, end, period_label = resolve_date_range(query.date_range, today)
            agent_df = df
            if start is not None and end is not None:
                agent_df = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]
            else:
                period_label = "All Time"

            if query.intent == "trend_analysis":
                result = agent_trend_analysis(agent_df, query, currency=currency)
            elif query.intent == "period_comparison":
                result = agent_period_comparison(df, query, today, currency=currency)
            elif query.intent == "merchant_analysis":
                result = agent_merchant_analysis(agent_df, query, currency=currency)
            elif query.intent == "income_analysis":
                result = agent_income_analysis(agent_df, query, currency=currency)
            elif query.intent == "cashflow_analysis":
                result = agent_cashflow_analysis(agent_df, query, currency=currency)
            elif query.intent == "budget_query":
                result = agent_budget_analysis(agent_df, query, currency=currency)
            else:
                result = agent_insights(agent_df, currency=currency)
            result.data["query"] = query
            result.data["parse_method"] = parse_method
            result.data["load_report"] = load_report
            result.data["llm_provider"] = config.active_llm_provider()
            result.data["currency"] = currency
            result.data.setdefault("period_label", period_label)
            self._record_turn(context, raw_query, query, result)
            return result

        try:
            analysis = tool_analyze_transactions(df, query, today)
            anomalies = tool_detect_anomalies(analysis["period_outcome"].filtered_df, currency=currency)
            analysis["anomalies"] = anomalies

            query_desc = _describe_query(query, currency=currency)
            summary_text, summary_method = tool_generate_summary(analysis, query, query_desc, currency=currency)

            matching_outcome = analysis["matching_outcome"]
            matching_stats = analysis["matching_stats"]

            direct_answer = _build_direct_answer(query, matching_stats, analysis, currency=currency)

            result = ToolResult(
                success=True,
                data={
                    "query": query,
                    "parse_method": parse_method,
                    "period_label": matching_outcome.period_label,
                    "period_start": matching_outcome.period_start,
                    "period_end": matching_outcome.period_end,
                    "matching_df": matching_outcome.filtered_df,
                    "period_df": analysis["period_outcome"].filtered_df,
                    "overall_stats": analysis["overall_stats"],
                    "matching_stats": matching_stats,
                    "category_breakdown": analysis["category_breakdown"],
                    "anomalies": anomalies,
                    "time_series": analysis["time_series"],
                    "summary_text": summary_text,
                    "summary_method": summary_method,
                    "direct_answer": direct_answer,
                    "load_report": load_report,
                    "llm_provider": config.active_llm_provider(),
                    "currency": currency,
                },
            )
            self._record_turn(context, raw_query, query, result)
            return result
        except Exception:
            logger.exception("Analysis error")
            return ToolResult(success=False, error="Analysis failed unexpectedly.")

    @staticmethod
    def _record_turn(context: ConversationContext | None, raw_query: str,
                     query: StructuredQuery, result: ToolResult):
        if context and result.success:
            preview = result.data.get("direct_answer", "") or result.data.get("summary_text", "")
            context.add_turn(
                query=raw_query,
                intent=query.intent,
                date_range=query.date_range,
                category=query.category,
                answer_preview=preview,
            )


def _describe_query(query: StructuredQuery, *, currency: str | None = None) -> str:
    from src.formatting import _symbol
    sym = _symbol(currency)
    parts = []
    if query.amount_threshold is not None and query.operator:
        op_word = {
            "greater_than": "above",
            "greater_than_or_equal": "at least",
            "less_than": "below",
            "less_than_or_equal": "at most",
            "equal": "equal to",
        }[query.operator]
        parts.append(f"transactions {op_word} {sym}{query.amount_threshold:,.0f}")
    else:
        parts.append("all transactions")
    if query.category:
        parts.append(f"in {query.category}")
    if query.transaction_type:
        parts.append(f"({query.transaction_type} only)")
    return " ".join(parts)


def _build_direct_answer(query: StructuredQuery, matching_stats: MatchingStatistics,
                         analysis: dict, *, currency: str | None = None) -> str:
    """Build a concise direct text answer from deterministic results."""
    fmt = lambda amt: format_inr(amt, currency)

    if matching_stats.matching_transaction_count == 0:
        if query.category:
            period_df = analysis.get("period_outcome")
            if period_df is not None:
                cats = sorted(period_df.filtered_df["category"].dropna().unique())
                if cats:
                    return (
                        f"No transactions found in the \"{query.category}\" category. "
                        f"Your available categories are: {', '.join(cats)}."
                    )
        return "No transactions matched your criteria."

    parts = []
    if query.intent == "category_spending" and query.category:
        parts.append(
            f"You spent {fmt(matching_stats.matching_total_amount)} on {query.category} "
            f"across {matching_stats.matching_transaction_count} transactions."
        )
    elif query.intent == "spending_summary":
        stats = analysis["overall_stats"]
        parts.append(
            f"Total spending: {fmt(stats.total_spending)}. "
            f"Total income: {fmt(stats.total_income)}. "
            f"Net cash flow: {fmt(stats.net_cash_flow)}."
        )
    elif query.intent == "top_expenses":
        parts.append(
            f"Found {matching_stats.matching_transaction_count} transactions. "
            f"Total: {fmt(matching_stats.matching_total_amount)}, "
            f"largest: {fmt(matching_stats.matching_largest_amount)}."
        )
    elif query.intent == "anomaly_detection":
        anomalies = analysis.get("anomalies", [])
        parts.append(
            f"{len(anomalies)} potentially unusual transaction{'s' if len(anomalies) != 1 else ''} detected "
            f"out of {matching_stats.matching_transaction_count} total."
        )
    elif query.intent == "income_analysis":
        parts.append(
            f"Total income: {fmt(matching_stats.matching_total_amount)} "
            f"from {matching_stats.matching_transaction_count} credit transactions."
        )
    elif query.intent == "cashflow_analysis":
        stats = analysis["overall_stats"]
        parts.append(
            f"Net cash flow: {fmt(stats.net_cash_flow)} "
            f"(income: {fmt(stats.total_income)}, expenses: {fmt(stats.total_spending)})."
        )
    else:
        parts.append(
            f"{matching_stats.matching_transaction_count} matching transactions, "
            f"totaling {fmt(matching_stats.matching_total_amount)}."
        )

    breakdown = analysis.get("category_breakdown", [])
    if breakdown and query.intent != "anomaly_detection":
        top3 = breakdown[:3]
        cat_parts = [f"{c.category} ({c.percentage_of_spending:.0f}%)" for c in top3]
        parts.append(f"Top categories: {', '.join(cat_parts)}.")

    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Conversation context
# --------------------------------------------------------------------------- #

MAX_CONVERSATION_TURNS = 10


@dataclasses.dataclass
class ConversationTurn:
    query: str
    intent: str
    date_range: str
    category: Optional[str]
    answer_preview: str


class ConversationContext:
    """Maintains conversation history for follow-up questions within a session.

    Stored in Streamlit session_state, scoped to the authenticated user.
    No sensitive financial data is persisted — only query metadata and short
    answer previews for context resolution.
    """

    def __init__(self):
        self.turns: list[ConversationTurn] = []
        self.user_id: int | None = None

    def add_turn(self, query: str, intent: str, date_range: str,
                 category: str | None, answer_preview: str):
        self.turns.append(ConversationTurn(
            query=query, intent=intent, date_range=date_range,
            category=category, answer_preview=answer_preview[:200],
        ))
        if len(self.turns) > MAX_CONVERSATION_TURNS:
            self.turns = self.turns[-MAX_CONVERSATION_TURNS:]

    def resolve_follow_up(self, query: StructuredQuery) -> StructuredQuery:
        """If the current query looks like a follow-up and is underspecified,
        fill in missing fields from the last turn."""
        if not self.turns:
            return query
        if not _query_references_prior(query.raw_query):
            return query
        last = self.turns[-1]
        updates = {}
        if query.date_range == "all_time" and last.date_range != "all_time":
            updates["date_range"] = last.date_range
        if query.category is None and last.category is not None:
            updates["category"] = last.category
        if updates:
            query = query.model_copy(update=updates)
        return query

    def clear(self):
        self.turns.clear()


_FOLLOW_UP_PATTERNS = [
    "what about", "how about", "and for", "same for", "also show",
    "what else", "anything else", "more detail", "break it down",
    "can you also", "tell me more", "elaborate",
]


def _query_references_prior(raw_query: str) -> bool:
    q = raw_query.lower()
    return any(p in q for p in _FOLLOW_UP_PATTERNS)
