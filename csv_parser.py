import csv
from datetime import datetime
from models import Student

# Columns we consume; everything else is passed through in Student.extra
KNOWN_COLUMNS = {
    "name", "start_time", "end_time", "private_room", "laptop",
    "furniture", "low_vision", "service_animal", "crn",
}

# Flexible aliases for boolean columns
_PRIVATE_TRUE = {"yes", "true", "1", "x", "private", "private room"}
_LAPTOP_TRUE = {"yes", "true", "1", "x"}

_REF_DATE = "2000-01-01"
_TIME_FORMATS = ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]

# DRS export format: normalized keys for derived fields
_DRS_PRIVATE_COL        = "svc_-_*_private_room_for_assessments"
_DRS_TYPE_RESPONSE_COL  = "svc_-_*_type_responses_to_short_answer_and_essay_questions"
_DRS_FURNITURE_COL      = "svc_-_*_furniture_request_during_assessments"
_DRS_LOW_VISION_COL     = "svc_-_r1_-_cctv_for_exams"
_DRS_SERVICE_ANIMAL_COL = "svc_-_*_service_animal_in_assessment_environment_-__notification"

# Extra columns to carry through from the DRS export (everything else is dropped)
_DRS_EXTRA_COLS = {
    "subject", "course", "section", "title",
    "instructor_name", "instructor_email",
    "exam_date", "crn", "tags", "barcode",
}


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


def _is_drs_export(norm: dict[str, str]) -> bool:
    """Detect the DRS exam management export format."""
    return "last_name" in norm and "preferred_name" in norm and "crn" in norm


def _parse_drs_rows(reader: csv.DictReader, norm: dict[str, str]) -> list[Student]:
    """Parse rows from a DRS exam management export CSV."""
    students = []

    def get(row: dict, key: str) -> str:
        orig = norm.get(key)
        return (row[orig] or "").strip() if orig else ""

    for i, row in enumerate(reader, start=2):
        preferred = get(row, "preferred_name")
        last = get(row, "last_name")
        name = f"{preferred} {last}".strip()
        if not name:
            continue  # blank trailing row

        try:
            start = _parse_time(get(row, "start_time"))
        except ValueError:
            raise ValueError(f"Row {i}: cannot parse start_time for '{name}'.")
        try:
            end = _parse_time(get(row, "end_time"))
        except ValueError:
            raise ValueError(f"Row {i}: cannot parse end_time for '{name}'.")

        if end <= start:
            raise ValueError(f"Row {i}: end_time must be after start_time for '{name}'.")

        needs_private        = get(row, _DRS_PRIVATE_COL).lower() in _PRIVATE_TRUE

        exam_type     = get(row, "exam_type")
        type_response = get(row, _DRS_TYPE_RESPONSE_COL).lower()
        uses_laptop   = "canvas/online" in exam_type.lower() or type_response in _LAPTOP_TRUE

        needs_furniture      = get(row, _DRS_FURNITURE_COL).lower()      in _LAPTOP_TRUE
        needs_low_vision     = get(row, _DRS_LOW_VISION_COL).lower()     in _LAPTOP_TRUE
        needs_service_animal = get(row, _DRS_SERVICE_ANIMAL_COL).lower() in _LAPTOP_TRUE
        crn                  = get(row, "crn") or None

        extra = {
            norm[k]: row[norm[k]]
            for k in _DRS_EXTRA_COLS
            if k in norm
        }

        students.append(Student(
            name=name, start=start, end=end,
            needs_private=needs_private, uses_laptop=uses_laptop,
            needs_furniture=needs_furniture,
            needs_low_vision=needs_low_vision,
            needs_service_animal=needs_service_animal,
            crn=crn,
            extra=extra,
        ))

    return students


def parse_csv(path: str) -> list[Student]:
    try:
        return _parse_csv_with_encoding(path, "utf-8-sig")
    except UnicodeDecodeError:
        return _parse_csv_with_encoding(path, "latin-1")


def _parse_csv_with_encoding(path: str, encoding: str) -> list[Student]:
    with open(path, newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file appears to be empty.")

        norm = _normalize_headers(list(reader.fieldnames))

        if _is_drs_export(norm):
            return _parse_drs_rows(reader, norm)

        # Generic format
        def get(row: dict, key: str) -> str:
            orig = norm.get(key)
            if orig is None:
                raise ValueError(f"Required column '{key}' not found in CSV headers: {list(reader.fieldnames)}")
            return (row[orig] or "").strip()

        students = []
        for i, row in enumerate(reader, start=2):
            name = get(row, "name")
            if not name:
                continue

            start = _parse_time(get(row, "start_time"))
            end = _parse_time(get(row, "end_time"))

            if end <= start:
                raise ValueError(f"Row {i}: end_time '{get(row, 'end_time')}' must be after start_time '{get(row, 'start_time')}'.")

            private_raw = get(row, "private_room").lower()
            needs_private = private_raw in _PRIVATE_TRUE

            laptop_orig = norm.get("laptop")
            uses_laptop = (row[laptop_orig].strip().lower() in _LAPTOP_TRUE) if laptop_orig else False

            def _flag(key: str) -> bool:
                orig = norm.get(key)
                return (row[orig] or "").strip().lower() in _LAPTOP_TRUE if orig else False

            needs_furniture      = _flag("furniture")
            needs_low_vision     = _flag("low_vision")
            needs_service_animal = _flag("service_animal")

            crn_orig = norm.get("crn")
            crn = (row[crn_orig] or "").strip() or None if crn_orig else None

            extra = {
                orig: row[orig]
                for norm_key, orig in norm.items()
                if norm_key not in KNOWN_COLUMNS
            }

            students.append(Student(
                name=name, start=start, end=end,
                needs_private=needs_private, uses_laptop=uses_laptop,
                needs_furniture=needs_furniture,
                needs_low_vision=needs_low_vision,
                needs_service_animal=needs_service_animal,
                crn=crn,
                extra=extra,
            ))

        return students
