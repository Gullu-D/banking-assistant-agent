"""
Phase 4 tests: conversational AI, specialized agents, follow-up resolution,
new intent routing, and conversation context isolation.
"""

from datetime import date
from unittest.mock import patch
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import Transaction
from src.orchestrator import (
    ConversationContext,
    Orchestrator,
    agent_insights,
    agent_period_comparison,
    agent_trend_analysis,
)
from src.query_parser import parse_deterministic
from src.services import create_user, get_default_account
from src.validators import StructuredQuery


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


def _seed_user(db, username="p4user", months=None):
    """Create a user with transactions across given months."""
    user = create_user(db, username, f"{username}@example.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)
    months = months or [(2026, 8), (2026, 9)]
    for m_idx, (y, m) in enumerate(months):
        for i in range(5):
            db.add(Transaction(
                account_id=account.id,
                date=date(y, m, 1 + i),
                description=f"Purchase {m_idx}-{i}",
                merchant="ShopAlpha" if i % 2 == 0 else "ShopBeta",
                category="Shopping" if i % 2 == 0 else "Food & Dining",
                txn_type="Debit",
                amount=1000 + i * 500,
            ))
        db.add(Transaction(
            account_id=account.id,
            date=date(y, m, 10),
            description=f"Salary {m_idx}",
            merchant="Employer",
            category="Salary / Income",
            txn_type="Credit",
            amount=50000,
        ))
    db.commit()
    return user


# ── Intent routing for new intents ──────────────────────────────────── #


def test_parse_trend_intent():
    q = parse_deterministic("How has my spending changed over time?")
    assert q.intent == "trend_analysis"


def test_parse_comparison_intent():
    q = parse_deterministic("Compare this month to last month")
    assert q.intent == "period_comparison"


def test_parse_insights_intent():
    q = parse_deterministic("What insights can you give me about my finances?")
    assert q.intent == "insights_query"


def test_parse_trend_not_triggered_with_amount():
    q = parse_deterministic("Show transactions above 5000 that increased")
    assert q.intent != "trend_analysis"


def test_parse_comparison_not_triggered_with_amount():
    q = parse_deterministic("Compare transactions above 10000")
    assert q.intent != "period_comparison"


# ── Specialized agents (deterministic) ──────────────────────────────── #


@pytest.fixture()
def user_data(db):
    return _seed_user(db)


def test_trend_analysis_routing(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("How has my spending changed over time?", today=date(2026, 10, 1))
    assert result.success
    assert "direct_answer" in result.data
    assert result.data["direct_answer"]
    assert result.data.get("period_label")


def test_period_comparison_routing(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("Compare this month to last month", today=date(2026, 10, 1))
    assert result.success
    assert "direct_answer" in result.data
    assert result.data["direct_answer"]


def test_insights_routing(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("What insights do you have about my spending?", today=date(2026, 10, 1))
    assert result.success
    assert "direct_answer" in result.data
    assert result.data["direct_answer"]


def test_trend_analysis_empty_df():
    import pandas as pd
    df = pd.DataFrame(columns=["date", "type", "amount", "merchant", "category",
                                "transaction_id", "description", "account"])
    result = agent_trend_analysis(df, StructuredQuery(intent="trend_analysis"))
    assert result.success
    assert "No transactions" in result.data["direct_answer"]


def test_period_comparison_empty_df():
    import pandas as pd
    df = pd.DataFrame(columns=["date", "type", "amount", "merchant", "category",
                                "transaction_id", "description", "account"])
    result = agent_period_comparison(df, StructuredQuery(intent="period_comparison"), date(2026, 10, 1))
    assert result.success
    assert "No transactions" in result.data["direct_answer"]


def test_insights_too_few_rows():
    import pandas as pd
    df = pd.DataFrame({
        "date": [date(2026, 9, 1)],
        "type": ["Debit"],
        "amount": [1000],
        "merchant": ["Store"],
        "category": ["Shopping"],
        "transaction_id": ["t1"],
        "description": ["Buy"],
        "account": ["acc"],
    })
    result = agent_insights(df)
    assert result.success
    assert "Not enough" in result.data["direct_answer"]


# ── Conversation context ────────────────────────────────────────────── #


def test_conversation_context_add_and_trim():
    ctx = ConversationContext()
    ctx.user_id = 1
    for i in range(15):
        ctx.add_turn(f"query {i}", "general_query", "all_time", None, f"answer {i}")
    assert len(ctx.turns) == 10  # MAX_CONVERSATION_TURNS


def test_conversation_context_clear():
    ctx = ConversationContext()
    ctx.user_id = 1
    ctx.add_turn("test", "general_query", "last_month", None, "result")
    ctx.clear()
    assert len(ctx.turns) == 0


def test_follow_up_resolves_date_range():
    ctx = ConversationContext()
    ctx.user_id = 1
    ctx.add_turn("spending last month", "spending_summary", "last_month", None, "result")
    q = StructuredQuery(intent="general_query", date_range="all_time", raw_query="what about shopping?")
    resolved = ctx.resolve_follow_up(q)
    assert resolved.date_range == "last_month"


def test_follow_up_resolves_category():
    ctx = ConversationContext()
    ctx.user_id = 1
    ctx.add_turn("show shopping", "category_spending", "last_month", "Shopping", "result")
    q = StructuredQuery(intent="general_query", date_range="all_time", raw_query="same for Food & Dining")
    resolved = ctx.resolve_follow_up(q)
    # "same for" triggers follow-up, but category is explicitly in the new query
    # The follow-up only fills in category if None and pattern matches
    # Here category is None in the StructuredQuery, and "same for" matches
    assert resolved.category == "Shopping"  # inherited from prior


def test_follow_up_no_false_positive():
    ctx = ConversationContext()
    ctx.user_id = 1
    ctx.add_turn("show shopping", "category_spending", "last_month", "Shopping", "result")
    q = StructuredQuery(intent="general_query", date_range="all_time", raw_query="show my biggest expenses")
    resolved = ctx.resolve_follow_up(q)
    assert resolved.category is None  # no follow-up pattern → no category inheritance


def test_context_passed_through_orchestrator(db, user_data):
    ctx = ConversationContext()
    ctx.user_id = user_data.id
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("What did I spend last month?", today=date(2026, 10, 1), context=ctx)
    assert result.success
    assert len(ctx.turns) == 1
    assert ctx.turns[0].intent == "spending_summary"


@patch("config.active_llm_provider", return_value=None)
def test_context_records_specialized_agent_turn(_mock, db, user_data):
    ctx = ConversationContext()
    ctx.user_id = user_data.id
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("How has my spending changed?", today=date(2026, 10, 1), context=ctx)
    assert result.success
    assert len(ctx.turns) == 1
    assert ctx.turns[0].intent == "trend_analysis"


# ── Deterministic fallback for new intents ──────────────────────────── #


@patch("config.active_llm_provider", return_value=None)
def test_new_intents_work_without_api_keys(_mock, db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    for query_text in [
        "How has my spending changed?",
        "Compare this month to last month",
        "What patterns do you see in my spending?",
    ]:
        result = orch.run(query_text, today=date(2026, 10, 1))
        assert result.success, f"Failed for: {query_text}"
        assert result.data["parse_method"] == "deterministic"


# ── User isolation for new intents ──────────────────────────────────── #


def test_trend_analysis_user_isolation(db):
    user_a = _seed_user(db, "trend_a")
    user_b = _seed_user(db, "trend_b")

    orch_a = Orchestrator(db=db, user_id=user_a.id)
    result_a = orch_a.run("How has my spending changed?", today=date(2026, 10, 1))
    assert result_a.success

    orch_b = Orchestrator(db=db, user_id=user_b.id)
    result_b = orch_b.run("How has my spending changed?", today=date(2026, 10, 1))
    assert result_b.success

    # Both succeed independently — they loaded their own data
    assert result_a.data["direct_answer"] == result_b.data["direct_answer"]  # same seed data


def test_context_isolated_by_user():
    ctx_a = ConversationContext()
    ctx_a.user_id = 1
    ctx_a.add_turn("query A", "spending_summary", "last_month", "Shopping", "answer A")

    ctx_b = ConversationContext()
    ctx_b.user_id = 2
    assert len(ctx_b.turns) == 0  # completely separate


# ── Direct answer for standard intents ──────────────────────────────── #


def test_direct_answer_on_standard_intent(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("What did I spend on shopping?", today=date(2026, 10, 1))
    assert result.success
    assert result.data.get("direct_answer")
    assert "Shopping" in result.data["direct_answer"]


# ── Unsupported / general query fallback ────────────────────────────── #


def test_general_query_falls_back_gracefully(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("Tell me something random about finance", today=date(2026, 10, 1))
    assert result.success
    assert "matching_stats" in result.data


# ── Error handling ──────────────────────────────────────────────────── #


@patch("config.active_llm_provider", return_value=None)
def test_empty_query_returns_error(_mock, db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("")
    assert result.success is False
    assert result.error


@patch("config.active_llm_provider", return_value=None)
def test_context_not_recorded_on_failure(_mock, db, user_data):
    ctx = ConversationContext()
    ctx.user_id = user_data.id
    orch = Orchestrator(db=db, user_id=user_data.id)
    orch.run("", context=ctx)
    assert len(ctx.turns) == 0


# ── Regression: "more than last month" parsed as comparison, not amount error
def test_more_than_last_month_is_comparison():
    q = parse_deterministic("Did I spend more than last month?")
    assert q.intent == "period_comparison"
    assert q.amount_threshold is None


def test_less_than_last_month_is_comparison():
    q = parse_deterministic("Did I spend less than last month?")
    assert q.intent == "period_comparison"
    assert q.amount_threshold is None


# ── Regression: unrelated query should not inherit stale date_range
def test_no_date_inheritance_without_follow_up_pattern():
    ctx = ConversationContext()
    ctx.user_id = 1
    ctx.add_turn("spending last month", "spending_summary", "last_month", "Shopping", "result")
    q = StructuredQuery(intent="top_expenses", date_range="all_time", raw_query="Show me biggest expenses")
    resolved = ctx.resolve_follow_up(q)
    assert resolved.date_range == "all_time"
    assert resolved.category is None


# ── Regression: standard intents with direct_answer should still show charts
def test_standard_intent_has_matching_stats(db, user_data):
    orch = Orchestrator(db=db, user_id=user_data.id)
    result = orch.run("What did I spend on shopping?", today=date(2026, 10, 1))
    assert result.success
    assert "matching_stats" in result.data
    assert "category_breakdown" in result.data
    assert result.data.get("direct_answer")
