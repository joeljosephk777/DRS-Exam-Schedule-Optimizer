import heapq
import os
import random
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
try:
    OUTLET_IDS, NO_OUTLET_IDS, PRIVATE_IDS = _parse_seat_format(_SEAT_FORMAT_PATH)
except FileNotFoundError:
    raise FileNotFoundError(
        f"seat_format.txt not found at '{_SEAT_FORMAT_PATH}'. "
        "This file is required to define the seat layout."
    )
_ALL_SHARED_IDS: list[int] = sorted(OUTLET_IDS + NO_OUTLET_IDS)
FURNITURE_IDS: list[int] = [17, 18]  # adjustable-height desks within no-outlet pool
_FURNITURE_SET = set(FURNITURE_IDS)

# Physical seat adjacency — same-side neighbours only (no cross-aisle, no cross-wall)
ADJACENCY: dict[SeatID, list[SeatID]] = {
    # Top — Side A: 31, 16, 15, 14, 13, 12
    31: [16],       16: [31, 15],   15: [16, 14],
    14: [15, 13],   13: [14, 12],   12: [13],
    # Top — Side B: 11, 32, 10, 33, 9, 34
    11: [32],       32: [11, 10],   10: [32, 33],
    33: [10, 9],    9:  [33, 34],   34: [9],
    # Center — Odd side: 17, 19, 21, 23, 25, 27, 29
    17: [19],       19: [17, 21],   21: [19, 23],
    23: [21, 25],   25: [23, 27],   27: [25, 29],   29: [27],
    # Center — Even side: 18, 20, 22, 24, 26, 28, 30
    18: [20],       20: [18, 22],   22: [20, 24],
    24: [22, 26],   26: [24, 28],   28: [26, 30],   30: [28],
    # Bottom: 5, 8, 6, 7
    5: [8],         8: [5, 6],      6: [8, 7],      7: [6],
    # Private rooms are fully enclosed — no adjacency entries
}


def _build_seats() -> dict[SeatID, Seat]:
    seats: dict[SeatID, Seat] = {}
    for n in OUTLET_IDS:
        seats[n] = Seat(number=n, is_private=False, has_outlet=True)
    for n in NO_OUTLET_IDS:
        seats[n] = Seat(number=n, is_private=False, has_outlet=False)
    for n in PRIVATE_IDS:
        seats[n] = Seat(number=n, is_private=True, has_outlet=True)
    return seats



def _private_greedy_with_preferences(
    students: list[Student],
    seats: dict[SeatID, Seat],
) -> tuple[list[Student], list[Student]]:
    """
    Greedy pass for private students using is_available() directly (only 4 rooms).
    Service-animal students prefer room e; low-vision students prefer room c;
    regular students avoid special rooms. Falls back to any available room.
    """
    def _sort_key(s: Student):
        prio = 0 if s.needs_service_animal else (1 if s.needs_low_vision else 2)
        return (s.start, prio, s.end)

    def _room_order(s: Student) -> list[str]:
        if s.needs_service_animal:
            return ["e", "b", "c", "d"]
        if s.needs_low_vision:
            return ["c", "b", "d", "e"]
        return ["b", "d", "c", "e"]

    scheduled: list[Student] = []
    unscheduled: list[Student] = []
    for student in sorted(students, key=_sort_key):
        placed = False
        for room in _room_order(student):
            if room in seats and seats[room].is_available(student.start, student.end):
                seats[room].book(student.start, student.end)
                student.assigned_seat = room
                scheduled.append(student)
                placed = True
                break
        if not placed:
            unscheduled.append(student)
    return scheduled, unscheduled


