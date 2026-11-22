"""
Service layer — thin wrappers around SQLAlchemy queries that the rest of the
app calls instead of touching sessions directly.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

import bcrypt
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data_loader import LoadReport
from src.models import Conversation, ConversationMessage, FinancialAccount, ImportRecord, Subscription, Transaction, User

import config

logger = config.get_logger(__name__)


# ── User helpers ────────────────────────────────────────────────────────── #

def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())


def create_user(db: Session, username: str, email: str, password: str) -> User:
    user = User(
        username=username,
        email=email.lower().strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    default_account = FinancialAccount(user_id=user.id, name="Primary", account_type="checking")
    db.add(default_account)
    db.flush()
    return user


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalars(select(User).where(User.username == username)).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email.lower().strip())).first()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


# ── Account helpers ─────────────────────────────────────────────────────── #

def get_user_accounts(db: Session, user_id: int) -> Sequence[FinancialAccount]:
    return db.scalars(
        select(FinancialAccount).where(FinancialAccount.user_id == user_id)
    ).all()


def get_default_account(db: Session, user_id: int) -> FinancialAccount | None:
    return db.scalars(
        select(FinancialAccount)
        .where(FinancialAccount.user_id == user_id)
        .order_by(FinancialAccount.id)
    ).first()


# ── DB-backed transaction repository ────────────────────────────────────── #

def _correct_types_from_category(df: pd.DataFrame) -> pd.DataFrame:
    """Fix txn_type using category when the source data is unreliable.

    When every row has the same type (typically all 'Debit' from imports
    that lacked a type column), infer Credit for known income categories.
    Checks both canonical names and common raw aliases (e.g. "Salary").
    """
    if df.empty or df["type"].nunique() > 1:
        return df
    income_cats = {c.casefold() for c in config.INCOME_CATEGORIES}
    # Also match raw aliases that the categorizer would map to income
    from src.categorizer import normalize_category
    def _is_income(cat: str) -> bool:
        low = cat.casefold()
        if low in income_cats:
            return True
        canonical = normalize_category(cat)
        return canonical is not None and canonical.casefold() in income_cats
    mask = df["category"].apply(_is_income)
    if mask.any():
        df = df.copy()
        df.loc[mask, "type"] = "Credit"
        logger.info("Corrected type to Credit for %d income-category transaction(s)", int(mask.sum()))
    return df


class DBTransactionRepository:
    """Loads transactions from the database for a given user, returning the
    same (DataFrame, LoadReport) tuple the CSV-based TransactionRepository
    produces so the rest of the pipeline works unchanged."""

    def __init__(self, db: Session, user_id: int, account_id: int | None = None):
        self.db = db
        self.user_id = user_id
        self.account_id = account_id

    def load(self) -> tuple[pd.DataFrame, LoadReport]:
        stmt = (
            select(Transaction)
            .join(FinancialAccount)
            .where(FinancialAccount.user_id == self.user_id)
        )
        if self.account_id is not None:
            stmt = stmt.where(Transaction.account_id == self.account_id)

        stmt = stmt.order_by(Transaction.date)
        rows = self.db.scalars(stmt).all()

        if not rows:
            df = pd.DataFrame(columns=[
                "transaction_id", "date", "description", "merchant",
                "category", "type", "amount", "account",
            ])
            return df, LoadReport(total_rows_in_file=0, valid_rows=0)

        records = [
            {
                "transaction_id": t.external_id,
                "date": pd.Timestamp(t.date),
                "description": t.description,
                "merchant": t.merchant,
                "category": t.category,
                "type": t.txn_type,
                "amount": float(t.amount),
                "account": t.account.name if t.account else "Unknown",
            }
            for t in rows
        ]
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])

        df = _correct_types_from_category(df)

        report = LoadReport(total_rows_in_file=len(df), valid_rows=len(df))
        logger.info("Loaded %d transactions from DB for user %d", len(df), self.user_id)
        return df, report


# ── Import record helpers ───────────────────────────────────────────────── #

def create_import_record(db: Session, user_id: int, filename: str, file_type: str) -> ImportRecord:
    rec = ImportRecord(user_id=user_id, filename=filename, file_type=file_type)
    db.add(rec)
    db.flush()
    return rec


def get_user_imports(db: Session, user_id: int) -> Sequence[ImportRecord]:
    return db.scalars(
        select(ImportRecord)
        .where(ImportRecord.user_id == user_id)
        .order_by(ImportRecord.created_at.desc())
    ).all()


# ── Subscription helpers ──────────────────────────────────────────────────── #

def get_user_plan(db: Session, user_id: int) -> str:
    """Return 'pro' if user has an active pro subscription or demo access, else 'free'."""
    plan, _ = get_user_plan_detail(db, user_id)
    return plan


def get_user_plan_detail(db: Session, user_id: int) -> tuple[str, bool]:
    """Return (plan, is_demo). plan is 'pro' or 'free'. is_demo is True when
    access comes from DEMO_USERNAMES rather than a real subscription."""
    from datetime import datetime
    # Check real subscription first
    sub = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.plan == "pro", Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
    ).first()
    if sub is not None:
        if sub.expires_at and sub.expires_at < datetime.utcnow():
            sub.status = "expired"
            db.flush()
        else:
            return "pro", sub.payment_provider == "demo"
    # Check demo access
    user = db.get(User, user_id)
    if user and user.username in config.DEMO_USERNAMES:
        return "pro", True
    return "free", False


def activate_pro(db: Session, user_id: int, payment_id: str, provider: str = "razorpay", days: int = 30) -> Subscription:
    from datetime import datetime, timedelta
    sub = Subscription(
        user_id=user_id,
        plan="pro",
        status="active",
        payment_id=payment_id,
        payment_provider=provider,
        started_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    db.add(sub)
    db.flush()
    return sub


def activate_demo(db: Session, user_id: int, activation_key: str) -> tuple[bool, str]:
    """Validate the demo activation key and grant a time-limited demo subscription.
    Returns (success, message)."""
    import hmac
    from datetime import datetime, timedelta
    if not config.DEMO_ACTIVATION_KEY:
        return False, "Demo activation is not configured on this server."
    if not hmac.compare_digest(activation_key, config.DEMO_ACTIVATION_KEY):
        return False, "Invalid activation key."
    # Check if already has active pro
    plan, is_demo = get_user_plan_detail(db, user_id)
    if plan == "pro" and not is_demo:
        return False, "You already have an active Pro subscription."
    if plan == "pro" and is_demo:
        return True, "Demo access is already active."
    sub = Subscription(
        user_id=user_id,
        plan="pro",
        status="active",
        payment_id=f"demo_{user_id}_{int(datetime.utcnow().timestamp())}",
        payment_provider="demo",
        started_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=config.DEMO_ACTIVATION_DAYS),
    )
    db.add(sub)
    db.flush()
    return True, f"Demo AI access activated for {config.DEMO_ACTIVATION_DAYS} days."


def cancel_pro(db: Session, user_id: int) -> bool:
    sub = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.plan == "pro", Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
    ).first()
    if sub:
        sub.status = "cancelled"
        db.flush()
        return True
    return False


# ── Conversation helpers ──────────────────────────────────────────────────── #

def create_conversation(db: Session, user_id: int, title: str = "New conversation") -> Conversation:
    conv = Conversation(user_id=user_id, title=title[:200])
    db.add(conv)
    db.flush()
    return conv


def get_user_conversations(db: Session, user_id: int, limit: int = 20) -> Sequence[Conversation]:
    return db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    ).all()


def get_conversation(db: Session, conversation_id: int, user_id: int) -> Conversation | None:
    conv = db.get(Conversation, conversation_id)
    if conv and conv.user_id == user_id:
        return conv
    return None


def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    intent: str | None = None,
    date_range: str | None = None,
    category: str | None = None,
) -> ConversationMessage:
    msg = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content[:10000],
        intent=intent,
        date_range=date_range,
        category=category,
    )
    db.add(msg)
    db.flush()
    conv = db.get(Conversation, conversation_id)
    if conv:
        from datetime import datetime
        conv.updated_at = datetime.utcnow()
        db.flush()
    return msg


def get_conversation_messages(db: Session, conversation_id: int, user_id: int) -> Sequence[ConversationMessage]:
    conv = get_conversation(db, conversation_id, user_id)
    if not conv:
        return []
    return db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at)
    ).all()


def delete_conversation(db: Session, conversation_id: int, user_id: int) -> bool:
    conv = get_conversation(db, conversation_id, user_id)
    if conv:
        db.delete(conv)
        db.flush()
        return True
    return False
