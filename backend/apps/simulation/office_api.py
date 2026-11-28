"""What the office draws (P4.1, from the P3.2 trial): the building, then one floor at a time.

``GET /games/<id>/office/`` is the building: its floors and their rooms, small and
rarely changing. ``GET /games/<id>/office/<floor>/`` is what that floor draws, and only
that: its rooms with a line on each, the people who sit there and what they are doing,
and the queue or the systems where the floor has them. The 3D page asks for the floor in
view every two seconds. Both are read only, for any role.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count
from django.http import Http404
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.org.models import Employee
from apps.workitems.models import ItemStatus, WorkItem

from . import building, executive, ground, it, places, startup, teams
from .api import _game
from .clock import TICK_MINUTES, TICKS_PER_DAY
from .models import ComplianceFinding, Game, Incident

MIN_DESKS = 6  # an established department's room shows room to hire
MIN_SUPPORT_DESKS = 2  # tickets pile up on them when there are no agents


def _plain(f: building.Floor) -> dict[str, Any]:
    return {
        "code": f.code,
        "name": f.name,
        "level": f.level,
        "plan": f.plan,
        "rooms": [{"code": r.code, "name": r.name, "kind": r.kind} for r in f.rooms],
    }


@api_view(["GET"])
def building_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    found = startup.office(game) if startup.is_startup(game) else None
    floors = building.floors(game)
    return Response(
        {
            "name": found.name if found is not None else "The bureau's building",
            "floors": [_plain(f) for f in floors],
            "no_office": not floors,
        }
    )


def _staff(game: Game, here: building.Floor) -> list[dict[str, Any]]:
    """The people this floor shows: those with a desk here, and those in its rooms now.

    Where each one is comes from ``places``, from the game's state alone (P4.2).
    """
    where = places.whereabouts(game)
    people = []
    for e in Employee.objects.filter(organization=game.organization, is_active=True).order_by(
        "employee_number"
    ):
        w = where[e.pk]
        desk = building.desk_room(game, e.department)
        now = (
            desk if w.place in (places.DESK, places.OUT) else building.room_for_place(game, w.place)
        )
        if now is None:
            now = desk  # the building has no such room: they stay in their own
        desk_here = desk is not None and desk[0].code == here.code
        now_here = now is not None and now[0].code == here.code and w.place != places.OUT
        if not (desk_here or now_here):
            continue  # on another floor, with their desk there too
        doing = w.words
        if not now_here and w.place != places.OUT and now is not None:
            doing += f" ({now[1].name}, {now[0].name.lower()})"
        people.append(
            {
                "number": e.employee_number,
                "name": f"{e.first_name} {e.last_name}",
                "job_title": e.job_title,
                "desk": desk[1].code if desk is not None and desk_here else None,
                "room": now[1].code if now is not None and now_here else None,
                "place": w.place,
                "activity": w.activity,
                "doing": doing,
                "item": w.item,
                "morale": e.morale,
            }
        )
    return people


def _teams(
    game: Game, here: building.Floor, incident: Incident | None, today: Any
) -> list[dict[str, Any]]:
    """The managed departments' derived teams on this floor (P4.4, A-093)."""
    codes = {r.code for r in here.rooms}
    out = []
    departments = {d for r in here.rooms for d in r.departments}
    for p in teams.team(game, incident, today, departments):
        desk = next((r.code for r in here.rooms if p["department"] in r.departments), None)
        room = p["room"] if p["room"] in codes else None
        if desk is None and room is None:
            continue
        out.append(
            {
                **p,
                "desk": desk,
                "room": room if room else (desk if p["place"] == places.DESK else None),
                "morale": None,
            }
        )
    return out


