"""
CSV / XLSX import pipeline.

Reads an uploaded file into a DataFrame, validates rows, detects duplicates
against the user's existing transactions, and inserts valid rows into the
database. Returns a detailed result so the UI can show imported / skipped /
rejected counts.

Duplicate strategy: a row is considered a duplicate if the user already has a
transaction with the same date, merchant (case-insensitive), amount (exact to
the cent), and transaction type. This catches re-imports of the same file
without relying on external IDs that source files rarely include.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import config
from src.models import FinancialAccount, ImportRecord, Transaction

logger = config.get_logger(__name__)

MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = {"csv", "xlsx"}


@dataclass
class ImportResult:
    success: bool
    error: str = ""
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    rows_duplicate: int = 0
    warnings: list[str] = field(default_factory=list)
    import_id: int | None = None


# Column aliases: user-friendly source name -> our internal name
_COLUMN_ALIASES: dict[str, str] = {
    "transaction_id": "transaction_id",
    "id": "transaction_id",
    "trans_id": "transaction_id",
    "transaction_number": "transaction_id",
    "date": "date",
    "transaction_date": "date",
    "trans_date": "date",
    "description": "description",
    "desc": "description",
    "details": "description",
    "narrative": "description",
    "transaction_description": "description",
    "merchant": "merchant",
    "merchant_name": "merchant",
    "payee": "merchant",
    "category": "category",
    "type": "txn_type",
    "transaction_type": "txn_type",
    "trans_type": "txn_type",
    "dr_cr": "txn_type",
    "amount": "amount",
    "amt": "amount",
    "value": "amount",
    "debit_amount": "_debit_amount",
    "credit_amount": "_credit_amount",
    "account": "account",
    "account_name": "account",
    "location_city": "_location_city",
    "location_country": "_location_country",
    "balance": "_balance",
}

REQUIRED_IMPORT_COLUMNS = {"date", "amount"}


def detect_file_type(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in ALLOWED_EXTENSIONS else None


def read_upload(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame | None, str]:
    file_type = detect_file_type(filename)
    if not file_type:
        return None, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        return None, f"File exceeds {MAX_FILE_SIZE_MB} MB limit."
    if len(file_bytes) == 0:
        return None, "File is empty."

    try:
        if file_type == "csv":
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=True)
        else:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, keep_default_na=True, engine="openpyxl")
    except Exception as exc:
        logger.warning("Failed to read upload %s: %s", filename, exc)
        return None, f"Could not parse file: {exc}"

    if df.empty or len(df.columns) < 2:
        return None, "File has no usable data."
    return df, ""


def apply_column_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    rename = {}
    for src_col, tgt_col in mapping.items():
        if src_col in df.columns and tgt_col:
            rename[src_col] = tgt_col
    return df.rename(columns=rename)


def auto_map_columns(df: pd.DataFrame) -> dict[str, str]:
    mapping = {}
    for col in df.columns:
        normalized = col.strip().lower().replace(" ", "_")
        if normalized in _COLUMN_ALIASES:
            mapping[col] = _COLUMN_ALIASES[normalized]
    return mapping


def _merge_debit_credit_columns(df: pd.DataFrame) -> pd.DataFrame:
    """When the source has separate Debit Amount / Credit Amount columns
    instead of a single Amount, merge them into amount + txn_type."""
    if "_debit_amount" not in df.columns and "_credit_amount" not in df.columns:
        return df
    has_debit = "_debit_amount" in df.columns
    has_credit = "_credit_amount" in df.columns

    amounts = []
    types = []
    for _, row in df.iterrows():
        d = _parse_amount(row.get("_debit_amount")) if has_debit else None
        c = _parse_amount(row.get("_credit_amount")) if has_credit else None
        if d and d > 0:
            amounts.append(d)
            types.append("Debit")
        elif c and c > 0:
            amounts.append(c)
            types.append("Credit")
        else:
            amounts.append(None)
            types.append(None)

    df = df.copy()
    if "txn_type" in df.columns:
        df["_original_txn_code"] = df["txn_type"]
    df["amount"] = amounts
    df["txn_type"] = types
    df = df.drop(columns=[c for c in ("_debit_amount", "_credit_amount") if c in df.columns])
    return df


def _enrich_merchant_from_description(df: pd.DataFrame) -> pd.DataFrame:
    """When merchant is missing, use description as merchant name."""
    if "merchant" not in df.columns and "description" in df.columns:
        df = df.copy()
        df["merchant"] = df["description"]
    return df


def run_import(
    db: Session,
    user_id: int,
    account_id: int,
    df: pd.DataFrame,
    filename: str,
    file_type: str,
) -> ImportResult:
    result = ImportResult(success=False)

    account = db.get(FinancialAccount, account_id)
    if not account or account.user_id != user_id:
        result.error = "Account not found or access denied."
        return result

    import_rec = ImportRecord(
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        rows_total=len(df),
        status="pending",
    )
    db.add(import_rec)
    db.flush()

    df = _merge_debit_credit_columns(df)
    df = _enrich_merchant_from_description(df)

    try:
        valid_rows, skipped, warnings = _validate_and_normalize(df)
        result.rows_total = len(df)
        result.rows_skipped = skipped
        result.warnings = warnings

        if not valid_rows:
            import_rec.status = "failed"
            import_rec.error_message = "No valid rows after validation."
            import_rec.rows_skipped = skipped
            result.error = "No valid rows to import after validation."
            return result

        duplicates = _find_duplicates(db, user_id, valid_rows)
        result.rows_duplicate = len(duplicates)

        new_rows = [r for i, r in enumerate(valid_rows) if i not in duplicates]
        if not new_rows:
            import_rec.status = "complete"
            import_rec.rows_duplicate = len(duplicates)
            import_rec.rows_imported = 0
            result.success = True
            result.import_id = import_rec.id
            result.warnings.append("All rows were duplicates of existing transactions.")
            return result

        nested = db.begin_nested()
        try:
            for row in new_rows:
                txn = Transaction(
                    account_id=account_id,
                    import_id=import_rec.id,
                    date=row["date"],
                    description=row.get("description", "Transaction"),
                    merchant=row.get("merchant", "Unknown"),
                    category=row.get("category", "Other"),
                    txn_type=row.get("txn_type", "Debit"),
                    amount=row["amount"],
                    original_description=row.get("original_description"),
                    original_category=row.get("original_category"),
                    original_txn_code=row.get("original_txn_code"),
                    balance=row.get("balance"),
                    location_city=row.get("location_city"),
                    location_country=row.get("location_country"),
                )
                db.add(txn)
            db.flush()
            nested.commit()
        except Exception:
            nested.rollback()
            raise

        import_rec.status = "complete"
        import_rec.rows_imported = len(new_rows)
        import_rec.rows_skipped = skipped
        import_rec.rows_duplicate = len(duplicates)

        result.success = True
        result.rows_imported = len(new_rows)
        result.import_id = import_rec.id

    except Exception as exc:
        logger.exception("Import failed for %s", filename)
        import_rec.status = "failed"
        import_rec.error_message = str(exc)[:500]
        result.error = f"Import failed: {exc}"

    return result


def _validate_and_normalize(df: pd.DataFrame) -> tuple[list[dict], int, list[str]]:
    valid = []
    skipped = 0
    negative_count = 0
    warnings = []

    if "date" not in df.columns:
        return [], len(df), ["Missing required 'date' column."]
    if "amount" not in df.columns:
        return [], len(df), ["Missing required 'amount' column."]

    has_explicit_type = "txn_type" in df.columns or "type" in df.columns

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        original_desc = str(row_dict.get("description", ""))[:500] if pd.notna(row_dict.get("description")) else None

        parsed_date = _parse_date(row_dict.get("date"))
        if parsed_date is None:
            skipped += 1
            continue

        parsed_amount = _parse_amount(row_dict.get("amount"))
        if parsed_amount is None:
            skipped += 1
            continue
        if parsed_amount == 0:
            skipped += 1
            continue

        if parsed_amount < 0:
            if has_explicit_type:
                skipped += 1
                negative_count += 1
                continue
            negative_count += 1
            inferred_type = "Debit"
            parsed_amount = abs(parsed_amount)
        else:
            inferred_type = None

        explicit_type = _parse_type(row_dict.get("txn_type") or row_dict.get("type", ""))
        txn_type = explicit_type if has_explicit_type else (inferred_type or explicit_type)
        description = str(row_dict.get("description", "")).strip() if pd.notna(row_dict.get("description")) else "Transaction"
        if not description:
            description = "Transaction"
        merchant = str(row_dict.get("merchant", "")).strip() if pd.notna(row_dict.get("merchant")) else "Unknown"
        if not merchant:
            merchant = "Unknown"
        category = str(row_dict.get("category", "")).strip() if pd.notna(row_dict.get("category")) else "Other"
        if not category:
            category = "Other"

        entry = {
            "date": parsed_date,
            "amount": parsed_amount,
            "txn_type": txn_type,
            "description": description[:500],
            "merchant": merchant[:200],
            "category": category[:80],
            "original_description": original_desc,
            "original_category": category[:80] if category != "Other" else None,
        }
        otc = row_dict.get("_original_txn_code")
        if pd.notna(otc) and otc:
            entry["original_txn_code"] = str(otc).strip()[:20]
        bal = row_dict.get("_balance")
        if pd.notna(bal) and bal:
            try:
                entry["balance"] = round(float(str(bal).replace(",", "")), 2)
            except (TypeError, ValueError):
                pass
        loc_city = row_dict.get("_location_city")
        if pd.notna(loc_city) and loc_city:
            entry["location_city"] = str(loc_city).strip()[:100]
        loc_country = row_dict.get("_location_country")
        if pd.notna(loc_country) and loc_country:
            entry["location_country"] = str(loc_country).strip()[:100]
        valid.append(entry)

    if negative_count and has_explicit_type:
        warnings.append(
            f"{negative_count} row(s) had negative amounts and were skipped. "
            "When a type column is present, amounts must be positive."
        )
    elif negative_count:
        warnings.append(
            f"{negative_count} row(s) had negative amounts — stored as Debit with absolute value. "
            "Add a type/txn_type column (Credit/Debit) for full income vs expense tracking."
        )
    if skipped - negative_count > 0:
        warnings.append(f"{skipped - negative_count} row(s) skipped due to invalid date or amount.")
    return valid, skipped, warnings


def _parse_date(val) -> date | None:
    if pd.isna(val):
        return None
    try:
        return pd.Timestamp(str(val).strip()).date()
    except Exception:
        return None


def _parse_amount(val) -> float | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    s = s.replace("₹", "").replace(",", "").replace("Rs.", "").replace("INR", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _parse_type(val) -> str:
    if pd.isna(val):
        return "Debit"
    s = str(val).strip().capitalize()
    return s if s in ("Debit", "Credit") else "Debit"


def _find_duplicates(db: Session, user_id: int, rows: list[dict]) -> set[int]:
    if not rows:
        return set()

    user_account_ids = db.scalars(
        select(FinancialAccount.id).where(FinancialAccount.user_id == user_id)
    ).all()
    if not user_account_ids:
        return set()

    existing = db.execute(
        select(
            Transaction.date,
            func.lower(Transaction.merchant),
            Transaction.amount,
            Transaction.txn_type,
        ).where(Transaction.account_id.in_(user_account_ids))
    ).all()

    existing_set = {(r[0], r[1], float(r[2]), r[3]) for r in existing}

    dupes = set()
    for i, row in enumerate(rows):
        key = (row["date"], row["merchant"].lower(), float(row["amount"]), row["txn_type"])
        if key in existing_set:
            dupes.add(i)
        else:
            existing_set.add(key)
    return dupes
