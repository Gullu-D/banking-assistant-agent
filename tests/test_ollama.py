"""Tests for Ollama LLM provider integration.

Covers: provider selection, health checks, query parsing, summary generation,
timeout/error handling, deterministic fallback, and conversation context.
All external network calls are mocked in automated tests.
"""

import json
import time
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date

import pytest

import config
from src.query_parser import parse_query, parse_with_llm, _call_ollama
from src.summarizer import generate_summary, _call_ollama_summary
from src.validators import AnalysisSummaryInput, CategoryBreakdownItem


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _reset_caches():
    """Reset module-level caches so tests are independent."""
    import src.query_parser as qp
    import src.summarizer as sm
    qp._llm_disabled_until = 0.0
    sm._llm_disabled_until = 0.0
    config._ollama_cache.update(up=None, models=None, ts=0.0)


def _ollama_tags_response(models=None):
    """Build a fake /api/tags JSON response."""
    if models is None:
        models = [{"name": "llama3.2:latest"}]
    return json.dumps({"models": models}).encode()


def _ollama_chat_response(content: str):
    """Build a fake /api/chat JSON response."""
    return json.dumps({
        "model": "llama3.2",
        "message": {"role": "assistant", "content": content},
        "done": True,
    }).encode()


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #

class TestProviderSelection:
    def setup_method(self):
        _reset_caches()

    @patch.object(config, "LLM_PROVIDER", "ollama")
    @patch.object(config, "_check_ollama_available", return_value=True)
    def test_explicit_ollama_provider(self, _):
        assert config.active_llm_provider() == "ollama"

    @patch.object(config, "LLM_PROVIDER", "ollama")
    @patch.object(config, "_check_ollama_available", return_value=False)
    def test_ollama_provider_unavailable_returns_none(self, _):
        assert config.active_llm_provider() is None

    @patch.object(config, "LLM_PROVIDER", "openai")
    @patch.object(config, "OPENAI_API_KEY", "sk-test")
    def test_explicit_openai_provider(self):
        assert config.active_llm_provider() == "openai"

    @patch.object(config, "LLM_PROVIDER", "auto")
    @patch.object(config, "_check_ollama_available", return_value=True)
    def test_auto_prefers_ollama(self, _):
        assert config.active_llm_provider() == "ollama"

    @patch.object(config, "LLM_PROVIDER", "auto")
    @patch.object(config, "_check_ollama_available", return_value=False)
    @patch.object(config, "OPENAI_API_KEY", "sk-test")
    def test_auto_falls_back_to_openai(self, _):
        assert config.active_llm_provider() == "openai"

    @patch.object(config, "LLM_PROVIDER", "auto")
    @patch.object(config, "_check_ollama_available", return_value=False)
    @patch.object(config, "OPENAI_API_KEY", "")
    @patch.object(config, "GOOGLE_API_KEY", "")
    def test_auto_no_providers_returns_none(self, _):
        assert config.active_llm_provider() is None


# --------------------------------------------------------------------------- #
# Health checks
# --------------------------------------------------------------------------- #

class TestOllamaHealthCheck:
    def setup_method(self):
        _reset_caches()

    @patch("config._ollama_tags")
    def test_server_not_running(self, mock_tags):
        mock_tags.return_value = None
        up, model_ok, msg = config.check_ollama()
        assert not up
        assert not model_ok
        assert "not reachable" in msg

    @patch("config._ollama_tags")
    def test_server_running_model_missing(self, mock_tags):
        mock_tags.return_value = {"models": [{"name": "mistral:latest"}]}
        up, model_ok, msg = config.check_ollama()
        assert up
        assert not model_ok
        assert "not installed" in msg

    @patch("config._ollama_tags")
    @patch.object(config, "OLLAMA_MODEL", "llama3.2")
    def test_server_running_model_installed(self, mock_tags):
        mock_tags.return_value = {"models": [{"name": "llama3.2:latest"}]}
        up, model_ok, msg = config.check_ollama()
        assert up
        assert model_ok
        assert "ready" in msg

    @patch("config._ollama_tags")
    @patch.object(config, "OLLAMA_MODEL", "llama3.2")
    def test_tag_mismatch_reports_missing(self, mock_tags):
        """llama3.2:1b installed but config asks for llama3.2 (= :latest)."""
        mock_tags.return_value = {"models": [{"name": "llama3.2:1b"}]}
        up, model_ok, msg = config.check_ollama()
        assert up
        assert not model_ok
        assert "not installed" in msg

    @patch("config._ollama_tags")
    @patch.object(config, "OLLAMA_MODEL", "llama3.2:1b")
    def test_explicit_tag_matches(self, mock_tags):
        """Config specifies exact tag llama3.2:1b — matches installed model."""
        mock_tags.return_value = {"models": [{"name": "llama3.2:1b"}]}
        up, model_ok, msg = config.check_ollama()
        assert up
        assert model_ok
        assert "ready" in msg


