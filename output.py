import csv
from models import Student

_PRIVATE_SEAT_COUNT = 3
_SHARED_SEAT_COUNT = 22


def _fmt(minutes: int) -> str:
    """Convert integer minutes-since-midnight to a 12-hour time string, e.g. '8:45 AM'."""
    h, m = divmod(minutes, 60)
    ampm = "AM" if h < 12 else "PM"
    h = h % 12 or 12
    return f"{h}:{m:02d} {ampm}"


def _conflict_info(student: Student, scheduled: list[Student]) -> tuple[str, list[Student]]:
    """Return (short reason string, list of scheduled students who conflict with this student)."""
    pool_size = _PRIVATE_SEAT_COUNT if student.needs_private else _SHARED_SEAT_COUNT
    pool_name = "private" if student.needs_private else "shared"
    conflicts = sorted(
        [
            st for st in scheduled
            if st.needs_private == student.needs_private
            and not (student.end <= st.start or student.start >= st.end)
        ],
        key=lambda st: st.start,
    )
    return f"All {pool_size} {pool_name} seats occupied", conflicts


def print_schedule(scheduled: list[Student], unscheduled: list[Student]) -> None:
    sorted_sched = sorted(scheduled, key=lambda s: (s.start, s.assigned_seat))

    print("\n=== SCHEDULED STUDENTS ===")
    if not sorted_sched:
        print("  (none)")
    else:
        print(f"{'SEAT':<6}{'NAME':<30}{'START':<12}{'END':<12}{'TYPE'}")
        print("-" * 70)
        for s in sorted_sched:
            room_type = "Private" if s.needs_private else "Shared"
            print(f"{s.assigned_seat:<6}{s.name:<30}{_fmt(s.start):<12}{_fmt(s.end):<12}{room_type}")

    print(f"\n=== UNSCHEDULED STUDENTS ({len(unscheduled)}) ===")
    if not unscheduled:
        print("  (none — all students scheduled)")
    else:
        print(f"{'NAME':<30}{'START':<12}{'END':<12}REASON")
        print("-" * 70)
        for s in sorted(unscheduled, key=lambda s: s.start):
            base_reason, conflicts = _conflict_info(s, scheduled)
            print(f"{s.name:<30}{_fmt(s.start):<12}{_fmt(s.end):<12}{base_reason}")
            if conflicts:
                names = ", ".join(st.name for st in conflicts[:4])
                if len(conflicts) > 4:
                    names += f" (+{len(conflicts) - 4} more)"
                print(f"    ↳ conflicts: {names}")

    total = len(scheduled) + len(unscheduled)
    print(f"\nSummary: {len(scheduled)}/{total} students scheduled, {len(unscheduled)} could not be placed.")

    _print_utilization(scheduled, unscheduled)


def _print_utilization(scheduled: list[Student], unscheduled: list[Student]) -> None:
    all_students = scheduled + unscheduled
    if not all_students:
        return

    day_start = min(s.start for s in all_students)
    day_end = max(s.end for s in all_students)
    window = day_end - day_start
    if window <= 0:
        return

    priv_all = [s for s in all_students if s.needs_private]
    shared_all = [s for s in all_students if not s.needs_private]

    priv_sched = [s for s in scheduled if s.needs_private]
    shared_sched = [s for s in scheduled if not s.needs_private]

    priv_booked = sum(s.end - s.start for s in priv_sched)
    shared_booked = sum(s.end - s.start for s in shared_sched)
    priv_cap = _PRIVATE_SEAT_COUNT * window
    shared_cap = _SHARED_SEAT_COUNT * window

    def peak_concurrent(students: list[Student]) -> int:
        events = []
        for s in students:
            events.append((s.start, 1))
            events.append((s.end, -1))
        events.sort()
        cur = pk = 0
        for _, delta in events:
            cur += delta
            pk = max(pk, cur)
        return pk

    priv_peak = peak_concurrent(priv_sched)
    shared_peak = peak_concurrent(shared_sched)

    print(f"\n=== SEAT UTILIZATION (window: {_fmt(day_start)}–{_fmt(day_end)}, {window} min) ===")
    if priv_all:
        print(
            f"  Private ({_PRIVATE_SEAT_COUNT} seats):  "
            f"{priv_booked:>6} / {priv_cap:>6} min booked "
            f"({priv_booked / priv_cap * 100:5.1f}%)  "
            f"peak {priv_peak}/{_PRIVATE_SEAT_COUNT} concurrent"
        )
    if shared_all:
        print(
            f"  Shared  ({_SHARED_SEAT_COUNT} seats):  "
            f"{shared_booked:>6} / {shared_cap:>6} min booked "
            f"({shared_booked / shared_cap * 100:5.1f}%)  "
            f"peak {shared_peak}/{_SHARED_SEAT_COUNT} concurrent"
        )


def write_csv(
    scheduled: list[Student],
    unscheduled: list[Student],
    path: str,
) -> None:
    extra_keys: list[str] = []
    for s in scheduled + unscheduled:
        for k in s.extra:
            if k not in extra_keys:
                extra_keys.append(k)

    base_fields = ["seat", "name", "start_time", "end_time", "private_room", "status", "reason"]
    fieldnames = base_fields + extra_keys

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for s in sorted(scheduled, key=lambda s: (s.start, s.assigned_seat)):
            row = {
                "seat": s.assigned_seat,
                "name": s.name,
                "start_time": _fmt(s.start),
                "end_time": _fmt(s.end),
                "private_room": "Yes" if s.needs_private else "No",
                "status": "Scheduled",
                "reason": "",
            }
            row.update(s.extra)
            writer.writerow(row)

        for s in sorted(unscheduled, key=lambda s: s.start):
            base_reason, conflicts = _conflict_info(s, scheduled)
            conflict_str = (
                "; conflicts: " + ", ".join(st.name for st in conflicts)
                if conflicts else ""
            )
            row = {
                "seat": "",
                "name": s.name,
                "start_time": _fmt(s.start),
                "end_time": _fmt(s.end),
                "private_room": "Yes" if s.needs_private else "No",
                "status": "Unscheduled",
                "reason": base_reason + conflict_str,
            }
            row.update(s.extra)
            writer.writerow(row)
