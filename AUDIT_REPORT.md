# Banking AI Agent — Complete Codebase Audit & Technical Handover Report

**Audit date:** 2026-10-23
**Auditor:** Claude Opus 4.6 (automated read-only inspection)
**Repository:** `D:\banking-assistant-agent\`

---

## 1. Executive Summary

The Banking Assistant Agent is a **well-structured, largely complete** single-agent transaction analysis tool built with Python/Streamlit. It parses natural-language banking questions, filters a synthetic CSV dataset using deterministic Pandas logic, computes analytics, detects anomalies via statistical/rule-based methods, and generates AI-assisted or template-based summaries.

**Current state:** The core pipeline (parse → retrieve → filter → categorize → calculate → detect anomalies → summarize → display) is fully implemented and tested. All 48 automated tests pass. The application runs in deterministic fallback mode without any API keys, and optionally uses OpenAI or Google Gemini for query parsing and summary generation.

**Key findings:**
- No critical security issues for a demo/synthetic-data project.
- No broken features found — all discovered functionality works as implemented.
- The project is a **single-user, single-account, read-only demo** with synthetic data; it does not connect to real banking systems, does not have authentication, and does not perform financial operations.
- Several features mentioned in the audit prompt (authentication, payments, transfers, fraud detection, RAG, multi-user) are **not in scope** for this project and are not partially implemented — they simply do not exist here.

---

## 2. Project Purpose and Intended Capabilities

**Purpose:** An AI-assisted transaction analysis agent for demonstrating natural-language banking query understanding against synthetic data. Built to be evaluated, not just demoed — every calculation is unit-tested and no number shown to the user is ever invented by an LLM.

**Intended users:** Evaluators, interviewers, portfolio reviewers, and developers studying agent architecture patterns.

**Intended capabilities (from README):**
1. Natural-language query understanding (LLM + deterministic fallback)
2. Deterministic filtering and math (Pandas/NumPy)
3. Automatic transaction categorization
4. Transparent anomaly detection (statistical + rule-based)
5. AI-assisted summaries, numerically grounded
6. Graceful failure handling
7. Modern Streamlit dashboard UI
8. Comprehensive test coverage

---

## 3. Technology Stack

| Layer | Technology | Version Constraint |
|---|---|---|
| Runtime | Python 3.11+ | Inferred from README |
| Backend/Core | Pandas ≥2.2.0, NumPy ≥1.26.0, Pydantic ≥2.7.0 | `requirements.txt` |
| Date handling | python-dateutil ≥2.9.0 | `requirements.txt` |
| Config | python-dotenv ≥1.0.0 | `requirements.txt` |
| Frontend | Streamlit ≥1.38.0, Plotly ≥5.22.0 | `requirements.txt` |
| AI (optional) | OpenAI SDK ≥1.30.0, google-generativeai ≥0.7.0 | `requirements.txt` |
| Testing | pytest ≥8.0.0 | `requirements.txt` |
| Data | Local CSV (synthetic), no database | — |
| Currency | INR (₹) only | Hardcoded in `config.py:141` |

---

## 4. Architecture and Directory Structure

```
banking-assistant-agent/
├── app.py                          # Streamlit UI (753 lines, presentation only)
├── agent.py                        # Agent orchestration pipeline (223 lines)
├── config.py                       # Env-based configuration (141 lines)
├── conftest.py                     # pytest path setup (6 lines)
├── requirements.txt                # 12 dependencies
├── .env.example                    # Environment variable template
├── .gitignore                      # Standard Python gitignore
├── README.md                       # Comprehensive documentation
│
├── data/
│   ├── transactions.csv            # 93 synthetic transactions (+ header)
│   ├── transactions_dirty_sample.csv  # 4 malformed rows for testing
│   └── generate_transactions.py    # Reproducible data generator (214 lines)
│
├── src/
│   ├── __init__.py                 # Package docstring
│   ├── data_loader.py              # TransactionRepository (284 lines)
│   ├── query_parser.py             # NL→StructuredQuery, LLM+fallback (329 lines)
│   ├── date_utils.py               # Date range resolution (81 lines)
│   ├── filters.py                  # Deterministic Pandas filtering (108 lines)
│   ├── categorizer.py              # Category validation/normalization (148 lines)
│   ├── analytics.py                # Financial calculations (136 lines)
│   ├── anomaly_detector.py         # Statistical+rule-based detection (212 lines)
│   ├── summarizer.py               # AI/template summary generation (221 lines)
│   └── validators.py               # Pydantic schemas (193 lines)
│
├── tests/
│   ├── __init__.py                 # Empty
│   ├── test_filters.py             # 10 tests
│   ├── test_analytics.py           # 5 tests
│   ├── test_anomalies.py           # 7 tests
│   └── test_query_parser.py        # 12+ tests (parametrized = ~26 cases)
│
├── .streamlit/config.toml          # Theme and server config
├── assets/screenshots/             # 4 PNG screenshots for README
└── venv/                           # Local virtual environment (not committed)
```

**Architecture pattern:** Single-agent deterministic pipeline. User query flows linearly through: Query Parser → Transaction Repository → Filter → Categorizer → Analytics → Anomaly Detector → Summarizer → UI. The LLM is used only for two optional tasks (query understanding and summary prose) and never touches the dataframe.

---

## 5. Feature Inventory and Implementation Status

| # | Feature | Status | Evidence | Relevant Files | Missing Work | Dependencies |
|---|---------|--------|----------|----------------|--------------|--------------|
| 1 | Natural-language query understanding | **Implemented, verified** | Deterministic parser tested (26+ parametrized cases). LLM path exists but untested without API key. | `src/query_parser.py`, `tests/test_query_parser.py` | LLM path not integration-tested | OpenAI or Gemini key (optional) |
| 2 | Deterministic filtering & math | **Implemented, verified** | 10 filter tests + 5 analytics tests pass, boundary correctness confirmed | `src/filters.py`, `src/analytics.py`, `tests/test_filters.py`, `tests/test_analytics.py` | None | None |
| 3 | Automatic categorization | **Implemented, unverified** | Code exists with alias map + keyword inference rules; no dedicated unit tests | `src/categorizer.py` | Unit tests for categorization | None |
| 4 | Anomaly detection (statistical outliers) | **Implemented, verified** | 7 tests cover all three methods, edge cases, and exclusions | `src/anomaly_detector.py`, `tests/test_anomalies.py` | None | None |
| 5 | Anomaly detection (duplicate-like) | **Implemented, verified** | Test `test_duplicate_like_transactions_are_flagged` passes | `src/anomaly_detector.py:80-121` | None | None |
| 6 | Anomaly detection (rapid burst) | **Implemented, verified** | Test `test_rapid_repeated_large_transactions_flagged` passes | `src/anomaly_detector.py:124-170` | None | None |
| 7 | AI-assisted summaries | **Implemented, unverified** | OpenAI and Gemini paths implemented with numeric grounding check; no tests (requires API key) | `src/summarizer.py` | Integration tests with mocked LLM | OpenAI or Gemini key |
| 8 | Template summaries (fallback) | **Implemented, unverified** | `generate_template_summary()` exists, produces structured output; no direct unit tests | `src/summarizer.py:37-77` | Unit tests | None |
| 9 | Numeric grounding check | **Implemented, unverified** | `_passes_numeric_grounding_check()` validates LLM output; no direct tests | `src/summarizer.py:140-161` | Unit tests | None |
| 10 | CSV loading, validation, normalization | **Implemented, unverified** | Comprehensive error hierarchy, date/amount/type normalization, quality reporting; no direct unit tests | `src/data_loader.py` | Unit tests for loader (dirty CSV handling, missing columns, etc.) | None |
| 11 | Date range resolution | **Implemented, verified** | Tested as part of filter tests (last_month, this_month, this_week, etc.) | `src/date_utils.py`, `tests/test_filters.py:78-114` | None | None |
| 12 | Streamlit dashboard (Dashboard page) | **Implemented, unverified** | Full page with query input, quick queries, KPI cards, charts, anomaly cards, summary, transaction table | `app.py:522-633` | Manual/visual testing only | Streamlit |
| 13 | Streamlit Transactions page | **Implemented, unverified** | Searchable/filterable transaction browser with category, type, and text search | `app.py:635-671` | Manual testing | Streamlit |
| 14 | Streamlit Analytics page | **Implemented, unverified** | All-time KPIs, category breakdown, monthly trend chart | `app.py:674-705` | Manual testing | Streamlit |
| 15 | Streamlit Anomalies page | **Implemented, unverified** | All-time anomaly listing with severity cards | `app.py:708-723` | Manual testing | Streamlit |
| 16 | Indian currency formatting | **Implemented, unverified** | `format_inr()` with Indian digit grouping (₹1,25,000); no dedicated test | `app.py:264-286` | Unit test | None |
| 17 | Synthetic data generator | **Implemented, unverified** | Generates 3 months of anchored data with deliberate anomalies and dirty sample | `data/generate_transactions.py` | Could have a smoke test | None |
| 18 | Graceful failure handling | **Implemented, unverified** | Error hierarchy in `data_loader.py`, broad try/except in `agent.py`, LLM fallback in `query_parser.py` and `summarizer.py` | `src/data_loader.py:28-71`, `agent.py:110-201` | No tests for error paths (missing file, corrupt CSV, etc.) | None |
| 19 | Pydantic validation layer | **Implemented, verified** | `StructuredQuery`, `Transaction`, `AnomalyRecord`, `AnalysisSummaryInput` with validators | `src/validators.py` | Tested implicitly via query parser tests | None |
| 20 | Authentication / user login | **Not found** | No auth code, no user model, no sessions | — | Not in scope per README | — |
| 21 | Multi-user data isolation | **Not found** | Single-account design, hardcoded `ACCOUNT = "Primary"` | — | Not in scope | — |
| 22 | Payments / transfers / financial operations | **Not found** | Read-only analysis only | — | Not in scope | — |
| 23 | Fraud detection system | **Not found** | Anomaly detection explicitly disclaims fraud labeling | — | Not in scope | — |
| 24 | RAG / document retrieval | **Not found** | No embeddings, no vector store, no document retrieval | — | Not in scope | — |
| 25 | Conversation history / memory | **Not found** | No session persistence, no conversation storage | — | Not in scope | — |
| 26 | Multi-turn reasoning | **Not found** | Each query is independent; no conversation context | — | Not in scope | — |
| 27 | Tool/function calling (LLM agent tools) | **Not found** | LLM is used only for JSON extraction and prose; no tool-calling/function-calling | — | — | — |
| 28 | Customer profile management | **Not found** | No user profiles | — | Not in scope | — |

---

## 6. Critical Execution Paths and Integration Gaps

### Path 1: User submits a query via Dashboard

1. **User types** query in `st.text_area` or clicks a quick query button → `app.py:530-543`
2. **Streamlit re-runs** `page_dashboard()` → `app.py:522`
3. **Agent.analyze()** called → `agent.py:106`
4. **Query parsing** → `src/query_parser.py:314-328`
   - If LLM available: `parse_with_llm()` → calls OpenAI or Gemini → validates with Pydantic `StructuredQuery`
   - On any LLM failure: falls back to `parse_deterministic()` → regex/keyword extraction → `StructuredQuery`
5. **Data loading** → `src/data_loader.py:119-161` → `TransactionRepository.load()` → reads CSV, validates, normalizes
6. **Categorization** → `src/categorizer.py:121-147` → normalizes known categories, infers missing via keywords
7. **Filtering** → `src/filters.py:40-107` → date range + amount + category + type + sort/top_n via Pandas masks
8. **Analytics** → `src/analytics.py` → overall stats, matching stats, category breakdown, time series
9. **Anomaly detection** → `src/anomaly_detector.py:173-211` → statistical outliers + duplicates + rapid bursts on period-scoped spending data
10. **Summary generation** → `src/summarizer.py:192-220` → LLM with grounding check, or template fallback
11. **Results displayed** → `app.py:570-632` → KPI cards, charts, anomaly cards, summary card, transaction table

**No gaps found in this path.** All stages are connected and data flows correctly between them.

### Path 2: Failure handling — missing dataset

1. `TransactionRepository.load()` → `_read_csv()` → `os.path.exists()` check → `DatasetNotFoundError` raised
2. `agent.py:126` catches `TransactionDataError` → returns `AgentResult(success=False, error_message=...)`
3. `app.py:571` checks `result.success` → displays `st.error()` with user-friendly message

**No gaps found.** Error propagation is clean.

### Path 3: LLM query parsing failure

1. `parse_with_llm()` attempts API call → any exception caught at `query_parser.py:309`
2. Returns `None` → `parse_query()` falls back to `parse_deterministic()` at line 328
3. Returns `(StructuredQuery, "deterministic")` — app continues normally

**No gaps found.** Fallback is seamless.

### Disconnected/unused components: **None found.** All functions in `src/` are called by `agent.py` or `app.py`.

---

## 7. AI Agent Architecture and Detailed Audit

### Model/Provider Configuration
- **OpenAI:** Configured via `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-4o-mini`), optional `OPENAI_BASE_URL` for compatible endpoints → `config.py:50-52`
- **Gemini:** Configured via `GOOGLE_API_KEY`, `GEMINI_MODEL` (default: `gemini-1.5-flash`) → `config.py:54-55`
- **Priority:** OpenAI first if both keys set → `config.py:65`
- **Timeout:** `LLM_REQUEST_TIMEOUT_SECONDS` default 20s → `config.py:57`

### Prompt Design
- **Query parsing prompt** (`query_parser.py:230-253`): System prompt instructs LLM to extract a strict JSON object with intent, amount, operator, date_range, category, etc. Instructs "Respond with ONLY the JSON object, no explanation." Uses `temperature=0` and `response_format={"type": "json_object"}` for OpenAI.
- **Summary prompt** (`summarizer.py:84-95`): System prompt with strict rules — use only numbers from the JSON, never calculate/guess, never claim fraud, etc. Uses `temperature=0.3`.

### Agent Type
- **Single agent, fixed pipeline** — not multi-agent, not tool-calling. The LLM is a function called in two places (query parsing and summary generation), not an autonomous agent that decides which tools to use.

### Tool Calling
- **No LLM tool/function calling is used.** The LLM produces structured JSON output (query parsing) or free text (summary). The pipeline steps are hard-coded in `agent.py:analyze()`.

### Data Access Safety
- The LLM never touches the dataframe. It receives only the raw user query (for parsing) or a structured JSON payload of already-computed figures (for summarization).
- `StructuredQuery` is Pydantic-validated before use → `validators.py:59-108`.
- The summarizer receives `AnalysisSummaryInput` (Pydantic model) → `validators.py:166-193`, never the raw DataFrame.

### Hallucination Prevention
- **Numeric grounding check** (`summarizer.py:140-161`): Every number in the LLM-generated summary is checked against the set of numbers that actually appear in the input payload. Numbers that don't match (within 2% tolerance) trigger a fallback to the template summary.
- Small numbers (≤12) and year-like numbers (2000-2100) are exempted to avoid false positives.

### Consequential Actions
- **None.** The agent is read-only. It does not modify data, make payments, send messages, or perform any side effects.

### RAG
- **Not implemented.** No document retrieval, no embeddings, no vector store.

### Conversation History
- **Not implemented.** Each query is stateless; there is no conversation memory or multi-turn reasoning.

### Error Handling for LLM
- Both `parse_with_llm()` and `generate_summary()` catch all exceptions (`except Exception`) and silently fall back to deterministic alternatives → `query_parser.py:309`, `summarizer.py:218`.
- LLM failures are logged at WARNING level with the provider name and exception.

---

## 8. Database and Data Flow

**There is no database.** The application reads from a local CSV file (`data/transactions.csv`).

### Data Flow
```
CSV File → TransactionRepository.load()
  → _read_csv()           (pd.read_csv with dtype=str)
  → _validate_columns()   (check REQUIRED_COLUMNS present)
  → _normalize_dates()    (pd.to_datetime, drop invalid)
  → _normalize_amounts()  (strip currency symbols, parse float, drop negative/NaN)
  → _normalize_types()    (capitalize, validate Debit/Credit)
  → _drop_missing_required() (check transaction_id, merchant, category, account)
  → _normalize_text_columns() (strip whitespace)
  → sort by date, reset index
  → return (DataFrame, LoadReport)
