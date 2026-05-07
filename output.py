import csv
import html as _html
import math
from models import Student
from algorithm import PRIVATE_IDS, OUTLET_IDS, NO_OUTLET_IDS

_PRIVATE_SEAT_COUNT = len(PRIVATE_IDS)
_SHARED_SEAT_COUNT = len(OUTLET_IDS) + len(NO_OUTLET_IDS)


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


def _seat_sort_key(seat_id):
    """Sort ints before strings; within each group, natural order."""
    return (isinstance(seat_id, str), seat_id)


def print_schedule(scheduled: list[Student], unscheduled: list[Student]) -> None:
    sorted_sched = sorted(scheduled, key=lambda s: (s.start, _seat_sort_key(s.assigned_seat)))

    print("\n=== SCHEDULED STUDENTS ===")
    if not sorted_sched:
        print("  (none)")
    else:
        print(f"{'SEAT':<6}{'NAME':<30}{'START':<12}{'END':<12}{'LAPTOP':<8}{'TYPE'}")
        print("-" * 78)
        for s in sorted_sched:
            room_type = "Private" if s.needs_private else "Shared"
            laptop_str = "Yes" if s.uses_laptop else "No"
            print(f"{str(s.assigned_seat):<6}{s.name:<30}{_fmt(s.start):<12}{_fmt(s.end):<12}{laptop_str:<8}{room_type}")

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

    flagged = [s for s in scheduled if s.adjacency_conflict]
    if flagged:
        print(f"\n=== ADJACENCY WARNINGS ({len(flagged)}) ===")
        print("  Same-exam students could not be fully separated (room was too full):")
        for s in flagged:
            print(f"  ! {s.name}  seat {s.assigned_seat}  CRN {s.crn}")

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

    base_fields = ["seat", "name", "start_time", "end_time", "private_room", "laptop", "adj_conflict", "status", "reason"]
    fieldnames = base_fields + extra_keys

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for s in sorted(scheduled, key=lambda s: (s.start, _seat_sort_key(s.assigned_seat))):
            row = {
                "seat": s.assigned_seat,
                "name": s.name,
                "start_time": _fmt(s.start),
                "end_time": _fmt(s.end),
                "private_room": "Yes" if s.needs_private else "No",
                "laptop": "Yes" if s.uses_laptop else "No",
                "adj_conflict": "Yes" if s.adjacency_conflict else "",
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
                "laptop": "Yes" if s.uses_laptop else "No",
                "adj_conflict": "",
                "status": "Unscheduled",
                "reason": base_reason + conflict_str,
            }
            row.update(s.extra)
            writer.writerow(row)


