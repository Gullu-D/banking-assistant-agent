"""
Financial calculation accuracy tests.

Uses isolated in-memory databases with controlled test data to verify:
- Expenses exclude income
- Income excludes expenses
- Top expenses are genuine expenses only
- Monthly expenditure is correct
- Category-wise expenditure is correct
- Income vs expense comparison is correct
- Negative amounts / refunds handled correctly
- Empty results return honest messages
- Date filters work correctly
- Type correction from category works
"""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import Transaction
from src.orchestrator import Orchestrator
from src.services import create_user, get_default_account, _correct_types_from_category
from src.analytics import (
    calculate_overall_statistics,
    calculate_category_breakdown,
    calculate_matching_statistics,
    income_expense_over_time,
    spending_over_time,
)
from src.validators import StructuredQuery


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


def _seed(db, username="finuser", txns=None):
    """Create a user with specific transactions."""
    user = create_user(db, username, f"{username}@example.com", "pass1234")
    db.commit()
    account = get_default_account(db, user.id)
    for t in (txns or []):
        db.add(Transaction(
            account_id=account.id,
            date=t["date"],
            description=t.get("description", "Transaction"),
            merchant=t.get("merchant", "Unknown"),
            category=t.get("category", "Other"),
            txn_type=t["type"],
            amount=t["amount"],
        ))
    db.commit()
    return user


# ── Type correction from category ─────────────────────────────── #


class TestTypeCorrection:
    def test_all_debit_income_categories_become_credit(self):
        df = pd.DataFrame({
            "type": ["Debit", "Debit", "Debit"],
            "category": ["Salary", "Freelance", "Interest"],
            "amount": [50000, 10000, 500],
        })
        result = _correct_types_from_category(df)
        assert (result["type"] == "Credit").all()

    def test_mixed_types_unchanged(self):
        df = pd.DataFrame({
            "type": ["Debit", "Credit"],
            "category": ["Shopping", "Salary"],
            "amount": [5000, 50000],
        })
        result = _correct_types_from_category(df)
        assert result["type"].tolist() == ["Debit", "Credit"]

    def test_all_debit_expense_categories_stay_debit(self):
        df = pd.DataFrame({
            "type": ["Debit", "Debit"],
            "category": ["Shopping", "Food & Dining"],
            "amount": [5000, 2000],
        })
        result = _correct_types_from_category(df)
        assert (result["type"] == "Debit").all()

    def test_mixed_income_and_expense_all_debit(self):
        """When all rows are Debit but only some are income categories,
        only the income ones get corrected."""
        df = pd.DataFrame({
            "type": ["Debit", "Debit", "Debit"],
            "category": ["Salary", "Shopping", "Refund"],
            "amount": [50000, 5000, 1000],
        })
        result = _correct_types_from_category(df)
        assert result["type"].tolist() == ["Credit", "Debit", "Credit"]

    def test_empty_df_unchanged(self):
        df = pd.DataFrame(columns=["type", "category", "amount"])
        result = _correct_types_from_category(df)
        assert result.empty

    def test_refund_becomes_credit(self):
        df = pd.DataFrame({
            "type": ["Debit"],
            "category": ["Refund"],
            "amount": [1500],
        })
        result = _correct_types_from_category(df)
        assert result["type"].iloc[0] == "Credit"

    def test_raw_salary_alias_resolved(self):
        """'Salary' (raw) maps to 'Salary / Income' (canonical) which is in INCOME_CATEGORIES."""
        df = pd.DataFrame({
            "type": ["Debit"],
            "category": ["Salary"],
            "amount": [50000],
        })
        result = _correct_types_from_category(df)
        assert result["type"].iloc[0] == "Credit"


# ── Expense vs Income separation ──────────────────────────────── #


