import colorsys
import csv
import html as _html
import json
import math
from models import Student
from algorithm import PRIVATE_IDS, OUTLET_IDS, NO_OUTLET_IDS, ADJACENCY

_PRIVATE_SEAT_COUNT = len(PRIVATE_IDS)
_SHARED_SEAT_COUNT = len(OUTLET_IDS) + len(NO_OUTLET_IDS)


def _fmt(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    ampm = "AM" if h < 12 else "PM"
    h = h % 12 or 12
    return f"{h}:{m:02d} {ampm}"


def _conflict_info(student: Student, scheduled: list[Student]) -> tuple[str, list[Student]]:
    pool_size = _PRIVATE_SEAT_COUNT if student.needs_private else _SHARED_SEAT_COUNT
    pool_name = "private" if student.needs_private else "shared"
    conflicts = sorted(
        [st for st in scheduled
         if st.needs_private == student.needs_private
         and not (student.end <= st.start or student.start >= st.end)],
        key=lambda st: st.start,
    )
    return f"All {pool_size} {pool_name} seats occupied", conflicts


def _seat_sort_key(seat_id):
    return (isinstance(seat_id, str), seat_id)


def print_schedule(scheduled: list[Student], unscheduled: list[Student]) -> None:
    sorted_sched = sorted(scheduled, key=lambda s: (s.start, _seat_sort_key(s.assigned_seat)))

    print("\n=== SCHEDULED STUDENTS ===")
    if not sorted_sched:
        print("  (none)")
    else:
        print(f"{'SEAT':<6}{'NAME':<30}{'START':<12}{'END':<12}{'LAPTOP':<8}{'TYPE':<9}CLASS")
        print("-" * 90)
        for s in sorted_sched:
            room_type  = "Private" if s.needs_private else "Shared"
            laptop_str = "Yes" if s.uses_laptop else "No"
            class_str  = " ".join(filter(None, [
                _extra(s, "Subject", "subject"),
                _extra(s, "Course",  "course"),
                _extra(s, "Section", "section"),
            ]))
            print(f"{str(s.assigned_seat):<6}{s.name:<30}{_fmt(s.start):<12}{_fmt(s.end):<12}"
                  f"{laptop_str:<8}{room_type:<9}{class_str}")

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
            neighbours = [
                o for o in scheduled
                if o is not s
                and o.crn == s.crn
                and not (s.end <= o.start or s.start >= o.end)
                and o.assigned_seat in ADJACENCY.get(s.assigned_seat, [])
            ]
            adj_str   = ", ".join(f"{o.name} (seat {o.assigned_seat})" for o in neighbours)
            class_str = " ".join(filter(None, [
                _extra(s, "Subject", "subject"),
                _extra(s, "Course",  "course"),
                _extra(s, "Section", "section"),
            ]))
            label = f"{class_str} — " if class_str else ""
            print(f"  ! {s.name}  seat {s.assigned_seat}  {label}adjacent to {adj_str or '?'}")

    _print_utilization(scheduled, unscheduled)


def _print_utilization(scheduled: list[Student], unscheduled: list[Student]) -> None:
    all_students = scheduled + unscheduled
    if not all_students:
        return
    day_start = min(s.start for s in all_students)
    day_end   = max(s.end   for s in all_students)
    window    = day_end - day_start
    if window <= 0:
        return

    priv_all   = [s for s in all_students if     s.needs_private]
    shared_all = [s for s in all_students if not s.needs_private]
    priv_sched   = [s for s in scheduled if     s.needs_private]
    shared_sched = [s for s in scheduled if not s.needs_private]

    priv_booked   = sum(s.end - s.start for s in priv_sched)
    shared_booked = sum(s.end - s.start for s in shared_sched)
    priv_cap   = _PRIVATE_SEAT_COUNT * window
    shared_cap = _SHARED_SEAT_COUNT * window

    def peak_concurrent(students):
        events = []
        for s in students:
            events.append((s.start, 1))
            events.append((s.end, -1))
        events.sort()
        cur = pk = 0
        for _, d in events:
            cur += d
            pk = max(pk, cur)
        return pk

    priv_peak   = peak_concurrent(priv_sched)
    shared_peak = peak_concurrent(shared_sched)

    print(f"\n=== SEAT UTILIZATION (window: {_fmt(day_start)}–{_fmt(day_end)}, {window} min) ===")
    if priv_all:
        print(f"  Private ({_PRIVATE_SEAT_COUNT} seats):  "
              f"{priv_booked:>6} / {priv_cap:>6} min booked "
              f"({priv_booked / priv_cap * 100:5.1f}%)  "
              f"peak {priv_peak}/{_PRIVATE_SEAT_COUNT} concurrent")
    if shared_all:
        print(f"  Shared  ({_SHARED_SEAT_COUNT} seats):  "
              f"{shared_booked:>6} / {shared_cap:>6} min booked "
              f"({shared_booked / shared_cap * 100:5.1f}%)  "
              f"peak {shared_peak}/{_SHARED_SEAT_COUNT} concurrent")


def write_csv(scheduled: list[Student], unscheduled: list[Student], path: str) -> None:
    extra_keys: list[str] = []
    for s in scheduled + unscheduled:
        for k in s.extra:
            if k not in extra_keys:
                extra_keys.append(k)

    base_fields = ["seat", "name", "start_time", "end_time", "private_room", "laptop",
                   "adj_conflict", "status", "reason"]
    fieldnames = base_fields + extra_keys

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for s in sorted(scheduled, key=lambda s: (s.start, _seat_sort_key(s.assigned_seat))):
            row = {
                "seat": s.assigned_seat, "name": s.name,
                "start_time": _fmt(s.start), "end_time": _fmt(s.end),
                "private_room": "Yes" if s.needs_private else "No",
                "laptop":       "Yes" if s.uses_laptop  else "No",
                "adj_conflict": "Yes" if s.adjacency_conflict else "",
                "status": "Scheduled", "reason": "",
            }
            row.update(s.extra)
            writer.writerow(row)

        for s in sorted(unscheduled, key=lambda s: s.start):
            base_reason, conflicts = _conflict_info(s, scheduled)
            conflict_str = ("; conflicts: " + ", ".join(st.name for st in conflicts)) if conflicts else ""
            row = {
                "seat": "", "name": s.name,
                "start_time": _fmt(s.start), "end_time": _fmt(s.end),
                "private_room": "Yes" if s.needs_private else "No",
                "laptop":       "Yes" if s.uses_laptop  else "No",
                "adj_conflict": "", "status": "Unscheduled",
                "reason": base_reason + conflict_str,
            }
            row.update(s.extra)
            writer.writerow(row)


# ─── Shared chart helpers ──────────────────────────────────────────────────────

_NO_CRN_COLOR = "#888888"


def _build_crn_colors(scheduled: list[Student]) -> dict[str, str]:
    crns = list(dict.fromkeys(s.crn for s in scheduled if s.crn))
    n    = max(len(crns), 1)
    return {
        crn: "#{:02x}{:02x}{:02x}".format(
            *[int(c * 255) for c in colorsys.hls_to_rgb(i / n, 0.42, 0.62)]
        )
        for i, crn in enumerate(crns)
    }


def _extra(student: Student, *keys: str) -> str:
    for k in keys:
        v = (student.extra.get(k) or "").strip()
        if v:
            return v
    return ""


# ─── CSS ──────────────────────────────────────────────────────────────────────

_CHART_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #f5f5f7; color: #1a1a1a; padding: 24px; }
h1  { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
.meta { font-size: 13px; color: #666; margin-bottom: 12px; }
.legend { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }

/* ── Tabs ── */
.tabs { display: flex; border-bottom: 2px solid #ddd; margin-bottom: 24px; }
.tab-btn {
  padding: 9px 22px; border: none; background: none; cursor: pointer;
  font-size: 14px; font-weight: 500; color: #666;
  border-bottom: 3px solid transparent; margin-bottom: -2px;
}
.tab-btn.active { color: #0060df; border-bottom-color: #0060df; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* ── Gantt chart ── */
.chart-outer { overflow-x: auto; border: 1px solid #ddd; border-radius: 8px; background: #fff; }
table.chart-table { border-collapse: collapse; }
.label-cell {
  position: sticky; left: 0; background: #fff; z-index: 2;
  width: 90px; min-width: 90px; max-width: 90px;
  padding: 0 10px; font-size: 12px; font-weight: 500;
  border-right: 1px solid #e0e0e0; white-space: nowrap; vertical-align: middle;
}
.lane-cell { padding: 0; vertical-align: top; }
.axis-row .label-cell  { height: 34px; background: #f9f9f9; font-size: 11px; color: #888; }
.group-row .label-cell { font-size: 10px; font-weight: 700; color: #555; text-transform: uppercase;
  letter-spacing: 0.5px; background: #f0f0f0; height: 22px; }
.group-row .lane-cell  { background: #f0f0f0; }
.seat-row { border-top: 1px solid #ebebeb; }
.seat-row.empty .label-cell { color: #bbb; font-weight: 400; }
.lane { position: relative; height: 40px; }
.seat-row.empty .lane { height: 26px; }
.time-axis { position: relative; height: 34px; border-bottom: 1px solid #ddd; background: #f9f9f9; }
.tick { position: absolute; top: 6px; font-size: 10px; color: #888;
        transform: translateX(-50%); white-space: nowrap; }
.tick::after { content:""; position:absolute; bottom:-8px; left:50%;
               width:1px; height:7px; background:#ccc; }
.bar {
  position: absolute; top: 5px; bottom: 5px; border-radius: 4px;
  display: flex; align-items: center; padding: 0 6px;
  font-size: 11px; color: #fff; overflow: visible; cursor: default;
  transition: filter 0.1s; min-width: 3px;
}
.bar:hover { filter: brightness(1.15); z-index: 10; }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.tooltip {
  display: none; position: absolute; bottom: calc(100% + 8px); left: 50%;
  transform: translateX(-50%); background: #1a1a1a; color: #fff;
  padding: 7px 11px; border-radius: 6px; white-space: pre; font-size: 12px;
  z-index: 100; pointer-events: none; line-height: 1.6; box-shadow: 0 2px 8px rgba(0,0,0,.3);
}
.bar:hover .tooltip { display: block; }
h2 { font-size: 15px; font-weight: 600; margin: 24px 0 10px; }
.unsched-table { border-collapse: collapse; font-size: 12px; width: 100%; max-width: 760px; }
.unsched-table th { text-align: left; padding: 6px 12px; background: #f2f2f2;
                    border-bottom: 2px solid #ddd; font-weight: 600; }
.unsched-table td { padding: 6px 12px; border-bottom: 1px solid #ebebeb; }
.unsched-table tr:last-child td { border-bottom: none; }
.no-unsched { font-size: 13px; color: #666; }

/* ── Seat map controls ── */
.map-controls {
  display: flex; align-items: center; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;
  background: #fff; padding: 12px 18px; border: 1px solid #ddd; border-radius: 8px;
}
#map-time-display { font-size: 22px; font-weight: 700; min-width: 95px; color: #1a1a1a; }
#map-slider { flex: 1; min-width: 200px; max-width: 500px; accent-color: #0060df; cursor: pointer; }
.map-btn {
  padding: 6px 16px; border: 1px solid #ccc; border-radius: 6px;
  background: #fff; cursor: pointer; font-size: 12px; font-weight: 500; color: #444;
}
.map-btn:hover { background: #f0f0f0; }

/* ── Floor-plan wrapper ── */
.floor-plan-wrap { overflow-x: auto; padding-bottom: 12px; }

/* ── Building layout: flex L-shape + private wing ──────────────────────────── */
.building-flex { display: inline-flex; align-items: stretch; }
.main-L { display: flex; flex-direction: column; min-width: 580px; }

/* Big rectangle (main testing room) */
.big-rect { display: flex; flex-direction: column; border: 3px solid #3a3a3a; }
.top-band  { display: flex; border-bottom: 2px solid #8fa8c8; }
.body-band { display: flex; }

/* ── Corner (top-left of big rect) ── */
.room-corner {
  width: 74px; flex-shrink: 0;
  background: #d8e2f0;
  border-right: 2px solid #8fa8c8;
}

/* ── Top-wall seats (Wall/Outlet — top row) ── */
.top-wall {
  flex: 1;
  background: #ebf0f8;
  padding: 8px 10px 10px;
  display: flex; flex-direction: column; gap: 6px;
}
.wall-label-h {
  font-size: 9px; font-weight: 800; color: #4266a0;
  text-transform: uppercase; letter-spacing: 0.8px;
}
.top-seats-row { display: flex; gap: 5px; }

/* ── Storage (top-right of big rect) ── */
.storage-cell {
  width: 112px; flex-shrink: 0;
  background: #f0f0f0;
  border-left: 1px solid #ccc;
  padding: 8px;
  display: flex; align-items: flex-start; justify-content: center;
}
.storage-box {
  width: 100%; background: #e4e4e4; border: 1.5px solid #bbb; border-radius: 3px;
  font-size: 10px; font-weight: 700; color: #999;
  display: flex; align-items: center; justify-content: center;
  text-align: center; padding: 8px 4px; min-height: 46px;
}

/* ── Left-wall seats (Wall/Outlet — left column) ── */
.left-wall {
  width: 74px; flex-shrink: 0;
  background: #ebf0f8;
  border-right: 2px solid #8fa8c8;
  padding: 10px 6px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.wall-label-v {
  writing-mode: vertical-rl; transform: rotate(180deg);
  font-size: 9px; font-weight: 800; color: #4266a0;
  text-transform: uppercase; letter-spacing: 0.8px; flex-shrink: 0;
}
.left-seats-col { display: flex; flex-direction: column; gap: 5px; }

/* ── Interior (center table area) ── */
.interior {
  flex: 1;
  background: #fafafa;
  padding: 20px 14px 14px 14px;
  display: flex; flex-direction: column;
  justify-content: flex-start;
}
.center-table-surface {
  display: flex; flex-direction: column; gap: 5px;
  background: #d8dde4; border: 2px solid #9aabb8;
  border-radius: 5px; padding: 10px 14px;
  align-self: flex-start;
  position: relative;
}
.table-row-seats { display: flex; gap: 5px; }
.seat-adj-badge {
  position: absolute; font-size: 9px; font-weight: 900; color: #fff;
  background: #556; border-radius: 3px; padding: 1px 4px; letter-spacing: 0.2px;
  line-height: 1.4; pointer-events: none;
}
.badge-tl { top: -9px; left:  4px; }
.badge-bl { bottom: -9px; left: 4px; }
/* Right cluster: seats 7,6,8,5 top→bottom on the right wall */
.right-cluster {
  display: flex; flex-direction: column; gap: 5px;
  padding: 10px 8px;
  align-items: center; justify-content: flex-end;
  border-left: 1px solid #e0e0e0;
}

/* ── DRS Office box inside the interior ── */
.interior-drs {
  flex: 1; margin-top: 18px;
  background: #e8e8e8; border: 2px solid #c0c0c0; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: #b0b0b0; letter-spacing: 0.3px;
  position: relative; padding: 20px;
}
.door-arc {
  position: absolute; width: 20px; height: 20px;
  border: 2px solid #b8b8b8;
}
.door-arc.tl { top: -2px; left: -2px; border-top: none; border-left: none;
               border-radius: 0 0 20px 0; }
.door-arc.br { bottom: -2px; right: -2px; border-bottom: none; border-right: none;
               border-radius: 20px 0 0 0; }

/* ── Private rooms wing (separate column, accessed from inside big rect) ── */
.private-wing {
  display: flex; flex-direction: column;
  width: 112px; min-width: 112px; flex-shrink: 0;
  border: 3px solid #3a3a3a; border-left: 2px solid #aaa;
  background: #f4f4f4; overflow: hidden;
}
.private-wing-header {
  background: #e6e6e6; border-bottom: 1px solid #ccc;
  padding: 5px 8px; text-align: center;
  font-size: 9px; font-weight: 800; color: #888;
  text-transform: uppercase; letter-spacing: 0.7px; flex-shrink: 0;
}

/* ── Shared seat boxes ── */
.map-seat {
  width: 54px; height: 50px; border-radius: 5px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 2px; text-align: center; overflow: hidden;
  background: #dcdcdc; color: #999; border: 1.5px solid #c0c0c0;
  transition: background 0.15s, color 0.15s;
  cursor: default; user-select: none; flex-shrink: 0;
}
.map-seat .seat-num { font-size: 13px; font-weight: 700; line-height: 1.2; }
/* Occupied content — hidden by default, shown when JS adds .occupied */
.map-seat .seat-occ-name,
.map-seat .seat-occ-class { display: none; }
.map-seat.occupied .seat-occ-name { display: block; font-size: 9px; line-height: 1.2; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 50px; }
.map-seat.occupied .seat-occ-class { display: block; font-size: 8px; line-height: 1.2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 50px; opacity: 0.88; }
.map-seat.occupied { color: #fff; border-color: transparent; }
.map-seat.occupied:hover { filter: brightness(1.1); }

/* ── Private room cells (inside .private-col) ── */
.map-seat.private-room {
  /* Override shared seat sizing — fill column height evenly */
  flex: 1; width: 100%; border-radius: 0;
  border: none; border-bottom: 1px solid #ddd;
  background: #f0f0f0;
  flex-direction: column; align-items: flex-start; justify-content: center;
  padding: 8px 10px; text-align: left;
  min-height: 0;
}
.map-seat.private-room:last-child { border-bottom: none; }
.map-seat.private-room .pr-id   { font-size: 13px; font-weight: 700; color: #555; line-height: 1.2; }
.map-seat.private-room .pr-code { font-size: 10px; color: #aaa; line-height: 1.3; }
.map-seat.private-room .pr-desc { font-size: 9px;  color: #c8c8c8; line-height: 1.3; }
/* When occupied: hide static labels, show dynamic name/class */
.map-seat.private-room.occupied .pr-id,
.map-seat.private-room.occupied .pr-code,
.map-seat.private-room.occupied .pr-desc { display: none; }
.map-seat.private-room.occupied .seat-occ-name  { max-width: 92px; }
.map-seat.private-room.occupied .seat-occ-class { max-width: 92px; }
.map-seat.private-room.occupied { color: #fff; border-bottom-color: rgba(255,255,255,.2); }
/* Hover tooltip */
.map-tooltip {
  display: none; position: fixed; z-index: 9999;
  background: #1a1a1a; color: #fff; padding: 8px 12px; border-radius: 6px;
  font-size: 12px; line-height: 1.7; pointer-events: none; white-space: pre;
  box-shadow: 0 2px 10px rgba(0,0,0,.35);
}
"""


# ─── Gantt bar renderer ────────────────────────────────────────────────────────

def _render_bars(students: list, crn_colors: dict, t_start: int, duration: int) -> str:
    bars = []
    for s in students:
        left_pct  = (s.start - t_start) / duration * 100
        width_pct = (s.end   - s.start) / duration * 100
        color = crn_colors.get(s.crn, _NO_CRN_COLOR) if s.crn else _NO_CRN_COLOR

        subject = _extra(s, "Subject", "subject")
        course  = _extra(s, "Course",  "course")
        section = _extra(s, "Section", "section")
        title   = _extra(s, "Title",   "title")
        prof    = _extra(s, "Instructor Name", "instructor_name")

        class_str = " ".join(filter(None, [subject, course, section]))
        lines = [s.name, f"{_fmt(s.start)} – {_fmt(s.end)}", f"Laptop: {'Yes' if s.uses_laptop else 'No'}"]
        if class_str: lines.append(f"Class: {class_str}")
        if title:     lines.append(title)
        if prof:      lines.append(f"Prof: {prof}")

        tooltip = _html.escape("\n".join(lines))
        bars.append(
            f'<div class="bar" style="left:{left_pct:.2f}%;width:{width_pct:.2f}%;background:{color}">'
            f'<span class="bar-label">{_html.escape(s.name)}</span>'
            f'<span class="tooltip">{tooltip}</span>'
            f'</div>'
        )
    return "".join(bars)


# ─── Seat map HTML builders ────────────────────────────────────────────────────

def _shared_box(seat_id: int) -> str:
    return (
        f'<div class="map-seat" data-seat="{seat_id}">'
        f'<span class="seat-num">{seat_id}</span>'
        f'<span class="seat-occ-name"></span>'
        f'<span class="seat-occ-class"></span>'
        f'</div>'
    )


def _private_box(seat_id: str, room_num: str, description: str) -> str:
    return (
        f'<div class="map-seat private-room" data-seat="{_html.escape(seat_id)}">'
        f'<span class="pr-id">Room {seat_id.upper()}</span>'
        f'<span class="pr-code">{room_num}</span>'
        f'<span class="pr-desc">{description}</span>'
        f'<span class="seat-occ-name"></span>'
        f'<span class="seat-occ-class"></span>'
        f'</div>'
    )


def _render_seat_map_body(t_start: int, t_end: int) -> str:
    # ── Physical seat positions (matching the room photo) ──────────────────────
    # Top wall (left → right): 11, 32, 10, 33, 9, 34
    top_row    = [11, 32, 10, 33, 9, 34]
    # Left wall (top → bottom): 12, 13, 14, 15, 16, 31
    left_col   = [12, 13, 14, 15, 16, 31]
    # Center table — even row (top face of table): 18, 20, 22, 24, 26, 28, 30
    center_even = [18, 20, 22, 24, 26, 28, 30]
    # Center table — odd row (bottom face of table): 17, 19, 21, 23, 25, 27, 29
    center_odd  = [17, 19, 21, 23, 25, 27, 29]
    # Hallway (left wall of hallway, top → bottom): 07, 06, 08, 05 (from photo)
    hallway_seats = [7, 6, 8, 5]
    # Private rooms (top → bottom)
    private_rooms = [
        ("b", "071B", "Alice's / Overflow"),
        ("c", "071C", "Private Equipment"),
        ("d", "071D", "Private Furniture"),
        ("e", "071E", "Private Computer"),
    ]

    tr_html = "".join(_shared_box(s) for s in top_row)
    lc_html = "".join(_shared_box(s) for s in left_col)
    hw_html = "".join(_shared_box(s) for s in hallway_seats)
    pr_html = "".join(_private_box(sid, code, desc) for sid, code, desc in private_rooms)

    # Center table: seat 18 and 17 have the adjustable-desk "A" badge
    ce_html = (
        f'<div class="map-seat" data-seat="18">'
        f'<span class="seat-adj-badge badge-tl">A</span>'
        f'<span class="seat-num">18</span>'
        f'<span class="seat-occ-name"></span><span class="seat-occ-class"></span>'
        f'</div>'
        + "".join(_shared_box(s) for s in center_even[1:])
    )
    co_html = (
        f'<div class="map-seat" data-seat="17">'
        f'<span class="seat-adj-badge badge-bl">A</span>'
        f'<span class="seat-num">17</span>'
        f'<span class="seat-occ-name"></span><span class="seat-occ-class"></span>'
        f'</div>'
        + "".join(_shared_box(s) for s in center_odd[1:])
    )

    return (
        # Controls
        '<div class="map-controls">'
        '<button class="map-btn" id="map-prev">&#9664; Prev event</button>'
        '<span id="map-time-display">—</span>'
        f'<input id="map-slider" type="range" min="{t_start}" max="{t_end}" step="1" value="{t_start}">'
        '<button class="map-btn" id="map-next">Next event &#9654;</button>'
        '<button class="map-btn" id="map-now">&#9679; Now</button>'
        '</div>'

        '<div class="floor-plan-wrap">'
        '<div class="building-flex">'
        '<div class="main-L">'

        # ── Big rectangle (main testing room) ────────────────────────────────
        '<div class="big-rect">'

        # Top band: corner | top-wall seats | storage
        '<div class="top-band">'
        '<div class="room-corner"></div>'
        '<div class="top-wall">'
        '<span class="wall-label-h">&#x26a1; Wall / Outlet</span>'
        f'<div class="top-seats-row">{tr_html}</div>'
        '</div>'
        '<div class="storage-cell"><div class="storage-box">Storage</div></div>'
        '</div>'

        # Body band: left-wall | interior (center table)
        '<div class="body-band">'
        '<div class="left-wall">'
        '<span class="wall-label-v">&#x26a1; Wall / Outlet</span>'
        f'<div class="left-seats-col">{lc_html}</div>'
        '</div>'
        '<div class="interior">'
        '<div class="center-table-surface">'
        f'<div class="table-row-seats">{ce_html}</div>'
        f'<div class="table-row-seats">{co_html}</div>'
        '</div>'
        '<div class="interior-drs">'
        '<div class="door-arc tl"></div>'
        'DRS Office'
        '<div class="door-arc br"></div>'
        '</div>'
        '</div>'
        f'<div class="right-cluster">{hw_html}</div>'
        '</div>'

        '</div>'  # big-rect

        '</div>'  # main-L

        # ── Private rooms wing (separate column, right of big rect) ──────────
        '<div class="private-wing">'
        '<div class="private-wing-header">Private Rooms</div>'
        f'{pr_html}'
        '</div>'

        '</div>'  # building-flex
        '</div>'  # floor-plan-wrap

        '<div class="map-tooltip" id="map-tooltip"></div>'
    )


# ─── JavaScript ───────────────────────────────────────────────────────────────

def _render_js(scheduled: list[Student], crn_colors: dict, t_start: int) -> str:
    bookings_data = []
    for s in scheduled:
        subj   = _extra(s, "Subject", "subject")
        course = _extra(s, "Course",  "course")
        sect   = _extra(s, "Section", "section")
        class_str = " ".join(filter(None, [subj, course, sect]))
        bookings_data.append({
            "seat":      s.assigned_seat,
            "name":      s.name,
            "start":     s.start,
            "end":       s.end,
            "crn":       s.crn or "",
            "class_str": class_str,
            "laptop":    s.uses_laptop,
        })

    event_times = sorted({t for s in scheduled for t in (s.start, s.end)})

    bj = json.dumps(bookings_data)
    cj = json.dumps(crn_colors)
    ej = json.dumps(event_times)

    return f"""<script>
(function () {{
  var BOOKINGS    = {bj};
  var CRN_COLORS  = {cj};
  var NO_COLOR    = "{_NO_CRN_COLOR}";
  var EVENT_TIMES = {ej};

  function fmtTime(m) {{
    var h = Math.floor(m / 60), mm = m % 60;
    var ap = h < 12 ? 'AM' : 'PM';
    h = h % 12 || 12;
    return h + ':' + (mm < 10 ? '0' : '') + mm + ' ' + ap;
  }}

  function getOccupant(seatId, time) {{
    for (var i = 0; i < BOOKINGS.length; i++) {{
      var b = BOOKINGS[i];
      if (String(b.seat) === String(seatId) && b.start <= time && b.end > time) return b;
    }}
    return null;
  }}

  function updateMap(time) {{
    document.querySelectorAll('.map-seat').forEach(function (el) {{
      var occ     = getOccupant(el.dataset.seat, time);
      var nameEl  = el.querySelector('.seat-occ-name');
      var classEl = el.querySelector('.seat-occ-class');
      if (occ) {{
        el.style.background = occ.crn ? (CRN_COLORS[occ.crn] || NO_COLOR) : NO_COLOR;
        el.classList.add('occupied');
        nameEl.textContent  = occ.name.split(' ')[0];
        classEl.textContent = occ.class_str;
        el._occ = occ;
      }} else {{
        el.style.background = '';
        el.classList.remove('occupied');
        nameEl.textContent  = '';
        classEl.textContent = '';
        el._occ = null;
      }}
    }});
    var disp = document.getElementById('map-time-display');
    if (disp) disp.textContent = fmtTime(time);
  }}

  var slider = document.getElementById('map-slider');
  slider.addEventListener('input', function () {{ updateMap(parseInt(this.value)); }});

  document.getElementById('map-now').addEventListener('click', function () {{
    var now = new Date();
    var mins = now.getHours() * 60 + now.getMinutes();
    mins = Math.max(parseInt(slider.min), Math.min(parseInt(slider.max), mins));
    slider.value = mins;
    updateMap(mins);
  }});

  document.getElementById('map-prev').addEventListener('click', function () {{
    var cur = parseInt(slider.value);
    for (var i = EVENT_TIMES.length - 1; i >= 0; i--) {{
      if (EVENT_TIMES[i] < cur) {{ slider.value = EVENT_TIMES[i]; updateMap(EVENT_TIMES[i]); return; }}
    }}
  }});
  document.getElementById('map-next').addEventListener('click', function () {{
    var cur = parseInt(slider.value);
    for (var i = 0; i < EVENT_TIMES.length; i++) {{
      if (EVENT_TIMES[i] > cur) {{ slider.value = EVENT_TIMES[i]; updateMap(EVENT_TIMES[i]); return; }}
    }}
  }});

  var tooltip = document.getElementById('map-tooltip');
  document.querySelectorAll('.map-seat').forEach(function (el) {{
    el.addEventListener('mouseenter', function () {{
      if (this._occ && tooltip) {{
        var o     = this._occ;
        var lines = [o.name, fmtTime(o.start) + ' – ' + fmtTime(o.end)];
        if (o.class_str) lines.push(o.class_str);
        tooltip.textContent = lines.join('\\n');
        tooltip.style.display = 'block';
      }}
    }});
    el.addEventListener('mousemove', function (e) {{
      if (tooltip) {{
        tooltip.style.left = (e.clientX + 14) + 'px';
        tooltip.style.top  = (e.clientY - 10) + 'px';
      }}
    }});
    el.addEventListener('mouseleave', function () {{
      if (tooltip) tooltip.style.display = 'none';
    }});
  }});

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      document.querySelectorAll('.tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
      document.querySelectorAll('.tab-panel').forEach(function (p) {{ p.classList.remove('active'); }});
      this.classList.add('active');
      var panel = document.getElementById(this.dataset.tab);
      if (panel) panel.classList.add('active');
    }});
  }});

  updateMap({t_start});
}})();
</script>"""


# ─── Main chart writer ─────────────────────────────────────────────────────────

def write_chart(scheduled: list[Student], unscheduled: list[Student], path: str) -> None:
    all_students = scheduled + unscheduled
    if not all_students:
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><head><meta charset="utf-8"><title>DRS Schedule</title></head>'
                    '<body><p style="padding:24px;font-family:sans-serif">No students to display.</p></body></html>')
        return

    t_start    = min(s.start for s in all_students)
    t_end      = max(s.end   for s in all_students)
    duration   = t_end - t_start
    chart_width = max(800, duration * 2)

    crn_colors = _build_crn_colors(scheduled)

    bookings_by_seat: dict = {}
    for s in sorted(scheduled, key=lambda x: x.start):
        bookings_by_seat.setdefault(s.assigned_seat, []).append(s)

    p = []
    p.append('<!DOCTYPE html>')
    p.append('<html lang="en"><head><meta charset="utf-8">')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append('<title>DRS Exam Schedule</title>')
    p.append(f'<style>{_CHART_CSS}</style></head><body>')
    p.append('<h1>DRS Exam Schedule</h1>')
    p.append(f'<div class="meta">{_fmt(t_start)} – {_fmt(t_end)}'
             f' &nbsp;|&nbsp; {len(scheduled)} scheduled, {len(unscheduled)} unscheduled</div>')

    # Legend
    p.append('<div class="legend">')
    for crn, color in crn_colors.items():
        ref   = next((s for s in scheduled if s.crn == crn), None)
        subj  = _extra(ref, "Subject", "subject") if ref else ""
        crs   = _extra(ref, "Course",  "course")  if ref else ""
        sect  = _extra(ref, "Section", "section") if ref else ""
        label = " ".join(filter(None, [subj, crs, sect])) or crn
        p.append(f'<div class="legend-item">'
                 f'<div class="legend-swatch" style="background:{color}"></div>'
                 f'<span>{_html.escape(label)}</span></div>')
    if not crn_colors:
        p.append('<div class="legend-item">'
                 '<div class="legend-swatch" style="background:#888"></div>'
                 '<span>Exam</span></div>')
    p.append('</div>')

    # Tabs
    p.append('<div class="tabs">')
    p.append('<button class="tab-btn active" data-tab="tab-gantt">Timeline</button>')
    p.append('<button class="tab-btn" data-tab="tab-map">Seat Map</button>')
    p.append('</div>')

    # ── Tab 1: Gantt ──────────────────────────────────────────────────────────
    p.append('<div id="tab-gantt" class="tab-panel active">')
    p.append('<div class="chart-outer"><table class="chart-table" cellspacing="0">')

    p.append('<tr class="axis-row"><td class="label-cell">Time ►</td><td class="lane-cell">')
    p.append(f'<div class="time-axis" style="width:{chart_width}px">')
    tick = math.ceil(t_start / 30) * 30
    while tick <= t_end:
        left_pct = (tick - t_start) / duration * 100
        p.append(f'<div class="tick" style="left:{left_pct:.2f}%">{_fmt(tick)}</div>')
        tick += 30
    p.append('</div></td></tr>')

    for group_name, seat_ids in [
        ("Private Rooms",      PRIVATE_IDS),
        ("Shared — Outlet",    OUTLET_IDS),
        ("Shared — No Outlet", NO_OUTLET_IDS),
    ]:
        p.append(f'<tr class="group-row"><td class="label-cell">{_html.escape(group_name)}</td>'
                 f'<td class="lane-cell" style="width:{chart_width}px"></td></tr>')
        for sid in seat_ids:
            students_here = bookings_by_seat.get(sid, [])
            row_cls = "seat-row" + ("" if students_here else " empty")
            label   = f"Room {sid}" if isinstance(sid, str) else f"Seat {sid}"
            bars    = _render_bars(students_here, crn_colors, t_start, duration)
            p.append(f'<tr class="{row_cls}"><td class="label-cell">{label}</td>'
                     f'<td class="lane-cell">'
                     f'<div class="lane" style="width:{chart_width}px">{bars}</div></td></tr>')

    p.append('</table></div>')
    p.append('</div>')  # tab-gantt

    # ── Tab 2: Seat map ───────────────────────────────────────────────────────
    p.append('<div id="tab-map" class="tab-panel">')
    p.append(_render_seat_map_body(t_start, t_end))
    p.append('</div>')  # tab-map

    # Unscheduled (below both tabs)
    p.append('<h2>Unscheduled Students</h2>')
    if not unscheduled:
        p.append('<p class="no-unsched">All students were scheduled.</p>')
    else:
        p.append('<table class="unsched-table"><tr>'
                 '<th>Name</th><th>Start</th><th>End</th><th>Type</th><th>Reason</th></tr>')
        for s in sorted(unscheduled, key=lambda x: x.start):
            base_reason, conflicts = _conflict_info(s, scheduled)
            names = ", ".join(st.name for st in conflicts[:4])
            if len(conflicts) > 4:
                names += f" (+{len(conflicts) - 4} more)"
            reason    = base_reason + (f" — conflicts: {names}" if conflicts else "")
            room_type = "Private" if s.needs_private else "Shared"
            p.append(f'<tr><td>{_html.escape(s.name)}</td><td>{_fmt(s.start)}</td>'
                     f'<td>{_fmt(s.end)}</td><td>{room_type}</td>'
                     f'<td>{_html.escape(reason)}</td></tr>')
        p.append('</table>')

    p.append(_render_js(scheduled, crn_colors, t_start))
    p.append('</body></html>')

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(p))
