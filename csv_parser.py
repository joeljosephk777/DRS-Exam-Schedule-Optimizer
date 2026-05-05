import csv
from datetime import datetime
from models import Student

# Columns we consume; everything else is passed through in Student.extra
KNOWN_COLUMNS = {"name", "start_time", "end_time", "private_room"}

# Flexible aliases for the private_room column
_PRIVATE_TRUE = {"yes", "true", "1", "x", "private", "private room"}

_REF_DATE = "2000-01-01"
_TIME_FORMATS = ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]


def _parse_time(value: str) -> int:
    """Parse a time string and return minutes since midnight."""
    value = value.strip()
    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(f"{_REF_DATE} {value}", f"%Y-%m-%d {fmt}")
            return dt.hour * 60 + dt.minute
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time: '{value}'. Expected formats like '9:00 AM' or '13:00'.")


def _normalize_headers(headers: list[str]) -> dict[str, str]:
    """Return mapping of normalized header -> original header."""
    return {h.strip().lower().replace(" ", "_"): h for h in headers}


def parse_csv(path: str) -> list[Student]:
    students = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file appears to be empty.")

        norm = _normalize_headers(list(reader.fieldnames))

        def get(row: dict, key: str) -> str:
            orig = norm.get(key)
            if orig is None:
                raise ValueError(f"Required column '{key}' not found in CSV headers: {list(reader.fieldnames)}")
            return row[orig].strip()

        for i, row in enumerate(reader, start=2):
            name = get(row, "name")
            if not name:
                continue  # skip blank rows

            start = _parse_time(get(row, "start_time"))
            end = _parse_time(get(row, "end_time"))

            if end <= start:
                raise ValueError(f"Row {i}: end_time '{get(row, 'end_time')}' must be after start_time '{get(row, 'start_time')}'.")

            private_raw = get(row, "private_room").lower()
            needs_private = private_raw in _PRIVATE_TRUE

            extra = {
                orig: row[orig]
                for norm_key, orig in norm.items()
                if norm_key not in KNOWN_COLUMNS
            }

            students.append(Student(name=name, start=start, end=end, needs_private=needs_private, extra=extra))

    return students
