import os
import tempfile

from csv_parser import parse_csv
from algorithm import schedule, OUTLET_IDS, NO_OUTLET_IDS, PRIVATE_IDS

OUTLET_SET = set(OUTLET_IDS)
PRIVATE_SET = set(PRIVATE_IDS)


def _tmp_csv(content: str) -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(content)
        fname = f.name
    try:
        return parse_csv(fname)
    finally:
        os.unlink(fname)


def test_no_laptop_column_defaults_false():
    students = _tmp_csv(
        "name,start_time,end_time,private_room\n"
        "Alice,9:00 AM,12:00 PM,No\n"
        "Bob,9:00 AM,11:00 AM,Yes\n"
    )
    assert all(not s.uses_laptop for s in students)
    sched, unsched = schedule(students)
    assert len(sched) == 2 and len(unsched) == 0


def test_laptop_students_get_outlet_seats():
    students = parse_csv("sample_import.csv")
    sched, _ = schedule(students)
    for s in sched:
        if s.uses_laptop and not s.needs_private:
            assert s.assigned_seat in OUTLET_SET, (
                f"{s.name} (laptop) got non-outlet seat {s.assigned_seat}"
            )


def test_private_students_get_letter_seats():
    students = parse_csv("sample_import.csv")
    sched, _ = schedule(students)
    for s in sched:
        if s.needs_private:
            assert s.assigned_seat in PRIVATE_SET, (
                f"{s.name} (private) got seat {s.assigned_seat}"
            )


def test_no_double_bookings():
    students = parse_csv("sample_import.csv")
    sched, _ = schedule(students)
    seat_bookings: dict = {}
    for s in sched:
        seat_bookings.setdefault(s.assigned_seat, []).append((s.start, s.end))
    for sid, bks in seat_bookings.items():
        for i, (s1, e1) in enumerate(bks):
            for s2, e2 in bks[i + 1:]:
                assert e1 <= s2 or s1 >= e2, (
                    f"Seat {sid}: ({s1},{e1}) overlaps ({s2},{e2})"
                )


def test_non_laptop_falls_back_to_non_outlet_when_outlets_full():
    # 17 laptop students saturate all 16 outlet seats; 1 non-laptop should spill
    rows = "name,start_time,end_time,private_room,laptop\n"
    for i in range(17):
        rows += f"Laptop{i},9:00 AM,10:00 AM,No,Yes\n"
    rows += "NonLaptop,9:00 AM,10:00 AM,No,No\n"
    students = _tmp_csv(rows)
    sched, unsched = schedule(students)
    assert len(sched) == 18 and len(unsched) == 0
    nl = next(s for s in sched if not s.uses_laptop)
    assert nl.assigned_seat not in OUTLET_SET


def test_laptop_overflows_to_non_outlet_when_outlets_full():
    # 17 laptop students -> 16 get outlets, 1 must fall back to non-outlet
    rows = "name,start_time,end_time,private_room,laptop\n"
    for i in range(17):
        rows += f"Laptop{i},9:00 AM,10:00 AM,No,Yes\n"
    rows += "NonLaptop,9:00 AM,10:00 AM,No,No\n"
    students = _tmp_csv(rows)
    sched, _ = schedule(students)
    laptop_seats = [s.assigned_seat for s in sched if s.uses_laptop]
    outlet_count = sum(1 for sid in laptop_seats if sid in OUTLET_SET)
    non_outlet_count = sum(1 for sid in laptop_seats if sid not in OUTLET_SET)
    assert outlet_count == 16
    assert non_outlet_count == 1


def test_no_double_bookings_stress():
    students = parse_csv("sample_stress_import.csv")
    sched, _ = schedule(students)
    seat_bookings: dict = {}
    for s in sched:
        seat_bookings.setdefault(s.assigned_seat, []).append((s.start, s.end))
    for sid, bks in seat_bookings.items():
        for i, (s1, e1) in enumerate(bks):
            for s2, e2 in bks[i + 1:]:
                assert e1 <= s2 or s1 >= e2, (
                    f"Seat {sid}: ({s1},{e1}) overlaps ({s2},{e2})"
                )


if __name__ == "__main__":
    tests = [
        test_no_laptop_column_defaults_false,
        test_laptop_students_get_outlet_seats,
        test_private_students_get_letter_seats,
        test_no_double_bookings,
        test_no_double_bookings_stress,
        test_non_laptop_falls_back_to_non_outlet_when_outlets_full,
        test_laptop_overflows_to_non_outlet_when_outlets_full,
    ]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
