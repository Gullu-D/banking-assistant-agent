"""
Integration tests for the full agent pipeline (agent.BankingAssistantAgent).
"""

import textwrap
from datetime import date
from unittest.mock import patch

import pytest

from agent import BankingAssistantAgent


@pytest.fixture()
def sample_csv(tmp_path):
    p = tmp_path / "txns.csv"
    p.write_text(textwrap.dedent("""\
        transaction_id,date,description,merchant,category,type,amount,account
        T1,2026-09-01,Salary credit,Company Salary,Salary / Income,Credit,90000,Primary
        T2,2026-09-05,Monthly rent,ABC Properties,Rent,Debit,35000,Primary
        T3,2026-09-10,Online purchase,Amazon,Shopping,Debit,60000,Primary
        T4,2026-09-12,Food order,Swiggy,Food & Dining,Debit,1500,Primary
        T5,2026-09-15,Grocery run,BigBasket,Groceries,Debit,3000,Primary
        T6,2026-09-18,Electronics,ABC Electronics,Shopping,Debit,180000,Primary
        T7,2026-09-20,Grocery,DMart,Groceries,Debit,2500,Primary
        T8,2026-09-22,Coffee,Cafe Coffee Day,Food & Dining,Debit,450,Primary
        T9,2026-09-25,Travel,MakeMyTrip,Travel,Debit,45000,Primary
        T10,2026-09-28,Investment,Zerodha,Investments,Debit,15000,Primary
    """))
    return str(p)


def test_analyze_returns_success(sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("Show all transactions", today=date(2026, 9, 30))
    assert result.success is True
    assert result.matching_stats.matching_transaction_count > 0


@patch("config.active_llm_provider", return_value=None)
def test_analyze_with_amount_filter(_mock, sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("Show transactions above ₹50,000", today=date(2026, 9, 30))
    assert result.success is True
    for _, row in result.matching_df.iterrows():
        assert row["amount"] > 50000


def test_analyze_detects_anomalies(sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("Find unusual transactions", today=date(2026, 9, 30))
    assert result.success is True
    assert result.structured_query.include_anomalies is True
    assert len(result.anomalies) > 0


def test_analyze_missing_file():
    agent = BankingAssistantAgent(csv_path="/nonexistent/path/txns.csv")
    result = agent.analyze("Show transactions")
    assert result.success is False
    assert result.error_message is not None
    assert "not found" in result.error_message.lower()


@patch("config.active_llm_provider", return_value=None)
def test_analyze_invalid_query(_mock, sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("")
    assert result.success is False
    assert result.error_message is not None


def test_analyze_category_filter(sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("How much did I spend on shopping", today=date(2026, 9, 30))
    assert result.success is True
    for _, row in result.matching_df.iterrows():
        assert row["category"] == "Shopping"


@patch("config.active_llm_provider", return_value=None)
def test_analyze_produces_summary(_mock, sample_csv):
    agent = BankingAssistantAgent(csv_path=sample_csv)
    result = agent.analyze("What did I spend this month?", today=date(2026, 9, 30))
    assert result.success is True
    assert len(result.summary_text) > 0
    assert result.summary_method in ("ai", "template")
