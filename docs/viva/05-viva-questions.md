# 5. Technical Viva Questions & Answers

## A. Python & Streamlit (10 questions)

### Q1. Why did you choose Streamlit over Flask or Django?
**A:** Streamlit is purpose-built for data-centric Python applications. It provides built-in session management, reactive UI updates, and native DataFrame/chart rendering without writing HTML/JS. For a banking analytics dashboard with Plotly charts and interactive filters, Streamlit eliminates the frontend build step entirely. Flask or Django would require a separate frontend framework (React, Vue) and REST API layer.

### Q2. How does Streamlit session management work in your app?
**A:** Streamlit `session_state` is a server-side dictionary tied to the browser's WebSocket connection. In `src/auth.py`, on successful login, we store `user_id`, `username`, a 256-bit `session_token` (via `secrets.token_hex(32)`), and `session_created_at`. Every page checks `is_authenticated()` which verifies these keys exist and the session hasn't expired (default 24 hours). A client cannot directly read or modify `session_state` — the WebSocket itself is the session boundary.

### Q3. How do you handle page routing in a single-page Streamlit app?
**A:** Via `app.py:render_sidebar()` which returns a page name string. The `main()` function at line 2457 dispatches to the appropriate page function (`page_overview()`, `page_transactions()`, `page_ai_assistant()`, etc.). A `_nav_override` session_state key allows programmatic navigation (e.g., redirecting from pricing to subscription after activation).

### Q4. What is `@st.cache_data` or `st.session_state` and when do you use each?
**A:** `session_state` persists across reruns within a single browser session — used for auth state, conversation context, and user preferences. We don't use `@st.cache_data` extensively because our data changes per-user and per-query; instead, we cache the user's currency in `session_state` (see `_user_currency()` at line 47) to avoid repeated DB lookups within a single page render.

### Q5. How do you prevent Streamlit's auto-rerun behavior from causing issues?
**A:** Streamlit reruns the entire script on every interaction. We guard expensive operations behind `is_authenticated()` checks and load data inside page functions (not at module level). The rate limiter in `src/auth.py` uses `time.monotonic()` (not `session_state`) so it survives reruns and isn't reset by page navigation.

### Q6. What Python version features do you use?
**A:** Python 3.12. Key features: `X | Y` union type syntax (`str | None` instead of `Optional[str]`), `from __future__ import annotations` for deferred evaluation of type hints, f-string formatting, dataclasses with `field(default_factory=...)`, and walrus operator where appropriate.

### Q7. How do you handle environment configuration?
**A:** All configuration lives in `config.py`, loaded from environment variables via `python-dotenv`. No secrets are hardcoded. The module reads `.env` at import time with `load_dotenv()`. A safety check raises `RuntimeError` if `DATABASE_URL` is set (production) but `SECRET_KEY` is the default value or too short.

### Q8. Why use `from __future__ import annotations` in every module?
**A:** It enables PEP 604 union syntax (`str | None`) and forward references in type hints on Python 3.12. All type hints are stored as strings and only evaluated when needed, avoiding `NameError` for classes defined later in the file.

### Q9. How does the logging system work?
**A:** `config.py` configures `logging.basicConfig()` with a standardized format (`timestamp | level | module | message`). Each module gets its own logger via `config.get_logger(__name__)`. Log level is configurable via `LOG_LEVEL` env var (default: INFO).

### Q10. What is the purpose of `conftest.py`?
**A:** It provides shared pytest fixtures (DB sessions, test users, sample data) used across all 24 test files. Fixtures like `db()` create in-memory SQLite databases for test isolation — each test gets a fresh database.

---

## B. SQLAlchemy & Alembic (8 questions)

### Q11. Why SQLAlchemy 2.x mapped_column style instead of the classic Column style?
**A:** SQLAlchemy 2.x `Mapped[T]` with `mapped_column()` provides proper type inference for IDEs and mypy. The type annotation (`Mapped[str]`) is the source of truth for both Python typing and the database column type. It's more explicit and catches type mismatches at development time.

### Q12. How do you handle database sessions and transactions?
**A:** `src/database.py:get_db()` is a context manager that yields a `Session`, commits on clean exit, and rolls back on exception. The `SessionLocal` factory uses `expire_on_commit=False` so objects remain usable after commit without triggering additional queries. For imports, nested transactions (`db.begin_nested()`) provide savepoints so a batch insert failure doesn't destroy the entire import.

