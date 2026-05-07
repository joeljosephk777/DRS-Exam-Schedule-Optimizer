``# TODO

## Done this session
- Fixed double-booking bug in `_greedy_pass` and `_shared_greedy_pass`: sort key changed from `(s.end, s.start)` (EDF) to `(s.start, s.end)` (start-time ordering). EDF is correct for single-machine scheduling but causes double-bookings in the k-machine case — a later-processed student with an earlier start can grab a seat released for a different student.
- Added `sample_stress_import.csv` — 70-student stress test (DRS export format, 8-column minimal, 2–4 hr exams, staggered times).
- Added `test_no_double_bookings_stress` to `test_scheduler.py`.
- Updated `test_scheduler.py`: `sample_input.csv` → `sample_import.csv` (old filename no longer exists).
- Updated `CLAUDE.md` and `README.md` algorithm descriptions to reflect start-time ordering and document why EDF was wrong.

## Pending
- Column remapping feature (aliases + `--col` flag) — waiting on the real DRS CSV file. See `future_updates.md`.
