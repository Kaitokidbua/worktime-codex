# attendance.py
from datetime import datetime

def calculate_work_hours(start_time, end_time, break_hours=1, ot_hours=0):
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    total_hours = (end - start).seconds / 3600
    net_hours = total_hours - break_hours + ot_hours
    return net_hours

if __name__ == "__main__":
    name = input("Enter employee name: ")
    start = input("Enter clock-in time (HH:MM): ")
    end = input("Enter clock-out time (HH:MM): ")
    break_h = float(input("Enter break hours: "))
    ot_h = float(input("Enter OT hours: "))

    hours = calculate_work_hours(start, end, break_h, ot_h)
    print(f"{name} worked {hours:.2f} hours today (including OT).")
