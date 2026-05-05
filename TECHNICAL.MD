# Technical Deep-Dive: DRS Exam Schedule Optimizer

This document explains how the code works from top to bottom — the data flow, every design decision, the algorithm and why it works, and the optimizations applied.

---

## Table of Contents

1. [High-Level Data Flow](#1-high-level-data-flow)
2. [Language and Libraries](#2-language-and-libraries)
3. [Data Models (models.py)](#3-data-models)
4. [Parsing (csv_parser.py)](#4-parsing)
5. [The Algorithm (algorithm.py)](#5-the-algorithm)
   - 5.1 The Interval Scheduling Problem
   - 5.2 Why Earliest Deadline First (EDF) is Optimal
   - 5.3 Tie-Breaking by Latest Start
   - 5.4 The Min-Heap Seat Selection
   - 5.5 The EDF Availability Invariant
   - 5.6 Independent Pool Scheduling
   - 5.7 The Swap Rescue Pass
6. [Output (output.py)](#6-output)
   - 6.1 Integer-to-Time Formatting
   - 6.2 Conflict Diagnostics
   - 6.3 Utilization Metrics (Sweep Line)
7. [Entry Point (scheduler.py)](#7-entry-point)
8. [Complexity Summary](#8-complexity-summary)

---

## 1. High-Level Data Flow

```
input CSV
    │
    ▼
csv_parser.parse_csv()
    │  produces list[Student]
    ▼
algorithm.schedule()
    │  produces (scheduled: list[Student], unscheduled: list[Student])
    ▼
output.print_schedule()   ──►  terminal
output.write_csv()        ──►  results.csv  (optional)
```

Each stage is a pure function: it takes data in, returns data out, with no global state. This makes each piece independently testable.

---

## 2. Language and Libraries

**Python 3.10+** — chosen because it is the standard scripting language for data processing tasks and requires no installation beyond Python itself.

**Standard library only — no external dependencies.**

| Module | Used for |
|---|---|
| `csv` | Reading input CSV, writing output CSV |
| `datetime` | Parsing time strings like "9:00 AM" into structured values |
| `heapq` | Min-heap priority queue for the scheduling algorithm |
| `dataclasses` | Clean data containers for Student and Seat objects |
| `argparse` | Command-line interface (flags, help text, error messages) |
| `typing` | Type hints (`Optional`, `list`, `tuple`, `dict`) |

No third-party packages (no pip install, no requirements.txt). The program runs on any machine with Python 3.10+.

---

## 3. Data Models

**File: `models.py`**

Two dataclasses represent the core domain objects.

### Student

```python
@dataclass
class Student:
    name: str
    start: int           # minutes since midnight, e.g. 9:00 AM = 540
    end: int             # minutes since midnight, e.g. 12:00 PM = 720
    needs_private: bool
    extra: dict          # any CSV columns beyond the 4 known ones
    assigned_seat: Optional[int] = None  # set by algorithm; None until scheduled
```

**Why store time as integers (minutes since midnight)?**

Originally, `start` and `end` were `datetime` objects. These were replaced with plain integers. Every time comparison in the algorithm (`start >= booked_end`, `end <= booked_start`) becomes a simple integer comparison instead of a `datetime` object method call. Python's `datetime` carries timezone awareness, locale formatting, and calendar arithmetic that we never use — storing raw minutes strips all of that overhead. It also makes the heap arithmetic trivial (no `.timestamp()` calls needed for negation).

The conversion is: `minutes = dt.hour * 60 + dt.minute`. This throws away date information, which is intentional — the scheduler only cares about clock time within a single day.

**Why `extra: dict`?**

The CSV might have columns beyond `name`, `start_time`, `end_time`, `private_room` — things like `course` or `instructor`. Rather than define a rigid schema, any unknown column is captured in `extra` and passed through to the output unchanged. This makes the tool forward-compatible with any additional columns without code changes.

### Seat

```python
@dataclass
class Seat:
    number: int
    is_private: bool
    bookings: list       # list of (start, end) int tuples

    def is_available(self, start, end) -> bool: ...
    def book(self, start, end) -> None: ...
```

A seat holds a list of all time intervals it has been booked for. `is_available` checks whether a proposed interval overlaps with any existing booking.

**Overlap logic:** Two intervals `[A, B]` and `[C, D]` overlap if and only if `A < D and C < B`. The code uses the contrapositive — they do NOT overlap if `B <= C or A >= D`. So:

```python
if not (end <= booked_start or start >= booked_end):
    return False  # overlap found
```

This handles edge cases: if one ends exactly when the other starts (e.g., 12:00 PM to 12:00 PM), the condition `end <= booked_start` is `True`, so no overlap — a seat freed at noon can immediately be given to a student starting at noon.

---

## 4. Parsing

**File: `csv_parser.py`**

### Header normalization

CSV column names from the real world are inconsistent — someone might write `"Name"`, `"NAME"`, `"name "`, or `"Student Name"`. The parser normalizes every header to lowercase with spaces replaced by underscores before matching:

```python
def _normalize_headers(headers):
    return {h.strip().lower().replace(" ", "_"): h for h in headers}
```

This maps `"Start Time"` → `"start_time"`, `"NAME"` → `"name"`, etc. The mapping stores the original header alongside the normalized key so we can still look up values in the raw row dict using the original column name.

### Time parsing

Five different formats are tried in sequence using `datetime.strptime`:

| Format string | Matches |
|---|---|
| `%I:%M %p` | `9:00 AM`, `12:30 PM` |
| `%I:%M%p` | `9:00AM`, `12:30PM` |
| `%H:%M` | `09:00`, `13:30` (24-hour) |
| `%I %p` | `9 AM`, `12 PM` |
| `%I%p` | `9AM`, `12PM` |

A dummy date `"2000-01-01"` is prepended before parsing because `strptime` requires a complete date-time string for most formats. Once parsed, only `dt.hour` and `dt.minute` are used to produce the integer minute value.

### private_room column

A broad set of truthy values is accepted: `"yes"`, `"true"`, `"1"`, `"x"`, `"private"`, `"private room"`. Anything else is treated as shared. This handles human-entered spreadsheet data where people might write any of these.

### Passthrough columns

After consuming the 4 known columns, every remaining column is collected into `Student.extra`:

```python
extra = {
    orig: row[orig]
    for norm_key, orig in norm.items()
    if norm_key not in KNOWN_COLUMNS
}
```

This is a dictionary comprehension: iterate over all headers, skip the ones the program already consumed, keep the rest mapped as `original_column_name → cell_value`.

---

## 5. The Algorithm

**File: `algorithm.py`**

### 5.1 The Interval Scheduling Problem

The core problem: given a set of intervals (each student's exam window), assign as many as possible to a limited number of resources (seats) such that no two intervals assigned to the same resource overlap.

This is called the **Interval Scheduling Maximization Problem** (ISMP). For a single resource, it is solved optimally by the greedy **Earliest Deadline First (EDF)** algorithm. For multiple resources, you run EDF but assign to any available resource at each step — this is equivalent to interval graph coloring and is also optimal.

In our case there are two separate resource pools (private seats and shared seats) and students can only use their designated pool. The problem reduces to running two independent single-pool scheduling problems.

### 5.2 Why Earliest Deadline First (EDF) is Optimal

**Intuition:** If you always pick the student whose exam ends soonest, you free up seats as early as possible, leaving the most room for future students.

**Formal proof (exchange argument):**

Suppose a different algorithm A produces a schedule with more students than EDF. Take the first position where A's ordering differs from EDF's — A chose a student `X` with a later end time instead of EDF's choice `Y` (earlier end). Now swap `X` and `Y` in A's schedule. Since `Y` ends earlier than `X`, placing `Y` first only makes that seat available sooner, which cannot cause any subsequent assignment to fail. After all such swaps, A's ordering becomes identical to EDF's without losing any scheduled students — contradiction.

Therefore no algorithm can schedule more students than EDF. EDF is optimal.

### 5.3 Tie-Breaking by Latest Start

When two students have the same end time, the one with the **latest start** (shortest duration) is processed first. Why?

A shorter exam fits into more gap windows than a longer one. If two students end at 3:00 PM but one starts at 11:00 AM (4 hours) and one starts at 1:00 PM (2 hours), the 2-hour exam is harder to place later because it might not fit into the small gaps that remain. Processing it earlier guarantees it gets a seat, while the 4-hour exam has fewer placement options anyway (it needs a seat free for a longer span).

The sort key is:
```python
sorted(students, key=lambda s: (s.end, -s.start))
```

`-s.start` reverses the start ordering: a later start time becomes a smaller (more negative) sort value, so it sorts earlier.

### 5.4 The Min-Heap Seat Selection

The original code scanned through all seats in a pool every time a student needed one — O(s) per student where s = pool size (3 or 22). The heap approach is O(log s).

Two heaps are maintained throughout the greedy pass:

```
free_heap:  min-heap of seat IDs for seats currently available
busy_heap:  min-heap of (end_time, seat_id) for seats currently occupied
```

For each student:
1. Pop every entry from `busy_heap` where `end_time <= student.start` and push those seat IDs into `free_heap`. These are seats that just finished their last booking and are now free.
2. If `free_heap` is non-empty, pop the smallest seat ID (lowest-numbered seat) and assign the student.
3. If `free_heap` is empty, all seats are occupied — student is unscheduled.

**Why min-heap for `free_heap`?** Python's `heapq` is a min-heap. Storing seat IDs directly means `heappop` always returns the smallest seat number, which preserves the original behavior of preferring lower-numbered seats.

**Why `(end_time, seat_id)` in `busy_heap`?** Sorting by end time lets us efficiently find which seats have finished their last booking. The `seat_id` as a tiebreaker is just for heap stability (so Python can compare tuples when end times are equal).

### 5.5 The EDF Availability Invariant

This is the key insight that makes the heap approach provably correct rather than just a heuristic.

**Claim:** Under EDF ordering, if a seat's most recent booking ends at time `L`, and `L ≤ student.start`, then the seat is guaranteed to have no overlap with the student's interval.

**Proof:**

We process students in order of end time. When we process the current student with end time `E`:
- All existing bookings on all seats were made for students with end time `≤ E` (EDF)
- Therefore every booking `(Sj, Ej)` satisfies `Ej ≤ E`

Now suppose seat has a booking with `Ej > student.start (= S)`. Does it overlap with `[S, E]`?
- We need to check: does `not (E ≤ Sj or S ≥ Ej)` hold?
- We know `Sj < Ej ≤ E`, so `Sj < E`, meaning `E ≤ Sj` is False
- We know `S < Ej`, so `S ≥ Ej` is False
- Therefore overlap = `not (False or False)` = **True**

So any booking with `Ej > S` creates an overlap. Equivalently: if the maximum booking end `L ≤ S`, all bookings end before or at `S`, and none can overlap with `[S, E]`.

This means the heap's `end_time` is not just a filter — it is an exact availability test under EDF. We don't need to scan the full booking list at all during the greedy pass.

### 5.6 Independent Pool Scheduling

Private-room students (seats 1, 3, 4) and shared students (seats 5–25) never compete for the same seats. Separating them into two completely independent `_greedy_pass` calls has two benefits:

1. **Clarity:** The EDF invariant applies cleanly within each pool. If both pools were mixed in one sort, the interleaving of private and shared students in the EDF order would be irrelevant noise.

2. **Correctness of the swap pass:** After the greedy run, the swap pass operates per-pool. If pools shared a sort order, a private student's placement might be affected by shared student processing, making the invariant harder to reason about.

```python
private_students = [s for s in students if s.needs_private]
shared_students  = [s for s in students if not s.needs_private]

priv_sched,   priv_unsched   = _greedy_pass(private_students, private_ids, seats)
shared_sched, shared_unsched = _greedy_pass(shared_students,  shared_ids,  seats)
```

### 5.7 The Swap Rescue Pass

The EDF greedy is optimal in the sense that no re-ordering of students can schedule more people. However, there is a class of cases it cannot handle: situations where a different seat assignment (not a different processing order) would allow an additional student to be scheduled.

**Example:** Private seats 1, 3, 4. Three students A (9–12), B (9–3), C (12–3), and D (9–3).

EDF order: A, C, B/D (tied at end=3). 
- A → seat 1, C → seat 1 (after A finishes at 12), B → seat 3, D → seat 4.
- All four scheduled. Fine.

But consider: A (9–5), B (9–5), C (9–3), D (3–5).

EDF order: C, D, A, B.
- C → seat 1, D → seat 1 (C done at 3), A → seat 3, B → seat 4. All scheduled.

Now a trickier case: A (9–5), B (9–5), C (9–5), D (10–3).

EDF order: D, A, B, C.
- D → seat 1, A → seat 3, B → seat 4, C → unscheduled (all 3 seats occupied).

The swap pass now checks C: "Is there any seat with exactly one conflict?" Seat 1 has booking (10, 3*60+0=180) for D, and C's window (9, 5pm=1020) overlaps with it. Seat 3 has A (9–5), seat 4 has B (9–5) — both fully overlap C, can't help. But for seat 1: D's booking (600 to 900) conflicts with C (540 to 1020). Can D move? D is 10 AM – 3 PM. Seat 3 has A (9–5): D (10–3) overlaps with A (9–5) ❌. Seat 4 has B (9–5): same ❌. No swap possible. C stays unscheduled — correctly, since all 3 seats are fully occupied for C's entire window.

The swap pass's logic:
```python
for seat_id in pool_ids:
    conflicts = [booking for booking in seat.bookings if overlaps with [S, E]]
    if len(conflicts) != 1:
        continue   # 0 = seat should have been assigned (bug), 2+ = need multiple swaps
    blocker = find student owning that booking
    for alt_id in other seats:
        if alt_seat is available for blocker's interval:
            move blocker to alt_seat
            assign unscheduled student to freed seat
            break
```

Only single swaps are attempted. Chain swaps (move A to free space for B, move B to free space for C) are not implemented — they would add O(n³) complexity and cover extremely rare edge cases.

---

## 6. Output

**File: `output.py`**

### 6.1 Integer-to-Time Formatting

`_fmt(minutes)` converts an integer back to a human-readable 12-hour string.

```python
def _fmt(minutes: int) -> str:
    h, m = divmod(minutes, 60)        # e.g. 525 → h=8, m=45
    ampm = "AM" if h < 12 else "PM"
    h = h % 12 or 12                  # 0→12 (midnight), 13→1, 12 stays 12
    return f"{h}:{m:02d} {ampm}"      # "8:45 AM"
```

The expression `h % 12 or 12` handles two edge cases:
- `0 % 12 = 0`, and `0 or 12 = 12` → midnight displays as `12:00 AM` ✓
- `12 % 12 = 0`, and `0 or 12 = 12` → noon displays as `12:00 PM` ✓

`{m:02d}` pads minutes with a leading zero so `9:05 AM` displays correctly rather than `9:5 AM`.

### 6.2 Conflict Diagnostics

For every unscheduled student, `_conflict_info` finds which scheduled students in the same pool have overlapping time windows:

```python
conflicts = [
    st for st in scheduled
    if st.needs_private == student.needs_private          # same pool
    and not (student.end <= st.start or student.start >= st.end)  # overlaps
]
```

This tells administrators exactly why a student couldn't be placed — not just "no seat available" but "seats were occupied by Alice, Bob, Carol during your window." This is the information needed to decide whether to add capacity or ask a student to shift their time.

The terminal output shows up to 4 names with a "+N more" indicator. The CSV output includes the full list.

### 6.3 Utilization Metrics (Sweep Line Algorithm)

The utilization section computes two statistics per pool:

**Booked percentage:**
```
booked_minutes = sum of (end - start) for each scheduled student in pool
capacity_minutes = seat_count × day_window
utilization = booked_minutes / capacity_minutes × 100
```

`day_window` is `max(end) - min(start)` across all students (scheduled and unscheduled), which represents the actual operating window of the day.

**Peak concurrent occupancy** uses a sweep line algorithm:

```python
events = []
for student in students:
    events.append((student.start, +1))   # arrival event
    events.append((student.end,   -1))   # departure event
events.sort()
current = peak = 0
for _, delta in events:
    current += delta
    peak = max(peak, current)
```

This works by imagining a horizontal line sweeping from left to right across the time axis. Every time we hit a student's start time, one more seat becomes occupied (+1). Every time we hit an end time, one seat is freed (-1). The maximum value of `current` at any point is the peak.

**Sorting detail:** When a student ends at time T and another starts at T, the events are `(T, -1)` and `(T, +1)`. Sorting by the second element puts -1 before +1, so the departure is counted before the arrival. This correctly reflects that the seat is freed at T and immediately reused — the peak doesn't double-count both the departing and arriving student at the same moment.

---

## 7. Entry Point

**File: `scheduler.py`**

`argparse` provides the command-line interface with automatic `--help` generation, type validation, and error messages. Two arguments:

- `input` (positional, required) — path to the input CSV
- `--output` / `-o` (optional) — path for the results CSV

Error handling wraps only the parsing step (where user-provided data can fail) and file access. The algorithm and output are not wrapped — if they fail, it indicates a programming error, not user error, and the full traceback is more useful than a caught exception.

---

## 8. Complexity Summary

| Step | Complexity | Notes |
|---|---|---|
| CSV parsing | O(n) | One pass through rows |
| Sort students | O(n log n) | Python's Timsort |
| Greedy pass (per pool) | O(n log s) | n students, s seats in pool (3 or 22) |
| Swap pass (per pool) | O(u · s · k) | u unscheduled, s seats, k bookings/seat |
| Conflict diagnostics | O(u · n) | u unscheduled × n scheduled |
| Peak concurrent | O(n log n) | Sort events list |
| **Total** | **O(n log n)** | Sort dominates; all other steps are O(n log n) or smaller |

**Space:** O(n) for student list + O(s · k) for seat bookings, where s·k ≤ n (each student has exactly one booking). So O(n) overall.

For the DRS use case (n ≈ 60 students, s = 3 or 22 seats), all operations complete in well under a millisecond. The algorithm would remain fast up to thousands of students.
