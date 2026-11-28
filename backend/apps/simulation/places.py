"""Where people are (P4.2; Document 05, Sections 5.4 and 8.2; Document 10).

A person's place follows from what the game already records about them, at a tick.
Nothing here is stored, and nothing is random, so two people watching one game at one
tick see the same office, and a replay sees it too. In order, the first that holds:

* after hours (the clock stands at a day's end, 17:00): **out**;
* on a training course (``away_until_tick``): **out**, at the course;
* in a meeting the game holds (below): in its **meeting room** or the **boardroom**;
* working on an item (in progress and assigned to them): at their **desk**;
* free: at the **cafeteria** for a break, or at their **desk**.

ASSUMPTION A-091 (the meetings' times and who goes; breaks):

* The monthly **Data Quality Review** is built at a month's last tick. It is held the
  next working morning, 10:00-11:00 (the 9th to 12th ticks after it), in the meeting
  room. Data Operations' Senior Data Officers go; with none, its most senior person
  (the highest role, then the longest serving).
* A quarterly **board review** is held from its tick (the quarter's first, 08:00) for
  two hours, in the boardroom (a Startup's meeting room). The most senior person of Data
  Operations presents the data.
* People in a meeting do no work on its ticks (``work_tick`` leaves them out), as people
  on a course do. That time is part of the game, so it replays.
* Training courses are bought from outside (GHS 2,500, P2.9), so a person on one is out.
  The PRD's building has no training room.
* A free person takes a break at the cafeteria (a Startup's kitchen) in the lunch hour,
  12:00-13:00, and at any time when their morale is below 0.5. Otherwise they wait at
  their desk. A break never stops work: a person with an item is at their desk.
* Sales meetings (P3.9) are held at the bureau: the prospect's representative comes in
  (P4.5, A-094, which replaced this assumption's first reading, Sales out at the prospect).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from apps.org.models import Employee
from apps.workitems.models import ItemStatus, WorkItem

from .clock import TICKS_PER_DAY
from .models import BoardReview, DataQualityReview, Game

# Places.
DESK, MEETING_ROOM, BOARDROOM, CAFETERIA, OUT = (
    "DESK", "MEETING_ROOM", "BOARDROOM", "CAFETERIA", "OUT",
)  # fmt: skip
# What a person is doing there.
WORKING, FREE, BREAK, REVIEW, BOARD, TRAINING, AFTER_HOURS = (
    "WORKING", "FREE", "BREAK", "DATA_QUALITY_REVIEW", "BOARD_REVIEW", "TRAINING",
    "AFTER_HOURS",
)  # fmt: skip

REVIEW_AFTER = range(9, 13)  # ticks after the review's own: 10:00-11:00 the next morning
BOARD_TICKS = 8  # two hours from the board's tick
LUNCH_SLOTS = range(16, 20)  # 12:00-13:00, as slots of the working day
LOW_MORALE = 0.5
SENIORITY = {"Senior Data Officer": 0, "Data Officer": 1, "Junior Data Officer": 2}

WORDS = {
    WORKING: "working on an item",
    FREE: "at their desk, nothing to do",
    BREAK: "on a break",
    REVIEW: "in the Data Quality Review",
    BOARD: "presenting to the board",
    TRAINING: "out on a training course",
    AFTER_HOURS: "gone home for the day",
}


@dataclass(frozen=True)
class Whereabouts:
    place: str
    activity: str
    item: int | None = None  # the item they are working on (WORKING only)

    @property
    def words(self) -> str:
        return WORDS[self.activity]


def after_hours(game: Game) -> bool:
    """Does the clock stand at a working day's end (17:00), before the next one starts?"""
    return game.current_tick > 0 and game.current_tick % TICKS_PER_DAY == 0


def slot(tick: int) -> int:
    """The tick's quarter hour in its working day: 0 is 08:00-08:15."""
    return (tick - 1) % TICKS_PER_DAY


def _senior_first(staff: Iterable[Employee]) -> list[Employee]:
    return sorted(staff, key=lambda e: (SENIORITY.get(e.job_title, 9), e.employee_number))


def meetings(game: Game, tick: int, staff: list[Employee]) -> dict[int, str]:
    """Who is in a meeting at ``tick``, and which (employee pk -> activity).

    ``staff`` is the active staff, the order makes no difference.
    """
    found: dict[int, str] = {}
    data_ops = _senior_first(e for e in staff if e.department == "DATA_OPERATIONS")
    if not data_ops:
        return found
    at = slot(tick)
    if (
        at < BOARD_TICKS
        and BoardReview.objects.filter(
            game=game, tick__gt=tick - BOARD_TICKS, tick__lte=tick
        ).exists()
    ):
        found[data_ops[0].pk] = BOARD
    if at in range(REVIEW_AFTER.start - 1, REVIEW_AFTER.stop - 1) and (
        DataQualityReview.objects.filter(
            game=game, tick__gte=tick - REVIEW_AFTER[-1], tick__lte=tick - REVIEW_AFTER[0]
        ).exists()
    ):
        seniors = [e for e in data_ops if e.job_title == "Senior Data Officer"] or data_ops[:1]
        for e in seniors:
            found.setdefault(e.pk, REVIEW)
    return found


def in_meetings(game: Game, tick: int) -> frozenset[int]:
    """The employees (pks) in a meeting at ``tick``, whom ``work_tick`` leaves out."""
    at = slot(tick)
    if at >= max(BOARD_TICKS, REVIEW_AFTER.stop - 1):
        return frozenset()  # no meeting is held after 11:00 (a cheap check, every tick)
    staff = list(Employee.objects.filter(organization=game.organization, is_active=True))
    return frozenset(meetings(game, tick, staff))


def whereabouts(game: Game) -> dict[int, Whereabouts]:
    """Where each active employee is now (pk -> place), at the tick under way."""
    staff = list(
        Employee.objects.filter(organization=game.organization, is_active=True).order_by(
            "employee_number"
        )
    )
    if after_hours(game):
        return {e.pk: Whereabouts(OUT, AFTER_HOURS) for e in staff}
    tick = game.current_tick + 1  # the tick under way, as the IT page counts it
    working = dict(
        WorkItem.objects.filter(
            organization=game.organization, status=ItemStatus.IN_PROGRESS
        ).values_list("assignee_id", "item_number")
    )
    meeting = meetings(game, tick, staff)
    where = {}
    for e in staff:
        where[e.pk] = place_of(e, tick, meeting.get(e.pk), working.get(e.pk))
    return where


def place_of(person: Employee, tick: int, meeting: str | None, item: int | None) -> Whereabouts:
    """One person's place at ``tick``, given their meeting and the item they hold."""
    if person.away_until_tick >= tick:
        return Whereabouts(OUT, TRAINING)
    if meeting is not None:
        return Whereabouts(BOARDROOM if meeting == BOARD else MEETING_ROOM, meeting)
    if item is not None:
        return Whereabouts(DESK, WORKING, item)
    if slot(tick) in LUNCH_SLOTS or person.morale < LOW_MORALE:
        return Whereabouts(CAFETERIA, BREAK)
    return Whereabouts(DESK, FREE)
