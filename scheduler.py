#!/usr/bin/env python3
import argparse
import sys

from csv_parser import parse_csv
from algorithm import schedule
from output import print_schedule, write_csv, write_chart


def main():
    parser = argparse.ArgumentParser(
        description="DRS Exam Schedule Optimizer — assign students to testing seats using interval scheduling."
    )
    parser.add_argument("input", help="Path to input CSV file")
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Write results to a CSV file (in addition to printing to screen)",
    )
    parser.add_argument(
        "--chart", "-c",
        metavar="FILE",
        help="Write a self-contained HTML Gantt chart to FILE (open in any browser)",
    )
    parser.add_argument(
        "--tries", "-t",
        metavar="N",
        type=int,
        default=1000,
        help="Number of random attempts to run; keeps the best result (default: 1000)",
    )
    args = parser.parse_args()

    try:
        students = parse_csv(args.input)
    except OSError as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing CSV: {e}", file=sys.stderr)
        sys.exit(1)

    if not students:
        print("No students found in CSV.")
        sys.exit(0)

    best_score = (float('inf'), float('inf'))
    best_snapshot = None
    best_scheduled, best_unscheduled = None, None

    for _ in range(max(1, args.tries)):
        sched, unsched = schedule(students)
        # Score must be captured NOW — next schedule() call resets all student objects
        score = (len(unsched), sum(s.adjacency_conflict for s in sched))
        if score < best_score:
            best_score = score
            best_snapshot = [(s.assigned_seat, s.adjacency_conflict) for s in students]
            best_scheduled, best_unscheduled = list(sched), list(unsched)

    # Restore best run's assignments onto the student objects
    for s, (seat, conflict) in zip(students, best_snapshot):
        s.assigned_seat = seat
        s.adjacency_conflict = conflict

    scheduled, unscheduled = best_scheduled, best_unscheduled
    print_schedule(scheduled, unscheduled)

    if args.output:
        try:
            write_csv(scheduled, unscheduled, args.output)
            print(f"Results written to: {args.output}")
        except OSError as e:
            print(f"Error writing CSV: {e}", file=sys.stderr)
            sys.exit(1)

    if args.chart:
        try:
            write_chart(scheduled, unscheduled, args.chart)
            print(f"Chart written to: {args.chart}")
        except OSError as e:
            print(f"Error writing chart: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
