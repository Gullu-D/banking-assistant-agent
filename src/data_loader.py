"""
Transaction retrieval layer.

All CSV-loading, validation, and normalization logic lives here in
`TransactionRepository`. Nothing else in the application should read the CSV
directly — every other module receives an already-validated pandas
DataFrame (or a well-defined error) from this class.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config

logger = config.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class TransactionDataError(Exception):
    """Base class for all transaction-data related failures."""

    user_message: str = "An unexpected error occurred while loading transaction data."


class DatasetNotFoundError(TransactionDataError):
    def __init__(self, path: str):
        self.path = path
        self.user_message = (
            "Transaction dataset not found. "
            f"Expected a CSV file at '{path}'. Please make sure data/transactions.csv exists."
        )
        super().__init__(self.user_message)


class DatasetCorruptedError(TransactionDataError):
    def __init__(self, detail: str = ""):
        self.detail = detail
        self.user_message = (
            "Unable to read transaction data. Please verify the dataset format. "
            "The file may be corrupted or not a valid CSV."
        )
        super().__init__(self.user_message)


class MissingColumnsError(TransactionDataError):
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns
        cols = ", ".join(missing_columns)
        self.user_message = (
            f"The transaction dataset is missing required column(s): {cols}. "
            f"Expected columns: {', '.join(config.REQUIRED_COLUMNS)}."
        )
        super().__init__(self.user_message)


class EmptyDatasetError(TransactionDataError):
    def __init__(self):
        self.user_message = (
            "The transaction dataset is empty. There is no data available to analyze."
        )
        super().__init__(self.user_message)


# --------------------------------------------------------------------------- #
# Load report
# --------------------------------------------------------------------------- #


@dataclass
class LoadReport:
    """Describes what happened while loading/cleaning the dataset, so the UI
    can surface data-quality issues transparently instead of silently
    dropping rows.
    """

    total_rows_in_file: int = 0
    valid_rows: int = 0
    rows_with_invalid_date: int = 0
    rows_with_invalid_amount: int = 0
    rows_with_missing_required_fields: int = 0
    rows_with_invalid_type: int = 0
    categories_normalized: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_rows_skipped(self) -> int:
        return self.total_rows_in_file - self.valid_rows

    def has_issues(self) -> bool:
        return self.total_rows_skipped > 0 or bool(self.warnings)


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #


class TransactionRepository:
    """Loads, validates, and normalizes transaction data from CSV.

    Usage:
        repo = TransactionRepository("data/transactions.csv")
        df, report = repo.load()
    """

    def __init__(self, csv_path: str | None = None):
        self.csv_path = csv_path or config.TRANSACTIONS_CSV_PATH

    # ------------------------------------------------------------------ #
    def load(self) -> tuple[pd.DataFrame, LoadReport]:
        """Load and fully validate/normalize the transaction CSV.

        Returns:
            (dataframe, report) where dataframe has columns:
                transaction_id, date (datetime64), description, merchant,
                category, type, amount (float), account
            and is sorted by date ascending, with a clean RangeIndex.

        Raises:
            DatasetNotFoundError, DatasetCorruptedError, MissingColumnsError,
            EmptyDatasetError
        """
        raw_df = self._read_csv()
        self._validate_columns(raw_df)

        report = LoadReport(total_rows_in_file=len(raw_df))
        if report.total_rows_in_file == 0:
            raise EmptyDatasetError()

        df = raw_df.copy()

        df = self._normalize_dates(df, report)
        df = self._normalize_amounts(df, report)
        df = self._normalize_types(df, report)
        df = self._drop_missing_required(df, report)
        df = self._normalize_text_columns(df)

        report.valid_rows = len(df)

        if report.valid_rows == 0:
            raise EmptyDatasetError()

        df = df.sort_values("date", kind="stable").reset_index(drop=True)

        logger.info(
            "Loaded %d/%d transactions from %s (%d skipped)",
            report.valid_rows,
            report.total_rows_in_file,
            self.csv_path,
            report.total_rows_skipped,
        )
        return df, report

    # ------------------------------------------------------------------ #
    def _read_csv(self) -> pd.DataFrame:
        if not os.path.exists(self.csv_path):
            raise DatasetNotFoundError(self.csv_path)

        if os.path.getsize(self.csv_path) == 0:
            raise EmptyDatasetError()

        try:
            df = pd.read_csv(self.csv_path, dtype=str, keep_default_na=True)
        except pd.errors.EmptyDataError:
            raise EmptyDatasetError()
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
            logger.exception("Failed to parse transactions CSV")
            raise DatasetCorruptedError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - genuinely unexpected
            logger.exception("Unexpected error reading transactions CSV")
            raise DatasetCorruptedError(str(exc)) from exc

        return df

    # ------------------------------------------------------------------ #
    def _validate_columns(self, df: pd.DataFrame) -> None:
        missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise MissingColumnsError(missing)

    # ------------------------------------------------------------------ #
    def _normalize_dates(self, df: pd.DataFrame, report: LoadReport) -> pd.DataFrame:
        parsed = pd.to_datetime(df["date"], errors="coerce", format="mixed")
        invalid_mask = parsed.isna()
        n_invalid = int(invalid_mask.sum())
        if n_invalid:
            report.rows_with_invalid_date = n_invalid
            report.warnings.append(
                f"{n_invalid} row(s) had an invalid/unparseable date and were excluded."
            )
        df = df.assign(date=parsed.dt.normalize())
        return df[~invalid_mask].copy() if n_invalid else df

    # ------------------------------------------------------------------ #
    def _normalize_amounts(self, df: pd.DataFrame, report: LoadReport) -> pd.DataFrame:
        def clean_amount(val):
            if pd.isna(val):
                return np.nan
            s = str(val).strip()
            if not s:
                return np.nan
            # Strip currency symbols, commas, and whitespace: "₹1,25,000" -> "125000"
            s = s.replace("₹", "").replace(",", "").replace("Rs.", "").replace("INR", "").strip()
            try:
                return float(s)
            except ValueError:
                return np.nan

        cleaned = df["amount"].apply(clean_amount)
        invalid_mask = cleaned.isna() | (cleaned < 0)
        n_invalid = int(invalid_mask.sum())
        if n_invalid:
            report.rows_with_invalid_amount = n_invalid
            report.warnings.append(
                f"{n_invalid} row(s) had a missing/invalid amount and were excluded."
            )
        df = df.assign(amount=cleaned)
        return df[~invalid_mask].copy() if n_invalid else df

    # ------------------------------------------------------------------ #
    def _normalize_types(self, df: pd.DataFrame, report: LoadReport) -> pd.DataFrame:
        def clean_type(val):
            if pd.isna(val):
                return None
            s = str(val).strip().capitalize()
            return s if s in config.VALID_TYPES else None

        cleaned = df["type"].apply(clean_type)
        invalid_mask = cleaned.isna()
        n_invalid = int(invalid_mask.sum())
        if n_invalid:
            report.rows_with_invalid_type = n_invalid
            report.warnings.append(
                f"{n_invalid} row(s) had an invalid transaction type (expected Debit/Credit) and were excluded."
            )
        df = df.assign(type=cleaned)
        return df[~invalid_mask].copy() if n_invalid else df

    # ------------------------------------------------------------------ #
    def _drop_missing_required(self, df: pd.DataFrame, report: LoadReport) -> pd.DataFrame:
        critical_cols = ["transaction_id", "merchant", "category", "account"]
        missing_mask = pd.Series(False, index=df.index)
        for col in critical_cols:
            missing_mask = missing_mask | df[col].isna() | (df[col].astype(str).str.strip() == "")

        n_missing = int(missing_mask.sum())
        if n_missing:
            report.rows_with_missing_required_fields += n_missing
            report.warnings.append(
                f"{n_missing} row(s) had missing required fields and were excluded."
            )
        df = df[~missing_mask].copy()

        # Description is allowed to be missing -> default to a safe placeholder.
        df["description"] = df["description"].fillna("").astype(str).str.strip()
        df.loc[df["description"] == "", "description"] = "Transaction"

        # Duplicate transaction_ids are a data-quality issue worth flagging,
        # but we do not silently drop them (they might be legitimately
        # identical-looking transactions on different dates in bad source
        # data) — flag only if the SAME id repeats.
        dup_ids = df["transaction_id"][df["transaction_id"].duplicated()].unique()
        if len(dup_ids):
            report.warnings.append(
                f"{len(dup_ids)} duplicate transaction_id value(s) found in the source file."
            )

        return df

    # ------------------------------------------------------------------ #
    def _normalize_text_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ["merchant", "category", "account", "transaction_id"]:
            df[col] = df[col].astype(str).str.strip()
        return df