### Q13. Why SQLite with WAL mode?
**A:** WAL (Write-Ahead Logging) allows concurrent reads during writes — essential for Streamlit which may serve multiple users/requests simultaneously. Without WAL, SQLite would serialize all access. We also enable `foreign_keys=ON` via a connect event listener since SQLite defaults to FK enforcement off.

### Q14. How does Alembic handle schema migrations?
**A:** Three migrations in `alembic/versions/`: initial schema, subscriptions table, and original data preservation columns. Alembic generates migration scripts by diffing the ORM models against the current database schema. Each migration has `upgrade()` and `downgrade()` functions for bidirectional migration.

### Q15. Why use `Numeric(15, 2)` for financial amounts?
**A:** `Numeric(15, 2)` stores exact decimal values with 2 decimal places and up to 15 total digits. This avoids floating-point representation errors (e.g., `0.1 + 0.2 ≠ 0.3` with IEEE 754 floats). For financial calculations, exact arithmetic is essential.

### Q16. Explain the cascade delete strategy.
**A:** `ondelete="CASCADE"` on foreign keys ensures that deleting a User cascades to their FinancialAccounts, which cascades to Transactions. Similarly, deleting an ImportRecord sets `import_id` to NULL on related Transactions (`ondelete="SET NULL"`) rather than deleting the transactions themselves. SQLAlchemy's `cascade="all, delete-orphan"` on relationships handles the ORM side.

### Q17. How does `expire_on_commit=False` affect your code?
**A:** After a `session.commit()`, SQLAlchemy normally expires all loaded objects, causing lazy-loads on next access. `expire_on_commit=False` keeps objects usable without triggering additional queries. This is important in Streamlit where we might access user objects after committing in the `get_db()` context manager.

### Q18. How do you handle concurrent access with SQLite?
**A:** WAL mode handles read concurrency. `check_same_thread=False` in `connect_args` allows the engine to be used across Streamlit's multiple threads. `pool_pre_ping=True` detects stale connections. For writes, SQLite's built-in locking serializes concurrent writes, which is acceptable for a single-server deployment.

---

## C. Database Design (7 questions)

### Q19. Why separate `financial_accounts` from `users`?
**A:** A user can have multiple accounts (checking, savings, credit card), each with its own currency. Transactions belong to accounts, not directly to users. This models real banking where one person has multiple accounts. It also enables per-account currency — the `moneydata_demo` user has a GBP account while others have INR.

### Q20. Why is `external_id` on Transaction a UUID, not an auto-increment?
**A:** `external_id` (UUID hex) serves as a globally unique, collision-free identifier for imported transactions. The auto-increment `id` is the internal primary key. During imports, `external_id` provides a stable reference that doesn't depend on insert order or database state.

### Q21. How does user data isolation work?
**A:** Transactions are never queried by `user_id` directly. The join path is `Transaction → FinancialAccount → User`. In `DBTransactionRepository.load()`, the query joins `Transaction` with `FinancialAccount` and filters on `FinancialAccount.user_id`. This makes cross-user data leakage structurally impossible — there's no query path that bypasses the account ownership check.

### Q22. Why store `original_description` and `original_category` alongside normalized values?
**A:** Data provenance. When importing from CSV/XLSX, the raw values are preserved so users can audit what their source data contained versus how the system categorized it. The `original_txn_code` field preserves the source's transaction type code (which may not be "Debit"/"Credit").

### Q23. How does the import duplicate detection work?
**A:** A row is duplicate if the user already has a transaction with the same (date, merchant_lowercase, amount, txn_type). This catches re-imports without relying on external IDs that source files rarely include. The check queries all existing transactions for the user's accounts and builds a set for O(1) lookup.

### Q24. Why is `import_id` nullable with `SET NULL` on delete?
**A:** If an import record is deleted (e.g., cleaning up metadata), the transactions themselves should survive. Setting `import_id` to NULL preserves the data while removing the import-tracking link. This is safer than CASCADE which would delete the transactions.

### Q25. Explain the conversation persistence model.
**A:** `conversations` stores per-user conversation sessions with titles and timestamps. `conversation_messages` stores individual messages with role ("user"/"assistant"), content (max 10,000 chars), and optional metadata (intent, date_range, category). Messages are ordered by `created_at`. The in-memory `ConversationContext` handles follow-up resolution during a session; the DB provides persistence across sessions.

---

## D. Multi-Agent Architecture (8 questions)

