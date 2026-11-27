"""The building the bureau works in (P4.1; PRD, Section 6.2; Document 05, Section 5.2).

An established bureau (and a Sandbox, which starts as one) has three floors:

* the ground floor, the public face: reception and the visitors' waiting area, Customer
  Support, Sales and Business Development, Finance and Accounting, HR and
  Administration, the cafeteria;
* the first floor, data and technology: Data Operations, Data Analytics, IT and
  Infrastructure, Product Development, the server room, the technical meeting room;
* the second floor, the executive floor: the CEO's office, Executive Management, the
  boardroom, Risk and Compliance, the executive meeting rooms.

A Startup works from the office it rents (``startup.OFFICES``): one floor with fewer
rooms, and before it rents one, none (Document 05: "a smaller office with fewer rooms").

ASSUMPTION A-090: the Startup offices' rooms (a serviced office: one open-plan room, a
meeting room, a server cupboard and a kitchenette; an office floor: reception, an
open-plan office, the founder's office, a meeting room, a server room and a kitchen),
and the screen each room opens. The building is held as data here, so P4.8's growing
office adds to it rather than to the drawing.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import scenarios
from .models import Game

# Room kinds: what the floor draws there.
DEPARTMENT, FACILITY, MEETING, SERVERS, OFFICE = (
    "DEPARTMENT", "FACILITY", "MEETING", "SERVERS", "OFFICE",
)  # fmt: skip

EVERYONE = "*"  # a room every department works in (a Startup's open-plan office)


@dataclass(frozen=True)
class Room:
    code: str
    name: str
    kind: str
    screen: str  # the game's screen the room opens (a navigation key)
    purpose: str  # one line: what goes on there
    departments: tuple[str, ...] = ()  # whose staff sit here (``Employee.department``)


@dataclass(frozen=True)
class Floor:
    code: str  # in the URL: /games/<id>/office/<code>/
    name: str
    level: int  # 0 is the ground floor
    plan: str  # which drawing the frontend lays it out with
    rooms: tuple[Room, ...]


GROUND = Floor(
    "ground",
    "Ground floor",
    0,
    "GROUND",
    (
        Room("RECEPTION", "Reception", FACILITY, "onboarding",
             "Visitors sign in here: lenders coming to join, suppliers, the public."),
        Room("WAITING", "Visitor waiting area", FACILITY, "disputes",
             "Members of the public waiting to see their report or raise a dispute."),
        Room("SUPPORT", "Customer Support", DEPARTMENT, "support",
             "Answers subscribers' and the public's questions.", ("CUSTOMER_SUPPORT",)),
        Room("SALES", "Sales and Business Development", DEPARTMENT, "sales",
             "Wins and keeps the lenders that buy reports.", ("SALES",)),
        Room("FINANCE", "Finance and Accounting", DEPARTMENT, "finance",
             "Bills subscribers, pays the bills, keeps the books.", ("FINANCE",)),
        Room("HR", "HR and Administration", DEPARTMENT, "staff",
             "Hires, trains and pays the staff.", ("HR",)),
        Room("CAFETERIA", "Cafeteria", FACILITY, "staff",
             "Where the staff take their breaks."),
    ),
)  # fmt: skip

FIRST = Floor(
    "first",
    "First floor",
    1,
    "FIRST",
    (
        Room("DATA_OPERATIONS", "Data Operations", DEPARTMENT, "queue",
             "Loads the lenders' files and works the queue.", ("DATA_OPERATIONS",)),
        Room("DATA_ANALYTICS", "Data Analytics", DEPARTMENT, "analytics",
             "Studies the data and builds the scorecards.", ("DATA_ANALYTICS",)),
        Room("IT", "IT and Infrastructure", DEPARTMENT, "it",
             "Keeps the systems running.", ("IT",)),
        Room("PRODUCT", "Product Development", DEPARTMENT, "products",
             "Designs the reports and scores the bureau sells.", ("PRODUCT",)),
        Room("SERVER_ROOM", "Server room", SERVERS, "it",
             "The bureau's systems and the data they hold."),
        Room("TECH_MEETING", "Technical meeting room", MEETING, "reviews",
             "Where the monthly Data Quality Reviews are held."),
    ),
)  # fmt: skip

SECOND = Floor(
    "second",
    "Second floor",
    2,
    "SECOND",
    (
        Room("CEO_OFFICE", "CEO's office", OFFICE, "dashboard",
             "The chief executive's desk: the company at a glance.", ("CEO",)),
        Room("EXECUTIVE", "Executive Management", DEPARTMENT, "health",
             "The heads of department and the company's health."),
        Room("BOARDROOM", "Boardroom", MEETING, "health",
             "Where the board reviews the company each quarter."),
        Room("COMPLIANCE", "Risk and Compliance", DEPARTMENT, "compliance",
             "Keeps the bureau within the law and the regulator's rules.", ("COMPLIANCE",)),
        Room("EXEC_MEETING", "Executive meeting rooms", MEETING, "events",
             "Where the executives meet about what has happened."),
    ),
)  # fmt: skip

ESTABLISHED_BUILDING = (GROUND, FIRST, SECOND)

# A Startup's rented office (startup.OFFICES), one floor each.
STARTUP_OFFICES: dict[str, tuple[Floor, ...]] = {
    "SMALL": (
        Floor(
            "office",
            "The serviced office",
            0,
            "SMALL",
            (
                Room("OPEN_PLAN", "Open-plan office", DEPARTMENT, "queue",
                     "Every department works here, at the desks the office provides.",
                     (EVERYONE,)),
                Room("MEETING", "Meeting room", MEETING, "reviews",
                     "Booked for the monthly Data Quality Reviews."),
                Room("SERVER_ROOM", "Server cupboard", SERVERS, "it",
                     "The bureau's systems, once IT is set up."),
                Room("KITCHEN", "Kitchenette", FACILITY, "staff",
                     "Where the staff take their breaks."),
            ),
        ),
    ),
    "STANDARD": (
        Floor(
            "office",
            "The office floor",
            0,
            "STANDARD",
            (
                Room("RECEPTION", "Reception", FACILITY, "onboarding",
                     "Visitors sign in here: lenders coming to join, suppliers, the public."),
                Room("OPEN_PLAN", "Open-plan office", DEPARTMENT, "queue",
                     "Every department works here, at the desks the office provides.",
                     (EVERYONE,)),
                Room("CEO_OFFICE", "Founder's office", OFFICE, "dashboard",
                     "The founder's desk: the company at a glance.", ("CEO",)),
                Room("MEETING", "Meeting room", MEETING, "reviews",
                     "Booked for the monthly Data Quality Reviews."),
                Room("SERVER_ROOM", "Server room", SERVERS, "it",
                     "The bureau's systems, once IT is set up."),
                Room("KITCHEN", "Kitchen", FACILITY, "staff",
                     "Where the staff take their breaks."),
            ),
        ),
    ),
}  # fmt: skip


def floors(game: Game) -> tuple[Floor, ...]:
    """The game's building, ground floor first: none for a Startup without an office."""
    if game.scenario == scenarios.STARTUP:
        return STARTUP_OFFICES.get(game.organization.office, ())
    return ESTABLISHED_BUILDING


def floor(game: Game, code: str) -> Floor | None:
    return next((f for f in floors(game) if f.code == code), None)


def room_for(game: Game, department: str) -> Room | None:
    """The room a department's staff sit in, if the building has one for it."""
    for f in floors(game):
        for r in f.rooms:
            if department in r.departments or EVERYONE in r.departments:
                return r
    return None