def _desks(game: Game, room: building.Room, people: list[dict[str, Any]]) -> int:
    """Desks in a room: a Startup's are its office's; a department's, its staff and more."""
    here = len([p for p in people if p["desk"] == room.code])
    if building.EVERYONE in room.departments:
        found = startup.office(game)
        return found.desks if found is not None else here
    if "DATA_OPERATIONS" in room.departments:  # the department the bureau hires into
        return max(MIN_DESKS, here)
    if "CUSTOMER_SUPPORT" in room.departments:
        return max(MIN_SUPPORT_DESKS, here)
    return here


ELSEWHERE = (
    ("in a meeting", (places.REVIEW, places.BOARD)),
    ("on a break", (places.BREAK,)),
    ("out", (places.TRAINING, places.AFTER_HOURS)),
)
GATHERED = {
    places.REVIEW: "The Data Quality Review",
    places.BOARD: "The board review",
    places.BREAK: "On a break",
}


def _names(people: list[dict[str, Any]]) -> str:
    names = [p["name"] for p in people]
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _summary(
    game: Game, room: building.Room, people: list[dict[str, Any]], extra: dict[str, Any]
) -> str:
    """One line on the room, from the game's state where it has one, else what it is for."""
    desks = [p for p in people if p["desk"] == room.code]
    present = [p for p in people if p["room"] == room.code and p["place"] != places.DESK]
    managed = [p for p in desks if p.get("managed")]
    if room.kind == building.SERVERS and "systems" in extra:
        return _servers_line(extra["systems"], present)
    if "DATA_ANALYTICS" in room.departments and "analytics" in extra:
        models = extra["analytics"]["models"]
        if not models:
            return "No scorecard yet: the analysts build one in the workbench."
        deployed = sum(m["status"] == "DEPLOYED" for m in models)
        return (
            f"{len(models)} scorecard(s): {deployed} deployed, {len(models) - deployed} draft(s)."
        )
    if "PRODUCT" in room.departments and "developments" in extra:
        building_now = extra["developments"]
        if not building_now:
            return "Nothing in development: new products start from the Products screen."
        return (
            "Developing "
            + ", ".join(f"the {d['name'].lower()} ({d['progress']:.0%})" for d in building_now)
            + "."
        )
    line = _ground_line(game, room, present, extra)
    if line is None:
        line = _exec_line(room, desks, present, extra)
    if line is not None:
        return line
    if managed and "IT" in room.departments:
        away = sum(p["place"] == teams.SERVER_ROOM for p in managed)
        line = f"IT team of {len(managed)}"
        if away:
            return line + f": {away} in the server room, restoring the systems."
        return line + ": at their desks."
    if desks and room.kind == building.DEPARTMENT:
        working = sum(p["activity"] == places.WORKING for p in desks)
        free = sum(p["activity"] == places.FREE for p in desks)
        line = f"{len(desks)} staff: {working} working, {free} free"
        for words, activities in ELSEWHERE:
            n = sum(p["activity"] in activities for p in desks)
            if n:
                line += f", {n} {words}"
        if "queue" in extra:
            line += f"; {extra['queue']['open']} item(s) waiting in the queue"
        return line + "."
    if present:
        by = present[0]["activity"]
        return f"{GATHERED.get(by, 'Here')}: {_names(present)}."
    if room.code == "COMPLIANCE":
        open_findings = ComplianceFinding.objects.filter(
            game=game, resolved_tick__isnull=True
        ).count()
        return f"{open_findings} compliance finding(s) open."
    return room.purpose