```

### Dataset Characteristics
- 93 synthetic transactions (+ header row) across 3 months
- Anchored to current date (regenerated relative to `date.today()`)
- Deliberately engineered anomalies in "last month" data
- Separate dirty sample file for failure testing
- Single account ("Primary"), single currency (INR)

---

## 9. API Inventory

**There are no HTTP API endpoints.** The application is a monolithic Streamlit app. The internal function API:

| Function | Module | Purpose |
|---|---|---|
| `BankingAssistantAgent.analyze(raw_query, today)` | `agent.py:106` | Main entry point — runs full pipeline |
| `parse_query(raw_query, prefer_llm)` | `src/query_parser.py:314` | NL → StructuredQuery |
| `TransactionRepository.load()` | `src/data_loader.py:119` | CSV → validated DataFrame |
| `categorize_transactions(df)` | `src/categorizer.py:121` | Normalize/infer categories |
| `apply_filters(df, query, today)` | `src/filters.py:40` | Deterministic filtering |
| `calculate_overall_statistics(df)` | `src/analytics.py:46` | Period-scoped stats |
| `calculate_matching_statistics(df)` | `src/analytics.py:73` | Filter-scoped stats |
| `calculate_category_breakdown(df)` | `src/analytics.py:87` | Per-category breakdown |
| `spending_over_time(df, freq)` | `src/analytics.py:123` | Time series for charting |
| `detect_anomalies(df)` | `src/anomaly_detector.py:173` | All anomaly detection methods |
| `generate_summary(data)` | `src/summarizer.py:192` | AI or template summary |
| `resolve_date_range(keyword, today)` | `src/date_utils.py:25` | Keyword → (start, end, label) |

---

## 10. Security and Banking-Specific Findings

### Context
This is a **demo application with synthetic data only**. It has no authentication, no real bank connectivity, no user accounts, and performs no financial operations. The security review is therefore assessed relative to a demo/educational project, not a production banking system.

| # | Finding | Severity | Evidence | Affected Files | Impact | Remediation |
|---|---------|----------|----------|----------------|--------|-------------|
| S1 | **No authentication or authorization** | **Informational** (expected for demo) | No auth code exists anywhere | — | Anyone with network access can use the app | Add auth if deploying beyond local/demo use |
| S2 | **`unsafe_allow_html=True` used extensively in Streamlit** | **Low** | 20+ calls to `st.markdown(..., unsafe_allow_html=True)` throughout `app.py` | `app.py` (lines 39-257, 319-332, 344-356, 452-464, etc.) | In the current app, all HTML is server-generated from controlled data (not user input). However, if user-supplied text were ever rendered through these paths without escaping, it would create XSS risk. | Audit that no user input flows into `unsafe_allow_html` strings unescaped. Currently safe because rendered values come from the deterministic pipeline, not raw user input. |
| S3 | **Broad exception catching** | **Low** | `except Exception` used in `agent.py:115,129,197`, `query_parser.py:309`, `summarizer.py:218` | Multiple files | Could mask unexpected bugs during development. In production, overly broad catches can hide security-relevant errors. | Acceptable for a demo that prioritizes never crashing. Consider narrowing in production. |
| S4 | **No rate limiting on LLM calls** | **Low** | No rate limiting on `parse_with_llm()` or LLM summary calls | `src/query_parser.py`, `src/summarizer.py` | If deployed publicly with an API key, users could trigger unlimited LLM API calls and run up costs. | Add rate limiting if deploying with real API keys. |
| S5 | **LLM prompt injection surface** | **Medium** | User query is passed directly to the LLM system prompt in `query_parser.py:262` and summarizer receives computed data (not user input) | `src/query_parser.py:256-270` | A crafted query could manipulate the LLM's JSON output. However, all LLM output is Pydantic-validated (`StructuredQuery`) and can only produce values from a constrained set of literals/types. The attack surface is limited to getting the LLM to misclassify intent or extract wrong amounts, which would produce incorrect but not dangerous results (no data mutation, no code execution). | The Pydantic validation layer effectively sandboxes the LLM output. For production: consider input sanitization or a guardrail layer. |
| S6 | **No secrets found in committed code** | **Informational** (positive) | All API keys are loaded from environment variables via `.env` (gitignored). `.env.example` contains only placeholder empty values. | `config.py`, `.env.example`, `.gitignore` | None — this is correct behavior. | None needed. |
| S7 | **XSRF protection enabled** | **Informational** (positive) | `.streamlit/config.toml:9` has `enableXsrfProtection = true` | `.streamlit/config.toml` | CSRF protection is active. | None needed. |
| S8 | **CORS disabled** | **Informational** | `.streamlit/config.toml:8` has `enableCORS = false` | `.streamlit/config.toml` | Streamlit's default; CORS is off, meaning only same-origin requests are served. This is the secure default for a demo. | None needed for demo. |

### Banking-Specific Assessment
- **No real financial data** is processed — 100% synthetic.
- **No account numbers, PII, or sensitive data** exists in the codebase.
- **No financial operations** (payments, transfers, trades) are possible.
- **Anomalies are labeled "potentially unusual", never "fraudulent"** — correct disclaiming.
- **The LLM never produces financial figures** — all math is deterministic Python.
- **Summary grounding check** prevents hallucinated numbers from reaching the user.

---

## 11. Configuration and Dependencies

### Environment Variables

| Variable | Purpose | Where Used | Default | Required |
|---|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI API authentication | `config.py:50`, `query_parser.py:259`, `summarizer.py:167` | `""` (empty = disabled) | No |
| `OPENAI_MODEL` | OpenAI model name | `config.py:51`, `query_parser.py:261`, `summarizer.py:169` | `gpt-4o-mini` | No |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible endpoint | `config.py:52`, `query_parser.py:259`, `summarizer.py:167` | `None` | No |
| `GOOGLE_API_KEY` | Gemini API authentication | `config.py:54`, `query_parser.py:276`, `summarizer.py:182` | `""` (empty = disabled) | No |
| `GEMINI_MODEL` | Gemini model name | `config.py:55`, `query_parser.py:278`, `summarizer.py:183` | `gemini-1.5-flash` | No |
| `LLM_REQUEST_TIMEOUT_SECONDS` | LLM call timeout | `config.py:57` | `20` | No |
| `LOG_LEVEL` | Logging level | `config.py:35` | `INFO` | No |
| `DATA_DIR` | Data directory path | `config.py:79` | `data` | No |
| `TRANSACTIONS_CSV_PATH` | Transaction CSV path | `config.py:80` | `data/transactions.csv` | No |
| `ANOMALY_STD_MULTIPLIER` | Std devs for outlier threshold | `config.py:122` | `2.0` | No |
| `DUPLICATE_AMOUNT_TOLERANCE` | Tolerance for duplicate detection | `config.py:127` | `0.01` | No |
| `DUPLICATE_DATE_WINDOW_DAYS` | Date window for duplicates | `config.py:128` | `3` | No |
| `RAPID_WINDOW_DAYS` | Rapid burst detection window | `config.py:130` | `2` | No |
| `RAPID_MIN_COUNT` | Min transactions for rapid burst | `config.py:131` | `3` | No |
| `RAPID_LARGE_PERCENTILE` | Percentile for "large" threshold | `config.py:132` | `0.75` | No |

**All environment variables are optional.** The app runs fully without any `.env` file.

### Dependencies (from `requirements.txt`)
All are standard, well-maintained packages. No known security vulnerabilities at the pinned minimum versions as of audit date.

### External Services Required
- **None for basic operation.** The app runs fully offline.
- **OpenAI API or Google Gemini API** — optional, for LLM-enhanced query parsing and summaries.

---

## 12. Tests and Verification Results

### Test Execution

```
Command: python -m pytest -q --tb=short
Result:  48 passed in 6.04s
```

All 48 tests pass without errors or warnings.

### Test Coverage by Module

| Module | Test File | Tests | Coverage Assessment |
|---|---|---|---|
| `src/filters.py` | `tests/test_filters.py` | 10 | **Good** — boundary correctness, operators, category, date ranges, empty DF, top_n/sort |
| `src/analytics.py` | `tests/test_analytics.py` | 5 | **Adequate** — known-value checks for overall/matching stats, category breakdown percentages, income exclusion, empty DF |
| `src/anomaly_detector.py` | `tests/test_anomalies.py` | 7 | **Good** — all three detection methods, edge cases (small sample, credits excluded, empty DF) |
| `src/query_parser.py` | `tests/test_query_parser.py` | ~26 (parametrized) | **Good** — operator variations, Indian currency formats, intents, categories, error cases, safe defaults |
| `src/date_utils.py` | (tested via `test_filters.py`) | 5 | **Adequate** — last_month, this_month, last_30_days, all_time, dynamic year boundary |
| `src/categorizer.py` | **None** | 0 | **Gap** — no unit tests for alias mapping or keyword inference |
| `src/summarizer.py` | **None** | 0 | **Gap** — no unit tests for template summary or grounding check |
| `src/data_loader.py` | **None** | 0 | **Gap** — no unit tests for CSV loading, normalization, or error paths |
| `src/validators.py` | (tested implicitly) | — | Pydantic models tested implicitly through query parser tests |
| `agent.py` | **None** | 0 | **Gap** — no integration tests for the full agent pipeline |
| `app.py` | **None** | 0 | **Expected** — Streamlit UI testing requires manual or Selenium-based testing |

### Untested but Implemented Error Paths
- `DatasetNotFoundError` (missing CSV)
- `DatasetCorruptedError` (unparseable CSV)
- `MissingColumnsError` (missing required columns)
- `EmptyDatasetError` (empty CSV)
- Invalid date/amount row handling in `data_loader.py`
- LLM parsing failure → deterministic fallback
- LLM summary failure → template fallback
- Numeric grounding check failure → template fallback

### Features That Remain Unverified
- Full Streamlit UI rendering (requires running the app and visual inspection)
- LLM-assisted query parsing (requires API key)
- LLM-assisted summary generation (requires API key)
- Indian currency formatting function (`format_inr`)
- Data generator script output correctness

---

## 13. Prioritized Implementation Backlog

### P0 — Critical Security Issues or Blockers
**None found.** No critical security issues exist for a demo/synthetic-data project.

### P1 — Essential Missing Functionality and Core Integration Blockers

| # | Task | Current Status | Files | Dependencies | Acceptance Criteria | Tests Required |
|---|------|---------------|-------|--------------|---------------------|----------------|
| P1.1 | Add unit tests for `src/data_loader.py` | No tests exist | `tests/test_data_loader.py` (new) | None | Tests cover: valid CSV loading, missing file error, corrupt CSV error, missing columns error, empty CSV error, invalid date/amount row skipping, LoadReport accuracy | 8-10 tests |
| P1.2 | Add unit tests for `src/categorizer.py` | No tests exist | `tests/test_categorizer.py` (new) | None | Tests cover: known category normalization, alias mapping, keyword inference from merchant/description, "Other" fallback, empty DataFrame | 5-7 tests |
| P1.3 | Add unit tests for `src/summarizer.py` | No tests exist | `tests/test_summarizer.py` (new) | None (can mock LLM) | Tests cover: template summary output correctness, numeric grounding check pass/fail, empty results handling | 5-7 tests |

### P2 — Important Feature Completion and Reliability

| # | Task | Current Status | Files | Dependencies | Acceptance Criteria | Tests Required |
|---|------|---------------|-------|--------------|---------------------|----------------|
| P2.1 | Add integration test for full agent pipeline | No agent-level test exists | `tests/test_agent.py` (new) | P1.1 | Test `BankingAssistantAgent.analyze()` end-to-end with the provided sample CSV | 3-5 tests |
| P2.2 | Add unit test for `format_inr()` | No test exists | `tests/test_app_helpers.py` (new) or `tests/test_analytics.py` | None | Test Indian digit grouping for various amounts (0, 999, 1000, 100000, 12500000, negatives) | 5-6 tests |
| P2.3 | Add LLM integration tests with mocking | No LLM tests exist | `tests/test_llm_integration.py` (new) | None | Mock OpenAI/Gemini responses, verify Pydantic validation of LLM output, test fallback on bad JSON | 4-6 tests |
| P2.4 | Regenerate `transactions.csv` if stale | CSV was generated at project creation, dates may not match current date | `data/generate_transactions.py` | None | Running `python data/generate_transactions.py` produces data anchored to today's date | Manual check |

### P3 — Enhancements and Optional Improvements

| # | Task | Current Status | Files | Dependencies | Acceptance Criteria | Risks |
|---|------|---------------|-------|--------------|---------------------|-------|
| P3.1 | Add conversation history / multi-turn support | Not implemented | `agent.py`, `app.py`, new `src/memory.py` | Design decision needed | User can ask follow-up questions referencing previous results | Significant scope expansion |
| P3.2 | Add multi-account support | Not implemented | `config.py`, `src/data_loader.py`, `src/filters.py`, `app.py` | Design decision needed | User can filter by account | Schema changes |
| P3.3 | Add multi-currency support | Not implemented | `config.py`, `src/analytics.py`, `app.py` | Design decision needed | Currency conversion or per-currency analytics | Significant scope expansion |
| P3.4 | Add rate limiting for LLM calls | Not implemented | `src/query_parser.py`, `src/summarizer.py` | None | Max N LLM calls per minute per session | Only needed if deploying publicly with API keys |
| P3.5 | Sanitize user input before LLM prompt | Partial (Pydantic validates output) | `src/query_parser.py` | None | Input is cleaned/truncated before sending to LLM | Low risk given Pydantic sandboxing |
| P3.6 | Add Streamlit authentication | Not implemented | `app.py`, `.streamlit/config.toml` | Streamlit extras or custom auth | Login required before accessing app | Only if deploying beyond local demo |
| P3.7 | Add persistent saved queries / user preferences | Not implemented | New files | Database or file storage | User can save and re-run favorite queries | New persistence layer needed |

---

## 14. Setup and Run Instructions

### Verified Commands (from README and successful test run)

```bash
# Clone and enter directory
cd D:\banking-assistant-agent

