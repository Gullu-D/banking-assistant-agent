# 7. Final Teacher Demonstration Checklist

## Pre-Demo (day before)

- [ ] Python 3.12 installed and on PATH
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Ollama installed and `llama3.2:1b` model pulled (`ollama pull llama3.2:1b`)
- [ ] `.env` file exists with at minimum `SECRET_KEY` and `DEMO_ACTIVATION_KEY` set
- [ ] `moneydata_demo` user exists with 6,519 GBP transactions imported
- [ ] Run `pytest --tb=short -q` — confirm 325 tests pass
- [ ] Start and stop the app once to verify no import errors

## Pre-Demo (15 minutes before)

- [ ] Start Ollama: `ollama serve`
- [ ] Verify Ollama responds: `curl http://localhost:11434/api/tags`
- [ ] Start the app: `streamlit run app.py`
- [ ] Open `http://localhost:8501` in browser
- [ ] Verify login page appears
- [ ] Log in as `moneydata_demo` — confirm dashboard loads
- [ ] Verify KPI cards show £ amounts (GBP)
- [ ] Log out, log in as a second user — verify ₹ amounts (INR), different data
- [ ] Log back into `moneydata_demo` for the demo

## During Demo — Feature Walkthrough

### Authentication
- [ ] Show login page, mention bcrypt + rate limiting
- [ ] Log in successfully

### Dashboard
- [ ] KPI cards visible with £ currency
- [ ] Switch date range (All Time → Last Month → This Year)
- [ ] Charts render (spending over time, category pie, top merchants)
- [ ] Period comparison section shows % changes

### Transactions
- [ ] Full transaction list loads (6,519 rows)
- [ ] Apply category filter
- [ ] Apply date range filter
- [ ] Show CSV download button

### Standard Mode Queries
- [ ] `What did I spend last month?` → spending summary in £
- [ ] `How much did I spend on groceries?` → category total
- [ ] `Find unusual transactions` → anomaly list with reasons
- [ ] `Compare this month to last month` → period comparison

### AI Mode (if Pro access active)
- [ ] Switch to AI Mode
- [ ] `What insights can you give me?` → multi-analysis response
- [ ] `What about shopping?` → follow-up inherits context

### User Isolation
- [ ] Log out of moneydata_demo
- [ ] Log into second account
- [ ] Dashboard shows different currency (₹) and different data
- [ ] No GBP data visible

### Data Import
- [ ] Navigate to Data Center
- [ ] Show import interface and import history
- [ ] Mention column auto-mapping and duplicate detection

### Architecture (code walkthrough)
- [ ] Open `src/query_parser.py` — two parsers, Pydantic validation
- [ ] Open `src/analytics.py` — pure Pandas/NumPy
- [ ] Open `src/orchestrator.py` — intent routing to 7 agents
- [ ] Open `src/anomaly_detector.py` — three explicit methods

### Test Suite
- [ ] Run `pytest --tb=short -q` or show previous passing run
- [ ] Mention: 325 tests, 24 files, in-memory SQLite isolation

## Key Talking Points

| Topic | One-liner |
|-------|-----------|
| LLM role | "Only query parsing and summaries — never touches data or calculations" |
| Deterministic guarantee | "Remove Ollama entirely and every number stays the same" |
| User isolation | "Transactions join through FinancialAccount — no direct user_id query on transactions" |
| Anomaly detection | "Three rule-based methods, not ML — every flag has a readable reason" |
| Multi-currency | "Account-level currency, Indian grouping for INR, Western for GBP/USD/EUR" |
| Payments | "Razorpay configured but keys not set — demo-only subscription system" |
| Testing | "325 tests including financial accuracy, user isolation, and security" |

## Post-Demo

- [ ] Stop the Streamlit server (`Ctrl+C`)
- [ ] Stop Ollama if no longer needed
- [ ] Confirm no changes were made to the database or code during the demo
