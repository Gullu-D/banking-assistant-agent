# Demo & Viva Guide — Banking Assistant Agent

## Prerequisites

- Python 3.12+, pip, virtualenv
- The repository at `D:\banking-assistant-agent`
- A `.env` file (see Setup below)
- A sample CSV file for import demo (use `data/transactions.csv` if available)

## Setup

```bash
cd D:\banking-assistant-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env`:
```
SECRET_KEY=your-strong-secret-key-at-least-16-chars
# Optional: for AI Mode demo
# OPENAI_API_KEY=sk-...
# DEMO_USERNAMES=demo_user
```

Run migrations:
```bash
alembic upgrade head
```

Start the app:
```bash
streamlit run app.py
```

## Demo Walkthrough

### 1. Registration & Login
- Open http://localhost:8501
- **Show the auth page** — dark navy dual-pane design with brand showcase
- Register a new account (e.g., `demo_user` / `demo@example.com` / `StrongPass123!`)
- Log in — observe session creation and redirect to Overview

### 2. Overview Dashboard (Empty State)
- Point out the **empty state** message — "Import your transaction data..."
- Explain: "This is a real application. No fake data is shown."

### 3. Data Center — Import Transactions
- Navigate to **Data Center** in sidebar
- Show the 4-step pipeline tracker
- Upload `data/transactions.csv` (or your own CSV/XLSX)
- Show column auto-mapping and preview
- Click Import — show the import summary (rows imported, duplicates, skipped)
- Explain signed-amount handling if CSV has negative amounts

### 4. Overview Dashboard (With Data)
- Navigate back to **Overview**
- **Hero banner** with welcome message and live telemetry indicator
- **4 KPI cards**: Treasury Balance, OpEx Velocity, Net Cashflow, Flagged Anomalies
- **Cash Flow chart** — Plotly area chart with income vs expenses
- **AI Copilot Insights** — deterministic insights from real data
- **Recent transactions** table
- Change date range and show KPIs/charts update

### 5. Transaction Ledger
- Navigate to **Transactions**
- Show filter controls: date range, category, type, sort, search
- Filter by a specific category — show totals update
- Search for a merchant name
- Expand a transaction for inspector details

### 6. AI Assistant
- Navigate to **AI Assistant**
- Show **Standard Mode** (toggle in header)
- Ask: "What are my top spending categories?"
- Show deterministic response with real data
- Ask: "Compare this month with last month"
- Show period comparison with percentage changes
- Ask: "Find unusual transactions"
- Show anomaly detection results

**If AI Mode is available (Pro + API key):**
- Toggle to **AI Mode (Pro)** in header
- Show the LLM-enhanced responses
- Explain: "Same calculations, but the summary uses natural language generation"

**If no API key:**
- Show the AI Mode locked state for free users
- Explain: "AI Mode requires a Pro subscription AND a configured LLM provider"

### 7. Pricing & Subscription
- Navigate to **Billing & Subscription**
- Show monthly/annual toggle (₹299/mo vs ₹2,990/yr)
- Show Free vs Pro feature comparison
- Explain: "Payment integration is scaffolded for Razorpay but not live"

### 8. Architecture Explanation

**Show the architecture diagram** from `docs/ARCHITECTURE.md`.

Key points to explain:

1. **Multi-agent orchestration**: The Orchestrator receives queries, parses them,
   routes to specialized agents (trend, comparison, insights), and returns structured results.

2. **Deterministic by default**: All financial math uses Pandas/NumPy. The LLM
   (when configured) only handles natural language — it never invents numbers.

3. **User isolation**: Every query is scoped by `user_id` through the
   `FinancialAccount` → `Transaction` relationship. One user cannot see another's data.

4. **Dual-mode design**: Standard Mode works without any external API.
   AI Mode adds LLM-generated explanations on top of verified calculations.

5. **Security**: bcrypt passwords, rate limiting, session tokens, XSS escaping,
   import validation, atomic database commits.

6. **Entitlement model**: Free → Pro → Demo are three distinct levels.
   Server-side enforcement via `get_user_plan()`.

### 9. Test Coverage

```bash
python -m pytest -v --tb=short
```

Show: 265 tests covering auth, analytics, anomalies, imports, orchestrator,
filters, security, isolation, UI helpers.

## Viva Q&A Preparation

**Q: How does the AI assistant work?**
A: The Orchestrator parses the query into a StructuredQuery, loads user-scoped
transactions, routes to the right agent function, and returns deterministic
results. In AI Mode, an LLM generates prose around verified calculations.

**Q: Can one user see another's data?**
A: No. All queries join through `financial_accounts.user_id`. Cross-user
isolation is tested in `test_isolation.py`.

**Q: What happens without an API key?**
A: The app runs in fallback mode. Standard Mode uses rule-based parsing and
template summaries. AI Mode shows a locked state or unavailable message.

**Q: How are transactions imported?**
A: CSV/XLSX → parse → validate → normalize amounts → detect duplicates →
atomic insert. Failed imports roll back. Import history is recorded.

**Q: What security measures exist?**
A: bcrypt hashing, rate limiting (5 attempts/5min lockout), session tokens
(64-char hex, 24h expiry), XSS escaping, input validation, file size limits,
SECRET_KEY enforcement in production mode.

**Q: What's the database schema?**
A: Five tables: users, financial_accounts, transactions, import_records,
subscriptions. Managed by SQLAlchemy ORM with Alembic migrations.

**Q: What's not implemented?**
A: Real bank integrations (webhooks), Razorpay payment processing,
hardware FIDO2/MFA, SOC2/ISO compliance, autonomous T-Bill sweeps.
These are future scope, clearly separated from implemented features.