def _ground_line(
    game: Game, room: building.Room, present: list[dict[str, Any]], extra: dict[str, Any]
) -> str | None:
    """The ground floor's rooms (P4.5, A-094): from their own state, or None."""
    guests = [p for p in present if p.get("visitor")]
    if room.code == "RECEPTION" and "visits" in extra:
        if guests:
            return f"Signing in: {_names(guests)}."
        n = len(extra["visits"])
        return (
            f"{n} visit(s) in the book today; nobody at the desk now."
            if n
            else ("No visitors yet today.")
        )
    if room.code == "WAITING" and "visits" in extra:
        return f"Waiting: {_names(guests)}." if guests else "Nobody is waiting."
    if "CUSTOMER_SUPPORT" in room.departments and "tickets" in extra:
        t = extra["tickets"]
        line = (
            f"{t['agents']} agent(s), answering {t['per_day']} a day; "
            f"{t['open']} ticket(s) open, {t['overdue']} past their time"
        )
        if t["today"]:
            line += f"; {t['today']} came in today"
            if t["outage_today"]:
                line += f", {t['outage_today']} about the outage"
        return line + "."
    if "SALES" in room.departments and "prospects" in extra:
        if guests:
            return f"Meeting {_names(guests)}, until 15:00."
        today = [p for p in extra["prospects"] if p["stage"] == "MEETING" and p.get("today")]
        if today:
            names = ", ".join(p["name"] for p in today)
            return f"Meeting {names} here today, {ground.MEETING_TIME}."
        n = len(extra["prospects"])
        if not n:
            return "No prospect in play: research a lender from the Sales screen."
        return f"Working on {n} prospect(s)."
    if "FINANCE" in room.departments and "close" in extra:
        c = extra["close"]
        month = f"{c['period']:%B %Y}"
        if not c["ended"]:
            return f"Keeping the books; {month} closes after its end ({c['done']} of {c['total']} done)."
        return f"Closing {month}: {c['done']} of {c['total']} done."
    if room.code == "HR":
        staff = Employee.objects.filter(organization=game.organization, is_active=True).count()
        return f"{staff} staff on the payroll."
    if room.code in ("CAFETERIA", "KITCHEN") and "welfare" in extra:
        w = extra["welfare"]
        on_break = [p for p in present if not p.get("visitor")]
        line = f"On a break: {_names(on_break)}. " if on_break else ""
        if not w["staff"]:
            return line + "Nobody on the payroll yet."
        return line + f"Morale {w['morale']:.2f} on average across {w['staff']} staff."
    return None


def _exec_line(
    room: building.Room,
    desks: list[dict[str, Any]],
    present: list[dict[str, Any]],
    extra: dict[str, Any],
) -> str | None:
    """The executive floor's rooms (P4.6, A-095): from their own state, or None."""
    if room.code == "BOARDROOM" and "board" in extra and not present:
        b = extra["board"]
        due = f"The next is due on the first working day of {b['next_on']:%B %Y}."
        if b["last"] is None:
            return (
                "No board review yet: the board meets once the management has run a full quarter. "
                + due
            )
        last = b["last"]
        return (
            f"Last review, {last['quarter']}: confidence {last['confidence']}, "
            f"{last['words']}. {due}"
        )
    if "CEO" in room.departments and desks and desks[0].get("managed"):
        return f"{desks[0]['name']}: {desks[0]['doing']}."
    if "COMPLIANCE" in room.departments and "compliance" in extra:
        c = extra["compliance"]
        line = f"{c['open']} finding(s) open; {len(c['samples'])} consent sample(s) in progress"
        if c["today"]:
            line += f"; today on {c['today']}"
        return line + "."
    if room.code == "EXECUTIVE" and "notices" in extra:
        n = extra["notices"]
        mission = (
            f"mission {n['mission']['code']}, {n['mission']['title']}"
            if n["mission"]
            else "no mission"
        )
        acts = len(n["regulator"])
        regulator = f"{acts} item(s) from the regulator" if acts else "nothing from the regulator"
        return f"Notice board: {mission}; {regulator}."
    return None


def _servers_line(systems: dict[str, Any], present: list[dict[str, Any]]) -> str:
    """The server room's line: its state, and its utilisation, storage and availability."""
    if not systems["installed"]:
        return "No systems yet: IT has not been set up."
    if systems["down"]:
        line = f"Systems down: {systems['detail']}"
        if present:
            line += f" {_names(present)} at the racks."
        return line
    return (
        f"Systems up; {systems['files_waiting']} file(s) waiting to process "
        f"({systems['utilisation']:.0%} of tonight's capacity); "
        f"{systems['availability']:.1%} available over 20 working days."
    )


