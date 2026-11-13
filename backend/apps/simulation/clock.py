"""Game time (Document 07, Section 5.1).

Ticks count working time only: 36 ticks of 15 minutes per working day
(08:00-17:00). Tick n (n >= 1) starts at

    08:00 + 15 min * ((n - 1) mod 36)   on working day number (n - 1) // 36,

counting working days from the first working day on or after the clock start.
Ghana keeps UTC all year, so game times are stored in UTC.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import UTC, date, datetime, time, timedelta

from apps.standards.calendar import is_working_day, next_working_day

TICK_MINUTES = 15
DAY_START = time(8, 0)
DAY_END = time(17, 0)
TICKS_PER_DAY = 36  # (17:00 - 08:00) / 15 minutes
TICKS_PER_HOUR = 60 // TICK_MINUTES
REAL_SECONDS_PER_TICK_AT_1X = 5.0  # 20 seconds per game hour


class Calendar:
    """Working days counted from a clock start, built lazily and cached."""

    def __init__(self, start: date) -> None:
        self.start = start
        self._days: list[date] = [next_working_day(start)]

    def day(self, index: int) -> date:
        while len(self._days) <= index:
            nxt = self._days[-1] + timedelta(days=1)
            self._days.append(next_working_day(nxt))
        return self._days[index]

    def index_of(self, day: date) -> int:
        """Index of the first working day on or after ``day`` (clamped to the start)."""
        target = next_working_day(max(day, self.start))
        while self._days[-1] < target:
            self.day(len(self._days))
        return bisect_left(self._days, target)

    # --- ticks -------------------------------------------------------------------

    def tick_start(self, tick: int) -> datetime:
        if tick < 1:
            raise ValueError("Ticks start at 1")
        day_index, slot = divmod(tick - 1, TICKS_PER_DAY)
        start = datetime.combine(self.day(day_index), DAY_START, tzinfo=UTC)
        return start + timedelta(minutes=TICK_MINUTES * slot)

    def tick_end(self, tick: int) -> datetime:
        return self.tick_start(tick) + timedelta(minutes=TICK_MINUTES)

    def first_tick_of_day(self, day_index: int) -> int:
        return day_index * TICKS_PER_DAY + 1

    def tick_at(self, moment: datetime) -> int:
        """The tick in progress at ``moment``, or the next tick if it is outside working time."""
        day, clock = moment.date(), moment.time()
        if day < self.start:
            return 1
        if not is_working_day(day) or clock >= DAY_END:
            return self.first_tick_of_day(self.index_of(day + timedelta(days=1)))
        index = self.index_of(day)
        if clock < DAY_START:
            return self.first_tick_of_day(index)
        minutes = (moment.hour - DAY_START.hour) * 60 + moment.minute
        return self.first_tick_of_day(index) + minutes // TICK_MINUTES

    def is_last_tick_of_day(self, tick: int) -> bool:
        return tick % TICKS_PER_DAY == 0

    def is_first_tick_of_month(self, tick: int) -> bool:
        """True for the first tick of the first working day of a calendar month."""
        if (tick - 1) % TICKS_PER_DAY:
            return False
        day_index = (tick - 1) // TICKS_PER_DAY
        today = self.day(day_index)
        return day_index == 0 or self.day(day_index - 1).month != today.month


def month_start(day: date) -> date:
    return day.replace(day=1)


def previous_month_end(day: date) -> date:
    return day.replace(day=1) - timedelta(days=1)
