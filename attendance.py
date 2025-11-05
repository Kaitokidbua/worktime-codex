"""Attendance tracking CLI and time calculation utilities.

This module provides pure functions for time parsing and work-hour
calculations alongside a localized (Thai/English) command-line interface.
The business rules cover cross-midnight shifts, flexible breaks, overtime
adjustments, and Excel report generation.  The implementation intentionally
avoids heavyweight dependencies so that it can run in restricted execution
environments.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

TIME_FORMAT = "%H:%M"
DATE_FORMAT = "%d/%m/%Y"
DATA_FILE = Path("attendance_daily.csv")
EXCEL_REPORT = Path("attendance_report.xlsx")


class AttendanceError(Exception):
    """Base class for attendance-related errors."""


class AttendanceValidationError(AttendanceError):
    """Raised when input data fails validation rules."""


class AttendanceIOError(AttendanceError):
    """Raised when persistence operations fail."""


@dataclass(frozen=True)
class Interval:
    """Simple start/end wrapper for overlap math."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:  # pragma: no cover - dataclass guard
        if self.end < self.start:
            raise AttendanceValidationError("Interval end must be on or after start")


def parse_time(time_str: str) -> datetime:
    """Return a datetime anchored to 1900-01-01 for an HH:MM string."""

    if not isinstance(time_str, str):
        raise AttendanceValidationError("Time value must be a string in HH:MM format")
    try:
        return datetime.strptime(time_str.strip(), TIME_FORMAT)
    except ValueError as exc:  # noqa: BLE001 - provide domain specific error
        raise AttendanceValidationError(
            f"Invalid time format '{time_str}'. Expected HH:MM"
        ) from exc


def parse_date(date_str: str) -> date:
    """Return a date object parsed from DD/MM/YYYY."""

    if not isinstance(date_str, str):
        raise AttendanceValidationError("Date value must be a string in DD/MM/YYYY format")
    try:
        return datetime.strptime(date_str.strip(), DATE_FORMAT).date()
    except ValueError as exc:  # noqa: BLE001
        raise AttendanceValidationError(
            f"Invalid date format '{date_str}'. Expected DD/MM/YYYY"
        ) from exc


def normalize_interval(start: datetime, end: datetime) -> Interval:
    """Ensure the end falls after start by rolling into the next day if required."""

    if end <= start:
        end = end + timedelta(days=1)
    return Interval(start=start, end=end)


def overlap_duration(interval_a: Interval, interval_b: Interval) -> timedelta:
    """Return the overlapping duration between two intervals."""

    latest_start = max(interval_a.start, interval_b.start)
    earliest_end = min(interval_a.end, interval_b.end)
    if earliest_end <= latest_start:
        return timedelta(0)
    return earliest_end - latest_start


