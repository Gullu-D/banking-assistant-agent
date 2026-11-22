# Teacher Demo Script

**Time:** ~8–10 minutes | **Commit:** `141522a` on `master` | **Data:** 100% synthetic

---

## Pre-demo Setup (once)

```bash
cd D:\banking-assistant-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

If `data/banking.db` exists and contains data you want to keep, back it up
first. For a clean demo, rename or delete it — the app creates a fresh one on
startup.

```bash
if exist data\banking.db ren data\banking.db banking_backup.db
streamlit run app.py
```

No `.env` file is needed — the app runs in deterministic fallback mode
without API keys.

Open `http://localhost:8501` in a browser.

---

## Step 1: Registration and Authentication (~1 min)

1. The login page appears. Click **Register new account**.
2. Enter:
   - Username: `demo_user`
   - Email: `demo@example.com`
   - Password: *(choose a secure password)*
3. Click **Register**. Observe:
   - Registration succeeds; you are redirected to login.
   - **Point out:** email must be `user@domain.tld` format (regex-validated).
     Try `bad@noext` — it is rejected.
4. Log in with `demo_user` and the password you just set.

**Talking point:** Passwords are bcrypt-hashed. Sessions use server-generated
tokens. Rate limiting locks out after 5 failed attempts for 5 minutes.

---

## Step 2: Import Synthetic Data (~1 min)

1. Navigate to the **Import Data** page (sidebar).
2. Click **Browse files** and select `data/transactions.csv`.
3. The preview table shows the first rows. Column mapping is auto-detected.
4. Click **Import**. Observe:
   - 93 rows imported, 0 skipped, 0 duplicates.
   - **Point out:** if you import the same file again, all 93 are detected as
     duplicates — the deduplication uses (date, merchant, amount, type).

**Talking point:** Import runs inside a database savepoint — if row 50 of 93
fails, rows 1–49 are rolled back automatically, and the import record is
saved with `status="failed"`.

---

## Step 3: Overview Dashboard (~2 min)

1. Navigate to **Overview** (sidebar).
2. Walk through the dashboard:
   - **4 KPI cards:** Total Spending, Total Income, Net Cash Flow, Total
     Transactions — all in INR with Indian digit grouping (₹1,25,000 format).
   - **Income vs Expenses chart** (monthly bars) — Plotly interactive.
   - **Spending by Category** (pie/donut) — hover for exact amounts.
   - **Top Merchants** (horizontal bar chart).
   - **Monthly Cash Flow** trend line.
3. Use the date-range selector to filter to a specific month.

**Talking point:** Every number is computed by Pandas/NumPy, never by an LLM.
The charts use Plotly. "Net Cash Flow" is income minus expenses — it is
clearly labeled, never called "account balance".

---

## Step 4: Transactions Page (~1 min)

1. Navigate to **Transactions** (sidebar).
2. Demonstrate:
   - **Search** by merchant name (e.g., "Zomato").
   - **Category filter** dropdown.
   - **Sort** by amount or date.
   - **Pagination** — 20 rows per page.
3. Show XSS safety: merchant names from the CSV are HTML-escaped when
   rendered.

---

## Step 5: Anomalies Page (~1 min)

1. Navigate to **Anomalies** (sidebar).
2. Show the flagged transactions. Expect ~11 anomalies across three methods:
   - **Statistical outliers:** amount > mean + 2 standard deviations.
   - **Duplicate-looking:** same merchant, near-identical amount, within 3
     days.
   - **Rapid burst:** 3+ large transactions (≥75th percentile) within 2 days.
3. Expand any anomaly to read the plain-English reason.

**Talking point:** These are statistical patterns, never called "fraud".
Every reason string explains the exact math — the threshold, the multiplier,
the percentile. No LLM involvement.

---

## Step 6: Insights Page (~30 sec)

1. Navigate to **Insights** (sidebar).
2. Show the deterministic insights:
   - Largest spending category and its percentage.
   - Expense-to-income ratio.
   - Most frequent merchant.
   - Count of unusual transactions.
3. All insights are backed by data — none are speculative.

---

## Step 7: AI Assistant (~2 min)

1. Navigate to **AI Assistant** (sidebar).
2. Ask these questions (works without any API key):
   - `"Show transactions above ₹50,000 from last month"`
     → filters, totals, category breakdown, template summary.
   - `"What did I spend on food?"`
     → category-specific spending analysis.
   - `"Any unusual transactions?"`
     → routes to anomaly detection agent.
   - `"How has my spending changed over time?"`
     → routes to trend analysis agent.
   - `"What about shopping?"` (follow-up)
     → resolves context from previous query.
3. Show the status indicator: "Deterministic mode" (no LLM) or the provider
   name if an API key is configured.

**Talking point:** The query parser converts natural language into a
`StructuredQuery` (Pydantic-validated). If an LLM is available, it extracts
intent/amount/date/category into JSON, which is re-validated. If no LLM is
available (or it fails), the deterministic regex/keyword parser produces the
same structured output. The LLM never touches the dataframe — it only reads
already-computed numbers.

---

## Step 8: User Isolation (~1 min)

1. Click **Logout**.
2. Register a second user: `demo_user2` / `user2@example.com` / *(choose a password)*.
3. Log in as `demo_user2`.
4. Navigate to Overview — **zero transactions**. No data from `demo_user`.
5. Navigate to AI Assistant, ask any question — confirms no cross-user data.

**Talking point:** Data isolation is enforced at the service/repository layer
(`DBTransactionRepository` always filters by `user_id`), not just the UI.
Even if you manipulate session state, the SQL query joins on the
authenticated user's account IDs.

---

## Step 9: Wrap-up (~30 sec)

- 253 automated tests cover all critical paths.
- The app works offline — no paid APIs, no internet, no real banking data.
- SQLite in dev, PostgreSQL supported for production.
- Alembic handles schema migrations.

---

## Quick Reference: Sample AI Assistant Questions

| Question | Intent Routed To |
|----------|-----------------|
| "Show transactions above ₹50,000" | `transaction_analysis` |
| "What did I spend last month?" | `spending_summary` |
| "Show my biggest expenses" | `top_expenses` |
| "How much did I spend on food?" | `category_spending` |
| "Any unusual transactions?" | `anomaly_detection` |
| "How has my spending changed?" | `trend_analysis` (agent) |
| "Compare this month to last" | `period_comparison` (agent) |
| "What insights can you give me?" | `insights_query` (agent) |
| "What about shopping?" | Follow-up (inherits prior context) |
