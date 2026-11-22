# 1. Project Architecture

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.12 |
| Web Framework | Streamlit | 1.45.1 |
| ORM | SQLAlchemy | 2.x (mapped_column style) |
| Database | SQLite | WAL mode, file at `data/banking.db` |
| Migrations | Alembic | 3 migrations |
| Data Processing | Pandas, NumPy | — |
| Charting | Plotly Express + Graph Objects | — |
| Validation | Pydantic v2 | BaseModel with field_validator |
| Password Hashing | bcrypt | — |
| LLM (optional) | Ollama (llama3.2:1b) / OpenAI / Gemini | — |
| Date Utilities | python-dateutil | relativedelta |

## Directory Structure

```
banking-assistant-agent/
├── app.py                  # Streamlit UI (presentation only)
├── agent.py                # BankingAssistantAgent — CSV-based orchestration
├── config.py               # All configuration from environment/.env
├── conftest.py             # Shared pytest fixtures
├── src/
│   ├── models.py           # SQLAlchemy ORM models (7 tables)
│   ├── database.py         # Engine, session factory, init_db()
│   ├── services.py         # Service layer (user CRUD, subscriptions, conversations)
│   ├── auth.py             # Streamlit session auth + rate limiting
│   ├── query_parser.py     # NL → StructuredQuery (LLM + deterministic)
│   ├── validators.py       # Pydantic schemas (StructuredQuery, AnomalyRecord, etc.)
│   ├── filters.py          # Deterministic transaction filtering
│   ├── date_utils.py       # Date range keyword → (start, end) resolution
│   ├── analytics.py        # Financial calculations (Pandas/NumPy)
│   ├── categorizer.py      # Category normalization + keyword inference
│   ├── anomaly_detector.py # 3-method statistical anomaly detection
│   ├── summarizer.py       # Template or LLM-based summary generation
│   ├── formatting.py       # Multi-currency formatting (INR/GBP/USD/EUR)
│   ├── orchestrator.py     # Multi-agent orchestrator (DB-backed)
│   ├── agents.py           # 7 specialist agent functions
│   ├── tool_result.py      # Shared ToolResult dataclass
│   ├── data_loader.py      # CSV loading + validation (TransactionRepository)
│   └── importer.py         # CSV/XLSX import pipeline
├── data/
│   ├── banking.db          # SQLite database
│   └── transactions.csv    # Legacy CSV data file
├── tests/                  # 24 test files, 325 tests
├── alembic/                # Database migrations (3 versions)
└── docs/viva/              # This documentation
```

## Request Processing Pipeline

When a user types a natural-language query (e.g., "Show my spending last month"), it flows through this pipeline:

```
User Query (natural language)
    │
    ▼
┌─────────────────────────────────┐
│  1. Query Parser                │  src/query_parser.py
│     parse_query()               │
│     ┌─ Try LLM (if available)  │  → parse_with_llm()
│     └─ Fallback: deterministic │  → parse_deterministic()
│     Output: StructuredQuery     │  (Pydantic-validated)
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  2. Follow-up Resolution        │  src/orchestrator.py
│     ConversationContext          │  .resolve_follow_up()
│     (inherit date_range/category │
│      from prior turn if needed) │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  3. Load Transactions           │  src/services.py
│     DBTransactionRepository     │  .load() → DataFrame
│     (user-scoped via            │
│      FinancialAccount.user_id)  │
└─────────────┬───────────────────┘
              │
              ▼
       ┌──────┴──────┐
       │  Route by   │
       │  Intent     │
       └──────┬──────┘
              │
    ┌─────────┴─────────┐
    ▼                   ▼
 Standard            Specialist
 Intents             Agents
 (5 types)           (7 types)
    │                   │
    ▼                   ▼
┌────────────┐  ┌────────────────┐
│ Categorize │  │ agent_trend    │  src/agents.py
│ Filter     │  │ agent_period   │
│ Calculate  │  │ agent_merchant │
│ Anomalies  │  │ agent_income   │
│ Summarize  │  │ agent_cashflow │
│            │  │ agent_budget   │
│            │  │ agent_insights │
└─────┬──────┘  └───────┬────────┘
      │                 │
      └────────┬────────┘
               ▼
        ToolResult (success, data, error)
               │
               ▼
        Streamlit UI renders:
        - KPI cards
        - Plotly charts
        - Transaction table
        - Anomaly list
        - Direct answer text
```

## Intent Routing

The orchestrator (`src/orchestrator.py`) dispatches queries based on the parsed intent:

| Intent | Route | Handler |
|--------|-------|---------|
| `spending_summary` | Standard pipeline | `tool_analyze_transactions()` |
| `top_expenses` | Standard pipeline | `tool_analyze_transactions()` |
| `category_spending` | Standard pipeline | `tool_analyze_transactions()` |
| `anomaly_detection` | Standard pipeline | `tool_analyze_transactions()` |
| `transaction_analysis` | Standard pipeline | `tool_analyze_transactions()` |
| `general_query` | Standard pipeline | `tool_analyze_transactions()` |
| `trend_analysis` | Specialist agent | `agent_trend_analysis()` |
| `period_comparison` | Specialist agent | `agent_period_comparison()` |
| `merchant_analysis` | Specialist agent | `agent_merchant_analysis()` |
| `income_analysis` | Specialist agent | `agent_income_analysis()` |
| `cashflow_analysis` | Specialist agent | `agent_cashflow_analysis()` |
| `budget_query` | Specialist agent | `agent_budget_analysis()` |
| `insights_query` | Specialist agent | `agent_insights()` |

## The Role of the LLM (Ollama)

The LLM is used in exactly two places:

1. **Query parsing** (`src/query_parser.py:parse_with_llm`) — Converts natural language to a `StructuredQuery` JSON. On any failure (timeout, bad JSON, validation error), falls back to the deterministic regex parser.

2. **Summary generation** (`src/summarizer.py:generate_summary`) — Generates a prose summary from pre-computed, validated `AnalysisSummaryInput`. On failure, falls back to a template-based summary.

**The LLM never:**
- Touches the DataFrame or raw data
- Performs financial calculations
- Invents numbers — every figure comes from deterministic Pandas/NumPy
- Filters or sorts transactions
- Categorizes transactions (done by `src/categorizer.py` deterministically)

This design means the application produces identical financial results with or without a working LLM. The LLM only improves natural-language understanding and prose quality.

## Deterministic vs LLM Distinction

| Component | Deterministic (always) | LLM (optional enhancement) |
|-----------|----------------------|---------------------------|
| Query parsing | Regex + keyword rules | Structured JSON extraction |
| Transaction loading | SQLAlchemy query | — |
| Filtering | Pandas boolean masks | — |
| Categorization | Alias map + keyword rules | — |
| Analytics | Pandas/NumPy arithmetic | — |
| Anomaly detection | Statistical (mean + std), duplicate, rapid-burst | — |
| Summary generation | Template-based | Prose generation from validated data |
| Currency formatting | `format_inr()` | — |

## Two Orchestration Layers

1. **`agent.py` → `BankingAssistantAgent`**: The original CSV-based agent. Still used for CSV-only testing. Runs the full pipeline (parse → load → categorize → filter → calculate → anomalies → summarize) in a single `analyze()` method.

2. **`src/orchestrator.py` → `Orchestrator`**: The DB-backed orchestrator used by the Streamlit UI. Adds multi-agent routing (7 specialist agents), conversation context tracking, and user-scoped DB queries. This is the primary orchestration layer in production.