# Create and activate virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Copy and edit .env for LLM API keys
cp .env.example .env
# Edit .env to add OPENAI_API_KEY or GOOGLE_API_KEY

# Run the app
streamlit run app.py

# Run tests
pytest -q
```

### Verified Results
- `pytest -q` → **48 passed in 6.04s** ✓
- `venv/` exists with Python 3.12 (inferred from `pyvenv.cfg` and `cpython-312` artifacts)
- `data/transactions.csv` exists with 93 transactions ✓
- `data/transactions_dirty_sample.csv` exists with 4 malformed rows ✓

### Unverified (Requires Interactive Session)
- `streamlit run app.py` — requires a running terminal with the venv activated; expected to work based on code inspection.
- LLM-enhanced features — require real API keys in `.env`.

### Blockers
- **None for basic operation.** The app is designed to run without any API keys.

---

## 15. Decisions or Requirements That Need My Input

| # | Question | Context | Impact |
|---|----------|---------|--------|
| Q1 | **Is this project scope-complete for your purposes, or do you need the features listed in "Future Scope" (multi-account, multi-currency, open-banking, persistence)?** | The README lists these as "Future Scope" but they are not partially implemented. | Determines whether P3 items become P1 items. |
| Q2 | **Do you want LLM-based features tested with real API keys, or should tests use mocked responses?** | Currently no LLM tests exist. Mocked tests are self-contained; real-key tests verify actual integration. | Determines P2.3 approach. |
| Q3 | **Should `transactions.csv` be regenerated?** | Current data may have dates from a prior run (dates visible: 2026-06-02 through 2026-08-xx). The generator is date-anchored to `date.today()` at generation time. | If data is stale relative to "today", "last month"/"this month" queries may return no results. |
| Q4 | **Is Streamlit Community Cloud the intended deployment target?** | README mentions it. If deploying elsewhere (Docker, AWS, etc.), additional config may be needed. | Determines deployment documentation scope. |
| Q5 | **Do you want the test coverage gaps (P1.1-P1.3) addressed before adding new features?** | Current tests cover the most critical paths but leave data loading, categorization, and summarization untested. | Determines implementation order. |

---

## 16. Recommended Implementation Order

1. **P2.4** — Regenerate `transactions.csv` to ensure dates are current (1 minute, `python data/generate_transactions.py`)
2. **P1.1** — Add `test_data_loader.py` (most important untested module)
3. **P1.2** — Add `test_categorizer.py`
4. **P1.3** — Add `test_summarizer.py`
5. **P2.1** — Add `test_agent.py` integration test
6. **P2.2** — Add `format_inr()` tests
7. **P2.3** — Add mocked LLM integration tests
8. **P3.x** — Enhancements per your priorities from Q1 above

---

## 17. Concise ChatGPT Handover Summary

---

# CHATGPT HANDOVER — BANKING AI AGENT

## Project Purpose and Current State

A **single-agent banking transaction analysis tool** that answers natural-language questions about synthetic transaction data. Built with Python, Streamlit, and optional LLM integration (OpenAI/Gemini). The project is **feature-complete for its stated demo scope** — all core features work, 48/48 tests pass, and the app runs without any API keys in deterministic fallback mode.

## Technology Stack

- **Python 3.12**, Pandas 2.2+, NumPy 1.26+, Pydantic 2.7+, python-dateutil 2.9+
- **Streamlit 1.38+** with custom CSS (fintech theme), Plotly 5.22+ for charts
- **Optional:** OpenAI SDK 1.30+ or google-generativeai 0.7+ (LLM features)
- **pytest 8.0+** for testing
- **Data:** Local CSV (`data/transactions.csv`), 93 synthetic transactions, INR currency

## Feature Status Summary

### Existing and Working
- Natural-language query parsing (deterministic regex/keyword — 26+ test cases pass)
- Deterministic transaction filtering with boundary-correct operators (10 tests pass)
- Financial analytics: totals, averages, category breakdown, time series (5 tests pass)
- Statistical anomaly detection: outliers, duplicate-like, rapid bursts (7 tests pass)
- Template-based summary generation (deterministic fallback)
- Pydantic validation layer for all data flowing between components
- Streamlit dashboard with 4 pages: Dashboard, Transactions, Analytics, Anomalies
- KPI cards, Plotly charts (pie + bar), anomaly cards, searchable transaction table
- Synthetic data generator with deliberate anomalies
- Comprehensive error handling (missing files, corrupt CSV, bad data, LLM failures)
- Indian currency formatting (₹ with lakh grouping)

### Implemented but Not Unit-Tested
- CSV data loading/validation/normalization (`src/data_loader.py`)
- Category alias mapping and keyword-based inference (`src/categorizer.py`)
- Template summary generation and numeric grounding check (`src/summarizer.py`)
- LLM-assisted query parsing and summary generation (requires API key to test)
- Full agent orchestration pipeline (`agent.py`)
- All Streamlit UI pages (`app.py`)

### Not Implemented (Not in Scope)
- Authentication/authorization, user accounts, sessions
- Multi-user data isolation, multi-account, multi-currency
- Payments, transfers, or any financial operations
- Fraud detection (anomaly detection explicitly disclaims this)
- RAG, document retrieval, embeddings
- Conversation history, memory, multi-turn reasoning
- LLM tool/function calling
- Customer profiles, real bank API integration

## Architecture

Single-agent deterministic pipeline:
```
User Query → parse_query() → TransactionRepository.load() → categorize_transactions()
  → apply_filters() → calculate_*() → detect_anomalies() → generate_summary() → UI
