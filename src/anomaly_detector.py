"""
Transparent, rule-based / statistical anomaly detection.

No black box, no "ask the LLM to find anomalies". Three explicit, auditable
methods are used:

  1. Statistical outliers — a transaction whose amount exceeds
     `mean + ANOMALY_STD_MULTIPLIER * std_dev` of the transaction's own
     "normal" population (Debit/spending transactions in the analysis
     period).
  2. Duplicate-looking transactions — same merchant, near-identical amount,
     occurring within a small date window (possible double-charge).
  3. Rapid repeated large transactions — several large transactions
     (>= the 75th percentile) clustered within a short time window (possible
     spending spree / card misuse pattern).

Every flagged transaction carries a human-readable `reason` string
explaining exactly why it was flagged. Anomalies are described as
"potentially unusual" — never as "fraudulent".
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

import config
from src.formatting import format_inr
from src.validators import AnomalyRecord

logger = config.get_logger(__name__)

MIN_SAMPLE_SIZE_FOR_STATS = 5

_currency: str | None = None


def _format_amount(amount: float) -> str:
    return format_inr(amount, _currency)


def _detect_statistical_outliers(spend_df: pd.DataFrame) -> list[AnomalyRecord]:
    if len(spend_df) < MIN_SAMPLE_SIZE_FOR_STATS:
        return []

    mean = spend_df["amount"].mean()
    std = spend_df["amount"].std(ddof=0)
    if std == 0 or np.isnan(std):
        return []

    threshold = mean + config.ANOMALY_STD_MULTIPLIER * std
    high_threshold = mean + (config.ANOMALY_STD_MULTIPLIER + 1) * std

    outliers = spend_df[spend_df["amount"] > threshold]

    records = []
    for _, row in outliers.iterrows():
        ratio = row["amount"] / mean if mean > 0 else 0
        severity = "high" if row["amount"] > high_threshold else "moderate"
        reason = (
            f"This transaction of {_format_amount(row['amount'])} is about {ratio:.1f}x your "
            f"average transaction amount of {_format_amount(mean)} in this period "
            f"(threshold for flagging: mean + {config.ANOMALY_STD_MULTIPLIER:.0f} standard deviations "
            f"= {_format_amount(threshold)})."
        )
        records.append(
            AnomalyRecord(
                transaction_id=row["transaction_id"],
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                merchant=row["merchant"],
                category=row["category"],
                amount=float(row["amount"]),
                anomaly_type="statistical_outlier",
                reason=reason,
                severity=severity,
            )
        )
    return records


def _detect_duplicate_like(spend_df: pd.DataFrame) -> list[AnomalyRecord]:
    records: list[AnomalyRecord] = []
    flagged_pairs = set()

    for merchant, group in spend_df.groupby("merchant"):
        if len(group) < 2:
            continue
        rows = group.to_dict("records")
        for a, b in combinations(rows, 2):
            date_diff = abs((a["date"] - b["date"]).days)
            if date_diff > config.DUPLICATE_DATE_WINDOW_DAYS:
                continue
            amt_a, amt_b = a["amount"], b["amount"]
            if amt_a == 0:
                continue
            pct_diff = abs(amt_a - amt_b) / max(amt_a, amt_b)
            if pct_diff <= config.DUPLICATE_AMOUNT_TOLERANCE:
                for txn in (a, b):
                    key = txn["transaction_id"]
                    if key in flagged_pairs:
                        continue
                    flagged_pairs.add(key)
                    other = b if txn is a else a
                    reason = (
                        f"A near-identical transaction ({_format_amount(other['amount'])} at "
                        f"{other['merchant']} on {other['date'].strftime('%b %d, %Y')}) was found "
                        f"within {config.DUPLICATE_DATE_WINDOW_DAYS} day(s) — this may be an "
                        f"accidental duplicate charge."
                    )
                    records.append(
                        AnomalyRecord(
                            transaction_id=txn["transaction_id"],
                            date=txn["date"].date() if hasattr(txn["date"], "date") else txn["date"],
                            merchant=txn["merchant"],
                            category=txn["category"],
                            amount=float(txn["amount"]),
                            anomaly_type="duplicate_like",
                            reason=reason,
                            severity="moderate",
                        )
                    )
    return records


def _detect_rapid_repeated_large(spend_df: pd.DataFrame) -> list[AnomalyRecord]:
    if len(spend_df) < config.RAPID_MIN_COUNT:
        return []

    large_cutoff = spend_df["amount"].quantile(config.RAPID_LARGE_PERCENTILE)
    large_txns = spend_df[spend_df["amount"] >= large_cutoff].sort_values("date")

    if len(large_txns) < config.RAPID_MIN_COUNT:
        return []

    records: list[AnomalyRecord] = []
    flagged_ids: set[str] = set()
    rows = large_txns.to_dict("records")

    for i in range(len(rows)):
        window = [rows[i]]
        for j in range(i + 1, len(rows)):
            if (rows[j]["date"] - rows[i]["date"]).days <= config.RAPID_WINDOW_DAYS:
                window.append(rows[j])
            else:
                break
        if len(window) >= config.RAPID_MIN_COUNT:
            total = sum(t["amount"] for t in window)
            for txn in window:
                if txn["transaction_id"] in flagged_ids:
                    continue
                flagged_ids.add(txn["transaction_id"])
                reason = (
                    f"{len(window)} large transactions (each at/above the "
                    f"{int(config.RAPID_LARGE_PERCENTILE * 100)}th percentile of "
                    f"{_format_amount(large_cutoff)}) occurred within "
                    f"{config.RAPID_WINDOW_DAYS} day(s) of each other, totaling "
                    f"{_format_amount(total)} — an unusually fast spending burst."
                )
                records.append(
                    AnomalyRecord(
                        transaction_id=txn["transaction_id"],
                        date=txn["date"].date() if hasattr(txn["date"], "date") else txn["date"],
                        merchant=txn["merchant"],
                        category=txn["category"],
                        amount=float(txn["amount"]),
                        anomaly_type="rapid_repeated_large",
                        reason=reason,
                        severity="moderate",
                    )
                )
    return records


def detect_anomalies(df: pd.DataFrame, *, currency: str | None = None) -> list[AnomalyRecord]:
    """Run all anomaly detection methods over `df` (typically the
    period-scoped, categorized spending data — NOT limited to the user's
    amount-threshold filter, so the baseline "normal" pattern is meaningful).

    Only Debit (spending) transactions are considered; income/credits are
    excluded since anomaly detection here is about spending behavior.
    """
    global _currency
    _currency = currency

    if df.empty:
        return []

    spend_df = df[df["type"] == "Debit"].copy()
    if spend_df.empty:
        return []

    # Cash withdrawals are naturally, legitimately repetitive (same amount,
    # same "merchant", close together) — excluding them from the
    # duplicate/rapid-burst checks avoids noisy false positives while still
    # letting a genuinely oversized withdrawal trip the statistical check.
    non_cash_df = spend_df[spend_df["category"] != "ATM / Cash Withdrawal"]

    records: list[AnomalyRecord] = []
    records.extend(_detect_statistical_outliers(spend_df))
    records.extend(_detect_duplicate_like(non_cash_df))
    records.extend(_detect_rapid_repeated_large(non_cash_df))

    # De-duplicate identical (transaction_id, anomaly_type) pairs, keep order.
    seen = set()
    deduped = []
    for r in records:
        key = (r.transaction_id, r.anomaly_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # Sort by amount descending so the most significant anomalies appear first.
    deduped.sort(key=lambda r: r.amount, reverse=True)
    return deduped
