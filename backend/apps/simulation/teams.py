"""The first floor's managed departments, as the office draws them (P4.4; Document 10).

IT, Data Analytics and Product Development have no employees of their own: the chief
executive manages them (P3.10), and the game holds their state (IT's capacity and
incidents, the scorecards, the products in development), not their people. The office
draws each as a small **team worked out from that state**, never stored, never random,
not on the payroll, and doing no work in the game. A department that gains real hires
(a later phase) shows them instead, and its derived team goes.

ASSUMPTION A-093 (the teams and the server room's figures):

* **IT:** two people on standard capacity, three on high; none before IT is set up.
  At their desks, and in the server room while an outage is under way.
* **Data Analytics:** one analyst for each scorecard that is not retired (deployed
  first, then the newest drafts), at most four; one analyst when there is none.
* **Product Development:** one person for each product in development, none when
  nothing is.
* Teams go home after hours with everyone else, and take no breaks or meetings. Only a
  department with a room of its own has a team: in a Startup's open-plan office the
  managed departments are the founder's own work, so none is drawn.
* The ground floor's Customer Support, Sales, Finance and HR teams are A-094's
  (``ground``); the chief executive and Compliance's officer are A-095's (``executive``).
* **The server room:** utilisation is tonight's batch against the capacity; storage
  the customers and credit accounts held (counting every monthly observation is too
  slow for a two-second refresh); availability the share of the last 20
  working days the systems were up; maintenance what IT is doing now. One rack for
  each file a night the capacity processes, at most five.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from apps.bureau.core.models import CreditAccount, Customer
from apps.org.models import Employee

from . import building, executive, ground, it, places, products, startup
from .clock import TICKS_PER_DAY, TICKS_PER_HOUR
from .models import Game, Incident, ProductDevelopment, ScoreModel

IT_TEAM = {"STANDARD": 2, "HIGH": 3}
MOST_ANALYSTS = 4
AVAILABILITY_DAYS = 20
MOST_RACKS = 5
TERMS = {
    "SHORT": "short term",
    "MID": "mid term",
    "LONG": "long term",
    "ALL": "all terms",
    "COMPOSITE": "composite",
}
# Where a team member is, beyond the places people have (A-091).
SERVER_ROOM, RESTORING = "SERVER_ROOM", "RESTORING"
TEAM_NAMES = {
    "IT": "IT",
    "DATA_ANALYTICS": "Analytics",
    "PRODUCT": "Product",
    "CUSTOMER_SUPPORT": "Support",
    "SALES": "Sales",
    "FINANCE": "Finance",
    "HR": "HR",
    "COMPLIANCE": "Compliance",
    "CEO": "CEO",
}
MOST_SALES = 4
FINANCE_TEAM = ("Finance manager", "Accountant")
HR_PER_STAFF, MOST_HR = 20, 3


def _own_room(game: Game, department: str) -> building.Room | None:
    """The department's own room in this building, if it has one (not a shared office)."""
    for f in building.floors(game):
        for r in f.rooms:
            if department in r.departments and building.EVERYONE not in r.departments:
                return r
    return None


def _has_staff(game: Game, department: str) -> bool:
    return Employee.objects.filter(
        organization=game.organization, department=department, is_active=True
    ).exists()


def _person(
    department: str,
    n: int,
    title: str,
    activity: str,
    doing: str,
    screen: str,
    *,
    place: str = places.DESK,
    room: str | None = None,
) -> dict[str, Any]:
    return {
        "number": f"{department}-{n}",
        "name": f"{TEAM_NAMES[department]} team {n}",
        "job_title": title,
        "department": department,
        "managed": True,
        "place": place,
        "activity": activity,
        "doing": doing,
        "room": room,
        "item": None,
        "screen": screen,
    }


def _day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _it_team(game: Game, incident: Incident | None) -> list[dict[str, Any]]:
    org = game.organization
    if not org.has_systems:
        return []
    out = []
    for n in range(1, IT_TEAM[org.it_capacity] + 1):
        if incident is not None:
            out.append(
                _person("IT", n, "IT engineer", RESTORING, "at the racks, restoring the systems",
                        "it", place=SERVER_ROOM, room="SERVER_ROOM")
            )  # fmt: skip
        else:
            out.append(
                _person("IT", n, "IT engineer", places.FREE, "at their desk: the systems are up",
                        "it")
            )  # fmt: skip
    return out


def scorecards(game: Game) -> list[ScoreModel]:
    """The scorecards the analysts look after: deployed first, then the newest drafts."""
    live = ScoreModel.objects.filter(game=game).exclude(status=ScoreModel.Status.RETIRED)
    deployed = list(live.filter(status=ScoreModel.Status.DEPLOYED).order_by("number"))
    drafts = list(live.filter(status=ScoreModel.Status.DRAFT).order_by("-number"))
    return (deployed + drafts)[:MOST_ANALYSTS]


