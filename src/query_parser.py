"""
Natural-language query understanding.

Converts a free-text banking question into a validated `StructuredQuery`
(src.validators.StructuredQuery). Two implementations are available:

  1. `parse_with_llm()`   — uses an OpenAI-compatible or Gemini LLM (only if
                             an API key is configured) purely to EXTRACT
                             intent/amount/date-range/category into JSON.
                             The LLM's output is always re-validated with
                             Pydantic before use — it never touches the
                             dataframe directly.
  2. `parse_deterministic()` — a dependency-free regex/keyword-based parser
                             that works identically with no API key at all.
                             This is also the SAFETY NET the LLM path falls
                             back to on any failure (timeout, bad JSON,
                             validation error, etc.), so the app never
                             breaks due to an LLM/API problem.

`parse_query()` is the single public entry point the rest of the app should
call.
"""

from __future__ import annotations

import json
import re
from datetime import date

import config
from src.validators import StructuredQuery

logger = config.get_logger(__name__)


class InvalidQueryError(Exception):
    """Raised when the user's query contains a recognizable but unparseable
    element (e.g. an amount keyword with no valid number), so the app can
    show a specific, helpful error instead of guessing.
    """

    def __init__(self, user_message: str):
        self.user_message = user_message
        super().__init__(user_message)


# --------------------------------------------------------------------------- #
# Deterministic fallback parser
# --------------------------------------------------------------------------- #

_OPERATOR_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bat\s+least\b|\bminimum\s+of\b|\bmin\.?\s+of\b|>=", re.I), "greater_than_or_equal"),
    (re.compile(r"\bat\s+most\b|\bmaximum\s+of\b|\bmax\.?\s+of\b|<=", re.I), "less_than_or_equal"),
    (re.compile(r"\babove\b|\bover\b|\bgreater\s+than\b|\bmore\s+than\b|\bexceeding\b|\bexceeds\b|>", re.I), "greater_than"),
    (re.compile(r"\bbelow\b|\bunder\b|\bless\s+than\b|\bcheaper\s+than\b|<", re.I), "less_than"),
    (re.compile(r"\bexactly\b|\bequal\s+to\b|\bequals\b", re.I), "equal"),
]

# Number possibly followed by an Indian-style scale word (lakh/crore) or "k".
_AMOUNT_TOKEN = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakh[s]?|crore[s]?|k\b)?",
    re.I,
)

_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\blast\s+30\s+days\b|\bpast\s+30\s+days\b|\blast\s+month'?s?\s+30\s+days\b", re.I), "last_30_days"),
    (re.compile(r"\byesterday\b", re.I), "yesterday"),
    (re.compile(r"\btoday\b", re.I), "today"),
    (re.compile(r"\bthis\s+week\b", re.I), "this_week"),
    (re.compile(r"\blast\s+week\b", re.I), "last_week"),
    (re.compile(r"\bthis\s+month\b", re.I), "this_month"),
    (re.compile(r"\blast\s+month\b", re.I), "last_month"),
    (re.compile(r"\bthis\s+year\b", re.I), "this_year"),
]

_CATEGORY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bfood\b|\bdining\b|\brestaurants?\b", re.I), "Food & Dining"),
    (re.compile(r"\bgroceries\b|\bgrocery\b", re.I), "Groceries"),
    (re.compile(r"\bshopping\b|\bshop\b", re.I), "Shopping"),
    (re.compile(r"\btravel\b|\btrip\b|\bflights?\b|\bcabs?\b", re.I), "Travel"),
    (re.compile(r"\brent\b", re.I), "Rent"),
    (re.compile(r"\butilit(y|ies)\b|\bbills?\b|\belectricity\b", re.I), "Utilities"),
    (re.compile(r"\bhealthcare\b|\bmedical\b|\bhospital\b|\bpharmacy\b", re.I), "Healthcare"),
    (re.compile(r"\beducation\b|\btuition\b|\bschool\b|\bcourse\b", re.I), "Education"),
    (re.compile(r"\bentertainment\b|\bmovies?\b|\bsubscriptions?\b", re.I), "Entertainment"),
    (re.compile(r"\binvestments?\b|\bmutual\s+funds?\b|\bsip\b", re.I), "Investments"),
    (re.compile(r"\btransfers?\b|\bupi\b|\bneft\b|\bimps\b", re.I), "Transfers"),
    (re.compile(r"\bsalary\b|\bincome\b", re.I), "Salary / Income"),
    (re.compile(r"\batm\b|\bcash\s+withdrawal\b", re.I), "ATM / Cash Withdrawal"),
]