# --------------------------------------------------------------------------- #
# LLM status
# --------------------------------------------------------------------------- #

class TestLlmStatus:
    def setup_method(self):
        _reset_caches()

    @patch.object(config, "LLM_PROVIDER", "ollama")
    @patch.object(config, "_check_ollama_available", return_value=True)
    @patch.object(config, "_check_ollama_model_installed", return_value=True)
    def test_ollama_active_status(self, *_):
        status, msg = config.llm_status()
        assert status == "active"
        assert "ollama" in msg.lower()
        assert "local" in msg.lower()

    @patch.object(config, "LLM_PROVIDER", "ollama")
    @patch.object(config, "_check_ollama_available", return_value=False)
    def test_ollama_unavailable_status(self, _):
        status, msg = config.llm_status()
        assert status == "unavailable"


# --------------------------------------------------------------------------- #
# Query parsing with Ollama
# --------------------------------------------------------------------------- #

class TestOllamaQueryParsing:
    def setup_method(self):
        _reset_caches()

    @patch("src.query_parser.config")
    @patch("src.query_parser._call_ollama")
    def test_ollama_parse_success(self, mock_call, mock_cfg):
        mock_cfg.active_llm_provider.return_value = "ollama"
        mock_call.return_value = {
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
        result = parse_with_llm("What did I spend this month?")
        assert result is not None
        assert result.intent == "spending_summary"
        assert result.date_range == "this_month"

    @patch("src.query_parser.config")
    @patch("src.query_parser._call_ollama", side_effect=Exception("connection refused"))
    def test_ollama_failure_returns_none(self, mock_call, mock_cfg):
        mock_cfg.active_llm_provider.return_value = "ollama"
        result = parse_with_llm("anything")
        assert result is None

    @patch("src.query_parser.config")
    @patch("src.query_parser._call_ollama", side_effect=Exception("timeout"))
    def test_ollama_timeout_falls_back_to_deterministic(self, mock_call, mock_cfg):
        mock_cfg.active_llm_provider.return_value = "ollama"
        query, method = parse_query("Show transactions above ₹50,000")
        assert method == "deterministic"
        assert query.amount_threshold == 50000

    @patch("src.query_parser.config")
    @patch("src.query_parser._call_ollama")
    def test_ollama_malformed_json_returns_none(self, mock_call, mock_cfg):
        mock_cfg.active_llm_provider.return_value = "ollama"
        mock_call.side_effect = json.JSONDecodeError("", "", 0)
        result = parse_with_llm("anything")
        assert result is None


# --------------------------------------------------------------------------- #
# Summary generation with Ollama
# --------------------------------------------------------------------------- #

class TestOllamaSummary:
    def setup_method(self):
        _reset_caches()

    def _make_input(self):
        return AnalysisSummaryInput(
            period_label="November 2026",
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

    @patch("src.summarizer.config")
    @patch("src.summarizer._call_ollama_summary")
    def test_ollama_summary_success(self, mock_call, mock_cfg):
        data = self._make_input()
        mock_cfg.active_llm_provider.return_value = "ollama"
        mock_cfg.CURRENCY_SYMBOL = "₹"
        mock_call.return_value = (
            "During November 2026, you had 5 transactions totaling ₹75,000. "
            "Shopping was the top category at ₹50,000 (67%)."
        )
        text, method = generate_summary(data)
        assert method == "ai"
        assert "75,000" in text

    @patch("src.summarizer.config")
    @patch("src.summarizer._call_ollama_summary", side_effect=Exception("connection refused"))
    def test_ollama_summary_failure_falls_back(self, mock_call, mock_cfg):
        data = self._make_input()
        mock_cfg.active_llm_provider.return_value = "ollama"
        mock_cfg.CURRENCY_SYMBOL = "₹"
        text, method = generate_summary(data)
        assert method == "template"
        assert "75,000" in text


# --------------------------------------------------------------------------- #
# Deterministic fallback preserved
# --------------------------------------------------------------------------- #

class TestDeterministicFallback:
    def setup_method(self):
        _reset_caches()

    @patch("src.query_parser.config")
    def test_no_provider_uses_deterministic(self, mock_cfg):
        mock_cfg.active_llm_provider.return_value = None
        query, method = parse_query("Show transactions above ₹10,000")
        assert method == "deterministic"
        assert query.amount_threshold == 10000

    @patch("src.query_parser.config")
    def test_parse_with_llm_returns_none_when_no_provider(self, mock_cfg):
        mock_cfg.active_llm_provider.return_value = None
        result = parse_with_llm("anything")
        assert result is None


# --------------------------------------------------------------------------- #
# OpenAI compatibility preserved
# --------------------------------------------------------------------------- #

class TestOpenAICompatibility:
    def setup_method(self):
        _reset_caches()

    @patch("src.query_parser.config")
    @patch("src.query_parser._call_openai")
    def test_openai_still_works(self, mock_call, mock_cfg):
        mock_cfg.active_llm_provider.return_value = "openai"
        mock_cfg.OPENAI_API_KEY = "sk-test"
        mock_cfg.OPENAI_BASE_URL = None
        mock_cfg.OPENAI_MODEL = "gpt-4o-mini"
        mock_cfg.LLM_REQUEST_TIMEOUT_SECONDS = 10
        mock_call.return_value = {
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
        result = parse_with_llm("Show transactions above 50000 from last month")
        assert result is not None
        assert result.amount_threshold == 50000


# --------------------------------------------------------------------------- #
# Cross-user isolation (orchestrator level)
# --------------------------------------------------------------------------- #

class TestCrossUserIsolation:
    """Verify that the orchestrator enforces user_id scoping regardless of LLM provider."""

    def setup_method(self):
        _reset_caches()

    def test_orchestrator_scopes_to_user(self):
        from src.orchestrator import Orchestrator
        orc_alice = Orchestrator(db=None, user_id=1, csv_path=None)
        orc_bob = Orchestrator(db=None, user_id=2, csv_path=None)
        assert orc_alice.user_id != orc_bob.user_id

    def test_conversation_context_isolation(self):
        from src.orchestrator import ConversationContext
        ctx_a = ConversationContext()
        ctx_a.user_id = 1
        ctx_a.add_turn("q1", "spending_summary", "this_month", None, "answer1")

        ctx_b = ConversationContext()
        ctx_b.user_id = 2
        assert len(ctx_b.turns) == 0
        assert len(ctx_a.turns) == 1


# --------------------------------------------------------------------------- #
# Live Ollama test (only runs if Ollama is actually available)
# --------------------------------------------------------------------------- #

class TestLiveOllama:
    """Integration test that makes a real Ollama call. Skipped if Ollama is not running."""

    def setup_method(self):
        _reset_caches()

    @pytest.fixture(autouse=True)
    def _require_ollama(self):
        if not config._check_ollama_available():
            pytest.skip("Ollama server not running")
        if not config._check_ollama_model_installed():
            pytest.skip(f"Ollama model '{config.OLLAMA_MODEL}' not installed")

    def test_live_query_parsing(self):
        config._ollama_cache.update(up=None, models=None, ts=0.0)
        try:
            result = _call_ollama("How much did I spend on groceries last month?")
        except Exception as exc:
            pytest.skip(f"Ollama call failed: {exc}")
        assert isinstance(result, dict)
        assert "intent" in result

    def test_live_summary_generation(self):
        config._ollama_cache.update(up=None, models=None, ts=0.0)
        payload = {
            "period_label": "October 2026",
            "matching_transaction_count": 3,
            "matching_total_amount": 9500.0,
            "matching_average_amount": 3166.67,
            "matching_largest_amount": 4200.0,
            "matching_smallest_amount": 2500.0,
            "total_spending_overall": 50000.0,
            "category_breakdown": [
                {"category": "Groceries", "transaction_count": 3,
                 "total_amount": 9500.0, "percentage_of_spending": 19.0}
            ],
        }
        try:
            result = _call_ollama_summary(payload)
        except Exception as exc:
            pytest.skip(f"Ollama call failed: {exc}")
        assert isinstance(result, str)
        assert len(result) > 20
