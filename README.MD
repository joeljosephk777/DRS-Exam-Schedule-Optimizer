# DRS Exam Schedule Optimizer

A command-line tool for the Disability Resource Services (DRS) testing center. Given a CSV of students with exam time windows and accommodation needs, it assigns each student to a numbered seat while maximizing the total number of students scheduled.

---

## Background

During finals and midterms, the DRS testing center handles 60+ students per day across 34 seats. Students are split into two groups:

- **Private room** — require an isolated seat (rooms b, c, d, e — all have wall outlets)
- **Shared room** — use the open testing area (seats 5–34)

Within the shared room, seats differ by outlet availability and physical features. Laptop students are assigned to outlet seats first. Students with specific accommodations (adjustable-height desks, CCTV/low-vision equipment, service animals) are routed to the matching seat or room.

Each student has a fixed exam window somewhere between 8:00 AM and 5:15 PM. No two students can share a seat at the same time. The goal is to fit as many students as possible.

The tool also flags **adjacency conflicts** — students taking the same exam (same CRN) who end up seated next to each other, which is a potential academic integrity concern.

---

## Usage

```bash
python3 scheduler.py <input.csv>
python3 scheduler.py <input.csv> --output results.csv
python3 scheduler.py <input.csv> --chart schedule.html
python3 scheduler.py <input.csv> --output results.csv --chart schedule.html
python3 scheduler.py <input.csv> --tries 500   # override attempt count
```

`--output` / `-o` writes the full schedule to a CSV file in addition to printing to the terminal.

`--chart` / `-c` generates a self-contained HTML file with two tabs: a **Timeline** (Gantt chart, one row per seat) and a **Seat Map** (interactive floor plan). The seat map has a time slider and a **Now** button that jumps to the current wall-clock time. To open it:

```bash
open schedule.html        # macOS
start schedule.html       # Windows
xdg-open schedule.html    # Linux
```

**In GitHub Codespaces:** run a local server in the terminal, then open the forwarded port in your browser:
```bash
python3 -m http.server 8080
```
Codespaces will detect port 8080 and show an **Open in Browser** prompt (or find it under the **Ports** tab). Press `Ctrl+C` in the terminal when done to stop the server.

The chart shows all seats as rows with colored bars for each booking. Each exam (CRN) gets a distinct color so same-exam students are immediately visible across rows. Hover a bar for the student's name, times, laptop status, and class. Empty seats appear as faded rows so available capacity is visible at a glance.

---

## Input CSV Format

The tool accepts two formats, detected automatically:

### DRS Export (primary)

The export CSV from the DRS exam management system. Required columns are read directly — no configuration needed.

| Field | Source column(s) |
|---|---|
| Name | `Preferred Name` + `Last Name` |
| Start / End | `Start Time` / `End Time` |
| CRN | `CRN` |
| Private room | `SVC - * Private Room for Assessments` = Yes |
| Laptop | `Exam Type` contains "Canvas/Online" **or** `SVC - * Type responses to short answer and essay questions` = Yes |
| Adjustable desk | `SVC - * Furniture Request During Assessments` = Yes |
| Low vision (CCTV) | `SVC - R1 - CCTV for Exams` = Yes |
| Service animal | `SVC - * Service Animal in Assessment Environment - Notification` = Yes |

Extra columns passed through to output: Subject, Course, Section, Title, Instructor Name, Instructor Email, Exam Date, Tags, Barcode.

### Generic CSV

Hand-crafted or simplified CSV with named columns:

| Column | Required | Description |
|---|---|---|
| `name` | Yes | Student name |
| `start_time` | Yes | Exam start (e.g. `9:00 AM`, `13:00`) |
| `end_time` | Yes | Exam end (same formats) |
| `private_room` | Yes | `Yes` / `No` (also accepts `true`, `1`, `x`, `private`) |
| `laptop` | No | `Yes` / `No` — defaults to No if column absent |
| `furniture` | No | `Yes` / `No` — adjustable-height desk needed |
| `low_vision` | No | `Yes` / `No` — CCTV equipment needed |
| `service_animal` | No | `Yes` / `No` — service animal present |
| `crn` | No | Course section identifier for anti-cheat separation |
| any other columns | No | Passed through to output unchanged |

Column names matched case-insensitively. Accepted time formats: `9:00 AM`, `9:00AM`, `13:00`, `9 AM`, `9AM`.

---

## Output

### Terminal