def _flatten_breaks(value: object) -> list[float]:
    """Convert various break representations into a list of hour floats."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (int, float)):
        if value < 0:
            raise AttendanceValidationError("Break duration cannot be negative")
        return [float(value)]
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in cleaned.replace(";", ",").split(",")]
        else:
            if not isinstance(parsed, list):
                parsed = [parsed]
        floats: list[float] = []
        for item in parsed:
            if isinstance(item, (int, float)):
                candidate = float(item)
            else:
                candidate = float(str(item).strip())
            if candidate < 0:
                raise AttendanceValidationError("Break duration cannot be negative")
            floats.append(candidate)
        return floats
    if isinstance(value, (list, tuple, set)):
        floats = []
        for item in value:
            candidate = float(item)
            if candidate < 0:
                raise AttendanceValidationError("Break duration cannot be negative")
            floats.append(candidate)
        return floats
    raise AttendanceValidationError("Unsupported break representation")


def _ensure_float(value: object, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:  # noqa: BLE001
        raise AttendanceValidationError(f"Field '{field_name}' must be numeric") from exc


def calc_work_hours(records: pd.DataFrame) -> pd.DataFrame:
    """Apply business rules and return normalized daily records.

    Parameters
    ----------
    records:
        A DataFrame containing the raw input rows with columns:
        date, employee_id, name, clock_in, clock_out, breaks, ot_hours,
        and optional shift_label.
    """

    required_columns = {"date", "employee_id", "name", "clock_in", "clock_out", "breaks", "ot_hours"}
    missing = required_columns - set(records.columns)
    if missing:
        raise AttendanceValidationError(f"Missing required columns: {sorted(missing)}")

    normalized_rows: list[dict[str, object]] = []

    for _, row in records.iterrows():
        work_date = parse_date(str(row["date"]))
        clock_in_dt = datetime.combine(work_date, parse_time(str(row["clock_in"])).time())
        clock_out_dt = datetime.combine(work_date, parse_time(str(row["clock_out"])).time())
        interval = normalize_interval(clock_in_dt, clock_out_dt)
        raw_hours = interval.end - interval.start

        breaks_list = _flatten_breaks(row["breaks"])
        break_total = sum(breaks_list)
        ot_hours = _ensure_float(row["ot_hours"], "ot_hours")
        if ot_hours < 0:
            raise AttendanceValidationError("Overtime hours cannot be negative")

        net_hours = raw_hours.total_seconds() / 3600 - break_total + ot_hours
        if net_hours < 0:
            raise AttendanceValidationError("Net worked hours cannot be negative")
        if net_hours > 16:
            raise AttendanceValidationError("Net worked hours cannot exceed 16 hours")

        normalized_rows.append(
            {
                "date": work_date,
                "employee_id": str(row["employee_id"]).strip(),
                "name": str(row["name"]).strip(),
                "shift_label": str(row.get("shift_label", "") or "").strip() or None,
                "clock_in": interval.start.strftime(TIME_FORMAT),
                "clock_out": interval.end.strftime(TIME_FORMAT),
                "break_total": round(break_total, 2),
                "ot_hours": round(ot_hours, 2),
                "work_hours": round(net_hours, 2),
            }
        )

    if not normalized_rows:
        return pd.DataFrame(
            columns=[
                "date",
                "employee_id",
                "name",
                "shift_label",
                "clock_in",
                "clock_out",
                "break_total",
                "ot_hours",
                "work_hours",
            ]
        )

    df = pd.DataFrame(normalized_rows)
    df.sort_values(by=["date", "employee_id"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def build_daily_summary(records: pd.DataFrame) -> pd.DataFrame:
    """Return daily summary sorted by date and employee."""

    columns = [
        "date",
        "employee_id",
        "name",
        "shift_label",
        "clock_in",
        "clock_out",
        "break_total",
        "ot_hours",
        "work_hours",
    ]
    missing = [col for col in columns if col not in records.columns]
    if missing:
        raise AttendanceValidationError(f"Records missing expected columns: {missing}")

    daily_rows: list[dict[str, object]] = []
    for _, row in records.iterrows():
        raw_date = row["date"]
        if isinstance(raw_date, datetime):
            day_value = raw_date.date()
        elif isinstance(raw_date, date):
            day_value = raw_date
        else:
            day_value = parse_date(str(raw_date))
        daily_rows.append(
            {
                "date": day_value,
                "employee_id": str(row["employee_id"]).strip(),
                "name": str(row["name"]).strip(),
                "shift_label": row.get("shift_label"),
                "clock_in": row["clock_in"],
                "clock_out": row["clock_out"],
                "break_total": float(row["break_total"]),
                "ot_hours": float(row["ot_hours"]),
                "work_hours": float(row["work_hours"]),
            }
        )

    daily_rows.sort(key=lambda item: (item["date"], item["employee_id"]))
    return pd.DataFrame(daily_rows, columns=columns)


def build_weekly_summary(records: pd.DataFrame) -> pd.DataFrame:
    """Aggregate totals Monday–Sunday."""

    daily = build_daily_summary(records)
    if daily.empty:
        return pd.DataFrame(
            columns=[
                "week_start",
                "week_end",
                "employee_id",
                "name",
                "work_hours_total",
                "ot_total",
                "days_present",
            ]
        )

    aggregates: dict[tuple[date, date, str, str], dict[str, object]] = {}
    for _, row in daily.iterrows():
        day_value = row["date"]
        week_start = day_value - timedelta(days=day_value.weekday())
        week_end = week_start + timedelta(days=6)
        key = (week_start, week_end, row["employee_id"], row["name"])
        aggregate = aggregates.setdefault(
            key,
            {
                "week_start": week_start,
                "week_end": week_end,
                "employee_id": row["employee_id"],
                "name": row["name"],
                "work_hours_total": 0.0,
                "ot_total": 0.0,
                "days_present": set(),
            },
        )
        aggregate["work_hours_total"] += float(row["work_hours"])
        aggregate["ot_total"] += float(row["ot_hours"])
        aggregate["days_present"].add(day_value)

    weekly_rows = []
    for value in aggregates.values():
        weekly_rows.append(
            {
                "week_start": value["week_start"],
                "week_end": value["week_end"],
                "employee_id": value["employee_id"],
                "name": value["name"],
                "work_hours_total": round(value["work_hours_total"], 2),
                "ot_total": round(value["ot_total"], 2),
                "days_present": len(value["days_present"]),
            }
        )

    weekly_rows.sort(key=lambda item: (item["week_start"], item["employee_id"]))
    return pd.DataFrame(
        weekly_rows,
        columns=[
            "week_start",
            "week_end",
            "employee_id",
            "name",
            "work_hours_total",
            "ot_total",
            "days_present",
        ],
    )


def build_monthly_summary(records: pd.DataFrame) -> pd.DataFrame:
    """Aggregate totals for each calendar month."""

    daily = build_daily_summary(records)
    if daily.empty:
        return pd.DataFrame(
            columns=[
                "month",
                "employee_id",
                "name",
                "work_hours_total",
                "ot_total",
                "days_present",
            ]
        )

    aggregates: dict[tuple[str, str, str], dict[str, object]] = {}
    for _, row in daily.iterrows():
        month_key = row["date"].strftime("%Y-%m")
        key = (month_key, row["employee_id"], row["name"])
        aggregate = aggregates.setdefault(
            key,
            {
                "month": month_key,
                "employee_id": row["employee_id"],
                "name": row["name"],
                "work_hours_total": 0.0,
                "ot_total": 0.0,
                "days_present": set(),
            },
        )
        aggregate["work_hours_total"] += float(row["work_hours"])
        aggregate["ot_total"] += float(row["ot_hours"])
        aggregate["days_present"].add(row["date"])

    monthly_rows = []
    for value in aggregates.values():
        monthly_rows.append(
            {
                "month": value["month"],
                "employee_id": value["employee_id"],
                "name": value["name"],
                "work_hours_total": round(value["work_hours_total"], 2),
                "ot_total": round(value["ot_total"], 2),
                "days_present": len(value["days_present"]),
            }
        )

    monthly_rows.sort(key=lambda item: (item["month"], item["employee_id"]))
    return pd.DataFrame(
        monthly_rows,
        columns=[
            "month",
            "employee_id",
            "name",
            "work_hours_total",
            "ot_total",
            "days_present",
        ],
    )


def load_daily_records() -> pd.DataFrame:
    """Load persisted daily records from CSV if present."""

    if not DATA_FILE.exists():
        return pd.DataFrame(
            columns=[
                "date",
                "employee_id",
                "name",
                "shift_label",
                "clock_in",
                "clock_out",
                "break_total",
                "ot_hours",
                "work_hours",
            ]
        )

    try:
        with DATA_FILE.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for record in reader:
                try:
                    day_value = parse_date(record["date"])
                except AttendanceValidationError as exc:
                    raise AttendanceIOError(f"Invalid date in stored data: {record['date']}") from exc
                rows.append(
                    {
                        "date": day_value,
                        "employee_id": record["employee_id"],
                        "name": record["name"],
                        "shift_label": record.get("shift_label") or None,
                        "clock_in": record["clock_in"],
                        "clock_out": record["clock_out"],
                        "break_total": float(record["break_total"] or 0),
                        "ot_hours": float(record["ot_hours"] or 0),
                        "work_hours": float(record["work_hours"] or 0),
                    }
                )
    except AttendanceIOError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AttendanceIOError(f"Failed to load data: {exc}") from exc

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "employee_id",
                "name",
                "shift_label",
                "clock_in",
                "clock_out",
                "break_total",
                "ot_hours",
                "work_hours",
            ]
        )
    return pd.DataFrame(rows)


def save_daily_records(records: pd.DataFrame) -> None:
    """Persist daily records to CSV using DD/MM/YYYY date format."""

    rows = []
    for _, row in records.iterrows():
        rows.append(
            {
                "date": row["date"].strftime(DATE_FORMAT),
                "employee_id": row["employee_id"],
                "name": row["name"],
                "shift_label": row.get("shift_label") or "",
                "clock_in": row["clock_in"],
                "clock_out": row["clock_out"],
                "break_total": row["break_total"],
                "ot_hours": row["ot_hours"],
                "work_hours": row["work_hours"],
            }
        )

    fieldnames = [
        "date",
        "employee_id",
        "name",
        "shift_label",
        "clock_in",
        "clock_out",
        "break_total",
        "ot_hours",
        "work_hours",
    ]
    try:
        with DATA_FILE.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as exc:  # noqa: BLE001
        raise AttendanceIOError(f"Failed to save data: {exc}") from exc


def write_excel_reports(daily: pd.DataFrame) -> None:
    """Create the Excel workbook with daily, weekly, and monthly sheets."""

    from openpyxl import Workbook

    daily_summary = build_daily_summary(daily)
    weekly_summary = build_weekly_summary(daily_summary)
    monthly_summary = build_monthly_summary(daily_summary)

    workbook = Workbook()
    # remove default sheet created by openpyxl
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    def _write_sheet(name: str, frame: pd.DataFrame, format_date: bool = False) -> None:
        worksheet = workbook.create_sheet(title=name)
        worksheet.append(frame.columns)
        for _, row in frame.iterrows():
            values: list[object] = []
            for column in frame.columns:
                value = row[column]
                if isinstance(value, date):
                    values.append(value.strftime(DATE_FORMAT) if format_date else value)
                else:
                    values.append(value)
            worksheet.append(values)

    _write_sheet("Daily", daily_summary, format_date=True)
    _write_sheet("Weekly", weekly_summary, format_date=True)
    _write_sheet("Monthly", monthly_summary)

    try:
        workbook.save(EXCEL_REPORT)
    except Exception as exc:  # noqa: BLE001
        raise AttendanceIOError(f"Failed to write Excel report: {exc}") from exc


def _prompt(text: str) -> str:
    return input(text).strip()


def _input_breaks() -> list[float]:
    raw = _prompt("กรอกช่วงพักเป็นชั่วโมง (คั่นด้วยจุลภาค / separate by comma) : ")
    try:
        return _flatten_breaks(raw)
    except AttendanceValidationError as exc:
        print(f"⚠️ ข้อมูลช่วงพักไม่ถูกต้อง: {exc}")
        return _input_breaks()


def _create_record_from_input() -> pd.DataFrame:
    print("\n--- บันทึกข้อมูลการเข้าออกงาน (Record attendance) ---")
    date_str = _prompt("วันที่ (DD/MM/YYYY): ")
    employee_id = _prompt("รหัสพนักงาน / Employee ID: ")
    name = _prompt("ชื่อพนักงาน / Name: ")
    shift_label = _prompt("กะการทำงาน (ใส่ได้ถ้ามี / optional shift label): ")
    clock_in = _prompt("เวลาเข้างาน (HH:MM): ")
    clock_out = _prompt("เวลาออกงาน (HH:MM): ")
    breaks = _input_breaks()
    ot_hours = _prompt("ชั่วโมง OT เพิ่มเติม (ถ้าไม่มีใส่ 0): ")

    record = pd.DataFrame(
        [
            {
                "date": date_str,
                "employee_id": employee_id,
                "name": name,
                "shift_label": shift_label,
                "clock_in": clock_in,
                "clock_out": clock_out,
                "breaks": breaks,
                "ot_hours": ot_hours or 0,
            }
        ]
    )
    return record


def _merge_records(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    columns: list[str] | None = None
    for frame in frames:
        if columns is None and frame.columns:
            columns = list(frame.columns)
        for _, row in frame.iterrows():
            if columns is None:
                columns = list(frame.columns)
            rows.append({col: row[col] for col in frame.columns})
    if columns is None:
        columns = [
            "date",
            "employee_id",
            "name",
            "shift_label",
            "clock_in",
            "clock_out",
            "break_total",
            "ot_hours",
            "work_hours",
        ]
    return pd.DataFrame(rows, columns=columns)


def _handle_record_single() -> pd.DataFrame:
    new_record = _create_record_from_input()
    try:
        processed = calc_work_hours(new_record)
    except AttendanceValidationError as exc:
        print(f"❌ ไม่สามารถบันทึกได้: {exc}")
        return pd.DataFrame()

    existing = load_daily_records()
    combined = _merge_records([existing, processed])
    save_daily_records(combined)
    print("✅ บันทึกข้อมูลสำเร็จ (Record saved).\n")
    return combined


def _handle_import_csv() -> pd.DataFrame:
    from io_csv import load_csv_records

    path = _prompt("ระบุไฟล์ CSV ที่ต้องการนำเข้า / Enter CSV path: ")
    try:
        imported = load_csv_records(path)
        processed = calc_work_hours(imported)
    except AttendanceError as exc:
        print(f"❌ นำเข้าไม่สำเร็จ: {exc}")
        return load_daily_records()

    existing = load_daily_records()
    combined = _merge_records([existing, processed])
    save_daily_records(combined)
    print("✅ นำเข้าข้อมูลสำเร็จ (Import successful).\n")
    return combined


def _handle_generate_reports() -> None:
    records = load_daily_records()
    if records.empty:
        print("⚠️ ยังไม่มีข้อมูลให้สร้างรายงาน (No data to summarize).\n")
        return
    try:
        write_excel_reports(records)
    except AttendanceIOError as exc:
        print(f"❌ ไม่สามารถสร้างไฟล์ Excel ได้: {exc}")
        return
    print(f"✅ สร้างไฟล์รายงานแล้วที่ {EXCEL_REPORT.resolve()}\n")


def _handle_export_filters() -> None:
    records = load_daily_records()
    if records.empty:
        print("⚠️ ยังไม่มีข้อมูลสำหรับส่งออก (No data available).\n")
        return
    choice = _prompt(
        "เลือกตัวกรอง: 1) ตามพนักงาน 2) ตามช่วงวันที่ / Choose filter (1 or 2): "
    )
    filtered_rows: list[dict[str, object]] = []
    if choice == "1":
        employee = _prompt("กรอกรหัสพนักงาน / Employee ID: ")
        for _, row in records.iterrows():
            if str(row["employee_id"]) == employee:
                filtered_rows.append({col: row[col] for col in records.columns})
    elif choice == "2":
        start = _prompt("วันที่เริ่ม (DD/MM/YYYY): ")
        end = _prompt("วันที่สิ้นสุด (DD/MM/YYYY): ")
        try:
            start_date = parse_date(start)
            end_date = parse_date(end)
        except AttendanceValidationError as exc:
            print(f"❌ ช่วงวันที่ไม่ถูกต้อง: {exc}")
            return
        for _, row in records.iterrows():
            day_value = row["date"] if isinstance(row["date"], date) else parse_date(str(row["date"]))
            if start_date <= day_value <= end_date:
                filtered_rows.append({col: row[col] for col in records.columns})
    else:
        print("⚠️ ตัวเลือกไม่ถูกต้อง (Invalid option).\n")
        return

    if not filtered_rows:
        print("⚠️ ไม่พบข้อมูลตามตัวกรอง (No matching records).\n")
        return

    export_path = _prompt("ระบุชื่อไฟล์ปลายทาง (เช่น export.csv): ") or "export.csv"
    fieldnames = records.columns
    try:
        with open(export_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in filtered_rows:
                row_copy = dict(row)
                if isinstance(row_copy.get("date"), date):
                    row_copy["date"] = row_copy["date"].strftime(DATE_FORMAT)
                writer.writerow(row_copy)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ ไม่สามารถบันทึกไฟล์ได้: {exc}")
        return
    print(f"✅ ส่งออกข้อมูลเรียบร้อย -> {Path(export_path).resolve()}\n")


def main() -> None:
    menu = (
        "\nระบบบันทึกเวลาทำงาน (Attendance Tracker)\n"
        "1) บันทึกข้อมูลเข้า-ออก / Record a single attendance entry\n"
        "2) นำเข้าจาก CSV / Import bulk records from CSV\n"
        "3) สร้างสรุปรายวัน-รายสัปดาห์-รายเดือน / Generate summaries to Excel\n"
        "4) ส่งออกรายงานตามพนักงานหรือช่วงวันที่ / Export filtered report\n"
        "0) ออกจากโปรแกรม / Exit\n"
    )

    while True:
        print(menu)
        choice = _prompt("เลือกเมนู (Enter choice): ")
        if choice == "1":
            _handle_record_single()
        elif choice == "2":
            _handle_import_csv()
        elif choice == "3":
            _handle_generate_reports()
        elif choice == "4":
            _handle_export_filters()
        elif choice == "0":
            print("ลาก่อน / Goodbye!")
            break
        else:
            print("⚠️ กรุณาเลือกเมนูที่ถูกต้อง (Please choose a valid option).\n")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