class TestExpenseIncomeSeparation:
    @pytest.fixture()
    def mixed_user(self, db):
        return _seed(db, "mixed", [
            {"date": date(2026, 9, 1), "type": "Credit", "amount": 50000,
             "category": "Salary / Income", "merchant": "Employer", "description": "Monthly salary"},
            {"date": date(2026, 9, 5), "type": "Debit", "amount": 3000,
             "category": "Food & Dining", "merchant": "Swiggy", "description": "Food order"},
            {"date": date(2026, 9, 10), "type": "Debit", "amount": 15000,
             "category": "Shopping", "merchant": "Amazon", "description": "Electronics"},
            {"date": date(2026, 9, 15), "type": "Credit", "amount": 2000,
             "category": "Refund", "merchant": "Amazon", "description": "Refund"},
            {"date": date(2026, 9, 20), "type": "Debit", "amount": 8000,
             "category": "Travel", "merchant": "MakeMyTrip", "description": "Flight tickets"},
        ])

    def test_total_expenses_exclude_income(self, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("Show my spending summary", today=date(2026, 10, 1))
        assert result.success
        stats = result.data.get("overall_stats")
        assert stats is not None
        assert stats.total_spending == 26000  # 3000 + 15000 + 8000
        assert stats.total_income == 52000  # 50000 + 2000

    def test_total_income_excludes_expenses(self, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("Show my spending summary", today=date(2026, 10, 1))
        stats = result.data["overall_stats"]
        assert stats.total_income == 52000  # salary + refund

    def test_top_expenses_only_debits(self, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("What are my top expenses?", today=date(2026, 10, 1))
        assert result.success
        matching = result.data.get("matching_stats")
        assert matching is not None
        assert matching.matching_total_amount == 26000  # 3000 + 15000 + 8000, excludes credits

    def test_category_breakdown_spending_only(self, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("Show my spending summary", today=date(2026, 10, 1))
        breakdown = result.data.get("category_breakdown", [])
        cat_names = {cb.category for cb in breakdown}
        assert "Salary / Income" not in cat_names
        assert "Refund" not in cat_names

    def test_net_cash_flow_correct(self, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("Show my spending summary", today=date(2026, 10, 1))
        stats = result.data["overall_stats"]
        assert stats.net_cash_flow == 26000  # 52000 - 26000

    @patch("config.active_llm_provider", return_value=None)
    def test_income_analysis_only_credits(self, _mock, db, mixed_user):
        orch = Orchestrator(db=db, user_id=mixed_user.id)
        result = orch.run("Show my income analysis", today=date(2026, 10, 1))
        assert result.success
        answer = result.data.get("direct_answer", "")
        assert "52,000" in answer or "52000" in answer.replace(",", "")


# ── Monthly expenditure ───────────────────────────────────────── #


class TestMonthlyExpenditure:
    @pytest.fixture()
    def monthly_user(self, db):
        txns = [
            {"date": date(2026, 8, 5), "type": "Debit", "amount": 10000,
             "category": "Shopping", "merchant": "Amazon"},
            {"date": date(2026, 8, 15), "type": "Debit", "amount": 5000,
             "category": "Food & Dining", "merchant": "Zomato"},
            {"date": date(2026, 9, 5), "type": "Debit", "amount": 12000,
             "category": "Shopping", "merchant": "Flipkart"},
            {"date": date(2026, 9, 10), "type": "Credit", "amount": 50000,
             "category": "Salary / Income", "merchant": "Employer"},
        ]
        return _seed(db, "monthly", txns)

    def test_spending_over_time_excludes_income(self, db, monthly_user):
        from src.services import DBTransactionRepository
        repo = DBTransactionRepository(db, monthly_user.id)
        df, _ = repo.load()
        sot = spending_over_time(df, freq="MS")
        # Only debit amounts should appear
        total = sot["amount"].sum()
        assert total == 27000  # 10000 + 5000 + 12000

    def test_income_expense_over_time(self, db, monthly_user):
        from src.services import DBTransactionRepository
        repo = DBTransactionRepository(db, monthly_user.id)
        df, _ = repo.load()
        ie = income_expense_over_time(df, freq="MS")
        # August: expense=15000, income=0
        # September: expense=12000, income=50000
        aug = ie[ie["period"].dt.month == 8].iloc[0]
        sep = ie[ie["period"].dt.month == 9].iloc[0]
        assert aug["expense"] == 15000
        assert aug["income"] == 0
        assert sep["expense"] == 12000
        assert sep["income"] == 50000


# ── Category-wise expenditure ─────────────────────────────────── #


class TestCategoryBreakdown:
    def test_category_totals_correct(self):
        df = pd.DataFrame({
            "type": ["Debit", "Debit", "Debit", "Credit"],
            "category": ["Shopping", "Shopping", "Food & Dining", "Salary / Income"],
            "amount": [5000, 3000, 2000, 50000],
            "date": pd.to_datetime(["2026-09-01"] * 4),
        })
        breakdown = calculate_category_breakdown(df, spending_only=True)
        totals = {cb.category: cb.total_amount for cb in breakdown}
        assert totals["Shopping"] == 8000
        assert totals["Food & Dining"] == 2000
        assert "Salary / Income" not in totals

    def test_percentages_sum_to_100(self):
        df = pd.DataFrame({
            "type": ["Debit", "Debit", "Debit"],
            "category": ["Shopping", "Food & Dining", "Travel"],
            "amount": [5000, 3000, 2000],
            "date": pd.to_datetime(["2026-09-01"] * 3),
        })
        breakdown = calculate_category_breakdown(df, spending_only=True)
        total_pct = sum(cb.percentage_of_spending for cb in breakdown)
        assert abs(total_pct - 100.0) < 0.1


# ── Empty results ─────────────────────────────────────────────── #


class TestEmptyResults:
    def test_no_expenses_honest_message(self, db):
        user = _seed(db, "income_only", [
            {"date": date(2026, 9, 1), "type": "Credit", "amount": 50000,
             "category": "Salary / Income", "merchant": "Employer"},
        ])
        orch = Orchestrator(db=db, user_id=user.id)
        result = orch.run("Show my top expenses", today=date(2026, 10, 1))
        assert result.success
        assert "No transactions matched" in result.data.get("direct_answer", "")

    def test_no_transactions_at_all(self, db):
        user = _seed(db, "empty_user", [])
        orch = Orchestrator(db=db, user_id=user.id)
        result = orch.run("Show my spending summary")
        assert result.success
        assert "No transactions matched" in result.data.get("direct_answer", "")


# ── Date filters ──────────────────────────────────────────────── #


class TestDateFilters:
    @pytest.fixture()
    def dated_user(self, db):
        txns = [
            {"date": date(2026, 8, 15), "type": "Debit", "amount": 5000,
             "category": "Shopping", "merchant": "Amazon"},
            {"date": date(2026, 9, 15), "type": "Debit", "amount": 8000,
             "category": "Shopping", "merchant": "Flipkart"},
            {"date": date(2026, 10, 15), "type": "Debit", "amount": 3000,
             "category": "Shopping", "merchant": "Myntra"},
        ]
        return _seed(db, "dated", txns)

    def test_last_month_filter(self, db, dated_user):
        orch = Orchestrator(db=db, user_id=dated_user.id)
        result = orch.run("What did I spend last month?", today=date(2026, 10, 1))
        assert result.success
        stats = result.data.get("matching_stats")
        if stats:
            assert stats.matching_total_amount == 8000

    def test_this_month_filter(self, db, dated_user):
        orch = Orchestrator(db=db, user_id=dated_user.id)
        result = orch.run("What did I spend this month?", today=date(2026, 10, 20))
        assert result.success
        stats = result.data.get("matching_stats")
        if stats:
            assert stats.matching_total_amount == 3000


# ── Orchestrator expense intent enforcement ───────────────────── #


class TestExpenseIntentFiltering:
    @pytest.fixture()
    def mixed_type_user(self, db):
        return _seed(db, "mixtype", [
            {"date": date(2026, 9, 1), "type": "Credit", "amount": 60000,
             "category": "Salary / Income", "merchant": "Employer"},
            {"date": date(2026, 9, 5), "type": "Debit", "amount": 5000,
             "category": "Shopping", "merchant": "Amazon"},
            {"date": date(2026, 9, 10), "type": "Debit", "amount": 2000,
             "category": "Food & Dining", "merchant": "Swiggy"},
            {"date": date(2026, 9, 15), "type": "Credit", "amount": 1500,
             "category": "Refund", "merchant": "Amazon"},
        ])

    def test_top_expenses_excludes_credits(self, db, mixed_type_user):
        orch = Orchestrator(db=db, user_id=mixed_type_user.id)
        result = orch.run("Show my top expenses", today=date(2026, 10, 1))
        assert result.success
        stats = result.data.get("matching_stats")
        assert stats is not None
        assert stats.matching_total_amount == 7000  # 5000 + 2000

    def test_spending_summary_excludes_credits(self, db, mixed_type_user):
        orch = Orchestrator(db=db, user_id=mixed_type_user.id)
        result = orch.run("Show my spending summary", today=date(2026, 10, 1))
        assert result.success
        stats = result.data.get("matching_stats")
        assert stats is not None
        assert stats.matching_total_amount == 7000

    def test_category_spending_excludes_credits(self, db, mixed_type_user):
        orch = Orchestrator(db=db, user_id=mixed_type_user.id)
        result = orch.run("What did I spend on shopping?", today=date(2026, 10, 1))
        assert result.success
        stats = result.data.get("matching_stats")
        assert stats is not None
        assert stats.matching_total_amount == 5000