```
=== SCHEDULED STUDENTS ===
SEAT  NAME                          START       END         LAPTOP  CLASS         TYPE
------------------------------------------------------------------------------------------
b     Alice Johnson                 8:45 AM     11:45 AM    Yes                   Private
c     Dana Kim                      9:00 AM     11:00 AM    No                    Private
5     Bob Lee                       9:00 AM     12:00 PM    Yes                   Shared
17    David Kim                     9:30 AM     12:30 PM    No     BIOL 202 A     Shared
...

=== UNSCHEDULED STUDENTS (1) ===
NAME                          START       END         REASON
----------------------------------------------------------------------
Irene Thomas                  11:00 AM    3:00 PM     All 4 private seats occupied
    ↳ conflicts: Alice Johnson, Carol White, Frank Nguyen, Mike Carter (+1 more)

Summary: 22/23 students scheduled, 1 could not be placed.

=== ADJACENCY WARNINGS (2) ===
  Same-exam students could not be fully separated (room was too full):
  ! Sofia Garcia  seat 21  CHEM 151 AA — adjacent to Priya Nguyen (seat 19)
  ! Priya Nguyen  seat 23  CHEM 151 AA — adjacent to Sofia Garcia (seat 21)

=== SEAT UTILIZATION (window: 8:00 AM–5:00 PM, 540 min) ===
  Private (4 seats):    1275 /   2160 min booked ( 59.0%)  peak 4/4 concurrent
  Shared  (30 seats):    2520 /  16200 min booked ( 15.6%)  peak 7/30 concurrent
```

### CSV output columns

`seat`, `name`, `start_time`, `end_time`, `private_room`, `laptop`, `adj_conflict` (`Yes` if the student could not be separated from a same-exam neighbour), `status` (`Scheduled` / `Unscheduled`), `reason` (blank for scheduled; lists conflicting students for unscheduled), plus any extra columns from the input.

---

## Seat Map

Defined in `seat_format.txt` (source of truth — edit there to change seat layout).

| Seats | Type | Outlet | Count | Notes |
|---|---|---|---|---|
| b, c, d, e | Private rooms | Yes | 4 | c = CCTV/low-vision; e = service-animal/accessible |
| 5–8, 9–11, 12–16, 31–34 | Shared | Yes | 16 | |
| 17–18 | Shared | No | 2 | Adjustable-height desks |
| 19–30 | Shared | No | 12 | |
| **Total** | | | **34** | |

The shared room is L-shaped. Adjacency is same-side only — no cross-aisle (top section) and no cross-wall (center divider between seats 17–29 and 18–30). The bottom cluster (5–8) is not adjacent to the center section.

---

## Algorithm

The scheduler runs independently for each pool (private and shared), then combines results.

**Step 1 — Randomised greedy pass with seat-feature preferences**

Students are sorted by start time, ties broken by end time. The private pool uses direct availability checks across 4 rooms, routing service-animal students to room e, low-vision students to room c, and regular students to b/d. The shared pool maintains three free-sets — outlet (`o`), furniture/adjustable (`f`), and plain no-outlet (`n`) — with a four-case routing table (furniture × laptop) to direct each student to their preferred category first and fall back gracefully. Within each category, a seat is chosen at **random** (rather than by seat ID order) so same-exam students scatter across the room instead of clustering into consecutive seats. All done in a single pass to avoid cross-pass booking conflicts.

Start-time ordering (not EDF) is used because EDF causes double-bookings in the k-machine case: a later-processed student with an earlier actual start can grab a seat released for another student. Start-time ordering guarantees that when a seat is released, all future students start at or after that point.

**Step 2 — Single-swap rescue pass**

After the greedy run, each unscheduled student gets one more attempt: if exactly one scheduled student is blocking a seat, the scheduler tries to move the blocker elsewhere. If a move is found, the unscheduled student takes the vacated slot.

**Step 3 — Anti-cheat adjacency pass**

After all scheduling is complete, students sharing the same CRN (same exam section) with overlapping time windows are checked for physical adjacency. If two same-exam students are placed in neighbouring seats, the scheduler tries to relocate one to a non-adjacent seat. Students who cannot be moved are flagged with an adjacency warning in the output — scheduling is never undone.

**Step 4 — Multi-start (1000 tries by default)**

Because Step 1 is randomised, the entire pipeline runs 1000 times. The result with the fewest unscheduled students is kept; adjacency warnings break ties. Override with `--tries N`. Each run completes in under 1 ms, so 1000 tries adds less than a second of wall time.

---

## Project Structure

```
scheduler.py      — CLI entry point (argparse)
algorithm.py      — scheduling logic; parses seat_format.txt at import
csv_parser.py     — auto-detecting CSV parser (DRS export + generic)
models.py         — Student and Seat dataclasses
output.py         — terminal printing, CSV writing, and HTML chart generation
seat_format.txt   — source of truth for seat numbers and outlet status
sample_import.csv — anonymized example of the DRS input format
test_scheduler.py — lightweight functional tests; runnable as a script
```
