# DRS Exam Schedule Optimizer

A command-line tool for the Disability Resource Services (DRS) testing center. Given a CSV of students with exam time windows and accommodation needs, it assigns each student to a numbered seat while maximizing the total number of students scheduled.

---

## Background

During finals and midterms, the DRS testing center handles 60+ students per day across 34 seats. Students are split into two groups:

- **Private room** — require an isolated seat (rooms b, c, d, e — all have wall outlets)
- **Shared room** — use the open testing area (seats 5–34)

Within the shared room, seats are further split by wall outlet availability. Laptop students (Canvas/Online exams or type-response accommodation) are assigned to outlet seats first.

Each student has a fixed exam window somewhere between 8:45 AM and 5:15 PM. No two students can share a seat at the same time. The goal is to fit as many students as possible.

---

## Usage

```bash
python3 scheduler.py <input.csv>
python3 scheduler.py <input.csv> --output results.csv
python3 scheduler.py <input.csv> --chart schedule.html
python3 scheduler.py <input.csv> --output results.csv --chart schedule.html
```

`--output` / `-o` writes the full schedule to a CSV file in addition to printing to the terminal.

`--chart` / `-c` generates a self-contained HTML Gantt chart — open it in any browser to see all seats as rows with colored bars showing when each seat is occupied. Hover a bar for student details. Empty seats are shown as faded rows so available capacity is visible at a glance.

---

## Input CSV Format

The tool accepts two formats, detected automatically:

### DRS Export (primary)

The export CSV from the DRS exam management system. Required columns are read directly — no configuration needed.

| Field | Source column(s) |
|---|---|
| Name | `Preferred Name` + `Last Name` |
| Start / End | `Start Time` / `End Time` |
| Private room | `SVC - * Private Room for Assessments` = Yes |
| Laptop | `Exam Type` contains "Canvas/Online" **or** `SVC - * Type responses to short answer and essay questions` = Yes |

Extra columns passed through to output: Subject, Course, Section, Title, Instructor Name, Instructor Email, Exam Date, CRN, Tags, Barcode.

### Generic CSV

Hand-crafted or simplified CSV with named columns:

| Column | Required | Description |
|---|---|---|
| `name` | Yes | Student name |
| `start_time` | Yes | Exam start (e.g. `9:00 AM`, `13:00`) |
| `end_time` | Yes | Exam end (same formats) |
| `private_room` | Yes | `Yes` / `No` (also accepts `true`, `1`, `x`, `private`) |
| `laptop` | No | `Yes` / `No` — defaults to No if column absent |
| any other columns | No | Passed through to output unchanged |

Column names matched case-insensitively. Accepted time formats: `9:00 AM`, `9:00AM`, `13:00`, `9 AM`, `9AM`.

---

## Output

### Terminal

```
=== SCHEDULED STUDENTS ===
SEAT  NAME                          START       END         LAPTOP  TYPE
------------------------------------------------------------------------------
b     Alice Johnson                 8:45 AM     11:45 AM    Yes     Private
5     Bob Lee                       9:00 AM     12:00 PM    Yes     Shared
17    David Kim                     9:30 AM     12:30 PM    No      Shared
...

=== UNSCHEDULED STUDENTS (1) ===
NAME                          START       END         REASON
----------------------------------------------------------------------
Irene Thomas                  11:00 AM    3:00 PM     All 4 private seats occupied
    ↳ conflicts: Alice Johnson, Carol White, Frank Nguyen, Mike Carter (+1 more)

Summary: 22/23 students scheduled, 1 could not be placed.

=== SEAT UTILIZATION (window: 8:45 AM–5:15 PM, 510 min) ===
  Private (4 seats):    1275 /   2040 min booked ( 62.5%)  peak 4/4 concurrent
  Shared  (30 seats):    2520 /  15300 min booked ( 16.5%)  peak 7/30 concurrent
```

### CSV output columns

`seat`, `name`, `start_time`, `end_time`, `private_room`, `laptop`, `status` (`Scheduled` / `Unscheduled`), `reason` (blank for scheduled; lists conflicting students for unscheduled), plus any extra columns from the input.

---

## Seat Map

Defined in `seat_format.txt` (source of truth — edit there to change seat layout).

| Seats | Type | Outlet | Count |
|---|---|---|---|
| b, c, d, e | Private rooms | Yes | 4 |
| 5–8, 9–11, 12–16, 31–34 | Shared | Yes | 16 |
| 17–30 | Shared | No | 14 |
| **Total** | | | **34** |

---

## Algorithm

The scheduler runs independently for each pool (private and shared), then combines results.

**Step 1 — Greedy pass with outlet-aware seat selection**

Students are sorted by start time, ties broken by end time (shortest exam first). Within the shared pool, two heaps track outlet and non-outlet seats separately. Laptop students pop from the outlet heap first; non-laptop students prefer non-outlet seats and fall back to outlet only when non-outlet is full. All done in a single pass to avoid cross-pass booking conflicts.

Start-time ordering (not EDF) is used because EDF is correct for single-machine interval scheduling but causes double-bookings in the k-machine case: a later-processed student with an earlier actual start can grab a seat that was released for another student, creating an overlap. Start-time ordering guarantees that when a seat is released, all future students start at or after that point.

**Step 2 — Single-swap rescue pass**

After the greedy run, each unscheduled student gets one more attempt: if exactly one scheduled student is blocking a seat, the scheduler tries to move the blocker elsewhere. If a move is found, the unscheduled student takes the vacated slot.

---

## Project Structure

```
scheduler.py      — CLI entry point (argparse)
algorithm.py      — scheduling logic; parses seat_format.txt at import
csv_parser.py     — auto-detecting CSV parser (DRS export + generic)
models.py         — Student and Seat dataclasses
output.py         — terminal printing and CSV writing
seat_format.txt        — source of truth for seat numbers and outlet status
sample_import.csv      — anonymized example of the DRS input format
test_scheduler.py — lightweight functional tests; runnable as a script
```
