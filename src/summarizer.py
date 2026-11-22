"""
AI-assisted (or template-based) summary generation.

CRITICAL DESIGN RULE: the LLM receives ONLY the structured, already-computed
`AnalysisSummaryInput` payload (see src.validators) — never the raw
dataframe. It is asked to turn numbers that already exist into readable
prose, not to calculate anything itself.

As a safety net, the LLM's output is lightly checked for numeric
hallucination: every number mentioned in the generated text should
correspond (allowing for rounding/formatting) to a number that actually
appears in the input payload. If the check fails, or the LLM is unavailable
/ errors out, a deterministic template-based summary is used instead — so a
'*summary is always produced, and it is always numerically grounded.
"""

from __future__ import annotations

import json
import re

import config
from src.formatting import format_inr
from src.validators import AnalysisSummaryInput

logger = config.get_logger(__name__)

_currency: str | None = None


def _fmt(amount: float) -> str:
    return format_inr(amount, _currency)


# --------------------------------------------------------------------------- #
# Deterministic template summary (fallback, always available)
# --------------------------------------------------------------------------- #


def generate_template_summary(data: AnalysisSummaryInput) -> str:
    lines: list[str] = []

    if data.matching_transaction_count == 0:
        lines.append(
            f"No transactions matched your criteria during {data.period_label}. "
            f"Try widening the date range or lowering the amount threshold."
        )
        return " ".join(lines)

    lines.append(
        f"You had {data.matching_transaction_count} matching transaction"
        f"{'s' if data.matching_transaction_count != 1 else ''} during {data.period_label}, "
        f"totaling {_fmt(data.matching_total_amount)}."
    )
    lines.append(
        f"The average matching transaction was {_fmt(data.matching_average_amount)}, "
        f"and the largest was {_fmt(data.matching_largest_amount)}."
    )

    if data.category_breakdown:
        top = data.category_breakdown[: min(3, len(data.category_breakdown))]
        cat_desc = ", ".join(f"{c.category} ({c.percentage_of_spending:.0f}%)" for c in top)
        lines.append(f"The majority of this spending came from: {cat_desc}.")

    if data.anomalies:
        lines.append(
            f"{len(data.anomalies)} transaction{'s' if len(data.anomalies) != 1 else ''} "
            f"{'were' if len(data.anomalies) != 1 else 'was'} flagged as potentially unusual "
            f"because they were significantly higher than your normal transaction pattern, "
            f"looked like possible duplicates, or occurred in an unusually rapid burst."
        )

    if data.total_spending_overall and data.matching_total_amount:
        share = (data.matching_total_amount / data.total_spending_overall * 100) if data.total_spending_overall else 0
        lines.append(
            f"Overall spending in this period was {_fmt(data.total_spending_overall)}, "
            f"so these matching transactions represent about {share:.0f}% of total spending."
        )

    return " ".join(lines)


# --------------------------------------------------------------------------- #
# LLM-assisted summary
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """You are a banking transaction summary writer.
You will be given a JSON object containing ALREADY-CALCULATED financial figures.
Write a concise, clear, friendly summary (4-7 sentences, plain prose, no markdown headers).

STRICT RULES:
- Use ONLY the numbers present in the JSON. Do not calculate, estimate, guess, or invent any number.
- Every number you state must appear in the JSON (possibly rounded for readability).
- Do not give investment or financial advice.
- Never claim a transaction is fraudulent — anomalies are only "potentially unusual".
- If matching_transaction_count is 0, clearly say no matching transactions were found; do not invent a result.
- Mention the period, the total, notable categories, and anomalies if present.
"""


def _allowed_numbers(data: AnalysisSummaryInput) -> set[int]:
    """Collect every numeric figure that legitimately appears in the input,
    rounded to the nearest integer, to sanity-check LLM output against.
    """
    numbers: set[int] = set()
    for field in (
        data.total_transactions_overall,
        data.total_spending_overall,
        data.total_income_overall,
        data.net_cash_flow_overall,
        data.matching_transaction_count,
        data.matching_total_amount,
        data.matching_average_amount,
        data.matching_largest_amount,
        data.matching_smallest_amount,
    ):
        try:
            numbers.add(round(float(field)))
        except (TypeError, ValueError):
            pass
    for c in data.category_breakdown:
        numbers.add(round(c.total_amount))
        numbers.add(round(c.percentage_of_spending))
        numbers.add(int(c.transaction_count))
    for a in data.anomalies:
        numbers.add(round(a.amount))
    return numbers


