from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Student:
    name: str
    start: int   # minutes since midnight
    end: int     # minutes since midnight
    needs_private: bool
    extra: dict = field(default_factory=dict)
    assigned_seat: Optional[int] = None


@dataclass
class Seat:
    number: int
    is_private: bool
    bookings: list = field(default_factory=list)  # list of (start, end) int-minute tuples

    def is_available(self, start: int, end: int) -> bool:
        for booked_start, booked_end in self.bookings:
            if not (end <= booked_start or start >= booked_end):
                return False
        return True

    def book(self, start: int, end: int) -> None:
        self.bookings.append((start, end))
