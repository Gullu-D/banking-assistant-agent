# Viva Explanation & Architecture Guide

---

## 1. Application Architecture & Data Flow

```
User (Browser)
    │
    ▼
Streamlit Web App (app.py)
    │
    ├─── Auth layer (src/auth.py)
    │       └── bcrypt hashing, rate limiting, session tokens
    │
    ├─── Import pipeline (src/importer.py)
    │       └── CSV/XLSX → validate → dedup → savepoint insert
    │
    └─── AI Assistant query flow:
            │
            ▼
        Query Parser (src/query_parser.py)
            │  LLM (optional) or deterministic regex/keyword parser
            │  Output: StructuredQuery (Pydantic-validated)
            ▼
        Orchestrator (src/orchestrator.py)
            │  Routes by intent to the right tool/agent
            ├── tool_load_transactions  → DBTransactionRepository (user-scoped)
            ├── tool_analyze_transactions → Filters + Analytics (Pandas/NumPy)
            ├── tool_detect_anomalies   → Statistical + rule-based detection
            ├── tool_generate_summary   → LLM prose or template fallback
            │
            │  Specialized agents (for trend/comparison/insights intents):
            ├── agent_trend_analysis    → month-over-month income/expense
            ├── agent_period_comparison → current vs prior period stats
            └── agent_insights          → deterministic spending patterns
            │
            ▼
        Results → Dashboard rendering (Streamlit + Plotly)
```

**Key principle:** The LLM is used only for (a) understanding natural
language and (b) generating prose summaries of already-computed numbers. All
financial calculations are deterministic Python (Pandas/NumPy).

---

## 2. Database Models & Migrations

**Four SQLAlchemy ORM models** in `src/models.py`:

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | Username, email (unique), bcrypt password hash, active flag |
| `FinancialAccount` | `financial_accounts` | Per-user account (auto-created on registration) |
| `Transaction` | `transactions` | Date, merchant, category, amount, type (Debit/Credit) |
| `ImportRecord` | `import_records` | Upload history: filename, row counts, status |

**Relationships:**
- User → has many FinancialAccounts (cascade delete)
- User → has many ImportRecords (cascade delete)
- FinancialAccount → has many Transactions (cascade delete)
- ImportRecord → has many Transactions (SET NULL on delete)

**Database engine** (`src/database.py`):
- SQLite in dev/test (auto-created at `data/banking.db`)
- PostgreSQL supported via `DATABASE_URL` environment variable
- WAL mode and `PRAGMA foreign_keys=ON` enabled via SQLAlchemy event listener
- `get_db()` context manager: commits on success, rollbacks on exception

**Migrations:**
- Alembic with a single initial migration (`d1b0c82c90a1`)
- `alembic upgrade head` creates the schema from scratch

---

## 3. Authentication & User Isolation

**Registration** (`src/auth.py:register`):
1. Validates username (letters, numbers, underscores, dots, hyphens; 3–80 chars via regex)
2. Validates email (`^[^@\s]+@[^@\s]+\.[^@\s]+$` regex)
3. Validates password (≥8 characters)
4. Checks username/email uniqueness against the database
5. Creates `User` + default `FinancialAccount` in one transaction

**Login** (`src/auth.py:login`):
1. Checks rate limiting (5 attempts / 5-minute lockout per username)
2. Verifies password against bcrypt hash (`src/services.authenticate_user`)
3. Sets `st.session_state` with user_id, username, and a `secrets.token_hex(32)` session token

**Session management:**
- Server-side only (Streamlit session_state, WebSocket-bound)
- 24-hour expiry (configurable)
- Logout clears all session state keys

**User isolation:**
- `DBTransactionRepository` always joins `Transaction → FinancialAccount` and filters by `user_id`
- Import operations verify `account.user_id == user_id` before inserting
- No API endpoint or service function accepts raw `account_id` without ownership verification

---

## 4. Import Validation & Duplicate Detection

**Pipeline** (`src/importer.py:run_import`):

