import heapq
import os
from models import Student, Seat, SeatID


def _parse_seat_list(spec: str) -> list:
    """Parse a comma-separated seat spec like '5-8,12-16,31,b,c' into seat IDs."""
    result = []
    for token in spec.strip().split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            result.append(int(token))
        elif "-" in token and token[0].isdigit():
            lo, hi = token.split("-", 1)
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(token)
    return result


def _parse_seat_format(path: str) -> tuple[list[int], list[int], list[str]]:
    """
    Read seat_format.txt and return (outlet_ids, no_outlet_ids, private_ids).
    Lines are identified by keywords: 'outlet'/'without'/'private'.
    """
    outlet_ids: list[int] = []
    no_outlet_ids: list[int] = []
    private_ids: list[str] = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if " - " not in line:
                continue
            label, spec = line.split(" - ", 1)
            label_l = label.lower()
            ids = _parse_seat_list(spec)
            if "private" in label_l:
                private_ids = [str(x) for x in ids]
            elif "without" in label_l:
                no_outlet_ids = [x for x in ids if isinstance(x, int)]
            elif "outlet" in label_l:
                outlet_ids = [x for x in ids if isinstance(x, int)]

    return outlet_ids, no_outlet_ids, private_ids


_SEAT_FORMAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seat_format.txt")
OUTLET_IDS, NO_OUTLET_IDS, PRIVATE_IDS = _parse_seat_format(_SEAT_FORMAT_PATH)
_ALL_SHARED_IDS: list[int] = sorted(OUTLET_IDS + NO_OUTLET_IDS)


def _build_seats() -> dict[SeatID, Seat]:
    seats: dict[SeatID, Seat] = {}
    for n in OUTLET_IDS:
        seats[n] = Seat(number=n, is_private=False, has_outlet=True)
    for n in NO_OUTLET_IDS:
        seats[n] = Seat(number=n, is_private=False, has_outlet=False)
    for n in PRIVATE_IDS:
        seats[n] = Seat(number=n, is_private=True, has_outlet=True)
    return seats


def _greedy_pass(
    students: list[Student],
    pool_ids: list,
    seats: dict[SeatID, Seat],
) -> tuple[list[Student], list[Student]]:
    """
    EDF greedy with min-heap seat selection. Tie-breaks equal end times by latest
    start (shortest-duration exam first), which leaves more room for longer exams.
    """
    free_heap: list = list(pool_ids)
    heapq.heapify(free_heap)
    busy_heap: list = []  # (last_booking_end, seat_id)

    scheduled: list[Student] = []
    unscheduled: list[Student] = []

    for student in sorted(students, key=lambda s: (s.start, s.end)):
        while busy_heap and busy_heap[0][0] <= student.start:
            _, seat_id = heapq.heappop(busy_heap)
            heapq.heappush(free_heap, seat_id)

        if free_heap:
            seat_id = heapq.heappop(free_heap)
            seats[seat_id].book(student.start, student.end)
            student.assigned_seat = seat_id
            heapq.heappush(busy_heap, (student.end, seat_id))
            scheduled.append(student)
        else:
            unscheduled.append(student)

    return scheduled, unscheduled