def _analysts(game: Game) -> list[dict[str, Any]]:
    models = scorecards(game)
    if not models:
        return [
            _person("DATA_ANALYTICS", 1, "Analyst", places.FREE,
                    "no scorecard yet: one is built in the workbench", "scorecards")
        ]  # fmt: skip
    out = []
    for n, m in enumerate(models, start=1):
        what = f"scorecard {m.number} ({TERMS.get(m.term, m.term.lower())})"
        doing = (
            f"watching {what}, deployed"
            if m.status == ScoreModel.Status.DEPLOYED
            else f"working on {what}, a draft not yet deployed"
        )
        person = _person(
            "DATA_ANALYTICS", n, "Analyst", places.WORKING, doing, f"scorecards/{m.number}"
        )
        person["model"] = {"number": m.number, "term": m.term, "status": m.status}
        out.append(person)
    return out


def _progress(project: ProductDevelopment, today: date) -> float:
    if project.started_on is None or project.ready_on is None:
        return 0.0
    total = (project.ready_on - project.started_on).days
    done = (today - project.started_on).days
    return 1.0 if total <= 0 else max(0.0, min(1.0, done / total))


def developments(game: Game, today: date) -> list[dict[str, Any]]:
    """The products in development, with their progress."""
    out = []
    for project in ProductDevelopment.objects.filter(
        game=game, started_on__isnull=False, launched_on__isnull=True
    ).order_by("started_tick", "code"):
        if project.ready_on is None:
            continue
        out.append(
            {
                "code": project.code,
                "name": products.MENU[project.code].name,
                "progress": round(_progress(project, today), 2),
                "ready_on": project.ready_on,
            }
        )
    return out


def _product_team(game: Game, today: date) -> list[dict[str, Any]]:
    out = []
    for n, d in enumerate(developments(game, today), start=1):
        person = _person(
            "PRODUCT", n, "Product manager", places.WORKING,
            f"developing the {d['name'].lower()}: {d['progress']:.0%} done, "
            f"ready on {_day(d['ready_on'])}",
            "products",
        )  # fmt: skip
        person["product"] = d["code"]
        out.append(person)
    return out


def _support_team(game: Game, today: date) -> list[dict[str, Any]]:
    """The contact centre's agents (P3.10), answering the open tickets."""
    agents = min(ground.MOST_AGENTS, game.organization.support_staff)
    waiting = ground.tickets(game, today)["open"] if agents else 0
    doing = (
        f"answering tickets: {waiting} waiting, oldest first" if waiting else "no tickets waiting"
    )
    return [
        _person("CUSTOMER_SUPPORT", n, "Support agent (contact centre)",
                places.WORKING if waiting else places.FREE, doing, "support")
        for n in range(1, agents + 1)
    ]  # fmt: skip


def _sales_team(game: Game, today: date) -> list[dict[str, Any]]:
    found = ground.prospects(game, today)[:MOST_SALES]
    if not found:
        return [
            _person("SALES", 1, "Business development officer", places.FREE,
                    "no prospect in play: research a lender from the Sales screen", "sales")
        ]  # fmt: skip
    out = []
    for n, p in enumerate(found, start=1):
        person = _person(
            "SALES", n, "Business development officer", places.WORKING,
            ground.prospect_words(p, today), "sales",
        )  # fmt: skip
        person["prospect"] = p["code"]
        out.append(person)
    return out


def _finance_team(game: Game, today: date) -> list[dict[str, Any]]:
    close = ground.month_close(game, today)
    done, total = close["done"], close["total"]
    month = f"{close['period']:%B %Y}"
    busy = close["ended"] and done < total
    doing = (
        f"closing {month}: {done} of {total} done"
        if close["ended"]
        else f"keeping the books; {month} closes after its end ({done} of {total} done)"
    )
    out = []
    for n, title in enumerate(FINANCE_TEAM, start=1):
        person = _person("FINANCE", n, title, places.WORKING if busy else places.FREE,
                         doing, "close")  # fmt: skip
        person["progress"] = round(done / total, 2) if total else 0.0
        out.append(person)
    return out