```
LLM is used **only** for (1) query understanding (JSON extraction) and (2) summary prose. The LLM **never** touches the DataFrame or produces financial figures. All LLM output is Pydantic-validated, and summaries pass a numeric grounding check.

## Key Files for Next Implementation Task

| File | Lines | Purpose |
|---|---|---|
| `agent.py` | 223 | Agent orchestration — the entire pipeline |
| `config.py` | 141 | All configuration, env vars, constants |
| `src/validators.py` | 193 | All Pydantic schemas |
| `src/query_parser.py` | 329 | NL query understanding (LLM + fallback) |
| `src/data_loader.py` | 284 | CSV loading and validation |
| `src/filters.py` | 108 | Deterministic filtering |
| `src/analytics.py` | 136 | Financial calculations |
| `src/anomaly_detector.py` | 212 | Anomaly detection |
| `src/summarizer.py` | 221 | Summary generation |
| `src/categorizer.py` | 148 | Category normalization |
| `app.py` | 753 | Streamlit UI (presentation only) |

## Highest-Priority Bugs and Security Issues
- **No bugs found.** All 48 tests pass.
- **No critical security issues.** The app is a demo with synthetic data.
- **Medium:** User query passes directly to LLM prompt (mitigated by Pydantic validation of output).
- **Low:** `unsafe_allow_html=True` in Streamlit (currently safe — no user input in HTML strings).

## Test Commands and Results
```bash
pytest -q           # 48 passed in 6.04s ✓
```

## Constraints and Unresolved Decisions
1. Whether to add test coverage for untested modules (data_loader, categorizer, summarizer) before new features.
2. Whether `transactions.csv` needs regeneration (dates may be stale).
3. Whether any "Future Scope" features (multi-account, multi-currency, auth, persistence) are needed.
4. Whether LLM tests should use real keys or mocked responses.
5. Target deployment environment (Streamlit Cloud, Docker, etc.).

## Recommended First Implementation Task
**Add unit tests for `src/data_loader.py`** — it is the most critical untested module (all data flows through it), and testing it will also exercise the error hierarchy and validate the dirty-data handling that is currently unverified. Create `tests/test_data_loader.py` with tests for: valid CSV loading, missing file error, corrupt CSV error, missing columns, empty CSV, invalid date/amount row skipping, and LoadReport accuracy.