_ANOMALY_KEYWORDS = re.compile(
    r"\bunusual\b|\banomal(y|ies)\b|\bsuspicious\b|\bstrange\b|\bodd\b|\bweird\b", re.I
)
_TOP_EXPENSE_KEYWORDS = re.compile(
    r"\bbiggest\b|\blargest\b|\btop\s+expenses\b|\bhighest\b|\btop\s+spending\b", re.I
)
_SUMMARY_KEYWORDS = re.compile(
    r"\bsummar(y|ize)\b|\bwhat\s+did\s+i\s+spend\b|\bhow\s+much\s+did\s+i\s+spend\b|\bspending\s+summary\b|\boverview\b",
    re.I,
)
_TOP_N_PATTERN = re.compile(r"\btop\s+(\d{1,3})\b", re.I)


def _scale_multiplier(scale_word: str | None) -> float:
    if not scale_word:
        return 1.0
    scale_word = scale_word.lower()
    if scale_word.startswith("lakh"):
        return 100_000.0
    if scale_word.startswith("crore"):
        return 10_000_000.0
    if scale_word == "k":
        return 1_000.0
    return 1.0


def _extract_amount_and_operator(text: str) -> tuple[float | None, str | None, bool]:
    """Find an amount threshold + comparison operator in free text.

    Returns (amount, operator, keyword_found_but_unparseable).
    The third element lets the caller distinguish "no amount mentioned at
    all" from "an amount keyword was used but the number was invalid" (e.g.
    "above xyz"), which should surface a specific error to the user.
    """
    for pattern, operator in _OPERATOR_KEYWORDS:
        match = pattern.search(text)
        if not match:
            continue
        # Look for a number within a short window after the keyword.
        window = text[match.end(): match.end() + 30]
        amount_match = _AMOUNT_TOKEN.search(window)
        if amount_match and amount_match.group(1):
            raw_number = amount_match.group(1).replace(",", "")
            try:
                base = float(raw_number)
            except ValueError:
                return None, operator, True
            amount = base * _scale_multiplier(amount_match.group(2))
            return amount, operator, False
        else:
            # Operator keyword found, but no valid number followed it.
            # Only treat as an error if there genuinely is no number nearby
            # at all (avoid false positives on things like "above average").
            fallback_number = re.search(r"\d", window)
            if fallback_number is None:
                return None, operator, True
    return None, None, False


def _extract_date_range(text: str) -> str:
    for pattern, keyword in _DATE_PATTERNS:
        if pattern.search(text):
            return keyword
    return "all_time"


def _extract_category(text: str) -> str | None:
    for pattern, category in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category
    return None


def _extract_intent(text: str, has_amount: bool, has_category: bool) -> str:
    if _ANOMALY_KEYWORDS.search(text):
        return "anomaly_detection"
    if _TOP_EXPENSE_KEYWORDS.search(text):
        return "top_expenses"
    if has_category and re.search(r"\bhow\s+much\b|\bspend\b|\bspent\b", text, re.I):
        return "category_spending"
    if has_amount:
        return "transaction_analysis"
    if _SUMMARY_KEYWORDS.search(text):
        return "spending_summary"
    return "general_query"


def parse_deterministic(raw_query: str) -> StructuredQuery:
    text = (raw_query or "").strip()
    if not text:
        raise InvalidQueryError("Please enter a question, e.g. \"Show transactions above ₹50,000 from last month.\"")

    amount, operator, unparseable = _extract_amount_and_operator(text)
    if unparseable:
        raise InvalidQueryError(
            "I couldn't determine the transaction amount. Please provide a valid amount such as ₹50,000."
        )

    date_range = _extract_date_range(text)
    category = _extract_category(text)
    has_amount = amount is not None
    intent = _extract_intent(text, has_amount, category is not None)

    top_n_match = _TOP_N_PATTERN.search(text)
    top_n = int(top_n_match.group(1)) if top_n_match else (10 if intent == "top_expenses" else None)

    include_anomalies = intent == "anomaly_detection" or bool(_ANOMALY_KEYWORDS.search(text))
    include_summary = True  # a concise summary is always useful; cheap to compute

    # Intents that are inherently about SPENDING (not income) default to
    # Debit-only, so e.g. "what did I spend last month" doesn't lump a
    # salary credit in with expenses. "transaction_analysis" (a literal
    # "show transactions above X") deliberately leaves type unrestricted,
    # since the user asked to see ALL transactions matching the amount.
    spending_intents = {"spending_summary", "top_expenses", "category_spending", "anomaly_detection"}
    transaction_type = None
    if intent in spending_intents and category != "Salary / Income":
        transaction_type = "Debit"

    return StructuredQuery(
        intent=intent,
        amount_threshold=amount,
        operator=operator,
        date_range=date_range,
        category=category,
        transaction_type=transaction_type,
        top_n=top_n,
        sort_by="amount_desc" if intent == "top_expenses" else None,
        include_summary=include_summary,
        include_anomalies=include_anomalies,
        raw_query=raw_query,
    )


