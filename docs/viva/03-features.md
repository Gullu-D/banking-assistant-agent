# 3. Feature Explanation

## Authentication & User Management

**Implementation**: `src/auth.py` + `src/services.py`

- **Registration**: Username (3–80 chars, alphanumeric + dots/hyphens/underscores), email (basic regex validation), password (min 8 chars). Passwords hashed with bcrypt (`bcrypt.hashpw` with auto-generated salt).
- **Login**: Username + password verified via `bcrypt.checkpw`. On success, a 256-bit session token (`secrets.token_hex(32)`) is stored in Streamlit `session_state`.
- **Session management**: Server-side via Streamlit `session_state` (tied to websocket). Session expires after `SESSION_LIFETIME_SECONDS` (default 24 hours). Expiry checked on every `is_authenticated()` call.
- **Rate limiting**: In-memory, thread-safe (`threading.Lock`). After `MAX_LOGIN_ATTEMPTS` (default 5) failed logins within `LOGIN_LOCKOUT_SECONDS` (default 300s), the username is locked out. Stale entries swept every 60 seconds.
- **Logout**: Clears all `session_state` keys.

## Dashboard / Overview Page

**Implementation**: `app.py:page_overview()` (line 1228)

- **KPI cards**: Net Cash Flow, Total Income, Total Expenses, Average Transaction — all computed by `src/analytics.py:calculate_overall_statistics()`.
- **Date range selector**: Dropdown with options (This Month, Last Month, Last 30 Days, This Year, All Time, Custom). Uses `src/date_utils.py:resolve_date_range()`.
- **Period comparison**: Compares current period vs equivalent prior period using `src/analytics.py:period_comparison()`. Shows percentage change with delta indicators.
- **Charts** (Plotly):
  - Spending over time (line/bar chart)
  - Income vs Expenses over time
  - Category breakdown (pie chart)
  - Top merchants (horizontal bar chart)
- **Insights section**: Auto-generated spending patterns via `app.py:_generate_insights()`.
- **Currency**: All amounts formatted via `_fmt()` which calls `format_inr(amount, _user_currency())`.

## Transaction Browser

**Implementation**: `app.py:page_transactions()` (line 1492)

- **Filtering**: Date range, category dropdown, transaction type (Debit/Credit/All), amount range slider.
- **Sorting**: By date (newest/oldest) or amount (highest/lowest).
- **Transaction table**: Styled DataFrame with anomaly highlighting (flagged rows shown with warning icon).
- **CSV export**: Download filtered transactions as CSV via `st.download_button`.
- **Data quality notice**: Displayed when `LoadReport` has issues (skipped rows, warnings).

## Data Import (Data Center)

**Implementation**: `app.py:page_import()` (line 1983) + `src/importer.py`

- **Supported formats**: CSV and XLSX (max 10 MB).
- **Column auto-mapping**: `auto_map_columns()` matches common column aliases (e.g., "transaction_date" → "date", "payee" → "merchant", "amt" → "amount").
- **Validation**: Dates parsed, amounts cleaned (strips ₹, commas, Rs.), types normalized to Debit/Credit.
- **Duplicate detection**: Matching on (date, merchant, amount, txn_type) — prevents re-importing the same file.
- **Separate Debit/Credit columns**: Automatically merged when source has `debit_amount`/`credit_amount` instead of a single `amount`.
- **Import record tracking**: Every import logged in `import_records` table with row counts and status.
- **Original data preservation**: Raw description, category, transaction code, balance, and location stored alongside normalized values.

## Anomaly Detection

**Implementation**: `src/anomaly_detector.py`

Three transparent, rule-based methods (no black box):

### Method 1: Statistical Outliers
- Flags transactions where `amount > mean + (ANOMALY_STD_MULTIPLIER × std_dev)`
- Default multiplier: 2.0 (≈97.7th percentile for normal distribution)
- Severity: "moderate" or "high" (if above `mean + 3 × std_dev`)
- Minimum sample size: 5 transactions
- Only Debit (spending) transactions considered

### Method 2: Duplicate-Like Transactions
- Same merchant, near-identical amount (within 1% tolerance), within 3-day window
- Possible double-charge indicator
- ATM/Cash Withdrawal excluded (naturally repetitive)

