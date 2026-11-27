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

from . import building, it, startup
from .api import _game
from .models import ComplianceFinding, Game

MIN_DESKS = 6  # an established department's room shows room to hire


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


def _staff(game: Game, rooms: dict[str, building.Room]) -> list[dict[str, Any]]:
    """The people who sit on this floor: in the room their department works in."""
    tick = game.current_tick + 1  # the tick under way, as the IT page counts it
    org = game.organization
    working = {
        w.assignee_id: w
        for w in WorkItem.objects.filter(organization=org, status=ItemStatus.IN_PROGRESS)
    }
    everyone = next((r for r in rooms.values() if building.EVERYONE in r.departments), None)
    people = []
    for e in Employee.objects.filter(organization=org, is_active=True).order_by("employee_number"):
        room = everyone or next((r for r in rooms.values() if e.department in r.departments), None)
        if room is None:
            continue  # sits on another floor
        item = working.get(e.pk)
        if e.away_until_tick >= tick:
            state = "AWAY"
        elif item is not None:
            state = "WORKING"
        else:
            state = "IDLE"
        people.append(
            {
                "number": e.employee_number,
                "name": f"{e.first_name} {e.last_name}",
                "job_title": e.job_title,
                "room": room.code,
                "state": state,
                "item": item.item_number if item is not None else None,
                "morale": e.morale,
            }
        )
    return people


def _desks(game: Game, room: building.Room, people: list[dict[str, Any]]) -> int:
    """Desks in a room: a Startup's are its office's; a department's, its staff and more."""
    here = len([p for p in people if p["room"] == room.code])
    if building.EVERYONE in room.departments:
        found = startup.office(game)
        return found.desks if found is not None else here
    if "DATA_OPERATIONS" in room.departments:  # the department the bureau hires into
        return max(MIN_DESKS, here)
    return here


def _summary(
    game: Game, room: building.Room, people: list[dict[str, Any]], extra: dict[str, Any]
) -> str:
    """One line on the room, from the game's state where it has one, else what it is for."""
    here = [p for p in people if p["room"] == room.code]
    if here and room.kind == building.DEPARTMENT:
        working = sum(p["state"] == "WORKING" for p in here)
        away = sum(p["state"] == "AWAY" for p in here)
        line = (
            f"{len(here)} staff: {working} working, {len(here) - working - away} free, {away} away"
        )
        if "queue" in extra:
            line += f"; {extra['queue']['open']} item(s) waiting in the queue"
        return line + "."
    if room.kind == building.SERVERS and "systems" in extra:
        systems = extra["systems"]
        if not systems["installed"]:
            return "No systems yet: IT has not been set up."
        if systems["down"]:
            return f"Systems down: {systems['detail']}"
        return f"Systems up; {systems['files_waiting']} file(s) waiting to process."
    if room.code == "COMPLIANCE":
        open_findings = ComplianceFinding.objects.filter(
            game=game, resolved_tick__isnull=True
        ).count()
        return f"{open_findings} compliance finding(s) open."
    if room.code == "HR":
        staff = Employee.objects.filter(organization=game.organization, is_active=True).count()
        return f"{staff} staff on the payroll."
    return room.purpose


@api_view(["GET"])
def floor_view(request: Request, game_id: int, floor: str) -> Response:
    game = _game(request, game_id)
    found = building.floor(game, floor)
    if found is None:
        raise Http404("No such floor in this game's building")
    org = game.organization
    rooms = {r.code: r for r in found.rooms}
    people = _staff(game, rooms)
    extra: dict[str, Any] = {}
    if any(
        "DATA_OPERATIONS" in r.departments or building.EVERYONE in r.departments
        for r in found.rooms
    ):
        open_items = WorkItem.objects.filter(organization=org, status=ItemStatus.OPEN)
        extra["queue"] = {
            "open": open_items.count(),
            "in_progress": sum(p["state"] == "WORKING" for p in people),
            "by_type": {
                row["item_type"]: row["n"]
                for row in open_items.values("item_type").annotate(n=Count("pk"))
            },
        }
    if any(r.kind == building.SERVERS for r in found.rooms):
        incident = it.active_incident(game, game.current_tick + 1)
        extra["systems"] = {
            "installed": org.has_systems,
            "down": incident is not None,
            "detail": incident.detail if incident is not None else "",
            "files_waiting": it.waiting(game),
            "capacity": org.it_capacity,
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
            **extra,
        }
    )
