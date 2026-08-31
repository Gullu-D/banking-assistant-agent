"""
Banking Assistant Agent — orchestration layer.

This is the single agent workflow described in the architecture:

    User Query
        -> Query Parser              (src.query_parser)
        -> Retrieve Transactions      (src.data_loader.TransactionRepository)
        -> Filter                    (src.filters)
        -> Categorize                (src.categorizer)
        -> Calculate                 (src.analytics)
        -> Detect Anomalies          (src.anomaly_detector)
        -> Generate Summary          (src.summarizer)
        -> Return Results

Deliberately a single, well-structured agent with reliable deterministic
tools rather than a multi-agent system — see MASTER PROMPT section 20.

Every external failure mode (missing file, corrupt CSV, bad query, LLM
outage) is caught here and converted into a clear, user-facing
`AgentResult.error_message` rather than propagating a raw exception/stack
trace to the UI.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Optional

import pandas as pd

import config
from src.analytics import (
    MatchingStatistics,
    OverallStatistics,
    calculate_category_breakdown,
    calculate_matching_statistics,
    calculate_overall_statistics,
    spending_over_time,
)
from src.anomaly_detector import detect_anomalies
from src.categorizer import categorize_transactions
from src.data_loader import LoadReport, TransactionDataError, TransactionRepository
from src.filters import FilterOutcome, apply_filters
from src.query_parser import InvalidQueryError, parse_query
from src.summarizer import generate_summary
from src.validators import AnalysisSummaryInput, AnomalyRecord, CategoryBreakdownItem, StructuredQuery

logger = config.get_logger(__name__)


def _describe_query(query: StructuredQuery) -> str:
    parts = []
    if query.amount_threshold is not None and query.operator:
        op_word = {
            "greater_than": "above",
            "greater_than_or_equal": "at least",
            "less_than": "below",
            "less_than_or_equal": "at most",
            "equal": "equal to",
        }[query.operator]
        parts.append(f"transactions {op_word} {config.CURRENCY_SYMBOL}{query.amount_threshold:,.0f}")
    else:
        parts.append("all transactions")
    if query.category:
        parts.append(f"in {query.category}")
    if query.transaction_type:
        parts.append(f"({query.transaction_type} only)")
    return " ".join(parts)


@dataclasses.dataclass
class AgentResult:
    success: bool
    error_message: Optional[str] = None

    structured_query: Optional[StructuredQuery] = None
    parse_method: str = ""  # "llm" | "deterministic"

    period_label: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    matching_df: pd.DataFrame = dataclasses.field(default_factory=pd.DataFrame)
    period_df: pd.DataFrame = dataclasses.field(default_factory=pd.DataFrame)

    overall_stats: OverallStatistics = dataclasses.field(default_factory=OverallStatistics)
    matching_stats: MatchingStatistics = dataclasses.field(default_factory=MatchingStatistics)
    category_breakdown: list[CategoryBreakdownItem] = dataclasses.field(default_factory=list)
    anomalies: list[AnomalyRecord] = dataclasses.field(default_factory=list)
    time_series: pd.DataFrame = dataclasses.field(default_factory=pd.DataFrame)

    summary_text: str = ""
    summary_method: str = ""  # "ai" | "template" | "skipped"

    load_report: Optional[LoadReport] = None
    llm_provider: Optional[str] = None


class BankingAssistantAgent:
    def __init__(self, csv_path: Optional[str] = None):
        self.repository = TransactionRepository(csv_path)

    # ------------------------------------------------------------------ #
    def analyze(self, raw_query: str, today: Optional[date] = None) -> AgentResult:
        today = today or date.today()

        # 1) Query Parser -----------------------------------------------------
        try:
            query, parse_method = parse_query(raw_query)
        except InvalidQueryError as exc:
            logger.info("Invalid query rejected: %s", raw_query)
            return AgentResult(success=False, error_message=exc.user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error parsing query")
            return AgentResult(
                success=False,
                error_message="Something went wrong understanding your question. Please try rephrasing it.",
            )

        # 2) Retrieve Transactions ---------------------------------------------
        try:
            raw_df, load_report = self.repository.load()
        except TransactionDataError as exc:
            logger.warning("Transaction data error: %s", exc.user_message)
            return AgentResult(success=False, error_message=exc.user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error loading transactions")
            return AgentResult(
                success=False,
                error_message="An unexpected error occurred while loading transaction data. Please try again.",
            )

        try:
            # 3) Categorize -----------------------------------------------------
            categorized_df = categorize_transactions(raw_df)

            # 4) Filter -----------------------------------------------------------
            # Period-only view (date range applied, no amount/category filter) —
            # used as the baseline for "overall" statistics and anomaly detection,
            # so the anomaly baseline reflects the user's normal spending pattern
            # for that period rather than only the transactions that already
            # passed their specific amount filter.
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
            period_outcome: FilterOutcome = apply_filters(categorized_df, period_query, today=today)

            # Full query (date + amount + category + type + sort/top_n) —
            # the actual transactions the user asked to see.
            matching_outcome: FilterOutcome = apply_filters(categorized_df, query, today=today)

            # 5) Calculate ----------------------------------------------------------
            overall_stats = calculate_overall_statistics(period_outcome.filtered_df)
            matching_stats = calculate_matching_statistics(matching_outcome.filtered_df)
            category_breakdown = calculate_category_breakdown(matching_outcome.filtered_df)
            time_series = spending_over_time(matching_outcome.filtered_df)

            # 6) Detect Anomalies -----------------------------------------------------
            anomalies = detect_anomalies(period_outcome.filtered_df)

            # 7) Generate Summary -------------------------------------------------------
            summary_input = AnalysisSummaryInput(
                period_label=matching_outcome.period_label,
                period_start=matching_outcome.period_start,
                period_end=matching_outcome.period_end,
                query_description=_describe_query(query),
                total_transactions_overall=overall_stats.total_transactions,
                total_spending_overall=overall_stats.total_spending,
                total_income_overall=overall_stats.total_income,
                net_cash_flow_overall=overall_stats.net_cash_flow,
                matching_transaction_count=matching_stats.matching_transaction_count,
                matching_total_amount=matching_stats.matching_total_amount,
                matching_average_amount=matching_stats.matching_average_amount,
                matching_largest_amount=matching_stats.matching_largest_amount,
                matching_smallest_amount=matching_stats.matching_smallest_amount,
                category_breakdown=category_breakdown,
                # Anomalies are always included in the structured payload handed to
                # the summarizer (cheap to compute); the UI decides how prominently
                # to surface them based on query.include_anomalies / whether any exist.
                anomalies=anomalies,
            )

            if query.include_summary:
                summary_text, summary_method = generate_summary(summary_input)
            else:
                summary_text, summary_method = "", "skipped"

        except Exception as exc:  # noqa: BLE001 - never let analysis crash the UI
            logger.exception("Unexpected error during transaction analysis")
            return AgentResult(
                success=False,
                error_message="An unexpected error occurred while analyzing your transactions. Please try again.",
            )

        return AgentResult(
            success=True,
            structured_query=query,
            parse_method=parse_method,
            period_label=matching_outcome.period_label,
            period_start=matching_outcome.period_start,
            period_end=matching_outcome.period_end,
            matching_df=matching_outcome.filtered_df,
            period_df=period_outcome.filtered_df,
            overall_stats=overall_stats,
            matching_stats=matching_stats,
            category_breakdown=category_breakdown,
            anomalies=anomalies,
            time_series=time_series,
            summary_text=summary_text,
            summary_method=summary_method,
            load_report=load_report,
            llm_provider=config.active_llm_provider(),
        )
