"""
Pydantic schemas used across the application.

These schemas serve two purposes:
  1. Validate the STRUCTURED QUERY produced by the query parser (whether it
     came from an LLM or the deterministic fallback) before it is ever used
     to filter data. The LLM never touches the dataframe directly — it only
     ever produces data that must pass through this validation layer first.
  2. Validate individual transaction rows and the structured, calculated
     results that are handed to the summarizer, so the LLM (when used for
     summarization) only ever sees numbers that have already been computed
     deterministically.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Structured query (output of query_parser, input to filters/analytics)
# --------------------------------------------------------------------------- #

Intent = Literal[
    "transaction_analysis",   # generic "show me / filter transactions"
    "spending_summary",       # "what did I spend last month"
    "top_expenses",           # "show my biggest expenses"
    "category_spending",      # "how much did I spend on shopping"
    "anomaly_detection",      # "find unusual transactions"
    "trend_analysis",         # "how has my spending changed" / month-over-month
    "period_comparison",      # "compare this month to last month"
    "insights_query",         # "what insights can you give me" / spending patterns
    "merchant_analysis",      # "where do I spend the most" / top merchants
    "income_analysis",        # "what is my income" / salary analysis
    "cashflow_analysis",      # "what is my cash flow" / net position
    "budget_query",           # "am I overspending" / budget-related
    "general_query",          # couldn't confidently classify -> safe default
]

Operator = Literal[
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "equal",
]

DateRangeKeyword = Literal[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_30_days",
    "this_year",
    "all_time",
    "custom",
]

TransactionType = Literal["Debit", "Credit"]


class StructuredQuery(BaseModel):
    """Validated, structured representation of a natural-language request.

    This is the ONLY thing the LLM (or the deterministic fallback parser) is
    allowed to produce. It is never allowed to run arbitrary pandas code or
    directly manipulate the dataframe.
    """

    intent: Intent = "general_query"
    amount_threshold: Optional[float] = Field(
        default=None, description="Numeric amount threshold extracted from the query, in INR."
    )
    operator: Optional[Operator] = Field(
        default=None, description="Comparison operator to apply against amount_threshold."
    )
    date_range: DateRangeKeyword = "all_time"
    custom_start_date: Optional[date_type] = None
    custom_end_date: Optional[date_type] = None
    category: Optional[str] = Field(
        default=None, description="A specific spending category the user asked about, if any."
    )
    transaction_type: Optional[TransactionType] = Field(
        default=None, description="Restrict to Debit or Credit transactions, if the user specified."
    )
    top_n: Optional[int] = Field(
        default=None, ge=1, le=1000, description="Number of top transactions requested (e.g. 'top 5')."
    )
    sort_by: Optional[Literal["amount_desc", "amount_asc", "date_desc", "date_asc"]] = None
    include_summary: bool = True
    include_anomalies: bool = False
    raw_query: str = ""

    @field_validator("amount_threshold")
    @classmethod
    def amount_must_be_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("amount_threshold must be non-negative")
        return v

    @model_validator(mode="after")
    def custom_range_requires_dates(self) -> "StructuredQuery":
        if self.date_range == "custom":
            if not self.custom_start_date or not self.custom_end_date:
                # Fail safe: fall back to all_time rather than crash.
                self.date_range = "all_time"
        if self.amount_threshold is not None and self.operator is None:
            # A threshold without an operator is ambiguous -> default to "greater_than"
            # since "above X" / "over X" is the overwhelmingly common phrasing.
            self.operator = "greater_than"
        return self


# --------------------------------------------------------------------------- #
# Transaction row validation
# --------------------------------------------------------------------------- #


class Transaction(BaseModel):
    transaction_id: str
    date: date_type
    description: str
    merchant: str
    category: str
    type: TransactionType
    amount: float = Field(ge=0)
    account: str

    @field_validator("transaction_id", "description", "merchant", "category", "account")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field must not be blank")
        return v


# --------------------------------------------------------------------------- #
# Anomaly record
# --------------------------------------------------------------------------- #

AnomalyType = Literal["statistical_outlier", "duplicate_like", "rapid_repeated_large"]


class AnomalyRecord(BaseModel):
    transaction_id: str
    date: date_type
    merchant: str
    category: str
    amount: float
    anomaly_type: AnomalyType
    reason: str
    severity: Literal["moderate", "high"] = "moderate"


# --------------------------------------------------------------------------- #
# Structured results handed to the summarizer (LLM sees ONLY this — never the
# raw dataframe).
# --------------------------------------------------------------------------- #


class CategoryBreakdownItem(BaseModel):
    category: str
    transaction_count: int
    total_amount: float
    percentage_of_spending: float


class AnalysisSummaryInput(BaseModel):
    """The complete, deterministic, calculated payload the summarizer may use.

    Every number that appears in the final AI-generated summary must
    originate from a field on this model.
    """

    period_label: str
    period_start: Optional[date_type] = None
    period_end: Optional[date_type] = None

    query_description: str = ""

    total_transactions_overall: int = 0
    total_spending_overall: float = 0.0
    total_income_overall: float = 0.0
    net_cash_flow_overall: float = 0.0

    matching_transaction_count: int = 0
    matching_total_amount: float = 0.0
    matching_average_amount: float = 0.0
    matching_largest_amount: float = 0.0
    matching_smallest_amount: float = 0.0

    category_breakdown: list[CategoryBreakdownItem] = Field(default_factory=list)

    anomalies: list[AnomalyRecord] = Field(default_factory=list)
