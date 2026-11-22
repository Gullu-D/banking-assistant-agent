"""
Central configuration for the Banking Assistant Agent.

All secrets/config come from environment variables (loaded from a local
.env file via python-dotenv, if present). Nothing is hard-coded.

Supported LLM providers (optional — the app works without either):
  - OpenAI-compatible APIs: set OPENAI_API_KEY (and optionally OPENAI_MODEL,
    OPENAI_BASE_URL for OpenAI-compatible endpoints).
  - Google Gemini: set GOOGLE_API_KEY (and optionally GEMINI_MODEL).

If neither key is present, the application automatically runs in
deterministic FALLBACK MODE: rule-based query parsing and template-based
summaries. Every calculation is deterministic regardless of which mode is
active — only natural-language understanding and prose generation are
affected.
"""

from __future__ import annotations

import os
import logging

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a listed dependency
    pass


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# --------------------------------------------------------------------------- #
# LLM provider configuration
# --------------------------------------------------------------------------- #
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

# Ollama (local LLM)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2").strip()

# Explicit provider override: "auto" (default) picks the first available,
# or force one of "ollama", "openai", "gemini".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()

LLM_REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "20"))


_ollama_cache: dict = {"up": None, "models": None, "ts": 0.0}
_OLLAMA_CACHE_TTL = 30  # seconds

def _ollama_tags() -> dict | None:
    """Fetch /api/tags with a short TTL cache so hot paths stay fast."""
    import time, urllib.request, json as _json
    now = time.monotonic()
    if now - _ollama_cache["ts"] < _OLLAMA_CACHE_TTL and _ollama_cache["up"] is not None:
        return _ollama_cache["models"] if _ollama_cache["up"] else None
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1) as resp:
            data = _json.loads(resp.read())
        _ollama_cache.update(up=True, models=data, ts=now)
        return data
    except Exception:
        _ollama_cache.update(up=False, models=None, ts=now)
        return None


def _check_ollama_available() -> bool:
    return _ollama_tags() is not None


def _check_ollama_model_installed() -> bool:
    data = _ollama_tags()
    if data is None:
        return False
    installed = {m.get("name", "") for m in data.get("models", [])}
    target = OLLAMA_MODEL if ":" in OLLAMA_MODEL else f"{OLLAMA_MODEL}:latest"
    return target in installed


def check_ollama() -> tuple[bool, bool, str]:
    """Return (server_up, model_installed, message)."""
    if not _check_ollama_available():
        return False, False, (
            f"Ollama server not reachable at {OLLAMA_BASE_URL}. "
            f"Install from https://ollama.com and run: ollama serve"
        )
    if not _check_ollama_model_installed():
        return True, False, (
            f"Ollama is running but model '{OLLAMA_MODEL}' is not installed. "
            f"Run: ollama pull {OLLAMA_MODEL}"
        )
    return True, True, f"Ollama ready — model: {OLLAMA_MODEL}"


def active_llm_provider() -> str | None:
    """Return which LLM provider is configured, or None for fallback mode.

    When LLM_PROVIDER is "auto": Ollama (if reachable) → OpenAI → Gemini → None.
    Otherwise uses the explicitly requested provider.
    """
    if LLM_PROVIDER in ("none", "off", "disabled"):
        return None
    if LLM_PROVIDER == "ollama":
        return "ollama" if _check_ollama_available() else None
    if LLM_PROVIDER == "openai":
        return "openai" if OPENAI_API_KEY else None
    if LLM_PROVIDER == "gemini":
        return "gemini" if GOOGLE_API_KEY else None
    # auto: try in order
    if _check_ollama_available():
        return "ollama"
    if OPENAI_API_KEY:
        return "openai"
    if GOOGLE_API_KEY:
        return "gemini"
    return None


def llm_is_available() -> bool:
    return active_llm_provider() is not None


def llm_status() -> tuple[str, str]:
    """Return (status, message) for the current LLM provider state.
    status is one of: 'active', 'credits_exhausted', 'unavailable'.
    """
    provider = active_llm_provider()
    if provider is None:
        if LLM_PROVIDER == "ollama":
            _, _, msg = check_ollama()
            return "unavailable", msg
        return "unavailable", "No LLM provider available. Set OPENAI_API_KEY, GOOGLE_API_KEY, or install Ollama."
    if provider == "ollama":
        server_up, model_ok, msg = check_ollama()
        if not model_ok:
            return "unavailable", msg
        return "active", f"LLM provider: ollama (local) — {OLLAMA_MODEL}"
    import src.query_parser as qp
    import src.summarizer as sm
    import time
    now = time.monotonic()
    if now < qp._llm_disabled_until or now < sm._llm_disabled_until:
        return "credits_exhausted", f"LLM provider ({provider}) has no credits. Deterministic analysis is active."
    return "active", f"LLM provider: {provider}"


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

