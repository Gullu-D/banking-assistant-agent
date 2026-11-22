"""
Streamlit session management for authentication.

Business logic (password hashing, user lookup) lives in src.services.
This module only manages Streamlit session_state — the thin bridge between
the service layer and the UI.

Security note: Streamlit session_state is server-side, tied to the browser's
websocket connection. A client cannot directly read or modify it. The session
token stored here is a defense-in-depth marker; the real session boundary is
the websocket itself. This is documented as a Streamlit limitation — it does
not support HTTP-only cookies or CSRF tokens natively.
"""

from __future__ import annotations

import re
import secrets
import threading
import time

import streamlit as st
from sqlalchemy.orm import Session

import config
from src.services import (
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_username,
)

_SESSION_KEYS = ("authenticated", "user_id", "username", "session_token")

# ── Rate limiter ─────────────────────────────────────────────────────────── #
# Module-level state survives Streamlit reruns and spans all sessions within
# the same process. It cannot be bypassed by opening a new browser tab.
# ponytail: in-memory only, resets on process restart. DB-backed if that matters.
_login_attempts: dict[str, list[float]] = {}
_rate_lock = threading.Lock()
_last_sweep: float = 0.0
_SWEEP_INTERVAL: float = 60.0


def _check_rate_limit(username: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds). Thread-safe."""
    global _last_sweep
    now = time.monotonic()
    window = config.LOGIN_LOCKOUT_SECONDS
    max_attempts = config.MAX_LOGIN_ATTEMPTS
    key = username.lower()

    with _rate_lock:
        if now - _last_sweep > _SWEEP_INTERVAL:
            _last_sweep = now
            stale = [k for k, v in _login_attempts.items()
                     if not any(now - t < window for t in v)]
            for k in stale:
                del _login_attempts[k]

        attempts = _login_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < window]
        if not attempts:
            _login_attempts.pop(key, None)
            return True, 0
        _login_attempts[key] = attempts

        if len(attempts) >= max_attempts:
            retry_after = int(window - (now - attempts[0])) + 1
            return False, retry_after
        return True, 0


def _record_failed_attempt(username: str) -> None:
    key = username.lower()
    with _rate_lock:
        _login_attempts.setdefault(key, []).append(time.monotonic())


def _clear_attempts(username: str) -> None:
    key = username.lower()
    with _rate_lock:
        _login_attempts.pop(key, None)


def is_authenticated() -> bool:
    if not (
        st.session_state.get("authenticated")
        and st.session_state.get("session_token")
        and st.session_state.get("user_id")
    ):
        return False
    created = st.session_state.get("session_created_at")
    if created and (time.time() - created) > config.SESSION_LIFETIME_SECONDS:
        logout()
        return False
    return True


def get_current_user_id() -> int | None:
    if is_authenticated():
        return st.session_state["user_id"]
    return None


def get_current_username() -> str:
    return st.session_state.get("username", "")


def login(db: Session, username: str, password: str) -> tuple[bool, str]:
    allowed, retry_after = _check_rate_limit(username)
    if not allowed:
        return False, f"Too many login attempts. Try again in {retry_after} seconds."

    user = authenticate_user(db, username, password)
    if not user:
        _record_failed_attempt(username)
        return False, "Invalid username or password."

    _clear_attempts(username)
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    st.session_state["session_token"] = secrets.token_hex(32)
    st.session_state["session_created_at"] = time.time()
    return True, ""


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def register(db: Session, username: str, email: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    email = email.strip()

    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(username) > 80:
        return False, "Username must be at most 80 characters."
    if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
        return False, "Username may only contain letters, numbers, dots, hyphens, and underscores."
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Please enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    if get_user_by_username(db, username):
        return False, "Username is already taken."
    if get_user_by_email(db, email):
        return False, "An account with this email already exists."

    create_user(db, username, email, password)
    return True, ""
