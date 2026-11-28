"""The ground floor: the public face, as the office draws it (P4.5; Document 10).

Reception and the waiting area show the visitors the game's own events bring; Customer
Support the open tickets; Finance the month-end close; the cafeteria the staff's
welfare. Everything here is worked out from what the game already holds, at the tick
under way: nothing is stored, nothing is random, so a replay draws the same visitors.

ASSUMPTION A-094 (visitors, and what the ground floor's rooms show):

* **A data subject with a dispute** comes in person on the working day it reaches the
  bureau (a dispute that arrives at 17:00 is brought the next morning). They sign in at
  reception for half an hour (two ticks), then wait in the waiting area until the day
  ends. Settling the dispute ends the visit at once. At most six are drawn at a time.
* **A prospect Sales meets** (P3.9) sends a representative to the bureau on the
  meeting's day: they sign in at reception at 13:45 and meet Sales in its room from
  14:00 to 15:00. This replaces P4.2's reading (A-091), in which Sales went out to the
  prospect, to follow the plan.
* **Customer Support's** agents are the contact centre's the chief executive pays for
  (P3.10): up to eight are drawn, at their desks; the open tickets are shared across
  their desks as paper, and with no agents they pile up on the empty desks.
* **Sales, Finance and HR** have no employees: like IT's (A-093), each shows a team
  worked out from its state. Sales: one person for each prospect in play (research
  under way, a meeting to come, a proposal waiting for its answer), at most four, one
  when there is none. Finance: two, their desks showing the month-end close checklist's
  progress. HR and Administration: one, and one more for each 20 staff on the payroll,
  at most three.
* **The cafeteria's welfare figures** are the payroll's: morale (its average, the
  lowest, how many take breaks for low morale and how many may resign), pay against the
  market rate for each role, the queue for each person (heavy above 40, which lowers
  morale; A-062), the items done today and who is on a course. Hours are the working
  day, 08:00 to 17:00 with lunch from 12:00: the game has no overtime.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from apps.bureau.quality.models import Dispute, DisputeStatus
from apps.org.models import Employee
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.models import Lender

from . import building, economy, finance_dept, hr, places, support
from .clock import DAY_END, TICKS_PER_DAY
from .engine import calendar
from .models import Game, LenderResearch, Proposal, SupportTicket

MOST_AGENTS = 8  # drawn in the Support room
MOST_VISITORS = 6  # data subjects drawn at a time
SIGN_IN_TICKS = 2  # half an hour at reception
ARRIVE_SLOT = 23  # 13:45: a prospect signs in
MEETING_SLOTS = range(24, 28)  # 14:00-15:00 with Sales
MEETING_TIME = "14:00-15:00"
VISIT, VISITING = "VISIT", "VISITING"


def _day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _clock(tick: int) -> str:
    minutes = 8 * 60 + places.slot(tick) * 15
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def now_of(game: Game) -> datetime:
    """The game's time: the end of the tick last run (as ``controls.state`` gives it)."""
    cal = calendar(game)
    return cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)


def _room(game: Game, *codes: str) -> str | None:
    """The first of these rooms the building has, by code."""
    have = {r.code for f in building.floors(game) for r in f.rooms}
    return next((c for c in codes if c in have), None)


# --- Customer Support ---------------------------------------------------------------------


def tickets(game: Game, today: date) -> dict[str, Any]:
    """Support's tickets as the room shows them: open, late, and today's wave."""
    waiting = SupportTicket.objects.filter(game=game, answered_on__isnull=True)
    arrived = SupportTicket.objects.filter(game=game, opened_on=today)
    agents = game.organization.support_staff
    return {
        "open": waiting.count(),
        "overdue": waiting.filter(due_on__lt=today).count(),
        "today": arrived.count(),
        "outage_today": arrived.filter(topic="OUTAGE").count(),
        "agents": agents,
        "per_day": agents * support.TICKETS_PER_AGENT,
        "satisfaction": support.satisfaction(game, now_of(game))["score"],
    }