# --------------------------------------------------------------------------- #
# LLM-assisted parser
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """You are a query-understanding component for a banking transaction analysis tool.
Given a user's natural-language banking question, extract a STRICT JSON object with these fields:

- intent: one of "transaction_analysis", "spending_summary", "top_expenses", "category_spending", "anomaly_detection", "general_query"
- amount_threshold: number or null (the INR amount mentioned, converted from lakh/crore/k to a plain number)
- operator: one of "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "equal", or null
- date_range: one of "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year", "all_time"
- category: one of "Food & Dining", "Shopping", "Travel", "Rent", "Utilities", "Healthcare", "Education", "Entertainment", "Groceries", "Investments", "Transfers", "Salary / Income", "ATM / Cash Withdrawal", "Other", or null
- top_n: integer or null
- sort_by: one of "amount_desc", "amount_asc", "date_desc", "date_asc", or null
- include_summary: boolean
- include_anomalies: boolean

Also include a field "transaction_type": one of "Debit", "Credit", or null.
For queries that are inherently about SPENDING/expenses (intent = spending_summary,
top_expenses, category_spending, or anomaly_detection) and the user did not ask about
income/salary/credits, set transaction_type to "Debit" so income is not counted as spending.
For a literal "show me transactions above/below X" request (intent = transaction_analysis),
leave transaction_type null so all transaction types are shown.

Respond with ONLY the JSON object, no explanation, no markdown fences.
If the query does not mention an amount, set amount_threshold and operator to null (do NOT invent a number).
If the query does not mention a date range, use "all_time".
"""


def _call_openai(raw_query: str) -> dict:
    from openai import OpenAI  # lazy import — optional dependency

    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL, timeout=config.LLM_REQUEST_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw_query},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    return json.loads(content)


def _call_gemini(raw_query: str) -> dict:
    import google.generativeai as genai  # lazy import — optional dependency

    genai.configure(api_key=config.GOOGLE_API_KEY)
    model = genai.GenerativeModel(
        config.GEMINI_MODEL,
        system_instruction=_SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json", "temperature": 0},
    )
    response = model.generate_content(raw_query, request_options={"timeout": config.LLM_REQUEST_TIMEOUT_SECONDS})
    return json.loads(response.text)


def parse_with_llm(raw_query: str) -> StructuredQuery | None:
    """Attempt LLM-based parsing. Returns None (never raises) on any failure
    so the caller can transparently fall back to the deterministic parser.
    """
    provider = config.active_llm_provider()
    if provider is None:
        return None

    try:
        if provider == "openai":
            data = _call_openai(raw_query)
        elif provider == "gemini":
            data = _call_gemini(raw_query)
        else:
            return None

        data["raw_query"] = raw_query
        # Coerce empty-string nulls some models emit.
        for key in ("amount_threshold", "operator", "category", "top_n", "sort_by"):
            if data.get(key) == "":
                data[key] = None

        return StructuredQuery(**data)
    except Exception as exc:  # noqa: BLE001 - any LLM/network/validation failure must degrade gracefully
        logger.warning("LLM query parsing failed (%s); falling back to deterministic parser: %s", provider, exc)
        return None


def parse_query(raw_query: str, prefer_llm: bool = True) -> tuple[StructuredQuery, str]:
    """Main entry point: parse a natural-language query into a StructuredQuery.

    Returns (structured_query, method) where method is "llm" or "deterministic".

    Raises InvalidQueryError for genuinely unparseable amount expressions —
    this is intentionally NOT swallowed, since it represents a case where we
    should ask the user to clarify rather than guess.
    """
    if prefer_llm:
        result = parse_with_llm(raw_query)
        if result is not None:
            return result, "llm"

    return parse_deterministic(raw_query), "deterministic"
