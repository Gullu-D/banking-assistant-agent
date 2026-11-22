# Feature Status Table

**Commit:** `141522a` | **Test suite:** 253/253 pass

---

## Implemented and Verified

| Feature | Test Coverage | Browser Verified |
|---------|--------------|-----------------|
| User registration with validation | `test_auth.py`, `test_phase6.py` (email) | Yes |
| Login with bcrypt password hashing | `test_auth.py` | Yes |
| Logout and session clearing | `test_auth.py` | Yes |
| Rate limiting (5 attempts / 5 min lockout) | `test_auth.py` | Yes (unit) |
| Session expiry (24 hours) | `test_auth.py` | Yes (unit) |
| CSV import with validation | `test_importer.py`, `test_phase6.py` | Yes (service layer) |
| XLSX import support | `test_importer.py` | No (unit tests only) |
| Auto column mapping (22+ aliases) | `test_importer.py` | Yes (implicit via CSV import) |
| Duplicate detection | `test_importer.py` | No (unit tests only) |
| Savepoint atomicity on import failure | `test_phase6.py` | No (unit tests only) |
| Negative amount rejection with warning | `test_phase6.py` | No (unit tests only) |
| Email validation (regex) | `test_phase6.py` | Yes |
| Overview dashboard (4 KPIs, charts) | `test_dashboard.py` | Yes |
| Transaction listing with filters/sort/pagination | — | Yes |
| Anomaly detection (3 methods) | `test_anomalies.py` | Yes |
| Deterministic insights | `test_dashboard.py` | Yes |
| AI Assistant (deterministic mode) | `test_query_parser.py`, `test_orchestrator.py` | Yes |
| Trend analysis agent | `test_phase4.py` | Yes |
| Period comparison agent | `test_phase4.py`, `test_phase6.py` | Yes (unit) |
| Insights agent | `test_phase4.py` | Yes |
| Follow-up question resolution | `test_phase4.py` | Partial |
| Conversation context (10-turn cap) | `test_phase4.py` | Partial |
| Cross-user data isolation | `test_isolation.py` | Yes |
| XSS protection (html.escape) | `test_orchestrator.py` | Yes (code review) |
| INR formatting (Indian digit grouping) | `test_format_inr.py` | Yes |
| Category normalization | `test_categorizer.py` | Yes (implicit) |
| Empty user experience (zero transactions) | `test_phase6.py` | Yes |
| SECRET_KEY validation | `config.py` startup check | Yes (unit) |
| XSRF protection | Streamlit config | Yes |

## Implemented but Not Fully Verified

| Feature | Status | Reason |
|---------|--------|--------|
| File upload via Streamlit widget | Works in manual use | Automated browser cannot inject files into Streamlit's custom uploader |
| Server restart persistence | DB-backed, expected to work | Would require server restart mid-session to verify |
| Manual column mapping UI | Implemented in app.py | Not tested when auto-mapping fails |
| Import history display | Implemented in app.py | Visible during import but not separately verified |

## Requires External Provider (Optional)

| Feature | Provider | Fallback |
|---------|----------|----------|
| LLM-assisted query parsing | OpenAI API or Google Gemini | Deterministic regex/keyword parser (identical structured output) |
| AI-generated prose summaries | OpenAI API or Google Gemini | Template-based summary (uses same computed figures) |
| AI summary grounding check | Runs only when LLM is active | Template summary is always numerically grounded by construction |

## Not Implemented (Out of Scope)

| Feature | Reason |
|---------|--------|
| Real bank connectivity (Plaid/Yodlee) | Demo project — synthetic data only |
| Multi-currency support | Single-currency (INR) demo scope |
| Budget tracking / alerts | Not in project scope |
| Export to CSV/PDF | Not in project scope |
| PostgreSQL production deployment | Supported in code, not verified locally |
| OAuth/SSO authentication | Streamlit limitation |
| HTTP-only session cookies | Streamlit limitation |
| Multi-worker rate limiting | In-memory only; needs DB-backed upgrade |
| Recurring transaction detection | Not in project scope |
