"""
Tests for statistical/rule-based anomaly detection (src.anomaly_detector).
"""

import pandas as pd

from src.anomaly_detector import detect_anomalies


_COLUMNS = ["transaction_id", "date", "description", "merchant", "category", "type", "amount", "account"]


def _make_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_intentionally_high_value_transaction_is_flagged():
    # 20 normal transactions around ~2000, one deliberate outlier at 200000.
    rows = [
        dict(transaction_id=f"T{i}", date=f"2026-07-{(i % 27) + 1:02d}", description="d",
             merchant=f"Merchant{i}", category="Food & Dining", type="Debit", amount=2000 + i * 10, account="Primary")
        for i in range(20)
    ]
    rows.append(
        dict(transaction_id="OUTLIER", date="2026-07-15", description="d", merchant="ABC Electronics",
             category="Shopping", type="Debit", amount=200000, account="Primary")
    )
    df = _make_df(rows)

    anomalies = detect_anomalies(df)
    flagged_ids = {a.transaction_id for a in anomalies if a.anomaly_type == "statistical_outlier"}
    assert "OUTLIER" in flagged_ids


def test_normal_transactions_are_not_flagged():
    # Tight, consistent amounts -> low std dev -> no statistical outliers among them.
    rows = [
        dict(transaction_id=f"T{i}", date=f"2026-07-{(i % 27) + 1:02d}", description="d",
             merchant=f"Merchant{i}", category="Food & Dining", type="Debit", amount=1000 + i, account="Primary")
        for i in range(15)
    ]
    df = _make_df(rows)
    anomalies = detect_anomalies(df)
    statistical = [a for a in anomalies if a.anomaly_type == "statistical_outlier"]
    assert statistical == []


def test_duplicate_like_transactions_are_flagged():
    rows = [
        dict(transaction_id="T1", date="2026-07-10", description="d", merchant="Croma",
             category="Shopping", type="Debit", amount=54999, account="Primary"),
        dict(transaction_id="T2", date="2026-07-11", description="d", merchant="Croma",
             category="Shopping", type="Debit", amount=54999, account="Primary"),
    ]
    # pad with unrelated small transactions so std-dev based checks don't dominate
    rows += [
        dict(transaction_id=f"P{i}", date="2026-07-05", description="d", merchant=f"Other{i}",
             category="Food & Dining", type="Debit", amount=500 + i, account="Primary")
        for i in range(5)
    ]
    df = _make_df(rows)
    anomalies = detect_anomalies(df)
    dup_ids = {a.transaction_id for a in anomalies if a.anomaly_type == "duplicate_like"}
    assert {"T1", "T2"}.issubset(dup_ids)


def test_rapid_repeated_large_transactions_flagged():
    rows = [
        dict(transaction_id="R1", date="2026-07-10", description="d", merchant="Amazon",
             category="Shopping", type="Debit", amount=60000, account="Primary"),
        dict(transaction_id="R2", date="2026-07-10", description="d", merchant="Flipkart",
             category="Shopping", type="Debit", amount=61000, account="Primary"),
        dict(transaction_id="R3", date="2026-07-11", description="d", merchant="Myntra",
             category="Shopping", type="Debit", amount=62000, account="Primary"),
    ]
    rows += [
        dict(transaction_id=f"P{i}", date="2026-07-01", description="d", merchant=f"Other{i}",
             category="Food & Dining", type="Debit", amount=500 + i, account="Primary")
        for i in range(6)
    ]
    df = _make_df(rows)
    anomalies = detect_anomalies(df)
    rapid_ids = {a.transaction_id for a in anomalies if a.anomaly_type == "rapid_repeated_large"}
    assert {"R1", "R2", "R3"}.issubset(rapid_ids)


def test_credit_transactions_are_excluded_from_anomaly_detection():
    rows = [
        dict(transaction_id="INC", date="2026-07-10", description="d", merchant="Company Salary",
             category="Salary / Income", type="Credit", amount=500000, account="Primary"),
    ]
    rows += [
        dict(transaction_id=f"P{i}", date="2026-07-01", description="d", merchant=f"Other{i}",
             category="Food & Dining", type="Debit", amount=500 + i, account="Primary")
        for i in range(6)
    ]
    df = _make_df(rows)
    anomalies = detect_anomalies(df)
    assert all(a.transaction_id != "INC" for a in anomalies)


def test_empty_dataframe_returns_no_anomalies():
    df = _make_df([])
    assert detect_anomalies(df) == []


def test_small_sample_size_skips_statistical_check():
    # Fewer than MIN_SAMPLE_SIZE_FOR_STATS transactions -> should not flag
    # anything as a statistical outlier (not enough data for a reliable std dev).
    rows = [
        dict(transaction_id="T1", date="2026-07-01", description="d", merchant="M",
             category="Shopping", type="Debit", amount=1000, account="Primary"),
        dict(transaction_id="T2", date="2026-07-02", description="d", merchant="M2",
             category="Shopping", type="Debit", amount=100000, account="Primary"),
    ]
    df = _make_df(rows)
    anomalies = detect_anomalies(df)
    assert all(a.anomaly_type != "statistical_outlier" for a in anomalies)