def _shared_greedy_pass(
    students: list[Student],
    outlet_ids: list[int],
    no_outlet_ids: list[int],
    seats: dict[SeatID, Seat],
) -> tuple[list[Student], list[Student]]:
    """
    Greedy pass for shared students, sorted by start time, with seat-feature preference.

    Three free sets: outlet ('o'), furniture/adjustable ('f'), plain no-outlet ('n').
    Selection within each set is random so same-CRN students scatter across the room
    rather than clustering into consecutive seats (which the anti-cheat pass then
    struggles to fix). busy_heap remains a min-heap ordered by end time.
    """
    furniture_ids = [x for x in no_outlet_ids if x in _FURNITURE_SET]
    plain_no_outlet_ids = [x for x in no_outlet_ids if x not in _FURNITURE_SET]

    outlet_free: set  = set(outlet_ids)
    furniture_free: set = set(furniture_ids)
    no_outlet_free: set = set(plain_no_outlet_ids)
    busy_heap: list = []  # (end, seat_id, category: 'o'/'f'/'n')

    scheduled: list[Student] = []
    unscheduled: list[Student] = []

    def _pop(sets_and_cats: list) -> tuple:
        for cat, free in sets_and_cats:
            if free:
                seat_id = random.choice(list(free))
                free.discard(seat_id)
                return seat_id, cat
        return None, None

    for student in sorted(students, key=lambda s: (s.start, s.end)):
        # Release seats whose last booking ended at or before student's start
        while busy_heap and busy_heap[0][0] <= student.start:
            _, seat_id, cat = heapq.heappop(busy_heap)
            if cat == "o":
                outlet_free.add(seat_id)
            elif cat == "f":
                furniture_free.add(seat_id)
            else:
                no_outlet_free.add(seat_id)

        if student.needs_furniture and student.uses_laptop:
            seat_id, cat = _pop([("f", furniture_free), ("o", outlet_free), ("n", no_outlet_free)])
        elif student.needs_furniture:
            seat_id, cat = _pop([("f", furniture_free), ("n", no_outlet_free), ("o", outlet_free)])
        elif student.uses_laptop:
            seat_id, cat = _pop([("o", outlet_free), ("n", no_outlet_free), ("f", furniture_free)])
        else:
            seat_id, cat = _pop([("n", no_outlet_free), ("o", outlet_free), ("f", furniture_free)])

        if seat_id is not None:
            seats[seat_id].book(student.start, student.end)
            student.assigned_seat = seat_id
            heapq.heappush(busy_heap, (student.end, seat_id, cat))
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


def _try_relocate(
    student: Student,
    crn_group: list[Student],
    seats: dict[SeatID, Seat],
) -> bool:
    """
    Try to move student to a non-adjacent, available seat within their pool.
    Returns True and updates student.assigned_seat on success; False otherwise.
    """
    pool = list(PRIVATE_IDS) if student.needs_private else list(_ALL_SHARED_IDS)

    banned: set = set()
    for peer in crn_group:
        if peer is student:
            continue
        if student.end <= peer.start or student.start >= peer.end:
            continue  # no time overlap — not a cheating risk
        banned.add(peer.assigned_seat)
        banned.update(ADJACENCY.get(peer.assigned_seat, []))

    for alt_id in pool:
        if alt_id == student.assigned_seat or alt_id in banned:
            continue
        if not seats[alt_id].is_available(student.start, student.end):
            continue
        seats[student.assigned_seat].bookings.remove((student.start, student.end))
        seats[alt_id].book(student.start, student.end)
        student.assigned_seat = alt_id
        return True
    return False


def _anti_cheat_pass(
    scheduled: list[Student],
    seats: dict[SeatID, Seat],
) -> None:
    """
    Post-process to separate same-CRN students from adjacent seats.
    Sets adjacency_conflict=True on any student that could not be moved.
    """
    by_crn: dict[str, list[Student]] = {}
    for s in scheduled:
        if s.crn:
            by_crn.setdefault(s.crn, []).append(s)

    for group in by_crn.values():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.end <= b.start or b.end <= a.start:
                    continue  # no time overlap
                if b.assigned_seat not in ADJACENCY.get(a.assigned_seat, []):
                    continue  # not adjacent
                if not _try_relocate(b, group, seats):
                    b.adjacency_conflict = True


def schedule(students: list[Student]) -> tuple[list[Student], list[Student]]:
    """
    Greedy interval scheduling (start-time order) with a post-greedy single-swap
    rescue pass. Laptop students get first pick of outlet seats within the shared
    pool. Private and shared pools are scheduled independently.
    Returns (scheduled, unscheduled).
    """
    for s in students:
        s.assigned_seat = None
        s.adjacency_conflict = False

    seats = _build_seats()

    private_students = [s for s in students if s.needs_private]
    shared_students = [s for s in students if not s.needs_private]

    priv_sched, priv_unsched = _private_greedy_with_preferences(private_students, seats)
    priv_sched, priv_unsched = _swap_pass(priv_unsched, priv_sched, seats, PRIVATE_IDS)

    shared_sched, shared_unsched = _shared_greedy_pass(
        shared_students, OUTLET_IDS, NO_OUTLET_IDS, seats
    )
    shared_sched, shared_unsched = _swap_pass(
        shared_unsched, shared_sched, seats, _ALL_SHARED_IDS
    )

    all_scheduled = priv_sched + shared_sched
    _anti_cheat_pass(all_scheduled, seats)
    return all_scheduled, priv_unsched + shared_unsched