### Method 3: Rapid Repeated Large Transactions
- 3+ transactions, each above 75th percentile, within 2-day window
- Possible spending spree or card misuse pattern
- ATM/Cash Withdrawal excluded

**Key design**: Every flagged transaction includes a human-readable `reason` string explaining exactly why it was flagged. Described as "potentially unusual" — never "fraudulent".

## AI Assistant

**Implementation**: `app.py:page_ai_assistant()` (line 1710) + `src/orchestrator.py`

### Two Modes

| Feature | Standard Mode (Free) | AI Mode (Pro) |
|---------|---------------------|---------------|
| Query parsing | Deterministic regex | LLM first, deterministic fallback |
| Financial calculations | Pandas/NumPy | Pandas/NumPy (identical) |
| Anomaly detection | Statistical rules | Statistical rules (identical) |
| Summary generation | Template-based | LLM prose + template fallback |
| Conversation memory | Yes | Yes |

### Standard Mode
- Always available (no API key needed)
- Uses `parse_deterministic()` for query understanding
- Supports 13 intent types via regex/keyword matching
- Template-based summaries

### AI Mode (Pro plan required)
- Uses Ollama `llama3.2:1b` for query parsing (with deterministic fallback)
- LLM-generated summaries from pre-validated `AnalysisSummaryInput`
- Same deterministic calculations — LLM only affects NL understanding and prose

### Conversation Context
- `ConversationContext` (in `src/orchestrator.py`) tracks up to 10 turns
- Follow-up resolution: "what about shopping?" inherits date_range from prior turn
- Pattern matching: "what about", "same for", "also show", "tell me more", etc.
- Conversations persisted in `conversations` + `conversation_messages` tables

### Query Examples
- "What did I spend last month?" → `spending_summary`, `last_month`
- "Show my top 5 expenses" → `top_expenses`, `top_n=5`
- "How much did I spend on groceries?" → `category_spending`, category="Groceries"
- "Find unusual transactions" → `anomaly_detection`
- "How has my spending changed over time?" → `trend_analysis`
- "Compare this month to last month" → `period_comparison`
- "What insights can you give me?" → `insights_query`
- "Show transactions above ₹50,000" → `transaction_analysis`, amount_threshold=50000

## Subscription / Demo System

**Implementation**: `src/services.py` (subscription helpers) + `config.py`

### Plan Tiers
- **Free**: Standard Mode (deterministic analysis, all calculations, anomaly detection, dashboard)
- **Pro**: AI Mode (LLM-enhanced parsing and summaries) + all Free features

### Access Methods
1. **Real payment** (Razorpay): Configured via `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `.env`. Currently unconfigured — payment gateway is not live.
2. **Demo usernames**: `DEMO_USERNAMES` env var — comma-separated list of usernames that get Pro features without payment. Shows "(Demo)" badge.
3. **Demo activation key**: `DEMO_ACTIVATION_KEY` env var — users enter this key in the UI to get a 7-day demo subscription. Uses `hmac.compare_digest` for constant-time comparison.

### Subscription State
- Stored in `subscriptions` table with `plan`, `status`, `expires_at`
- Auto-expiry: checked on every `get_user_plan_detail()` call
- Cancellation: sets status to "cancelled"

## Reports & Exports

- **CSV download**: Available on the Transactions page for filtered data
- **Data quality report**: `LoadReport` shown after imports with skipped/invalid row counts
- **Import history**: All past imports visible in the Data Center with filename, row counts, status
- **Conversation history**: Past AI conversations listed with titles and timestamps

## Category System

**Implementation**: `src/categorizer.py`

17 canonical categories defined in `config.py:VALID_CATEGORIES`:
Food & Dining, Shopping, Travel, Rent, Utilities, Healthcare, Education, Entertainment, Groceries, Investments, Transfers, Salary / Income, ATM / Cash Withdrawal, Freelance, Interest, Refund, Other.

**Two-step categorization**:
1. **Normalize**: Match raw category against alias map (50+ aliases, case-insensitive)
2. **Infer**: If unrecognized, use merchant/description keyword rules (13 regex patterns) to assign a category. Falls back to "Other".

Income categories (Salary / Income, Freelance, Interest, Refund) are treated specially — used for type correction when all transactions are Debit.
