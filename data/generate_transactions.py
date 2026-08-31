"""
Synthetic transaction data generator for the Banking Assistant Agent demo.

IMPORTANT: This script generates 100% SYNTHETIC, FICTIONAL banking data.
No real people, accounts, or financial information are used or represented.

Run this script to regenerate data/transactions.csv:
    python data/generate_transactions.py

The generated dataset is anchored relative to the current system date so that
"this month" / "last month" queries always have real data to work with.
"""

import csv
import random
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

random.seed(42)

TODAY = date.today()

# Anchor to the first day of the current month, then generate data for the
# previous full month, the month before that, and the current month so far.
THIS_MONTH_START = TODAY.replace(day=1)
LAST_MONTH_START = THIS_MONTH_START - relativedelta(months=1)
TWO_MONTHS_AGO_START = THIS_MONTH_START - relativedelta(months=2)

ACCOUNT = "Primary"

MERCHANTS = {
    "Food & Dining": ["Cafe Coffee Day", "Domino's Pizza", "Swiggy", "Zomato", "The Grand Kitchen", "Barbeque Nation"],
    "Groceries": ["BigBasket", "DMart", "Reliance Fresh", "More Supermarket", "Nature's Basket"],
    "Shopping": ["Amazon", "Flipkart", "Myntra", "ABC Electronics", "Croma", "Reliance Digital", "Lifestyle Stores"],
    "Travel": ["MakeMyTrip", "IndiGo Airlines", "Ola Cabs", "Uber", "IRCTC", "OYO Rooms"],
    "Rent": ["ABC Properties"],
    "Utilities": ["State Electricity Board", "Airtel Broadband", "Jio Fiber", "Municipal Water Dept"],
    "Healthcare": ["Apollo Pharmacy", "Fortis Hospital", "Dr. Lal PathLabs", "Max Healthcare"],
    "Education": ["Coursera", "Udemy", "Byju's", "City International School"],
    "Entertainment": ["BookMyShow", "Netflix", "Spotify", "PVR Cinemas"],
    "Investments": ["Zerodha", "Groww", "HDFC Mutual Fund"],
    "Transfers": ["UPI Transfer", "NEFT Transfer", "IMPS Transfer"],
    "Salary / Income": ["Company Salary"],
    "ATM / Cash Withdrawal": ["ATM Withdrawal"],
    "Other": ["Miscellaneous Payment"],
}

DESCRIPTIONS = {
    "Food & Dining": "Restaurant / food order",
    "Groceries": "Grocery purchase",
    "Shopping": "Online / retail purchase",
    "Travel": "Travel booking",
    "Rent": "Monthly rent",
    "Utilities": "Utility bill payment",
    "Healthcare": "Healthcare expense",
    "Education": "Education payment",
    "Entertainment": "Entertainment expense",
    "Investments": "Investment contribution",
    "Transfers": "Fund transfer",
    "Salary / Income": "Salary credit",
    "ATM / Cash Withdrawal": "Cash withdrawal",
    "Other": "Miscellaneous transaction",
}

rows = []
txn_counter = 1


def add_txn(d, category, merchant, amount, txn_type, description=None):
    global txn_counter
    rows.append(
        {
            "transaction_id": f"TXN{txn_counter:04d}",
            "date": d.isoformat(),
            "description": description or DESCRIPTIONS[category],
            "merchant": merchant,
            "category": category,
            "type": txn_type,
            "amount": amount,
            "account": ACCOUNT,
        }
    )
    txn_counter += 1


def month_end(start):
    nxt = start + relativedelta(months=1)
    return nxt - timedelta(days=1)


def random_day_in_month(start, cap_at_today=False):
    end = month_end(start)
    if cap_at_today and end > TODAY:
        end = TODAY
    span = (end - start).days
    if span <= 0:
        return start
    return start + timedelta(days=random.randint(0, span))


def generate_month(start, cap_at_today=False):
    # --- Recurring fixed transactions (always present, realistic) ---
    add_txn(start + timedelta(days=1), "Salary / Income", "Company Salary",
             round(random.uniform(85000, 95000), 2), "Credit")
    add_txn(start + timedelta(days=4), "Rent", "ABC Properties", 35000.00, "Debit")
    add_txn(start + timedelta(days=6), "Utilities", "State Electricity Board",
             round(random.uniform(1800, 3200), 2), "Debit")
    add_txn(start + timedelta(days=7), "Utilities", "Jio Fiber", 999.00, "Debit")
    add_txn(start + timedelta(days=9), "Investments", "Zerodha",
             round(random.uniform(10000, 20000), 2), "Debit")

    # --- Regular smaller transactions across the month ---
    small_categories = ["Food & Dining", "Groceries", "Entertainment", "Transfers", "ATM / Cash Withdrawal"]
    for _ in range(random.randint(18, 24)):
        category = random.choice(small_categories)
        merchant = random.choice(MERCHANTS[category])
        d = random_day_in_month(start, cap_at_today)
        if category == "Food & Dining":
            amount = round(random.uniform(250, 3500), 2)
        elif category == "Groceries":
            amount = round(random.uniform(500, 6500), 2)
        elif category == "Entertainment":
            amount = round(random.uniform(199, 2500), 2)
        elif category == "Transfers":
            amount = round(random.uniform(500, 15000), 2)
        else:  # ATM
            amount = round(random.choice([2000, 5000, 10000]), 2)
        add_txn(d, category, merchant, amount, "Debit")

    # --- A handful of high value (but "normal") transactions ---
    high_value_pool = ["Shopping", "Travel", "Healthcare", "Education"]
    for _ in range(random.randint(2, 4)):
        category = random.choice(high_value_pool)
        merchant = random.choice(MERCHANTS[category])
        d = random_day_in_month(start, cap_at_today)
        amount = round(random.uniform(15000, 60000), 2)
        add_txn(d, category, merchant, amount, "Debit")

    return start


