import heapq
from models import Student, Seat

# Seat numbers 1-25; private rooms are seats 1, 3, and 4
PRIVATE_SEAT_NUMBERS = {1, 3, 4}
ALL_SEAT_NUMBERS = set(range(1, 26))
SHARED_SEAT_NUMBERS = ALL_SEAT_NUMBERS - PRIVATE_SEAT_NUMBERS


def _build_seats() -> dict[int, Seat]:
    return {
        n: Seat(number=n, is_private=(n in PRIVATE_SEAT_NUMBERS))
        for n in ALL_SEAT_NUMBERS
    }


def _greedy_pass(
    students: list[Student],
    pool_ids: list[int],
    seats: dict[int, Seat],
) -> tuple[list[Student], list[Student]]:
    """
    EDF greedy with min-heap seat selection. Tie-breaks equal end times by latest
    start (shortest-duration exam first), which leaves more room for longer exams.

    Uses two heaps:
      free_heap  — seat IDs available right now (min by seat number)
      busy_heap  — (end_time, seat_id) for occupied seats

    Under EDF processing order, a seat's last-booking end time is an exact
    availability test: last_end <= student.start guarantees no overlap.
    """
    free_heap: list[int] = list(pool_ids)
    heapq.heapify(free_heap)
    busy_heap: list[tuple[int, int]] = []  # (last_booking_end, seat_id)

    scheduled: list[Student] = []
    unscheduled: list[Student] = []

    for student in sorted(students, key=lambda s: (s.end, -s.start)):
        # Release seats whose last booking finished at or before this student's start
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


def _swap_pass(
    unscheduled: list[Student],
    scheduled: list[Student],
    seats: dict[int, Seat],
    pool_ids: list[int],
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
            # Need exactly one conflicting booking to attempt a single swap
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
    Greedy interval scheduling (earliest end time, latest start tie-break) with a
    post-greedy single-swap rescue pass. Private and shared pools are independent.
    Returns (scheduled, unscheduled).
    """
    seats = _build_seats()
    private_ids = sorted(PRIVATE_SEAT_NUMBERS)
    shared_ids = sorted(SHARED_SEAT_NUMBERS)

    private_students = [s for s in students if s.needs_private]
    shared_students = [s for s in students if not s.needs_private]

    priv_sched, priv_unsched = _greedy_pass(private_students, private_ids, seats)
    shared_sched, shared_unsched = _greedy_pass(shared_students, shared_ids, seats)

    priv_sched, priv_unsched = _swap_pass(priv_unsched, priv_sched, seats, private_ids)
    shared_sched, shared_unsched = _swap_pass(shared_unsched, shared_sched, seats, shared_ids)

    return priv_sched + shared_sched, priv_unsched + shared_unsched