_CHART_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f7; color: #1a1a1a; padding: 24px; }
h1 { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
.meta { font-size: 13px; color: #666; margin-bottom: 12px; }
.legend { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }
.chart-outer { overflow-x: auto; border: 1px solid #ddd; border-radius: 8px; background: #fff; }
table.chart-table { border-collapse: collapse; }
.label-cell {
  position: sticky; left: 0; background: #fff; z-index: 2;
  width: 90px; min-width: 90px; max-width: 90px;
  padding: 0 10px; font-size: 12px; font-weight: 500;
  border-right: 1px solid #e0e0e0; white-space: nowrap; vertical-align: middle;
}
.lane-cell { padding: 0; vertical-align: top; }
.axis-row .label-cell { height: 34px; background: #f9f9f9; font-size: 11px; color: #888; }
.group-row .label-cell { font-size: 10px; font-weight: 700; color: #555; text-transform: uppercase; letter-spacing: 0.5px; background: #f0f0f0; height: 22px; }
.group-row .lane-cell { background: #f0f0f0; }
.seat-row { border-top: 1px solid #ebebeb; }
.seat-row.empty .label-cell { color: #bbb; font-weight: 400; }
.lane { position: relative; height: 40px; }
.seat-row.empty .lane { height: 26px; }
.time-axis { position: relative; height: 34px; border-bottom: 1px solid #ddd; background: #f9f9f9; }
.tick { position: absolute; top: 6px; font-size: 10px; color: #888; transform: translateX(-50%); white-space: nowrap; }
.tick::after { content: ""; position: absolute; bottom: -8px; left: 50%; width: 1px; height: 7px; background: #ccc; }
.bar {
  position: absolute; top: 5px; bottom: 5px; border-radius: 4px;
  display: flex; align-items: center; padding: 0 6px;
  font-size: 11px; color: #fff; overflow: visible; cursor: default;
  transition: filter 0.1s; min-width: 3px;
}
.bar:hover { filter: brightness(1.15); z-index: 10; }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.bar-private   { background: #7c4dbd; }
.bar-outlet    { background: #2a7ae2; }
.bar-no-outlet { background: #2a9e6a; }
.tooltip {
  display: none; position: absolute; bottom: calc(100% + 8px); left: 50%;
  transform: translateX(-50%); background: #1a1a1a; color: #fff;
  padding: 7px 11px; border-radius: 6px; white-space: pre; font-size: 12px;
  z-index: 100; pointer-events: none; line-height: 1.6; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.bar:hover .tooltip { display: block; }
h2 { font-size: 15px; font-weight: 600; margin: 24px 0 10px; }
.unsched-table { border-collapse: collapse; font-size: 12px; width: 100%; max-width: 760px; }
.unsched-table th { text-align: left; padding: 6px 12px; background: #f2f2f2; border-bottom: 2px solid #ddd; font-weight: 600; }
.unsched-table td { padding: 6px 12px; border-bottom: 1px solid #ebebeb; }
.unsched-table tr:last-child td { border-bottom: none; }
.no-unsched { font-size: 13px; color: #666; }
"""


def _render_bars(students: list, seat_type: str, t_start: int, duration: int) -> str:
    bars = []
    for s in students:
        left_pct = (s.start - t_start) / duration * 100
        width_pct = (s.end - s.start) / duration * 100
        tooltip = _html.escape(
            f"{s.name}\n{_fmt(s.start)} – {_fmt(s.end)}\n"
            f"{'Private room' if s.needs_private else 'Shared'} | Laptop: {'Yes' if s.uses_laptop else 'No'}"
        )
        bars.append(
            f'<div class="bar bar-{seat_type}" style="left:{left_pct:.2f}%;width:{width_pct:.2f}%">'
            f'<span class="bar-label">{_html.escape(s.name)}</span>'
            f'<span class="tooltip">{tooltip}</span>'
            f'</div>'
        )
    return "".join(bars)


def write_chart(
    scheduled: list[Student],
    unscheduled: list[Student],
    path: str,
) -> None:
    all_students = scheduled + unscheduled
    if not all_students:
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><head><meta charset="utf-8"><title>DRS Schedule</title></head>'
                    '<body><p style="padding:24px;font-family:sans-serif">No students to display.</p></body></html>')
        return

    t_start = min(s.start for s in all_students)
    t_end = max(s.end for s in all_students)
    duration = t_end - t_start
    chart_width = max(800, duration * 2)

    bookings_by_seat: dict = {}
    for s in sorted(scheduled, key=lambda x: x.start):
        bookings_by_seat.setdefault(s.assigned_seat, []).append(s)

    p = []
    p.append('<!DOCTYPE html>')
    p.append('<html lang="en"><head><meta charset="utf-8">')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append('<title>DRS Exam Schedule — Gantt Chart</title>')
    p.append(f'<style>{_CHART_CSS}</style></head><body>')
    p.append('<h1>DRS Exam Schedule</h1>')
    p.append(
        f'<div class="meta">{_fmt(t_start)} – {_fmt(t_end)}'
        f' &nbsp;|&nbsp; {len(scheduled)} scheduled, {len(unscheduled)} unscheduled</div>'
    )

    p.append('<div class="legend">')
    p.append('<div class="legend-item"><div class="legend-swatch" style="background:#7c4dbd"></div><span>Private room</span></div>')
    p.append('<div class="legend-item"><div class="legend-swatch" style="background:#2a7ae2"></div><span>Shared — outlet</span></div>')
    p.append('<div class="legend-item"><div class="legend-swatch" style="background:#2a9e6a"></div><span>Shared — no outlet</span></div>')
    p.append('</div>')

    p.append('<div class="chart-outer"><table class="chart-table" cellspacing="0">')

    # Time axis row
    p.append('<tr class="axis-row"><td class="label-cell">Time ►</td><td class="lane-cell">')
    p.append(f'<div class="time-axis" style="width:{chart_width}px">')
    tick = math.ceil(t_start / 30) * 30
    while tick <= t_end:
        left_pct = (tick - t_start) / duration * 100
        p.append(f'<div class="tick" style="left:{left_pct:.2f}%">{_fmt(tick)}</div>')
        tick += 30
    p.append('</div></td></tr>')

    groups = [
        ("Private Rooms", [(sid, "private") for sid in PRIVATE_IDS]),
        ("Shared — Outlet", [(sid, "outlet") for sid in OUTLET_IDS]),
        ("Shared — No Outlet", [(sid, "no-outlet") for sid in NO_OUTLET_IDS]),
    ]

    for group_name, seats_in_group in groups:
        p.append(f'<tr class="group-row"><td class="label-cell">{_html.escape(group_name)}</td>'
                 f'<td class="lane-cell" style="width:{chart_width}px"></td></tr>')
        for sid, seat_type in seats_in_group:
            students_here = bookings_by_seat.get(sid, [])
            row_cls = "seat-row" + ("" if students_here else " empty")
            label = f"Room {sid}" if isinstance(sid, str) else f"Seat {sid}"
            bars = _render_bars(students_here, seat_type, t_start, duration)
            p.append(
                f'<tr class="{row_cls}"><td class="label-cell">{label}</td>'
                f'<td class="lane-cell"><div class="lane" style="width:{chart_width}px">{bars}</div></td></tr>'
            )

    p.append('</table></div>')

    # Unscheduled section
    p.append('<h2>Unscheduled Students</h2>')
    if not unscheduled:
        p.append('<p class="no-unsched">All students were scheduled.</p>')
    else:
        p.append('<table class="unsched-table"><tr><th>Name</th><th>Start</th><th>End</th><th>Type</th><th>Reason</th></tr>')
        for s in sorted(unscheduled, key=lambda x: x.start):
            base_reason, conflicts = _conflict_info(s, scheduled)
            names = ", ".join(st.name for st in conflicts[:4])
            if len(conflicts) > 4:
                names += f" (+{len(conflicts) - 4} more)"
            reason = base_reason + (f" — conflicts: {names}" if conflicts else "")
            room_type = "Private" if s.needs_private else "Shared"
            p.append(
                f'<tr><td>{_html.escape(s.name)}</td><td>{_fmt(s.start)}</td>'
                f'<td>{_fmt(s.end)}</td><td>{room_type}</td><td>{_html.escape(reason)}</td></tr>'
            )
        p.append('</table>')

    p.append('</body></html>')

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(p))