def _shared_greedy_pass(
    students: list[Student],
    outlet_ids: list[int],
    no_outlet_ids: list[int],
    seats: dict[SeatID, Seat],
) -> tuple[list[Student], list[Student]]:
    """
    EDF greedy for shared (non-private) students with laptop-outlet preference.

    Maintains two free heaps — outlet and non-outlet — plus one unified busy heap.
    Laptop students prefer outlet seats; non-laptop students prefer non-outlet seats
    (falling back to outlet only when non-outlet is full). This runs in a single pass
    so there are no cross-pass booking conflicts.
    """
    outlet_heap: list[int] = list(outlet_ids)
    heapq.heapify(outlet_heap)
    no_outlet_heap: list[int] = list(no_outlet_ids)
    heapq.heapify(no_outlet_heap)
    busy_heap: list = []  # (last_booking_end, seat_id, is_outlet: bool)

    scheduled: list[Student] = []
    unscheduled: list[Student] = []

    for student in sorted(students, key=lambda s: (s.start, s.end)):
        # Release seats whose last booking ended at or before student's start
        while busy_heap and busy_heap[0][0] <= student.start:
            _, seat_id, is_outlet = heapq.heappop(busy_heap)
            if is_outlet:
                heapq.heappush(outlet_heap, seat_id)
            else:
                heapq.heappush(no_outlet_heap, seat_id)

        seat_id = None
        is_outlet = False

        if student.uses_laptop:
            # Prefer outlet seats; fall back to non-outlet only if none free
            if outlet_heap:
                seat_id = heapq.heappop(outlet_heap)
                is_outlet = True
            elif no_outlet_heap:
                seat_id = heapq.heappop(no_outlet_heap)
                is_outlet = False
        else:
            # Prefer non-outlet seats to leave outlets free for laptop students
            if no_outlet_heap:
                seat_id = heapq.heappop(no_outlet_heap)
                is_outlet = False
            elif outlet_heap:
                seat_id = heapq.heappop(outlet_heap)
                is_outlet = True

        if seat_id is not None:
            seats[seat_id].book(student.start, student.end)
            student.assigned_seat = seat_id
            heapq.heappush(busy_heap, (student.end, seat_id, is_outlet))
            scheduled.append(student)
        else:
            unscheduled.append(student)

    return scheduled, unscheduled


def _swap_pass(
    unscheduled: list[Student],
    scheduled: list[Student],
    seats: dict[SeatID, Seat],
    pool_ids: list,
) -> tuple[list[Student], list[Student]]:
    """
    For each unscheduled student, try to move one already-scheduled student to
    a different seat in the same pool to free a slot. Only single-swap rescues.
    """
    still_unscheduled: list[Student] = []
    newly_scheduled: list[Student] = []

    for student in unscheduled:
        S, E = student.start, student.end
        placed = False

        for seat_id in pool_ids:
            seat = seats[seat_id]
            conflicts = [
                (bs, be) for bs, be in seat.bookings
                if not (E <= bs or S >= be)
            ]
            if len(conflicts) != 1:
                continue

            cs, ce = conflicts[0]
            blocker = next(
                (
                    st for st in scheduled + newly_scheduled
                    if st.start == cs and st.end == ce and st.assigned_seat == seat_id
                ),
                None,
            )
            if blocker is None:
                continue

            for alt_id in pool_ids:
                if alt_id == seat_id:
                    continue
                if seats[alt_id].is_available(blocker.start, blocker.end):
                    seat.bookings.remove((blocker.start, blocker.end))
                    seats[alt_id].book(blocker.start, blocker.end)
                    blocker.assigned_seat = alt_id
                    seat.book(S, E)
                    student.assigned_seat = seat_id
                    placed = True
                    break

            if placed:
                break

        if placed:
            newly_scheduled.append(student)
        else:
            still_unscheduled.append(student)

    return scheduled + newly_scheduled, still_unscheduled


def schedule(students: list[Student]) -> tuple[list[Student], list[Student]]:
    """
    Greedy interval scheduling (EDF, earliest end time / latest start tie-break)
    with a post-greedy single-swap rescue pass.

    Laptop students get first pick of outlet seats within the shared pool (single
    EDF pass, no conflicts). Private and shared pools are independent.
    Returns (scheduled, unscheduled).
    """
    seats = _build_seats()

    private_students = [s for s in students if s.needs_private]
    shared_students = [s for s in students if not s.needs_private]

    priv_sched, priv_unsched = _greedy_pass(private_students, PRIVATE_IDS, seats)
    priv_sched, priv_unsched = _swap_pass(priv_unsched, priv_sched, seats, PRIVATE_IDS)

    shared_sched, shared_unsched = _shared_greedy_pass(
        shared_students, OUTLET_IDS, NO_OUTLET_IDS, seats
    )
    shared_sched, shared_unsched = _swap_pass(
        shared_unsched, shared_sched, seats, _ALL_SHARED_IDS
    )

    return priv_sched + shared_sched, priv_unsched + shared_unsched
