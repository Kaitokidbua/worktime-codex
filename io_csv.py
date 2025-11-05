"""CSV utilities for the attendance tracker."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from attendance import AttendanceIOError

EXPECTED_COLUMNS = [
    "date",
    "employee_id",
    "name",
    "clock_in",
    "clock_out",
    "breaks",
    "ot_hours",
    "shift_label",
]


def load_csv_records(path: str | Path) -> pd.DataFrame:
    """Load a CSV file into a DataFrame with the expected columns."""

    file_path = Path(path)
    if not file_path.exists():
        raise AttendanceIOError(f"CSV file not found: {file_path}")

    try:
        with file_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
    except Exception as exc:  # noqa: BLE001
        raise AttendanceIOError(f"Failed to read CSV: {exc}") from exc

    if not rows:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    for row in rows:
        for column in EXPECTED_COLUMNS:
            row.setdefault(column, None)

    return pd.DataFrame(rows, columns=EXPECTED_COLUMNS)