```
Upload → read_upload() → auto_map_columns() → _validate_and_normalize()
    → _find_duplicates() → db.begin_nested() → insert → commit/rollback
```

1. **File validation:** type check (CSV/XLSX only), size check (≤10 MB), parse with pandas
2. **Column mapping:** auto-detects 22+ column name aliases → internal names
3. **Row validation** (`_validate_and_normalize`):
   - Date: `pd.Timestamp` parsing (returns None on failure → skip)
   - Amount: strips ₹/Rs./INR/commas, `float()`, must be ≥ 0
   - Negative amounts: skipped with a specific warning message
   - Type: normalizes to "Debit" or "Credit" (defaults to Debit)
4. **Duplicate detection** (`_find_duplicates`): matches (date, merchant lowercase, amount exact, type) against existing user transactions
5. **Atomic insert:** wrapped in `db.begin_nested()` (savepoint). On failure, the savepoint rolls back all inserted transactions but the `ImportRecord` survives with `status="failed"`.

---

## 5. Orchestrator & Specialist Agents

**Orchestrator** (`src/orchestrator.py:Orchestrator.run`):

1. Parses user query → `StructuredQuery`
2. If conversation context exists, resolves follow-ups (inherits date range/category from prior turn)
3. Loads transactions from DB (user-scoped)
4. Routes by intent:

| Intent | Handler | What It Does |
|--------|---------|-------------|
| `trend_analysis` | `agent_trend_analysis()` | Month-over-month income/expense, top merchants |
| `period_comparison` | `agent_period_comparison()` | Current vs previous equivalent period |
| `insights_query` | `agent_insights()` | Largest category, expense-to-income ratio, frequent merchants |
| All others | Main pipeline | Filter → Analyze → Detect anomalies → Summarize |

**Main pipeline tools:**
- `tool_load_transactions` — loads from DB via `DBTransactionRepository`
- `tool_analyze_transactions` — applies filters, computes statistics, category breakdown, time series
- `tool_detect_anomalies` — three detection methods (see section below)
- `tool_generate_summary` — LLM prose (with numeric grounding check) or template fallback

**Conversation context** (`ConversationContext`):
- In-memory per session, stores query metadata (not financial data)
- Capped at 10 turns
- Follow-up detection via keyword patterns ("what about", "same for", etc.)

---

## 6. Deterministic vs LLM-Powered

| Component | Deterministic (always) | LLM-powered (optional) |
|-----------|----------------------|----------------------|
| Query parsing | Regex/keyword parser → `StructuredQuery` | LLM extracts intent/params → same `StructuredQuery` (Pydantic-validated) |
| Filtering | Pandas boolean masks | — |
| Statistics | Pandas `.sum()`, `.mean()`, `.groupby()` | — |
| Category breakdown | Pandas groupby + percentage calculation | — |
| Anomaly detection | Statistical (mean+kσ), duplicate-like, rapid burst | — |
| Period comparison | Pandas date masking + OverallStatistics | — |
| Trend analysis | `income_expense_over_time()`, `top_merchants()` | — |
| Summary generation | Template-based (fill-in-the-blank) | LLM generates prose from pre-computed `AnalysisSummaryInput` (grounding-checked) |
| INR formatting | `format_inr()` — Indian digit grouping | — |

**Grounding check** (`src/summarizer.py`): Every number in an LLM-generated
summary is verified against the numbers in the input payload. If any number
doesn't match (within 2% tolerance), the summary is replaced with the
deterministic template. The LLM never invents figures.

---

## 7. Anomaly Detection Methods

All three methods operate on Debit (spending) transactions only.

| Method | Logic | Config |
|--------|-------|--------|
| **Statistical outlier** | amount > mean + k·σ | `ANOMALY_STD_MULTIPLIER=2.0` |
| **Duplicate-looking** | Same merchant, amount within 1%, within 3 days | `DUPLICATE_AMOUNT_TOLERANCE=0.01`, `DUPLICATE_DATE_WINDOW_DAYS=3` |
| **Rapid burst** | ≥3 transactions above 75th percentile within 2 days | `RAPID_MIN_COUNT=3`, `RAPID_LARGE_PERCENTILE=0.75`, `RAPID_WINDOW_DAYS=2` |

