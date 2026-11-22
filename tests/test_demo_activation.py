"""Tests for demo AI activation flow."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.services import create_user, get_default_account, get_user_plan, get_user_plan_detail, activate_demo, cancel_pro
import config


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user(db):
    u = create_user(db, "demo_tester", "demo@test.com", "TestPass123!")
    db.commit()
    return u


class TestDemoActivation:
    def test_valid_key_activates_demo(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "test-secret-key"):
            ok, msg = activate_demo(db, user.id, "test-secret-key")
            db.commit()
        assert ok is True
        assert "activated" in msg.lower()
        plan, is_demo = get_user_plan_detail(db, user.id)
        assert plan == "pro"
        assert is_demo is True

    def test_invalid_key_rejected(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "correct-key"):
            ok, msg = activate_demo(db, user.id, "wrong-key")
        assert ok is False
        assert "invalid" in msg.lower()
        assert get_user_plan(db, user.id) == "free"

    def test_empty_key_rejected(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "correct-key"):
            ok, msg = activate_demo(db, user.id, "")
        assert ok is False

    def test_activation_disabled_when_no_key_configured(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", ""):
            ok, msg = activate_demo(db, user.id, "any-key")
        assert ok is False
        assert "not configured" in msg.lower()

    def test_already_demo_returns_success(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "key123"):
            activate_demo(db, user.id, "key123")
            db.commit()
            ok, msg = activate_demo(db, user.id, "key123")
        assert ok is True
        assert "already active" in msg.lower()

    def test_demo_subscription_has_expiry(self, db, user):
        from datetime import datetime
        with patch.object(config, "DEMO_ACTIVATION_KEY", "key123"):
            ok, _ = activate_demo(db, user.id, "key123")
            db.commit()
        assert ok is True
        from sqlalchemy import select
        from src.models import Subscription
        sub = db.scalars(
            select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
        ).first()
        assert sub is not None
        assert sub.payment_provider == "demo"
        assert sub.expires_at is not None
        assert sub.expires_at > datetime.utcnow()

    def test_demo_shows_as_demo_not_paid(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "key123"):
            activate_demo(db, user.id, "key123")
            db.commit()
        plan, is_demo = get_user_plan_detail(db, user.id)
        assert plan == "pro"
        assert is_demo is True

    def test_cancel_demo_reverts_to_free(self, db, user):
        with patch.object(config, "DEMO_ACTIVATION_KEY", "key123"):
            activate_demo(db, user.id, "key123")
            db.commit()
        cancel_pro(db, user.id)
        db.commit()
        assert get_user_plan(db, user.id) == "free"

    def test_timing_attack_resistant(self, db, user):
        """activate_demo uses hmac.compare_digest, not ==."""
        import inspect
        from src.services import activate_demo as fn
        source = inspect.getsource(fn)
        assert "compare_digest" in source
