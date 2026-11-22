"""
Tests for LLM-dependent code paths using mocks (no real API keys needed).

Covers: query parsing with mocked LLM, LLM fallback on bad JSON, Gemini
path, and summary generation with mocked LLM.
"""

import json
from unittest.mock import MagicMock, patch
from datetime import date

import pytest

from src.query_parser import parse_query, parse_with_llm
from src.summarizer import generate_summary
from src.validators import AnalysisSummaryInput, CategoryBreakdownItem


class TestLLMQueryParsing:
    def setup_method(self):
        import src.query_parser as qp
        import src.summarizer as sm
        qp._llm_disabled_until = 0.0
        sm._llm_disabled_until = 0.0

    def _mock_openai_response(self, data: dict):
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(data)
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    def test_openai_parse_success(self):
        llm_output = {
            "intent": "transaction_analysis",
            "amount_threshold": 50000,
            "operator": "greater_than",
            "date_range": "last_month",
            "category": None,
            "transaction_type": None,
            "top_n": None,
            "sort_by": None,
            "include_summary": True,
            "include_anomalies": False,
        }

        with patch("src.query_parser.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "openai"
            mock_cfg.OPENAI_API_KEY = "fake-key"
            mock_cfg.OPENAI_BASE_URL = None
            mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10

            with patch("src.query_parser._call_openai") as mock_call:
                mock_call.return_value = llm_output
                result = parse_with_llm("Show transactions above 50000 from last month")

        assert result is not None
        assert result.amount_threshold == 50000
        assert result.operator == "greater_than"
        assert result.date_range == "last_month"

    def test_openai_bad_json_returns_none(self):
        with patch("src.query_parser.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "openai"
            mock_cfg.OPENAI_API_KEY = "fake-key"
            mock_cfg.OPENAI_BASE_URL = None
            mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10

            with patch("src.query_parser._call_openai", side_effect=Exception("parse error")):
                result = parse_with_llm("anything")

        assert result is None

    def test_gemini_parse_success(self):
        llm_output = {
            "intent": "spending_summary",
            "amount_threshold": None,
            "operator": None,
            "date_range": "this_month",
            "category": None,
            "transaction_type": "Debit",
            "top_n": None,
            "sort_by": None,
            "include_summary": True,
            "include_anomalies": False,
        }

        with patch("src.query_parser.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "gemini"
            mock_cfg.GOOGLE_API_KEY = "fake-key"
            mock_cfg.GEMINI_MODEL = "gemini-1.5-flash"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10

            with patch("src.query_parser._call_gemini") as mock_call:
                mock_call.return_value = llm_output
                result = parse_with_llm("What did I spend this month?")

        assert result is not None
        assert result.intent == "spending_summary"

    def test_no_provider_returns_none(self):
        with patch("src.query_parser.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = None
            result = parse_with_llm("anything")
        assert result is None

    def test_parse_query_falls_back_to_deterministic_on_llm_failure(self):
        with patch("src.query_parser.parse_with_llm", return_value=None):
            query, method = parse_query("Show transactions above ₹50,000")
        assert method == "deterministic"
        assert query.amount_threshold == 50000

    def test_parse_query_uses_llm_when_available(self):
        from src.validators import StructuredQuery
        fake_query = StructuredQuery(
            intent="transaction_analysis",
            amount_threshold=50000,
            operator="greater_than",
            raw_query="test",
        )
        with patch("src.query_parser.parse_with_llm", return_value=fake_query):
            query, method = parse_query("test")
        assert method == "llm"
        assert query.amount_threshold == 50000


class TestLLMSummaryGeneration:
    def _make_input(self):
        return AnalysisSummaryInput(
            period_label="September 2026",
            matching_transaction_count=5,
            matching_total_amount=75000.0,
            matching_average_amount=15000.0,
            matching_largest_amount=30000.0,
            matching_smallest_amount=5000.0,
            total_spending_overall=150000.0,
            category_breakdown=[
                CategoryBreakdownItem(category="Shopping", transaction_count=3,
                                      total_amount=50000.0, percentage_of_spending=66.67),
            ],
        )

    def test_openai_summary_success(self):
        data = self._make_input()
        good_summary = (
            "During September 2026, you had 5 matching transactions totaling ₹75,000. "
            "Shopping accounted for ₹50,000 (67%)."
        )

        with patch("src.summarizer.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "openai"
            mock_cfg.OPENAI_API_KEY = "fake"
            mock_cfg.OPENAI_BASE_URL = None
            mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
            mock_cfg.CURRENCY_SYMBOL = "₹"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10
            with patch("src.summarizer._call_openai_summary", return_value=good_summary):
                text, method = generate_summary(data)

        assert method == "ai"
        assert "75,000" in text

    def test_gemini_summary_success(self):
        data = self._make_input()
        good_summary = "You had 5 transactions in September 2026 totaling ₹75,000."

        with patch("src.summarizer.config") as mock_cfg:
            mock_cfg.active_llm_provider.return_value = "gemini"
            mock_cfg.GOOGLE_API_KEY = "fake"
            mock_cfg.GEMINI_MODEL = "gemini-1.5-flash"
            mock_cfg.CURRENCY_SYMBOL = "₹"
            mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10
            with patch("src.summarizer._call_gemini_summary", return_value=good_summary):
                text, method = generate_summary(data)

        assert method == "ai"
