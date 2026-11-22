# 6. Project Limitations

## Fully Implemented

These features work end-to-end as described in the documentation:

| Feature | Evidence |
|---------|----------|
| Deterministic query parsing (13 intents) | `src/query_parser.py:parse_deterministic()` — regex/keyword rules |
| Multi-agent orchestration (7 specialists) | `src/orchestrator.py` dispatches, `src/agents.py` executes |
| Anomaly detection (3 methods) | `src/anomaly_detector.py` — statistical, duplicate-like, rapid-burst |
| CSV/XLSX import with duplicate detection | `src/importer.py:run_import()` |
| Multi-currency formatting (INR/GBP/USD/EUR) | `src/formatting.py:format_inr()` + `FinancialAccount.currency` |
| bcrypt password hashing | `src/services.py:hash_password()` / `verify_password()` |
| Rate-limited login (5 attempts / 5 min) | `src/auth.py:_check_rate_limit()` |
| Session-based auth with 24h expiry | `src/auth.py:is_authenticated()` |
| User data isolation (account-scoped queries) | `DBTransactionRepository.load()` joins through `FinancialAccount` |
| Conversation context with follow-up resolution | `ConversationContext` in `src/orchestrator.py` (10-turn window) |
| Category normalization (50+ aliases, 13 keyword rules) | `src/categorizer.py` |
| Alembic migrations (3 versions) | `alembic/versions/` — schema is version-controlled |
| 325 passing tests across 24 files | `tests/` directory |
| Column auto-mapping for imports | `src/importer.py:auto_map_columns()` — 30+ aliases |
| Original data preservation on import | `original_description`, `original_category`, `original_txn_code` columns |

## Demo-Only / Simulated

These features exist in code but operate in a limited or demo capacity:

| Feature | What exists | What's missing |
|---------|------------|----------------|
| **Subscription system** | `subscriptions` table, plan checks, Pro/Free gating | No real payment flow — Razorpay keys are unconfigured placeholders in `config.py` |
| **Demo activation** | `DEMO_ACTIVATION_KEY` env var, `activate_demo()` with `hmac.compare_digest` | Key is set per-deployment, not a real purchase; 7-day expiry is hardcoded |
| **Demo usernames** | `DEMO_USERNAMES` config list grants Pro automatically | Bypasses payment entirely — intended for demonstration |
| **Pro plan pricing page** | `page_pricing()` renders ₹299/month with Razorpay checkout JS | Button calls `Razorpay()` constructor but keys are empty — payment will fail |
| **Billing page** | `page_billing()` shows plan status, cancel button | No invoice history, no real payment provider webhook handling |

## Unconfigured / Requires External Setup

These features have code paths but need external services to function:

| Feature | Code location | What's needed |
|---------|--------------|---------------|
| **OpenAI provider** | `config.py:OPENAI_API_KEY`, `query_parser.py:_call_openai()` | Set `OPENAI_API_KEY` in `.env` |
| **Gemini provider** | `config.py:GEMINI_API_KEY`, `query_parser.py:_call_gemini()` | Set `GEMINI_API_KEY` in `.env` |
| **Razorpay payments** | `config.py:RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Set both keys in `.env`, configure webhook |
| **PostgreSQL** | `database.py` reads `DATABASE_URL` | Set `DATABASE_URL` to a PostgreSQL connection string |
| **Custom SECRET_KEY** | `config.py` raises `RuntimeError` if default + `DATABASE_URL` set | Set `SECRET_KEY` to a strong random value for production |

## Known Technical Limitations

| Limitation | Impact | Upgrade path |
|------------|--------|-------------|
| **SQLite single-file DB** | No horizontal scaling, limited concurrent writes | PostgreSQL via `DATABASE_URL` |
| **In-memory rate limiter** | Resets on app restart; no cross-process state | Redis or DB-backed rate limiting |
| **Streamlit session_state auth** | Tied to WebSocket — no HTTP-only cookies, no CSRF token | Reverse proxy + cookie-based sessions |
| **`datetime.utcnow()` deprecation** | 19 warnings in Python 3.12 (cosmetic) | Replace with `datetime.now(datetime.UTC)` |
| **Ollama `llama3.2:1b` accuracy** | Misclassifies intents, misparses formatted numbers | Upgrade to 3b+ or 7b model |
| **No email verification** | Users can register with any email | Add email confirmation flow |
| **No password reset** | No "forgot password" feature | Add email-based reset tokens |
| **No audit logging** | No record of who did what when | Add audit trail table |
| **No HTTPS** | Streamlit serves HTTP by default | TLS termination via reverse proxy |
| **Module-level `_currency` pattern** | Global mutable state in `anomaly_detector.py`, `summarizer.py` | Pass currency as parameter through all calls |
| **CSV-based `BankingAssistantAgent`** | Legacy agent in `agent.py` — not used by the UI | Remove or document as test-only |

## Not Implemented (Future Work)

These features do not exist in the codebase:

- Real-time bank account syncing (Plaid, Yodlee, Account Aggregator)
- Multi-user collaboration or shared accounts
- Budget goal setting and tracking alerts
- Recurring transaction detection and prediction
- Email or push notifications
- Two-factor authentication (2FA)
- API layer (REST/GraphQL) for mobile clients
- Data export to accounting software (QIF, OFX)
- Machine learning–based categorization (current system is rule-based)
- Scheduled report generation