# --- Sales --------------------------------------------------------------------------------


def prospects(game: Game, today: date) -> list[dict[str, Any]]:
    """The lenders Sales is working on: research under way, a meeting, a proposal out."""
    found: dict[str, dict[str, Any]] = {}
    for r in LenderResearch.objects.filter(game=game).order_by("lender_code"):
        if r.ready_on > today:
            found[r.lender_code] = {"stage": "RESEARCH", "on": r.ready_on}
        elif r.meeting_on is not None and r.meeting_on >= today:
            found[r.lender_code] = {"stage": "MEETING", "on": r.meeting_on}
    for p in Proposal.objects.filter(game=game, status__in=["PENDING", "COUNTERED"]).order_by(
        "number"
    ):
        found[p.lender_code] = {
            "stage": p.status,
            "proposal": p.number,
            "counter": str(p.counter_price) if p.counter_price is not None else None,
        }
    names = dict(
        Lender.objects.filter(world=game.world, code__in=list(found)).values_list("code", "name")
    )
    return [{"code": code, "name": names.get(code, code), **found[code]} for code in found]


def prospect_words(p: dict[str, Any], today: date) -> str:
    name = p["name"]
    if p["stage"] == "RESEARCH":
        return f"researching {name}: the findings are due on {_day(p['on'])}"
    if p["stage"] == "MEETING":
        when = f"here today, {MEETING_TIME}" if p["on"] == today else f"on {_day(p['on'])}"
        return f"meeting {name} {when}"
    if p["stage"] == "COUNTERED":
        return f"{name} countered proposal {p['proposal']} at GHS {p['counter']} a report"
    return f"waiting for {name}'s answer to proposal {p['proposal']}"


# --- Finance ------------------------------------------------------------------------------


def month_close(game: Game, today: date) -> dict[str, Any]:
    """The next month to close and its checklist (P3.11), for Finance's desks."""
    period = finance_dept.next_to_close(game)
    items = finance_dept.checklist(game, period)
    return {
        "period": period,
        "ended": period < today,
        "done": sum(bool(i["done"]) for i in items),
        "total": len(items),
        "items": [{"title": i["title"], "done": bool(i["done"])} for i in items],
    }


# --- Visitors -----------------------------------------------------------------------------


def _visitor(number: str, name: str, room: str, doing: str, screen: str) -> dict[str, Any]:
    return {
        "number": number,
        "name": name,
        "job_title": "Visitor",
        "visitor": True,
        "desk": None,
        "room": room,
        "place": VISIT,
        "activity": VISITING,
        "doing": doing,
        "item": None,
        "morale": None,
        "screen": screen,
    }