def _time(game: Game) -> str:
    """The clock's time of day, "HH:MM", for the office's light (P4.3): 17:00 after hours."""
    at = TICKS_PER_DAY if places.after_hours(game) else game.current_tick % TICKS_PER_DAY
    minutes = 8 * 60 + at * TICK_MINUTES
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@api_view(["GET"])
def floor_view(request: Request, game_id: int, floor: str) -> Response:
    game = _game(request, game_id)
    found = building.floor(game, floor)
    if found is None:
        raise Http404("No such floor in this game's building")
    org = game.organization
    incident = it.active_incident(game, game.current_tick + 1)
    today = teams.today_of(game)
    codes = {r.code for r in found.rooms}
    guests, book = ground.visitors(game, today)
    people = (
        _staff(game, found)
        + _teams(game, found, incident, today)
        + [v for v in guests + executive.directors(game) if v["room"] in codes]
    )
    extra: dict[str, Any] = {}
    departments = {d for r in found.rooms for d in r.departments}
    if "RECEPTION" in codes:
        extra["visits"] = book
    if "CUSTOMER_SUPPORT" in departments:
        extra["tickets"] = ground.tickets(game, today)
    if "SALES" in departments:
        extra["prospects"] = [
            p
            | {
                "today": p["stage"] == "MEETING" and p["on"] == today,
                "doing": ground.prospect_words(p, today),
            }
            for p in ground.prospects(game, today)
        ]
    if "FINANCE" in departments:
        extra["close"] = ground.month_close(game, today)
    if codes & {"CAFETERIA", "KITCHEN"}:
        extra["welfare"] = ground.welfare(game, today)
    boardroom = building.room_for_place(game, places.BOARDROOM)
    if boardroom is not None and boardroom[0].code == found.code:
        extra["board"] = executive.board(game, today)
    if "COMPLIANCE" in departments:
        extra["compliance"] = executive.compliance_state(game, today)
    if "EXECUTIVE" in codes:
        extra["notices"] = executive.notices(game, today)
    if "DATA_ANALYTICS" in departments:
        extra["analytics"] = {
            "models": [
                {"number": m.number, "term": m.term, "status": m.status}
                for m in teams.scorecards(game)
            ],
        }
    if "PRODUCT" in departments:
        extra["developments"] = teams.developments(game, today)
    if any(
        "DATA_OPERATIONS" in r.departments or building.EVERYONE in r.departments
        for r in found.rooms
    ):
        open_items = WorkItem.objects.filter(organization=org, status=ItemStatus.OPEN)
        extra["queue"] = {
            "open": open_items.count(),
            "in_progress": WorkItem.objects.filter(
                organization=org, status=ItemStatus.IN_PROGRESS
            ).count(),
            "by_type": {
                row["item_type"]: row["n"]
                for row in open_items.values("item_type").annotate(n=Count("pk"))
            },
        }
    if any(r.kind == building.SERVERS for r in found.rooms):
        extra["systems"] = {
            "installed": org.has_systems,
            "down": incident is not None,
            "detail": incident.detail if incident is not None else "",
            "files_waiting": it.waiting(game),
            "capacity": org.it_capacity,
            **teams.server_room(game, incident, today),
        }
    return Response(
        {
            **_plain(found),
            "rooms": [
                {
                    "code": r.code,
                    "name": r.name,
                    "kind": r.kind,
                    "screen": r.screen,
                    "summary": _summary(game, r, people, extra),
                    "desks": _desks(game, r, people),
                }
                for r in found.rooms
            ],
            "staff": people,
            "after_hours": places.after_hours(game),
            "time": _time(game),
            **extra,
        }
    )
