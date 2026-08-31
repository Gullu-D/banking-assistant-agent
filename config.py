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

LLM_REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "20"))


def active_llm_provider() -> str | None:
    """Return which LLM provider is configured, or None for fallback mode.

    OpenAI takes priority if both keys happen to be set.
    """
    if OPENAI_API_KEY:
        return "openai"
    if GOOGLE_API_KEY:
        return "gemini"
    return None


def llm_is_available() -> bool:
    return active_llm_provider() is not None


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
    "Other",
]

# Categories that represent money coming IN rather than spending. Used to
# separate "spending" analysis from "income" analysis.
INCOME_CATEGORIES = {"Salary / Income"}

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
# App metadata
# --------------------------------------------------------------------------- #
APP_NAME = "Banking Assistant Agent"
APP_TAGLINE = "AI-assisted transaction analysis — synthetic demo data only"
CURRENCY_SYMBOL = "₹"
