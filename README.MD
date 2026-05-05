# DRS Exam Schedule Optimizer

A command-line tool for the Disability Resource Services (DRS) testing center. Given a CSV of students with exam time windows and accommodation needs, it assigns each student to a numbered seat while maximizing the total number of students scheduled.

---

## Background

During finals and midterms, the DRS testing center handles 60+ students per day across 25 seats. Students are split into two groups:

- **Private room** — require an isolated seat (seats 1, 3, 4)
- **Shared room** — use the open testing area (seats 5–25)

Each student has a fixed exam window (typically 3–4 hours) somewhere between 8:45 AM and 5:15 PM. No two students can share a seat at the same time. The goal is to fit as many students as possible.

---

## Usage

```bash
python3 scheduler.py <input.csv>
python3 scheduler.py <input.csv> --output results.csv
```

`--output` / `-o` writes the full schedule to a CSV file in addition to printing to the terminal.

---

## Input CSV Format

| Column | Required | Description |
|---|---|---|
| `name` | Yes | Student name |
| `start_time` | Yes | Exam start (e.g. `9:00 AM`, `13:00`) |
| `end_time` | Yes | Exam end (same formats) |
| `private_room` | Yes | `Yes` / `No` (also accepts `true`, `1`, `x`, `private`) |
| any other columns | No | Passed through to output unchanged (e.g. `course`, `instructor`) |

Column names are matched case-insensitively. Accepted time formats: `9:00 AM`, `9:00AM`, `13:00`, `9 AM`, `9AM`.

**Example:**
```
name,start_time,end_time,private_room,course
Alice Johnson,8:45 AM,11:45 AM,Yes,MATH 101
Bob Lee,9:00 AM,12:00 PM,No,ENGL 201
```

---

## Output

### Terminal

```
=== SCHEDULED STUDENTS ===
SEAT  NAME                          START       END         TYPE
----------------------------------------------------------------------
1     Alice Johnson                 8:45 AM     11:45 AM    Private
2     Bob Lee                       9:00 AM     12:00 PM    Shared
...

=== UNSCHEDULED STUDENTS (1) ===
NAME                          START       END         REASON
----------------------------------------------------------------------
Irene Thomas                  11:00 AM    3:00 PM     All 3 private seats occupied
    ↳ conflicts: Alice Johnson, Carol White, Frank Nguyen, Mike Carter (+1 more)

Summary: 19/20 students scheduled, 1 could not be placed.

=== SEAT UTILIZATION (window: 8:45 AM–5:15 PM, 510 min) ===
  Private (3 seats):    1035 /   1530 min booked ( 67.6%)  peak 3/3 concurrent
  Shared  (22 seats):    2520 /  11220 min booked ( 22.5%)  peak 7/22 concurrent
```

### CSV output columns

`seat`, `name`, `start_time`, `end_time`, `private_room`, `status` (`Scheduled` / `Unscheduled`), `reason` (blank for scheduled; lists conflicting students for unscheduled), plus any extra columns from the input.

---

## Project Structure

```
scheduler.py      — CLI entry point (argparse)
algorithm.py      — scheduling logic
csv_parser.py     — CSV parsing and time normalization
models.py         — Student and Seat dataclasses
output.py         — terminal printing and CSV writing
sample_input.csv  — 20-student example input
sample_output.csv — expected output for the sample
```

---

## Algorithm

The scheduler runs independently for each seat pool (private and shared), then combines results.

**Step 1 — Greedy EDF with min-heap seat selection**

Students are sorted by earliest end time (EDF), with ties broken by latest start time (shortest-duration exam first). Two heaps track seat availability:

- `free_heap` — seat IDs available now (min-heap, so the lowest-numbered seat is always picked first)
- `busy_heap` — `(end_time, seat_id)` for occupied seats

Under EDF processing order, a seat's last-booking end time is an exact availability test — if `last_end ≤ student.start`, the seat is guaranteed free. This gives O(log s) per student instead of scanning all seats.

**Step 2 — Single-swap rescue pass**

After the greedy run, each unscheduled student gets one more attempt: for every seat in their pool, if exactly one scheduled student is blocking that seat, the scheduler tries to move the blocker to a different seat. If a move is found, the unscheduled student takes the vacated slot.

**Complexity:** O(n log n) for sort + O(n log s) for greedy + O(u · s · k) for swap pass, where n = students, s = seats in pool (3 or 22), u = unscheduled count, k = bookings per seat.

---

## Seat Map

| Seats | Type | Count |
|---|---|---|
| 1, 3, 4 | Private room | 3 |
| 5–25 | Shared / open | 21 |
| **Total** | | **24** |

> Note: seat 2 is shared. Private seats are specifically 1, 3, and 4.