def _hr_team(game: Game) -> list[dict[str, Any]]:
    payroll = Employee.objects.filter(organization=game.organization, is_active=True).count()
    size = min(MOST_HR, 1 + payroll // HR_PER_STAFF)
    return [
        _person("HR", n, "HR and administration officer", places.FREE,
                f"looking after {payroll} staff on the payroll", "staff")
        for n in range(1, size + 1)
    ]  # fmt: skip


def _ceo(game: Game) -> list[dict[str, Any]]:
    """The player, at their desk, or in the boardroom for a board review (A-095)."""
    where = executive.ceo_place(game)
    if where is None:
        where = (places.OUT, places.AFTER_HOURS, places.WORDS[places.AFTER_HOURS])
    place, activity, doing = where
    room = None
    if place == places.BOARDROOM:
        found = building.room_for_place(game, places.BOARDROOM)
        room = found[1].code if found is not None else None
    person = _person("CEO", 1, "Chief executive", activity, doing, "dashboard",
                     place=place, room=room)  # fmt: skip
    person.update(number="CEO", name="The chief executive (you)")
    return [person]


def _compliance_team(game: Game, today: date) -> list[dict[str, Any]]:
    """Compliance's one officer (A-088), at work on what their day went to."""
    state = executive.compliance_state(game, today)
    if state["today"]:
        activity, doing = places.WORKING, f"working on {state['today']}"
    elif state["open"]:
        activity, doing = places.WORKING, f"following up {state['open']} open finding(s)"
    else:
        activity, doing = places.FREE, "no finding open"
    return [_person("COMPLIANCE", 1, "Compliance officer", activity, doing, "compliance")]


def team(
    game: Game,
    incident: Incident | None,
    today: date,
    departments: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Everyone the managed departments' rooms draw, in the order the floor lists them.

    Only where the department has its own room, and no real staff of its own; only
    ``departments`` (a floor's) when given.
    """
    makers: tuple[tuple[str, Callable[[], list[dict[str, Any]]]], ...] = (
        ("DATA_ANALYTICS", lambda: _analysts(game)),
        ("IT", lambda: _it_team(game, incident)),
        ("PRODUCT", lambda: _product_team(game, today)),
        ("CUSTOMER_SUPPORT", lambda: _support_team(game, today)),
        ("SALES", lambda: _sales_team(game, today)),
        ("FINANCE", lambda: _finance_team(game, today)),
        ("HR", lambda: _hr_team(game)),
        ("CEO", lambda: _ceo(game)),
        ("COMPLIANCE", lambda: _compliance_team(game, today)),
    )
    out: list[dict[str, Any]] = []
    for department, make in makers:
        if departments is not None and department not in departments:
            continue
        if _own_room(game, department) is None or _has_staff(game, department):
            continue
        out.extend(make())
    if places.after_hours(game):
        for p in out:
            p.update(place=places.OUT, activity=places.AFTER_HOURS, room=None,
                     doing=places.WORDS[places.AFTER_HOURS])  # fmt: skip
    return out


def _maintenance(game: Game, incident: Incident | None, today: date) -> str:
    org = game.organization
    if not org.has_systems:
        return "Not set up: IT has no systems yet."
    if not startup.systems_ready(game, today) and org.it_ready_on is not None:
        return f"Being installed: ready on {_day(org.it_ready_on)}."
    if incident is not None:
        if incident.kind == "SUPPLIER_HOLD":
            return "Service suspended by the hosting company until its bill is paid."
        how = {"VENDOR": "the vendor is fixing it", "BACKUP": "restoring from backup"}.get(
            incident.response, "no response yet"
        )
        return f"Outage {incident.number} under way: {how}."
    last = Incident.objects.filter(game=game).order_by("-number").first()
    if last is None:
        return "Running normally: no outage so far."
    return f"Running normally: the last outage was number {last.number}."


def server_room(game: Game, incident: Incident | None, today: date) -> dict[str, Any]:
    """What the server room shows when selected (PRD Section 6.3), from the IT state."""
    org = game.organization
    capacity = it.CAPACITY[org.it_capacity]
    waiting = it.waiting(game)
    now = game.current_tick
    first = max(1, now - AVAILABILITY_DAYS * TICKS_PER_DAY + 1)
    span = max(1, now - first + 1) if now else 1
    down = it.downtime_hours(game, first, now) * TICKS_PER_HOUR if now else 0.0  # ticks
    accounts = CreditAccount.objects.filter(organization=org).count()
    customers = Customer.objects.filter(organization=org).count()
    return {
        "utilisation": round(min(1.0, waiting / capacity), 2),
        "tonight": {"waiting": waiting, "capacity": capacity},
        "storage": {"customers": customers, "accounts": accounts},
        "availability": round(max(0.0, 1 - down / span), 3) if org.has_systems else 0.0,
        "maintenance": _maintenance(game, incident, today),
        "racks": min(MOST_RACKS, capacity) if org.has_systems else 1,
    }


def today_of(game: Game) -> date:
    return ground.now_of(game).date()