# Generate three months of history: two months ago (full), last month (full),
# and this month so far (partial, capped at today).
generate_month(TWO_MONTHS_AGO_START, cap_at_today=False)
generate_month(LAST_MONTH_START, cap_at_today=False)
generate_month(THIS_MONTH_START, cap_at_today=True)

# --- Deliberately engineered anomalies inside LAST MONTH so the demo query
#     ("...transactions above 50,000 from last month...") reliably surfaces them.

# 1) A clear high-value outlier, well above the mean + 2*std of the dataset.
add_txn(LAST_MONTH_START + timedelta(days=12), "Shopping", "ABC Electronics", 185000.00, "Debit",
        description="Electronics purchase")

# 2) A second, less extreme but still unusual outlier.
add_txn(LAST_MONTH_START + timedelta(days=18), "Travel", "MakeMyTrip", 92000.00, "Debit",
        description="International flight booking")

# 3) Duplicate-looking transactions: same merchant, same amount, one day apart
#    (classic "was I charged twice?" scenario).
add_txn(LAST_MONTH_START + timedelta(days=20), "Shopping", "Croma", 54999.00, "Debit",
        description="Laptop purchase")
add_txn(LAST_MONTH_START + timedelta(days=21), "Shopping", "Croma", 54999.00, "Debit",
        description="Laptop purchase")

# 4) Rapid repeated large transactions within a short window (possible card
#    misuse pattern / rapid spending spree).
add_txn(LAST_MONTH_START + timedelta(days=25), "Shopping", "Amazon", 61000.00, "Debit")
add_txn(LAST_MONTH_START + timedelta(days=25), "Entertainment", "PVR Cinemas", 58000.00, "Debit",
        description="Event tickets bulk purchase")
add_txn(LAST_MONTH_START + timedelta(days=26), "Shopping", "Flipkart", 63500.00, "Debit")

# 5) A large, entirely legitimate education fee (high value but NOT an anomaly
#    once category context is considered) to test that not every high-value
#    transaction is flagged without justification.
add_txn(LAST_MONTH_START + timedelta(days=15), "Education", "City International School", 75000.00, "Debit",
        description="Term fee payment")

# --- A couple of intentionally messy rows to exercise failure handling.
# (Kept in a SEPARATE dirty file, not the main CSV, so the main dataset stays
#  clean — see data/transactions_dirty_sample.csv for the malformed-data test.)

rows.sort(key=lambda r: r["date"])

# Re-number transaction IDs in chronological order for readability.
for i, r in enumerate(rows, start=1):
    r["transaction_id"] = f"TXN{i:04d}"

fieldnames = ["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"]

with open("data/transactions.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} synthetic transactions -> data/transactions.csv")
print(f"Date range: {rows[0]['date']} to {rows[-1]['date']}")
print(f"Two months ago window starts: {TWO_MONTHS_AGO_START}")
print(f"Last month window: {LAST_MONTH_START} to {month_end(LAST_MONTH_START)}")
print(f"This month window (partial): {THIS_MONTH_START} to {TODAY}")

# --- Generate a small dirty/malformed CSV sample used by tests +
#     the app's failure-handling demo (missing columns, bad dates, bad amounts).
dirty_rows = [
    "transaction_id,date,description,merchant,category,type,amount,account",
    "TXN9001,2026-07-05,Suspicious row,Unknown Merchant,Shopping,Debit,not_a_number,Primary",
    "TXN9002,not-a-date,Bad date row,Unknown Merchant,Shopping,Debit,5000,Primary",
    "TXN9003,2026-07-06,Missing amount row,Unknown Merchant,Shopping,Debit,,Primary",
    "TXN9004,2026-07-07,Valid row among dirty data,Amazon,Shopping,Debit,12000,Primary",
]
with open("data/transactions_dirty_sample.csv", "w") as f:
    f.write("\n".join(dirty_rows) + "\n")

print("Generated data/transactions_dirty_sample.csv for failure-handling tests/demo")
