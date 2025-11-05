# Worktime Codex

A bilingual (Thai/English) attendance-tracking toolkit for capturing daily time
entries, aggregating weekly/monthly summaries, and exporting Excel reports.

## Features

- Pure, unit-testable time utilities for parsing and interval math.
- Robust handling of cross-midnight shifts, flexible breaks, and overtime.
- Command-line menu with Thai prompts and localized error feedback.
- Excel report generation with Daily/Weekly/Monthly sheets.
- CSV import/export for integrating with other systems.

## Getting Started

Install the dependencies:

```bash
pip install pandas openpyxl pytest
```

Run the CLI:

```bash
python attendance.py
```

### Example Session (English)

```
Attendance Tracker
1) Record a single attendance entry
2) Import bulk records from CSV
3) Generate summaries to Excel
4) Export filtered report
0) Exit
Enter choice: 1
Date (DD/MM/YYYY): 01/07/2024
Employee ID: E001
Name: Alice
Shift label (optional): Day
Clock-in (HH:MM): 08:00
Clock-out (HH:MM): 17:30
Breaks in hours (comma separated): 1,0.5
Additional OT hours: 1
✅ Record saved
```

### ตัวอย่างการใช้งาน (ภาษาไทย)

```
ระบบบันทึกเวลาทำงาน
1) บันทึกข้อมูลเข้า-ออก
2) นำเข้าจาก CSV
3) สร้างสรุปรายวัน-รายสัปดาห์-รายเดือน
4) ส่งออกรายงาน
0) ออกจากโปรแกรม
เลือกเมนู: 1
วันที่ (DD/MM/YYYY): 01/07/2024
รหัสพนักงาน: E001
ชื่อพนักงาน: สมชาย
กะการทำงาน: เช้า
เวลาเข้างาน (HH:MM): 08:00
เวลาออกงาน (HH:MM): 17:30
กรอกช่วงพักเป็นชั่วโมง (คั่นด้วยจุลภาค): 1,0.5
ชั่วโมง OT เพิ่มเติม: 1
✅ บันทึกข้อมูลสำเร็จ
```

### Sample Data

A sample CSV for bulk import is available at `samples/timesheet_sample.csv`.

## Testing

```bash
python -m compileall attendance.py
pytest -q
```

## Future Improvements

- Integrate Thai Buddhist calendar date parsing.
- Support official holiday calendars for automatic overtime tagging.
- Expand CSV import to map custom column headings.