def _extract_numbers_from_text(text: str) -> list[int]:
    # Matches things like 1,25,000 / 125000 / 85625.50 / 36%
    raw = re.findall(r"[\d,]+(?:\.\d+)?", text)
    out = []
    for token in raw:
        cleaned = token.replace(",", "")
        try:
            out.append(round(float(cleaned)))
        except ValueError:
            continue
    return out


def _passes_numeric_grounding_check(summary_text: str, data: AnalysisSummaryInput, tolerance: float = 0.02) -> bool:
    """Verify every number in the summary roughly matches something in the
    allowed set (within a small relative tolerance, to allow for rounding).
    Small numbers (< 13, e.g. "4 transactions", counts, or years/dates) are
    always allowed since they're low-risk and often legitimately reworded.
    """
    allowed = _allowed_numbers(data)
    if not allowed:
        return True

    found = _extract_numbers_from_text(summary_text)
    for n in found:
        if n <= 12 or 2000 <= n <= 2100:  # small counts / years — not financial figures
            continue
        if n in allowed:
            continue
        # allow small relative rounding tolerance against any allowed number
        if any(abs(n - a) <= max(1, tolerance * max(a, 1)) for a in allowed):
            continue
        logger.warning("Summary numeric grounding check failed on value %s", n)
        return False
    return True


def _call_openai_summary(payload: dict) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL, timeout=config.LLM_REQUEST_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _call_gemini_summary(payload: dict) -> str:
    import google.generativeai as genai

    genai.configure(api_key=config.GOOGLE_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL, system_instruction=_SYSTEM_PROMPT)
    response = model.generate_content(
        json.dumps(payload, default=str),
        generation_config={"temperature": 0.3},
        request_options={"timeout": config.LLM_REQUEST_TIMEOUT_SECONDS},
    )
    return response.text.strip()


def _call_ollama_summary(payload: dict) -> str:
    import urllib.request
    body = json.dumps({
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.LLM_REQUEST_TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read())
    return data.get("message", {}).get("content", "").strip()


_llm_disabled_until: float = 0.0

def generate_summary(data: AnalysisSummaryInput, *, currency: str | None = None) -> tuple[str, str]:
    """Generate a spending summary. Returns (summary_text, method) where
    method is "ai" or "template". Always succeeds — falls back to the
    deterministic template on any LLM failure or grounding-check failure.
    """
    global _llm_disabled_until, _currency
    _currency = currency
    import time

    provider = config.active_llm_provider()
    if provider is None:
        return generate_template_summary(data), "template"
    if provider != "ollama" and time.monotonic() < _llm_disabled_until:
        return generate_template_summary(data), "template"

    try:
        payload = json.loads(data.model_dump_json())
        if provider == "openai":
            text = _call_openai_summary(payload)
        elif provider == "gemini":
            text = _call_gemini_summary(payload)
        elif provider == "ollama":
            text = _call_ollama_summary(payload)
        else:
            return generate_template_summary(data), "template"

        if not text:
            raise ValueError("Empty response from LLM")

        if not _passes_numeric_grounding_check(text, data):
            logger.warning("AI summary failed numeric grounding check; using template summary instead.")
            return generate_template_summary(data), "template"

        return text, "ai"
    except Exception as exc:  # noqa: BLE001 - LLM failures must never crash the app
        exc_str = str(exc)
        if "credit_balance_exhausted" in exc_str or "insufficient_quota" in exc_str:
            _llm_disabled_until = time.monotonic() + 3600
            logger.warning("LLM provider (%s) has no credits; disabling summaries for 1 hour.", provider)
        else:
            logger.warning("AI summary generation failed (%s); falling back to template: %s", provider, exc)
        return generate_template_summary(data), "template"