def _subjects(game: Game, today: date, tick: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Data subjects in with a dispute now, and the day's visits for reception's book."""
    cal = calendar(game)
    reception = _room(game, "RECEPTION")
    if reception is None:
        return [], []
    waiting = _room(game, "WAITING", "RECEPTION") or reception
    day = (tick - 1) // TICKS_PER_DAY
    since = datetime.combine(today - timedelta(days=7), DAY_END, tzinfo=UTC)
    here, book = [], []
    for d in Dispute.objects.filter(organization=game.organization, received_at__gt=since).order_by(
        "dispute_number"
    ):
        came = cal.tick_at(d.received_at)
        if (came - 1) // TICKS_PER_DAY != day or came > tick:
            continue  # not today's, or not yet in
        about = f"dispute {d.dispute_number}"
        if d.status != DisputeStatus.OPEN:
            book.append(f"{d.subject_name}, about {about}, came at {_clock(came)}: settled, gone")
            continue
        at = reception if tick - came < SIGN_IN_TICKS else waiting
        where = "signing in" if at == reception else "in the waiting area"
        book.append(f"{d.subject_name}, about {about}, came at {_clock(came)}: {where}")
        here.append(
            _visitor(f"V-D{d.dispute_number}", d.subject_name, at,
                     f"come in person about {about}: {d.claim}", "disputes")
        )  # fmt: skip
    return here[-MOST_VISITORS:], book


def _representatives(game: Game, today: date, tick: int) -> tuple[list[dict[str, Any]], list[str]]:
    """A prospect's representative, in for the meeting with Sales on its day."""
    met = list(LenderResearch.objects.filter(game=game, meeting_on=today).order_by("lender_code"))
    reception = _room(game, "RECEPTION")
    meeting = _room(game, "SALES", "MEETING")
    if not met or meeting is None:
        return [], []
    names = dict(
        Lender.objects.filter(world=game.world, code__in=[r.lender_code for r in met])
        .values_list("code", "name")
    )  # fmt: skip
    at = places.slot(tick)
    here, book = [], []
    for r in met:
        name = names.get(r.lender_code, r.lender_code)
        who = f"{name}'s representative"
        if at < ARRIVE_SLOT:
            book.append(f"{who}: expected at 13:45 to meet Sales, {MEETING_TIME}")
            continue
        if at == ARRIVE_SLOT and reception is not None:
            room, doing = reception, f"signing in to meet Sales at 14:00, for {name}"
        elif at in MEETING_SLOTS or at == ARRIVE_SLOT:
            room, doing = meeting, f"meeting Sales, for {name}, until 15:00"
        else:
            book.append(f"{who}: met Sales, {MEETING_TIME}, gone")
            continue
        book.append(f"{who}: {'signing in' if room == reception else 'with Sales'}")
        here.append(_visitor(f"V-L{r.lender_code}", who, room, doing, "sales"))
    return here, book


def visitors(game: Game, today: date) -> tuple[list[dict[str, Any]], list[str]]:
    """Everyone visiting now, and reception's book for the day: none after hours."""
    if places.after_hours(game):
        return [], []
    tick = game.current_tick + 1  # the tick under way
    subjects, signed = _subjects(game, today, tick)
    reps, expected = _representatives(game, today, tick)
    return subjects + reps, signed + expected


# --- The cafeteria: welfare -------------------------------------------------------------


def welfare(game: Game, today: date) -> dict[str, Any]:
    """The payroll's welfare, as the cafeteria shows it (Document 05, Section 5.3)."""
    staff = list(
        Employee.objects.filter(organization=game.organization, is_active=True).order_by(
            "employee_number"
        )
    )
    shown: dict[str, Any] = {
        "staff": len(staff),
        "day": "08:00-17:00",
        "lunch": "12:00-13:00",
    }
    if not staff:
        return shown
    tick = game.current_tick + 1
    wages = economy.wage_factor(game, today)
    pay = [float(e.monthly_salary / hr.market_salary(e.job_title, wages)) for e in staff]
    lowest = min(staff, key=lambda e: (e.morale, e.employee_number))
    queue = WorkItem.objects.filter(
        organization=game.organization, status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
    ).count()
    day = calendar(game).index_of(today)
    return shown | {
        "morale": round(sum(e.morale for e in staff) / len(staff), 2),
        "lowest": {"name": f"{lowest.first_name} {lowest.last_name}", "morale": lowest.morale},
        "low": sum(e.morale < places.LOW_MORALE for e in staff),
        "at_risk": sum(e.morale < hr.RESIGN_BELOW for e in staff),
        "pay": round(sum(pay) / len(pay), 2),
        "below_market": sum(p < 1 for p in pay),
        "queue_per_person": math.ceil(queue / len(staff)),
        "heavy": queue / len(staff) > hr.HEAVY_QUEUE_PER_PERSON,
        "done_today": sum(e.done_today for e in staff if e.work_day == day),
        "on_course": sum(e.away_until_tick >= tick for e in staff),
    }
