"""Unit tests for attendance time calculations."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from attendance import AttendanceValidationError, calc_work_hours


def _df(**kwargs):
    return pd.DataFrame([kwargs])


def test_regular_shift_with_ot():
    records = _df(
        date="01/07/2024",
        employee_id="E001",
        name="Alice",
        clock_in="08:00",
        clock_out="17:00",
        breaks=1,
        ot_hours=2,
        shift_label="Day",
    )
    result = calc_work_hours(records)
    assert pytest.approx(result.iloc[0]["work_hours"], rel=1e-4) == 10.0


def test_cross_midnight_shift():
    records = _df(
        date="01/07/2024",
        employee_id="E002",
        name="Bob",
        clock_in="19:00",
        clock_out="04:00",
        breaks=1,
        ot_hours=0,
        shift_label="Night",
    )
    result = calc_work_hours(records)
    assert pytest.approx(result.iloc[0]["work_hours"], rel=1e-4) == 8.0


def test_long_day_with_lunch_break():
    records = _df(
        date="01/07/2024",
        employee_id="E003",
        name="Chai",
        clock_in="08:30",
        clock_out="18:00",
        breaks=1,
        ot_hours=0,
        shift_label="Day",
    )
    result = calc_work_hours(records)
    assert pytest.approx(result.iloc[0]["work_hours"], rel=1e-4) == 8.5


def test_invalid_time_raises():
    records = _df(
        date="01/07/2024",
        employee_id="E004",
        name="Dana",
        clock_in="25:00",
        clock_out="18:00",
        breaks=1,
        ot_hours=0,
        shift_label="Day",
    )
    with pytest.raises(AttendanceValidationError):
        calc_work_hours(records)