### Q26. What is a "multi-agent" system in this context?
**A:** The orchestrator dispatches queries to 7 specialist agent functions, each handling a specific type of financial analysis. Unlike multi-agent systems where agents communicate with each other, here agents are independent functions called by a central orchestrator. Each agent receives a DataFrame and StructuredQuery, and returns a ToolResult with deterministic analysis.

### Q27. List all 7 specialist agents and their responsibilities.
**A:**
1. `agent_trend_analysis` — Month-over-month spending/income trends
2. `agent_period_comparison` — Current vs prior period comparison with % changes
3. `agent_merchant_analysis` — Top merchants by spending with transaction counts
4. `agent_income_analysis` — Credit transaction breakdown by source
5. `agent_cashflow_analysis` — Net cash flow, savings rate, positive cash flow months
6. `agent_budget_analysis` — Expense-to-income ratio, category-wise budget breakdown
7. `agent_insights` — Pattern detection: top category, frequent merchant, anomalies

### Q28. How does the orchestrator decide which agent to call?
**A:** Based on the `intent` field in the `StructuredQuery`. The set `_agent_intents = {"trend_analysis", "period_comparison", "insights_query", "merchant_analysis", "income_analysis", "cashflow_analysis", "budget_query"}` routes to specialist agents. All other intents go through the standard pipeline (`tool_analyze_transactions()`).

### Q29. What is the `ToolResult` pattern?
**A:** `ToolResult` (defined in `src/tool_result.py`) is a simple dataclass with `success: bool`, `data: dict`, `error: str`. All agents and the standard pipeline return this, providing a uniform interface. The orchestrator and UI check `result.success` and either display `result.data` or show `result.error`.

### Q30. How do agents maintain user data isolation?
**A:** The orchestrator loads user-scoped data once via `tool_load_transactions()` which calls `DBTransactionRepository.load()` (joins through FinancialAccount). Agents receive the pre-filtered DataFrame — they never query the database themselves.

### Q31. Why are agents functions instead of classes?
**A:** Each agent is stateless — it takes a DataFrame and query, returns a result. There's no state to maintain between calls. Functions are simpler, testable in isolation, and avoid the overhead of instantiation. This follows the principle of using the simplest construct that works.

### Q32. How does `BankingAssistantAgent` differ from `Orchestrator`?
**A:** `BankingAssistantAgent` (in `agent.py`) is the original CSV-based pipeline — a single `analyze()` method that runs all steps sequentially. `Orchestrator` (in `src/orchestrator.py`) is the DB-backed evolution that adds multi-agent routing, conversation context, currency resolution, and user-scoped queries. The app uses `Orchestrator`; `BankingAssistantAgent` remains for CSV-based testing.

### Q33. How does conversation context work in the orchestrator?
**A:** `ConversationContext` stores up to 10 turns (query, intent, date_range, category, answer_preview). When a new query matches a follow-up pattern (e.g., "what about", "same for"), `resolve_follow_up()` inherits the previous turn's date_range and category into the current query. This allows "What did I spend last month?" followed by "What about shopping?" to retain the last_month date range.

---

## E. LLMs & Ollama (7 questions)

### Q34. What is Ollama and why did you choose it?
**A:** Ollama is a local LLM runtime that runs models on the user's machine. We chose it because: (1) no API key needed, (2) no data leaves the machine (privacy), (3) works offline, (4) free. The model `llama3.2:1b` is small (1 billion parameters) for fast inference, though it sometimes misclassifies intents.

### Q35. How does the LLM provider selection work?
**A:** `config.py:active_llm_provider()` implements a priority chain: if `LLM_PROVIDER=auto` (default), it tries Ollama first (checks if server is reachable via `/api/tags` with 1-second timeout), then OpenAI (if API key set), then Gemini (if API key set). Returns `None` if nothing is available. The result is cached for 30 seconds to avoid repeated HTTP calls.

### Q36. What happens when the LLM fails?
**A:** `parse_with_llm()` wraps the entire LLM call in a try/except. On any failure (timeout, bad JSON, Pydantic validation error, network error), it returns `None` — never raises. The caller (`parse_query()`) then falls back to `parse_deterministic()`. For billing errors ("credit_balance_exhausted"), the LLM is disabled for 1 hour. The app never breaks due to an LLM problem.

