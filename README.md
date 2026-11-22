# 🏦 Banking Assistant Agent

An AI-assisted transaction analysis agent that answers natural-language banking questions
against a synthetic transaction dataset — with **all financial math performed
deterministically in Python/Pandas**, and an **optional LLM used only for language
understanding and prose summaries**.

> ⚠️ **This project uses 100% synthetic, fictional transaction data.** It does not connect
> to any real bank account and is not a financial advisor. See [Limitations](#limitations).

---

## Overview

Ask a question like:

> *"Show all transactions above ₹50,000 from last month and summarize my spending."*

...and the agent will parse your intent, pull the right transactions, categorize and total
them, flag anything statistically unusual, and generate a plain-English summary — all
backed by a modern fintech-style Streamlit dashboard.

The project is built to be evaluated, not just demoed: every calculation is unit-tested,
every failure mode (missing files, bad data, unparseable queries, LLM outages) is handled
explicitly, and no number shown to the user is ever invented by an LLM.

## Features

- **User authentication** — registration, login, logout with bcrypt password hashing and
  server-side session management. Every financial page requires authentication.
- **Per-user data isolation** — transactions, accounts, and imports are scoped to the
  authenticated user in the service/repository layer, not just the UI.
- **CSV/XLSX import** — upload files, preview data, map columns, validate rows, detect
  duplicates, and persist to the database with full import history.
- **Natural-language query understanding** — LLM-assisted (OpenAI or Gemini) with a
  dependency-free deterministic regex/keyword parser as both the fallback and the
  no-API-key default.
- **Deterministic filtering & math** — every total, average, min/max, and percentage is
  computed with Pandas/NumPy. The LLM never touches the dataframe.
- **Automatic categorization** — normalizes known categories and infers missing ones from
  merchant/description keywords.
- **Transparent anomaly detection** — statistical outliers (mean + *k*·σ), duplicate-looking
  charges, and rapid bursts of large transactions, each with a plain-English reason.
- **AI-assisted summaries, numerically grounded** — the summary LLM receives only
  already-computed figures, and its output is checked for invented numbers before being
  shown; falls back to a template summary otherwise.
- **Multi-agent orchestration foundation** — typed tool interfaces wrapping each pipeline
  stage (load, analyze, detect anomalies, summarize), user-scoped, with deterministic
  fallback on provider failure.
- **Professional financial dashboard** — Overview page with date-range selectors, period
  comparisons, 4 KPI cards with delta indicators, interactive Plotly charts (income vs
  expenses, spending by category, top merchants, monthly cash flow). Transactions page
  with filters, sorting, search, and pagination. Deterministic Insights page. AI Assistant
  page for natural-language queries. Dark sidebar with live AI/data status.
- **Conversational AI assistant** — Follow-up questions with session-scoped context,
  specialized agents for trend analysis, period comparison, and financial insights, all
  backed by deterministic analytics. Context is isolated per authenticated user/session.
- **Multi-currency support** — account-level currency (INR, GBP, USD, EUR). Indian digit
  grouping (₹1,25,000) for INR, Western grouping (£125,000) for others. Currency flows
  through the entire pipeline from database to UI.
- **Fully tested** — 325 automated tests across 24 test files covering filters, analytics,
  anomaly detection, query parsing, authentication, import validation, user isolation,
  orchestration, rate limiting, session expiry, dashboard analytics, conversational context,
  follow-up resolution, specialized agents, financial accuracy, adversarial cross-user
  attack paths, and regression tests.

## Architecture

```text
                    USER
                      │
                  ┌───┴───┐
              Login/Register
                      │
                      ▼
              Streamlit Web Dashboard (authenticated)
                      │
               ┌──────┼──────┐
          Overview    │   Import Data
        AI Assistant  │      │
               │      ▼      ▼
         NL Query  Browse  CSV/XLSX Upload
               │             │
               ▼             ▼
     Orchestrator      Importer (validate → dedup → persist)
               │
               ▼
  ┌─ Parse Query (LLM or deterministic)
  ├─ Load Transactions (DB-backed, user-scoped)
  ├─ Filter (Pandas)
  ├─ Categorize
  ├─ Calculate (deterministic)
  ├─ Detect Anomalies (statistical + rule-based)
  └─ Generate Summary (LLM or template fallback)
               │
               ▼
       Results + Insights → Dashboard
```

## Technology Stack

| Layer            | Technology                                            |
|-------------------|--------------------------------------------------------|
| Backend / core     | Python 3.12+, Pandas, NumPy, Pydantic, `logging`       |
| Database           | PostgreSQL (production) / SQLite (dev/test), SQLAlchemy, Alembic |
| Auth               | bcrypt password hashing, Streamlit session state        |
| AI (optional)      | Ollama (local), OpenAI-compatible API, or Google Gemini |
| Frontend           | Streamlit + custom CSS, Plotly charts                  |
| Testing            | pytest (325 tests across 24 files)                     |

No API keys or secrets are hard-coded — see [Environment Variables](#environment-variables).

## Project Structure

```text
banking-assistant-agent/
│
├── app.py                       # Streamlit dashboard (auth + presentation)
├── agent.py                     # Legacy agent (preserved for backward compat)
├── config.py                    # Env-based configuration
├── requirements.txt
├── alembic.ini                  # Alembic config
│
├── alembic/
│   ├── env.py                   # Migration environment
│   └── versions/                # Migration scripts
│
├── data/
│   ├── transactions.csv               # Synthetic demo dataset
│   ├── transactions_dirty_sample.csv  # Malformed sample for tests
│   └── generate_transactions.py       # Reproducible generator
│
├── src/
│   ├── database.py              # SQLAlchemy engine, session, Base
│   ├── models.py                # User, FinancialAccount, Transaction, ImportRecord
│   ├── services.py              # Service layer (user CRUD, DB repo, auth helpers)
│   ├── auth.py                  # Streamlit session management
│   ├── importer.py              # CSV/XLSX import pipeline
│   ├── orchestrator.py          # Multi-agent orchestration foundation
│   ├── data_loader.py           # CSV-based TransactionRepository (legacy)
│   ├── query_parser.py          # NL → StructuredQuery
│   ├── date_utils.py            # Date-range resolution
│   ├── filters.py               # Deterministic Pandas filtering
│   ├── categorizer.py           # Category normalization / inference
│   ├── analytics.py             # Deterministic totals, averages, breakdowns
│   ├── anomaly_detector.py      # Statistical + rule-based anomaly detection
│   ├── summarizer.py            # AI / template summary generation
│   ├── formatting.py            # Multi-currency formatting (INR/GBP/USD/EUR)
│   ├── agents.py                # 7 specialist agent functions
│   ├── tool_result.py           # Shared ToolResult dataclass
│   └── validators.py            # Pydantic schemas
│
├── tests/
│   ├── test_auth.py             # Registration, login, logout, session, validation
│   ├── test_importer.py         # CSV/XLSX import, column mapping, dedup, rollback
│   ├── test_orchestrator.py     # Routing, fallback, user isolation
│   ├── test_isolation.py        # Cross-user data access prevention
│   ├── test_db_models.py        # DB models, services, relationships
│   ├── test_data_loader.py      # CSV loading and validation
│   ├── test_filters.py          # Amount/date/category filtering
│   ├── test_analytics.py        # Statistics and breakdowns
│   ├── test_anomalies.py        # Anomaly detection
│   ├── test_query_parser.py     # Query parsing (LLM + deterministic)
│   ├── test_categorizer.py      # Category normalization
│   ├── test_summarizer.py       # Summary generation and grounding
│   ├── test_format_inr.py       # Indian currency formatting
│   ├── test_dashboard.py         # Phase 3 analytics, insights, period comparison
│   ├── test_phase4.py            # Conversational AI, agents, follow-ups, context
│   ├── test_phase6.py            # Import rollback, email validation, negative amounts
│   ├── test_agent.py            # Agent integration
│   ├── test_llm_mocks.py        # Mocked LLM provider tests
│   ├── test_financial_accuracy.py  # Expense/income separation, exact totals
│   ├── test_ollama.py           # Ollama provider tests
│   └── test_ui_helpers.py       # UI formatting helpers
│
├── docs/
│   └── viva/                    # Teacher/viva preparation (7 files)
│
└── .env.example
```

## Setup

```bash
git clone <repository>
cd banking-assistant-agent

python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Database Setup

The app uses **SQLite by default** (auto-created at `data/banking.db`) — no setup needed.

For **PostgreSQL** (recommended for production — **not verified locally**):

```bash
# Create database
createdb banking_agent

# Set in .env
DATABASE_URL=postgresql://user:password@localhost:5432/banking_agent
```

Run migrations:

```bash
alembic upgrade head
```

### Environment Variables

Copy `.env.example` to `.env` and fill in only what you want:

```bash
cp .env.example .env
```

```text
# Database (leave blank for SQLite)
DATABASE_URL=
SECRET_KEY=change-me-in-production

# LLM — all optional; app works without any of them
# Option A: Ollama (local, free, no API key)
#   Install from https://ollama.com, then: ollama serve && ollama pull llama3.2:1b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
LLM_PROVIDER=auto

# Option B: OpenAI
OPENAI_API_KEY=

# Option C: Google Gemini
GOOGLE_API_KEY=
```

**All are optional.** With no keys set, the app runs fully in **deterministic fallback mode**.
With Ollama running locally, AI Mode activates automatically (no API key needed).

## Run

```bash
streamlit run app.py
```

Then open `http://localhost:8501`, register an account, and import transactions.

## Testing

```bash
pytest -q
```

**325 tests** covering:

- Authentication: registration, duplicate handling, login, logout, session state, password hashing, input validation, rate limiting, session expiry
- Authorization: cross-user access attempts against accounts, transactions, imports, fabricated user IDs, direct account ID manipulation
- Import: valid/invalid/empty/malformed files, column mapping, date/amount parsing, duplicate detection, accurate counts, rollback, savepoint atomicity, negative-amount rejection
- Orchestrator: routing, schema validation, deterministic fallback, user isolation
- Conversational AI: intent routing (trend, comparison, insights), specialized agents, follow-up resolution, context isolation, conversation history limits, direct answers, error handling
- Analytics: filtering boundaries, statistics, category breakdowns, anomaly detection
- Dashboard: income/expense time series, top merchants, period comparison, insights generation, edge cases (zero income, single-day range, debit-only periods)
- Query parsing: multiple phrasings, Indian currency, operators, LLM and deterministic paths, ambiguous phrases ("more than last month", "over time")
- Data loading: valid/corrupt/missing CSV, row skipping, error hierarchy

All tests use in-memory SQLite — no external database required.

## Authentication & Session Management

- Passwords are hashed with **bcrypt** (never stored in plaintext).
- Registration validates username format (alphanumeric, 3-80 chars), email (must have
  user@domain.tld structure), and password length (minimum 8 characters).
- Login returns a server-generated session token stored in `st.session_state`.
- **Rate limiting** — configurable per-username throttling (default: 5 attempts / 5 min
  lockout). Survives Streamlit reruns and spans all sessions within the process. Cannot be
  bypassed by opening new tabs.
- **Session expiry** — sessions expire after a configurable lifetime (default: 24 hours).
- **SECRET_KEY validation** — the app refuses to start with the default secret when
  `DATABASE_URL` is set (production mode). In dev mode it logs a warning.
- Logout clears all session state.
- Every financial page checks authentication before rendering.
- Data access is enforced in the **service/repository layer** (not just the UI) — the
  `DBTransactionRepository` always filters by `user_id`, and import operations verify
  account ownership.
- **XSS protection** — user-imported data (merchant names, categories) is HTML-escaped
  before rendering in `unsafe_allow_html` contexts.

**Streamlit limitation:** Streamlit's `session_state` is server-side and tied to the
WebSocket connection. It does not support HTTP-only cookies or CSRF tokens natively. The
session token is a defense-in-depth marker; the real session boundary is the WebSocket.
Rate limiting is in-memory (resets on process restart) — a database-backed implementation
is the upgrade path if multi-worker deployment is needed.

## Import Behavior

- Supported formats: **CSV**, **XLSX** (via openpyxl).
- Max file size: 10 MB.
- Auto-detects common column names (`date`, `amount`, `merchant`, `transaction_date`, `amt`, `payee`, etc.).
- Manual column mapping UI for non-standard headers.
- Validates dates, amounts, and transaction types row-by-row.
- **Duplicate detection**: a row is a duplicate if the user already has a transaction with the same date, merchant (case-insensitive), amount (exact to the cent), and transaction type.
- Reports imported / skipped / duplicate counts with warnings.
- All operations run in a database transaction with savepoint-based atomicity —
  partial failures roll back without committing incomplete data.
- Imported records feed the existing analytics pipeline immediately.
- Uploaded content is never executed (no formula evaluation, no macros).

## Anomaly Detection

Three explicit, auditable methods — never "ask the LLM to find anomalies":

1. **Statistical outliers** — amount > mean + k·σ
2. **Duplicate-looking transactions** — same merchant, near-identical amount, close dates
3. **Rapid repeated large transactions** — several large charges in a short window

## Limitations

- Uses **synthetic, fictional transaction data only** — no real bank connectivity.
- Anomaly detection is statistical/rule-based, not a fraud-detection system.
- Streamlit does not support HTTP-only session cookies or CSRF tokens.
- PostgreSQL recommended for production; SQLite is for development and testing.
- Razorpay payment gateway is configured but keys are not set — the subscription
  system is demo-only.

## Dataset

The project ships with a small synthetic INR dataset (`data/transactions.csv`) for
development. For the full GBP demo, import the MoneyData personal finance dataset:

1. Download from [Kaggle: MoneyData – UK Personal Finance Dataset](https://www.kaggle.com/datasets/laramee26/moneydata) (free, requires Kaggle account)
2. Log in as `moneydata_demo` and use the Data Center import page to upload the CSV
3. The system auto-maps columns and sets the account currency to GBP

Do not redistribute the MoneyData workbook without checking its licence terms on Kaggle.

## Documentation

Full teacher/viva preparation materials are in [`docs/viva/`](docs/viva/):

1. **Architecture** — system design, pipeline diagram, intent routing
2. **Database** — all 7 tables, ER diagram, migrations, user isolation
3. **Features** — auth, dashboard, import, anomaly detection, AI assistant
4. **Demo Script** — 10–15 minute walkthrough with exact queries
5. **Viva Questions** — 60 Q&A across 9 technical categories
6. **Limitations** — implemented vs demo-only vs future work
7. **Demo Checklist** — pre-demo, during-demo, and post-demo checklists

---

*This is a demo/educational project. It is not affiliated with, and does not represent,
any real bank or financial institution.*
