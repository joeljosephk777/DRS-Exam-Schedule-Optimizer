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
    args = parser.parse_args()

    try:
        students = parse_csv(args.input)
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing CSV: {e}", file=sys.stderr)
        sys.exit(1)

    if not students:
        print("No students found in CSV.")
        sys.exit(0)

    scheduled, unscheduled = schedule(students)
    print_schedule(scheduled, unscheduled)

    if args.output:
        write_csv(scheduled, unscheduled, args.output)
        print(f"Results written to: {args.output}")

    if args.chart:
        write_chart(scheduled, unscheduled, args.chart)
        print(f"Chart written to: {args.chart}")


if __name__ == "__main__":
    main()