### Q37. How do you prevent the LLM from inventing financial data?
**A:** Three safeguards:
1. **Query parser**: The LLM's JSON output is validated through `StructuredQuery` Pydantic model before use. It can only produce intent/date_range/category/amount — never raw data.
2. **Summarizer**: The LLM receives `AnalysisSummaryInput` — a Pydantic model containing only pre-computed, deterministic numbers. It generates prose from these numbers, never invents them.
3. **No DataFrame access**: The LLM never sees or touches raw transaction data.

### Q38. What is the LLM system prompt and what does it constrain?
**A:** The system prompt (in `src/query_parser.py:_SYSTEM_PROMPT`) instructs the LLM to extract a strict JSON object with exactly the `StructuredQuery` fields. It specifies allowed values for each field (intent types, operators, categories, date ranges) and explicitly states: "Respond with ONLY the JSON object, no explanation" and "do NOT invent a number."

### Q39. How does the Ollama API call work?
**A:** `_call_ollama()` sends a POST to `{OLLAMA_BASE_URL}/api/chat` with the model name, system prompt, user query, `stream: false`, `format: "json"`, and `temperature: 0`. The response's `message.content` is parsed as JSON. The timeout is configurable via `LLM_REQUEST_TIMEOUT_SECONDS` (default 20s).

### Q40. Why did some tests fail with Ollama enabled, and how was it fixed?
**A:** 10 tests assumed deterministic parsing but ran with Ollama active. The `llama3.2:1b` model would: parse empty strings as valid queries, misclassify intents, and misparse amount thresholds (e.g., "₹50,000" → 15000). Fix: `@patch("config.active_llm_provider", return_value=None)` on tests that test deterministic behavior. This is correct — these tests verify the deterministic pipeline, not Ollama's quality.

---

## F. Financial Calculations (5 questions)

### Q41. How do you separate expenses from income?
**A:** `txn_type` column: "Debit" = expense, "Credit" = income. In `calculate_overall_statistics()`, `total_spending` sums only Debit rows, `total_income` sums only Credit rows. Spending-focused intents (spending_summary, top_expenses, category_spending) automatically set `transaction_type="Debit"` in the query, so income transactions are excluded before analysis.

### Q42. How does type correction from category work?
**A:** `_correct_types_from_category()` in `src/services.py` handles imported data where all transactions have the same type (typically all "Debit" from sources without a type column). If every row is Debit, it checks each row's category against `config.INCOME_CATEGORIES` (Salary / Income, Freelance, Interest, Refund) and reclassifies matching rows as "Credit". This uses both canonical names and raw aliases via `normalize_category()`.

### Q43. How does the category breakdown calculation work?
**A:** `calculate_category_breakdown()` in `src/analytics.py`: filters to Debit-only (spending_only=True by default), groups by category, sums amounts, calculates count, and computes percentages relative to total spending. Returns a list of `CategoryBreakdownItem` Pydantic models sorted by total_amount descending.

### Q44. How does period comparison work?
**A:** `period_comparison()` in `src/analytics.py` takes a current date range and computes the equivalent prior period (same number of days, ending the day before the current period starts). It calculates `OverallStatistics` for both periods and percentage changes for spending, income, net cash flow, and transaction count. Returns `None` for percentage change when the previous value is 0 (avoids division by zero).

### Q45. Why do you use `_safe_float()` in analytics?
**A:** `_safe_float()` converts `None`, `NaN`, and `Inf` to 0.0. Pandas aggregation functions can return NaN on empty DataFrames or Inf on certain operations. Without this guard, NaN would propagate through calculations and appear in the UI. It's used consistently in `calculate_overall_statistics()` and `calculate_matching_statistics()`.

---

## G. Security & Auth (5 questions)

### Q46. How are passwords stored?
**A:** Using bcrypt via `bcrypt.hashpw(raw.encode(), bcrypt.gensalt())`. Each password gets a unique random salt (embedded in the hash output). Verification uses `bcrypt.checkpw()` which is constant-time to prevent timing attacks. The hash is stored in `users.password_hash` (String 128).

### Q47. How does the rate limiter prevent brute-force attacks?
**A:** `_check_rate_limit()` in `src/auth.py` tracks failed login attempts per username (lowercased) with timestamps. After `MAX_LOGIN_ATTEMPTS` (5) within `LOGIN_LOCKOUT_SECONDS` (300s), further attempts are rejected with a "try again in X seconds" message. The limiter is thread-safe (`threading.Lock`), survives Streamlit reruns (module-level state), and sweeps stale entries every 60 seconds.