ATM/Cash Withdrawal transactions are excluded from duplicate and rapid-burst
checks (they are legitimately repetitive) but still checked for statistical
outliers.

---

## 8. Key File Map

| Area | File | Lines |
|------|------|-------|
| **Web app / UI** | `app.py` | 1266 |
| **Config** | `config.py` | 166 |
| **Database engine** | `src/database.py` | 69 |
| **ORM models** | `src/models.py` | 117 |
| **Service layer** | `src/services.py` | 145 |
| **Authentication** | `src/auth.py` | 155 |
| **Import pipeline** | `src/importer.py` | 327 |
| **Orchestrator** | `src/orchestrator.py` | 528 |
| **Query parser** | `src/query_parser.py` | 352 |
| **Pydantic schemas** | `src/validators.py` | 195 |
| **Filters** | `src/filters.py` | 107 |
| **Analytics** | `src/analytics.py` | 213 |
| **Anomaly detection** | `src/anomaly_detector.py` | 211 |
| **Summarizer** | `src/summarizer.py` | 220 |
| **INR formatting** | `src/formatting.py` | 30 |
| **Date utilities** | `src/date_utils.py` | 80 |
| **Categorizer** | `src/categorizer.py` | 147 |
| **Tests (Phase 6)** | `tests/test_phase6.py` | 246 |

---

## 9. Current Limitations & Future Extensions

**Current limitations:**
- Single-currency (INR) — only Indian Rupee formatting
- SQLite for development only — no concurrent write safety
- Rate limiting is in-memory — resets on process restart
- Streamlit session management — no HTTP-only cookies or CSRF tokens
- PostgreSQL production path — supported but not verified locally
- No real bank connectivity — synthetic data only

**Realistic future extensions:**
- Multi-currency support with exchange rate API
- Database-backed rate limiting for multi-worker deployment
- Budget tracking with user-defined category limits
- Recurring transaction detection (subscriptions, EMIs)
- Export to CSV/PDF
- PostgreSQL deployment with proper connection pooling
- OAuth/SSO integration for enterprise use

---

## 10. Common Viva Questions & Answers

**Q: Why not let the LLM compute the totals directly?**
A: LLMs hallucinate numbers. By computing all figures deterministically in
Pandas and only letting the LLM generate prose from verified results, we
guarantee numerical accuracy. The grounding check catches any LLM-invented
numbers.

**Q: What happens if the LLM is unavailable?**
A: The app degrades gracefully. Query parsing falls back to the deterministic
regex/keyword parser. Summary generation falls back to a template. Every
feature works identically — only the naturalness of language understanding
and prose changes.

**Q: How do you prevent one user from seeing another's data?**
A: The `DBTransactionRepository` always joins `transactions →
financial_accounts` and filters by the authenticated `user_id`. This is
enforced at the service layer, not the UI layer, so even if session state
is manipulated, SQL queries never return another user's data.

**Q: What is a savepoint and why use it here?**
A: A savepoint is a nested transaction boundary. `db.begin_nested()` creates
one inside the main transaction. If the insert loop fails, `nested.rollback()`
undoes only the inserts while the parent transaction (and the import record)
survives. Without it, a failure would either lose the "failed" record or
commit partial data.

**Q: How does anomaly detection work?**
A: Three explicit methods — (1) statistical outliers above mean + 2σ, (2)
duplicate-looking charges at the same merchant with near-identical amounts
within 3 days, (3) rapid bursts of 3+ large transactions within 2 days.
Each flagged transaction gets a human-readable reason explaining the exact
math. We never call anything "fraud" — only "potentially unusual".

**Q: Why store amounts as positive with a type column?**
A: This is standard banking convention (Debit/Credit). It avoids ambiguity
about sign and makes aggregation clear: sum of Debits is spending, sum of
Credits is income. Negative amounts in imports are rejected with a guidance
message.