_DEFAULT_SECRET = "change-me-in-production"
if DATABASE_URL and (SECRET_KEY == _DEFAULT_SECRET or len(SECRET_KEY) < 16):
    raise RuntimeError(
        "SECRET_KEY is the default value or too short, but DATABASE_URL is set "
        "(production mode). Set a strong, unique SECRET_KEY (>= 16 chars) in your .env."
    )
if SECRET_KEY == _DEFAULT_SECRET:
    logging.getLogger(__name__).warning(
        "SECRET_KEY is the default value. Set a strong, unique SECRET_KEY "
        "before deploying to production."
    )

# --------------------------------------------------------------------------- #
# Auth / rate-limiting
# --------------------------------------------------------------------------- #
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "300"))
SESSION_LIFETIME_SECONDS = int(os.getenv("SESSION_LIFETIME_SECONDS", str(24 * 3600)))

# --------------------------------------------------------------------------- #
# Data configuration
# --------------------------------------------------------------------------- #
DATA_DIR = os.getenv("DATA_DIR", "data")
TRANSACTIONS_CSV_PATH = os.getenv("TRANSACTIONS_CSV_PATH", os.path.join(DATA_DIR, "transactions.csv"))

REQUIRED_COLUMNS = [
    "transaction_id",
    "date",
    "description",
    "merchant",
    "category",
    "type",
    "amount",
    "account",
]

VALID_CATEGORIES = [
    "Food & Dining",
    "Shopping",
    "Travel",
    "Rent",
    "Utilities",
    "Healthcare",
    "Education",
    "Entertainment",
    "Groceries",
    "Investments",
    "Transfers",
    "Salary / Income",
    "ATM / Cash Withdrawal",
    "Freelance",
    "Interest",
    "Refund",
    "Other",
]

# Categories that represent money coming IN rather than spending. Used to
# separate "spending" analysis from "income" analysis and to correct
# txn_type when the source data lacks a reliable type column.
INCOME_CATEGORIES = {"Salary / Income", "Freelance", "Interest", "Refund"}

VALID_TYPES = ["Debit", "Credit"]

# --------------------------------------------------------------------------- #
# Anomaly detection configuration
# --------------------------------------------------------------------------- #
# Number of standard deviations above the mean that defines a statistical
# anomaly. 2.0 is a common, defensible default (~97.7th percentile for a
# roughly normal distribution).
ANOMALY_STD_MULTIPLIER = float(os.getenv("ANOMALY_STD_MULTIPLIER", "2.0"))

# Two transactions are considered "duplicate-looking" if they share the same
# merchant, an amount within this tolerance, and occur within this many days
# of each other.
DUPLICATE_AMOUNT_TOLERANCE = float(os.getenv("DUPLICATE_AMOUNT_TOLERANCE", "0.01"))  # 1%
DUPLICATE_DATE_WINDOW_DAYS = int(os.getenv("DUPLICATE_DATE_WINDOW_DAYS", "3"))

# "Rapid repeated large transactions": N or more transactions, each above the
# large-transaction percentile, within this many days of each other.
RAPID_WINDOW_DAYS = int(os.getenv("RAPID_WINDOW_DAYS", "2"))
RAPID_MIN_COUNT = int(os.getenv("RAPID_MIN_COUNT", "3"))
RAPID_LARGE_PERCENTILE = float(os.getenv("RAPID_LARGE_PERCENTILE", "0.75"))

# --------------------------------------------------------------------------- #
# Subscription / Pro plan
# --------------------------------------------------------------------------- #
PRO_MONTHLY_PRICE_INR = int(os.getenv("PRO_MONTHLY_PRICE_INR", "299"))
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()

# --------------------------------------------------------------------------- #
# Demo access (for college viva presentations)
# --------------------------------------------------------------------------- #
# Set DEMO_USERNAMES to a comma-separated list of usernames that get Pro
# features without a real subscription. These accounts will show "(Demo)" in
# the plan badge. Never represents a genuine paid subscription.
DEMO_USERNAMES = [u.strip() for u in os.getenv("DEMO_USERNAMES", "").split(",") if u.strip()]

# Set DEMO_ACTIVATION_KEY to a secret key that unlocks demo Pro access from
# the UI. Users who enter this key get a 7-day demo subscription. Leave empty
# to disable the UI activation flow entirely.
DEMO_ACTIVATION_KEY = os.getenv("DEMO_ACTIVATION_KEY", "").strip()
DEMO_ACTIVATION_DAYS = int(os.getenv("DEMO_ACTIVATION_DAYS", "7"))

# --------------------------------------------------------------------------- #
# App metadata
# --------------------------------------------------------------------------- #
APP_NAME = "Banking Assistant Agent"
APP_TAGLINE = "AI-assisted transaction analysis — synthetic demo data only"
CURRENCY_SYMBOL = "₹"