### Q48. What security validations exist on user registration?
**A:** Username: 3–80 chars, `[a-zA-Z0-9_.-]` only. Email: basic `^[^@\s]+@[^@\s]+\.[^@\s]+$` regex. Password: minimum 8 characters. Username and email uniqueness enforced at both the application level (query before insert) and database level (UNIQUE constraints).

### Q49. How is cross-user data leakage prevented?
**A:** Three layers: (1) Database structure — transactions belong to accounts, accounts belong to users, queries always join through this chain. (2) Service layer — `DBTransactionRepository` requires `user_id` and queries only that user's accounts. (3) UI layer — `get_current_user_id()` reads from server-side `session_state`, never from client input.

### Q50. How is the demo activation key validated?
**A:** `hmac.compare_digest(activation_key, config.DEMO_ACTIVATION_KEY)` in `src/services.py:activate_demo()`. `hmac.compare_digest` is constant-time — it prevents timing attacks where an attacker could deduce the key character by character based on comparison time.

---

## H. Testing & Debugging (5 questions)

### Q51. How many tests are there and what do they cover?
**A:** 325 tests across 24 test files. Coverage includes: query parsing (deterministic and LLM), analytics calculations (expense/income separation, category breakdowns, date filters), anomaly detection, orchestrator routing, user isolation, authentication/security, data import, format validation, categorization, summarization, and UI helpers.

### Q52. How do tests handle the database?
**A:** Each test creates an in-memory SQLite database: `engine = create_engine("sqlite:///:memory:")`. This is fast, isolated, and disposable. Fixtures create users and seed transactions with known values so assertions can verify exact amounts.

### Q53. How did you handle Ollama-related test failures?
**A:** Tests that verify deterministic behavior use `@patch("config.active_llm_provider", return_value=None)` to disable the LLM. Patching `os.environ` doesn't work because `config.LLM_PROVIDER` is read at import time, and Ollama doesn't need API keys. The patch targets `active_llm_provider` which is the runtime check that controls whether an LLM is used.

### Q54. What is the `test_financial_accuracy.py` test strategy?
**A:** It creates controlled test data with known amounts (e.g., 3000 Debit + 15000 Debit + 8000 Debit = 26000 expenses, 50000 + 2000 = 52000 income) and verifies the pipeline produces exact results. Tests cover: total expenses exclude income, income excludes expenses, top expenses are Debit-only, category breakdown excludes income categories, net cash flow is correct, and date filtering is accurate.

### Q55. How do you test user isolation?
**A:** Create two users with different transactions, run the same query through both orchestrators, and verify neither sees the other's data. `test_orchestrator_user_isolation` in `test_orchestrator.py` checks that User A's results contain no data from User B's StoreB merchant, and vice versa.

---

## I. Limitations & Future (5 questions)

### Q56. Why is `llama3.2:1b` sometimes inaccurate?
**A:** At 1 billion parameters, the model lacks the capacity for reliable structured output extraction. It misclassifies intents (e.g., "total income" → "spending_summary"), misparses formatted numbers (₹50,000 → 15000), and sometimes generates valid JSON for empty/garbage input. A 3b+ or 7b model would significantly improve parsing quality.

### Q57. Is this connected to a real bank?
**A:** No. The app uses 100% synthetic/imported data. There is no live banking API integration, no real payment processing, no access to real bank accounts. The Razorpay payment gateway configuration exists in `config.py` but keys are not set — the subscription system is demo-only.

### Q58. What would be needed for production deployment?
**A:** PostgreSQL instead of SQLite, proper HTTPS/TLS termination, HTTP-only cookies for sessions (Streamlit limitation — would need a reverse proxy), real payment gateway configuration, email verification, password reset flow, audit logging, and rate limiting backed by Redis or database instead of in-memory.

### Q59. What are the `datetime.utcnow()` deprecation warnings?
**A:** 19 warnings from `src/services.py` — `datetime.utcnow()` is deprecated in Python 3.12 in favor of `datetime.now(datetime.UTC)` which returns a timezone-aware datetime. This is cosmetic and doesn't affect correctness.

### Q60. How would you add real-time bank account syncing?
**A:** Integrate with an account aggregation API (e.g., Plaid, Yodlee, or India's Account Aggregator framework). This would require: OAuth consent flow, webhook handlers for new transactions, incremental sync (only fetch new data), and proper credential storage (never in the database). The existing import pipeline could be adapted to receive API data instead of file uploads.
