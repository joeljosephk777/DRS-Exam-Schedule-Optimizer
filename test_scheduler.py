import os
import tempfile

from csv_parser import parse_csv
from algorithm import (
    schedule, OUTLET_IDS, NO_OUTLET_IDS, PRIVATE_IDS, FURNITURE_IDS, ADJACENCY,
    _anti_cheat_pass, _build_seats,
)
from models import Student as _Student

OUTLET_SET = set(OUTLET_IDS)
PRIVATE_SET = set(PRIVATE_IDS)
FURNITURE_SET = set(FURNITURE_IDS)


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


def test_furniture_students_get_seats_17_18():
    rows = "name,start_time,end_time,private_room,furniture\n"
    rows += "FurnA,9:00 AM,11:00 AM,No,Yes\n"
    rows += "FurnB,9:00 AM,11:00 AM,No,Yes\n"
    for i in range(10):
        rows += f"Regular{i},9:00 AM,11:00 AM,No,No\n"
    students = _tmp_csv(rows)
    sched, unsched = schedule(students)
    assert len(unsched) == 0
    for s in sched:
        if s.needs_furniture:
            assert s.assigned_seat in FURNITURE_SET, (
                f"{s.name} (furniture) got seat {s.assigned_seat}, expected 17 or 18"
            )


def test_low_vision_gets_room_c():
    rows = "name,start_time,end_time,private_room,low_vision\n"
    rows += "LowVision,9:00 AM,11:00 AM,Yes,Yes\n"
    students = _tmp_csv(rows)
    sched, _ = schedule(students)
    assert len(sched) == 1
    assert sched[0].assigned_seat == "c", f"Expected room c, got {sched[0].assigned_seat}"


def test_service_animal_gets_room_e():
    rows = "name,start_time,end_time,private_room,service_animal\n"
    rows += "ServiceAnimal,9:00 AM,11:00 AM,Yes,Yes\n"
    students = _tmp_csv(rows)
    sched, _ = schedule(students)
    assert len(sched) == 1
    assert sched[0].assigned_seat == "e", f"Expected room e, got {sched[0].assigned_seat}"


def test_feature_fallback():
    # Seats 17 and 18 fully occupied; third furniture student falls back to any available seat
    rows = "name,start_time,end_time,private_room,furniture\n"
    rows += "FurnA,9:00 AM,12:00 PM,No,Yes\n"
    rows += "FurnB,9:00 AM,12:00 PM,No,Yes\n"
    rows += "FurnC,9:00 AM,11:00 AM,No,Yes\n"
    students = _tmp_csv(rows)
    sched, unsched = schedule(students)
    assert len(unsched) == 0, f"Expected all scheduled; unscheduled: {[s.name for s in unsched]}"
    assert len(sched) == 3
    assigned = [s.assigned_seat for s in sched]
    assert len(set(assigned)) == 3, "Each student must have a distinct seat"


def _drs_csv(rows: list[tuple]) -> list:
    """Build a minimal DRS-format CSV (Last Name, Preferred Name, CRN, Start Time, End Time)."""
    header = "Last Name,Preferred Name,CRN,Start Time,End Time,Exam Type,SVC - * Private Room for Assessments\n"
    body = "".join(
        f"{last},{first},{crn},{start},{end},Written,No\n"
        for last, first, crn, start, end in rows
    )
    return _tmp_csv(header + body)


def test_same_crn_not_adjacent():
    # 2 students with the same CRN and overlapping times must not end up in adjacent seats
    students = _drs_csv([
        ("Smith", "Alice", "99999", "9:00 AM", "11:00 AM"),
        ("Jones", "Bob",   "99999", "9:00 AM", "11:00 AM"),
    ])
    sched, _ = schedule(students)
    assert len(sched) == 2
    a, b = sched[0].assigned_seat, sched[1].assigned_seat
    assert b not in ADJACENCY.get(a, []), (
        f"Same-CRN students placed in adjacent seats {a} and {b}"
    )


def test_same_crn_conflict_flagged():
    # Directly place two same-CRN students in adjacent seats 5 & 8, fill every
    # other shared seat so relocation is impossible, then verify the flag is set.
    seats = _build_seats()
    S, E = 540, 660  # 9:00–11:00 AM

    a = _Student(name="CrnA", start=S, end=E, needs_private=False, uses_laptop=False, crn="TEST")
    b = _Student(name="CrnB", start=S, end=E, needs_private=False, uses_laptop=False, crn="TEST")
    seats[5].book(S, E); a.assigned_seat = 5
    seats[8].book(S, E); b.assigned_seat = 8

    fillers = []
    for sid in OUTLET_IDS + NO_OUTLET_IDS:
        if sid not in (5, 8):
            f = _Student(name=f"F{sid}", start=S, end=E, needs_private=False, uses_laptop=False)
            seats[sid].book(S, E); f.assigned_seat = sid
            fillers.append(f)

    _anti_cheat_pass(fillers + [a, b], seats)
    assert b.adjacency_conflict, "CrnB should be flagged — no free non-adjacent seat"
    assert not a.adjacency_conflict, "CrnA (the anchor) should not be flagged"


if __name__ == "__main__":
    tests = [
        test_no_laptop_column_defaults_false,
        test_laptop_students_get_outlet_seats,
        test_private_students_get_letter_seats,
        test_no_double_bookings,
        test_no_double_bookings_stress,
        test_non_laptop_falls_back_to_non_outlet_when_outlets_full,
        test_laptop_overflows_to_non_outlet_when_outlets_full,
        test_furniture_students_get_seats_17_18,
        test_low_vision_gets_room_c,
        test_service_animal_gets_room_e,
        test_feature_fallback,
        test_same_crn_not_adjacent,
        test_same_crn_conflict_flagged,
    ]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
