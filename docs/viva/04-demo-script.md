# 4. Demonstration Script (10–15 minutes)

## Pre-Demo Setup

1. Ensure Ollama is running (`ollama serve`) with `llama3.2:1b` pulled
2. Start the app: `streamlit run app.py`
3. Verify the app opens at `http://localhost:8501`
4. Have two browser tabs ready (one for each account)

---

## Part 1: Authentication (1 minute)

**Show the login page.**

> "The app requires authentication before accessing any financial data. Passwords are hashed with bcrypt — the database never stores plaintext."

1. Log in as `moneydata_demo` (password set locally — not published in repo)
2. Point out the rate limiter: "After 5 failed attempts, the account locks for 5 minutes."

---

## Part 2: Dashboard Overview (2 minutes)

**On the Overview page after login:**

> "This is the main dashboard. All numbers are computed deterministically using Pandas and NumPy — never by the LLM."

1. **KPI cards**: Point to Net Cash Flow (-£1,980), Total Income (£503,203), Total Expenses (£505,183)
   - "Notice the £ symbol — this account uses GBP. The system formats currency per-account."
2. **Date range selector**: Switch between "This Month", "Last Month", "All Time"
   - "Date ranges are resolved to concrete start/end dates at runtime — nothing is hardcoded."
3. **Charts**: Show the spending-over-time chart and category pie chart
   - "Charts use Plotly with hover templates showing the correct currency symbol."
4. **Period comparison**: Show the comparison section
   - "This compares the selected period against the equivalent prior period — same number of days."

---

## Part 3: Transaction Browser (1 minute)

**Navigate to Transactions page.**

1. Show the full transaction list: "6,519 transactions from the MoneyData GBP dataset"
2. Apply a category filter (e.g., "Groceries")
3. Apply a date range filter
4. Point out the anomaly-highlighted rows (if visible)
5. Show the CSV download button

---

## Part 4: Standard Mode Queries (3 minutes)

**Navigate to AI Assistant. Ensure Standard Mode is active.**

> "Standard Mode uses deterministic regex-based query parsing — no LLM needed. Let me demonstrate several query types."

### Query 1: Spending Summary
Type: `What did I spend last month?`

**Expected**: Direct answer with total spending, income, net cash flow in £. Category breakdown. Time series chart.

> "The parser matched 'spend' and 'last month' to set intent=spending_summary and date_range=last_month."

### Query 2: Category Spending
Type: `How much did I spend on groceries?`

**Expected**: Grocery spending total in £ with transaction count.

> "Category is extracted from the keyword 'groceries' — mapped to the canonical 'Groceries' category."

### Query 3: Anomaly Detection
Type: `Find unusual transactions`

**Expected**: List of flagged transactions with explanations.

> "Three detection methods: statistical outliers (mean + 2σ), duplicate-like, and rapid repeated large. Each anomaly has a human-readable reason."

### Query 4: Period Comparison
Type: `Compare this month to last month`

**Expected**: Current vs prior period comparison with percentage changes.

> "Intent 'period_comparison' routes to the specialist `agent_period_comparison()` function."

---

## Part 5: AI Mode (2 minutes)

**Switch to AI Mode** (if the account has Pro access).

> "AI Mode uses Ollama llama3.2:1b for query parsing. The financial calculations are identical — only the NL understanding changes."

### Query 5: Natural language query
Type: `What insights can you give me about my finances?`

**Expected**: Pattern analysis, top spending category, expense-to-income ratio, most frequent merchant, anomaly count.

> "This routes to `agent_insights()`, which runs five separate deterministic analyses and combines them into a narrative."

### Query 6: Follow-up
Type: `What about shopping?`

**Expected**: Inherits date_range from prior turn, focuses on Shopping category.

> "Conversation context tracks the last 10 turns. The follow-up pattern 'what about' triggers context inheritance."

---

## Part 6: User Isolation (1 minute)

> "Let me demonstrate that user data is completely isolated."

1. Log out of moneydata_demo
2. Log in as a different account (e.g., Gaurav)
3. Show the dashboard: different currency (₹), different transaction count (48 transactions)
4. "This user's account uses INR with Indian digit grouping (1,25,000). The MoneyData GBP data is invisible."

---

## Part 7: Data Import (1 minute)

**Navigate to Data Center.**

> "Users can import CSV or XLSX files. The system auto-maps common column names and detects duplicates."

1. Show the import interface
2. Point out import history (past imports with row counts)
3. "Column aliases handle variations: 'transaction_date' maps to 'date', 'payee' maps to 'merchant'. Duplicate detection uses (date, merchant, amount, type) matching."

---

## Part 8: Architecture Walkthrough (2 minutes)

> "Let me show the code architecture."

1. Open `src/query_parser.py`: "Two parsers — LLM-based and deterministic. Every LLM response is validated through Pydantic before use."
2. Open `src/validators.py`: "StructuredQuery is the ONLY thing the LLM produces. 13 intent types, validated amounts, date ranges."
3. Open `src/analytics.py`: "Pure Pandas/NumPy. Every financial number comes from here."
4. Open `src/anomaly_detector.py`: "Three explicit methods. No ML model — purely statistical."
5. Open `src/orchestrator.py`: "Routes queries to 7 specialist agents or the standard pipeline."

---

## Part 9: Test Suite (1 minute)

> "325 tests, all passing. Let me show the test structure."

Run: `pytest --tb=short -q` (or show a previous test run)

Key test files to mention:
- `test_financial_accuracy.py`: Verifies expense/income separation, category breakdowns, date filters
- `test_security.py`: Auth, isolation, injection tests
- `test_anomalies.py`: Anomaly detection accuracy
- `test_orchestrator.py`: Query routing and user isolation

---

## Closing (30 seconds)

> "To summarize: this is a multi-agent banking analysis system with 7 specialist agents, deterministic financial calculations, optional LLM enhancement, multi-currency support, and comprehensive anomaly detection. All 325 tests pass, and the system works identically with or without an LLM."
