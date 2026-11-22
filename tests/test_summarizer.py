"""
Tests for the summary generation module (src.summarizer).

Covers: template summary output, numeric grounding check, LLM fallback
behavior with mocked providers.
"""

from unittest.mock import MagicMock, patch
from datetime import date

from src.summarizer import (
    _allowed_numbers,
    _extract_numbers_from_text,
    _passes_numeric_grounding_check,
    generate_summary,
    generate_template_summary,
)
from src.validators import AnalysisSummaryInput, AnomalyRecord, CategoryBreakdownItem


def _make_summary_input(**overrides):
    defaults = dict(
        period_label="September 2026",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        query_description="all transactions",
        total_transactions_overall=50,
        total_spending_overall=200000.0,
        total_income_overall=90000.0,
        net_cash_flow_overall=-110000.0,
        matching_transaction_count=10,
        matching_total_amount=85000.0,
        matching_average_amount=8500.0,
        matching_largest_amount=25000.0,
        matching_smallest_amount=1200.0,
        category_breakdown=[
            CategoryBreakdownItem(category="Shopping", transaction_count=4,
                                  total_amount=40000.0, percentage_of_spending=47.06),
            CategoryBreakdownItem(category="Food & Dining", transaction_count=6,
                                  total_amount=45000.0, percentage_of_spending=52.94),
        ],
        anomalies=[],
    )
    defaults.update(overrides)
    return AnalysisSummaryInput(**defaults)


class TestTemplateSummary:
    def test_produces_nonempty_text(self):
        data = _make_summary_input()
        text = generate_template_summary(data)
        assert len(text) > 50
        assert "10" in text  # matching count
        assert "85,000" in text or "85000" in text  # total

    def test_zero_matches_produces_helpful_message(self):
        data = _make_summary_input(matching_transaction_count=0, matching_total_amount=0)
        text = generate_template_summary(data)
        assert "no transactions" in text.lower()

    def test_mentions_top_categories(self):
        data = _make_summary_input()
        text = generate_template_summary(data)
        assert "Shopping" in text or "Food" in text

    def test_mentions_anomalies_when_present(self):
        anomaly = AnomalyRecord(
            transaction_id="T99", date=date(2026, 9, 15), merchant="M",
            category="Shopping", amount=99000, anomaly_type="statistical_outlier",
            reason="High", severity="high",
        )
        data = _make_summary_input(anomalies=[anomaly])
        text = generate_template_summary(data)
        assert "unusual" in text.lower() or "flagged" in text.lower()


class TestNumericGrounding:
    def test_allowed_numbers_extracts_all_fields(self):
        data = _make_summary_input()
        nums = _allowed_numbers(data)
        assert 85000 in nums
        assert 8500 in nums
        assert 40000 in nums
        assert 47 in nums

    def test_extract_numbers_from_text(self):
        nums = _extract_numbers_from_text("You spent ₹85,000 across 10 transactions.")
        assert 85000 in nums
        assert 10 in nums

    def test_grounding_passes_with_valid_numbers(self):
        data = _make_summary_input()
        text = "You had 10 transactions totaling ₹85,000. Average was ₹8,500."
        assert _passes_numeric_grounding_check(text, data) is True

    def test_grounding_fails_with_invented_number(self):
        data = _make_summary_input()
        text = "You had 10 transactions totaling ₹85,000. You also spent ₹999,999 on travel."
        assert _passes_numeric_grounding_check(text, data) is False

    def test_small_numbers_and_years_always_pass(self):
        data = _make_summary_input()
        text = "In 2026, your 3 biggest purchases were analyzed."
        assert _passes_numeric_grounding_check(text, data) is True


class TestGenerateSummaryFallback:
    def test_no_llm_returns_template(self):
        data = _make_summary_input()
        with patch("src.summarizer.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = None
            mock_cfg.CURRENCY_SYMBOL = "₹"
            text, method = generate_summary(data)
        assert method == "template"
        assert len(text) > 0

    def test_llm_failure_falls_back_to_template(self):
        data = _make_summary_input()
        with patch("src.summarizer.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "openai"
            mock_cfg.OPENAI_API_KEY = "fake"
            mock_cfg.OPENAI_BASE_URL = None
            mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
            mock_cfg.CURRENCY_SYMBOL = "₹"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 5
            with patch("src.summarizer._call_openai_summary", side_effect=Exception("API down")):
                text, method = generate_summary(data)
        assert method == "template"
        assert len(text) > 0

    def test_llm_hallucination_falls_back_to_template(self):
        data = _make_summary_input()
        hallucinated = "You spent ₹999,999,999 on everything. Total was ₹85,000."
        with patch("src.summarizer.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "openai"
            mock_cfg.OPENAI_API_KEY = "fake"
            mock_cfg.OPENAI_BASE_URL = None
            mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
            mock_cfg.CURRENCY_SYMBOL = "₹"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 5
            with patch("src.summarizer._call_openai_summary", return_value=hallucinated):
                text, method = generate_summary(data)
        assert method == "template"
