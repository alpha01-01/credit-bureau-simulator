"""The office's building and floors (P4.1; PRD, Section 6.2; Document 05, Section 5.2).

Done when (Document 10): each floor's rooms are those of PRD Section 6.2 (and Document
05's additions); a Startup works from its one rented office, or none; a floor's
endpoint returns only what that floor draws, and follows the game (the P3.2 trial's
test, moved here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.org.models import Employee
from apps.simulation import building, controls, it, scenarios, startup
from apps.simulation.bridge import start_game
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

# PRD Section 6.2, with Document 05 Section 5.2's additions (the visitor waiting area,
# the technical meeting room, Executive Management).
PRD_ROOMS = {
    "ground": {
        "Reception",
        "Visitor waiting area",
        "Customer Support",
        "Sales and Business Development",
        "Finance and Accounting",
        "HR and Administration",
        "Cafeteria",
    },
    "first": {
        "Data Operations",
        "Data Analytics",
        "IT and Infrastructure",
        "Product Development",
        "Server room",
        "Technical meeting room",
    },
    "second": {
        "CEO's office",
        "Executive Management",
        "Boardroom",
        "Risk and Compliance",
        "Executive meeting rooms",
    },
}


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _client(owner: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(owner)
    return client


def test_the_building_has_the_prds_three_floors_and_every_room_opens_a_screen() -> None:
    assert [f.code for f in building.ESTABLISHED_BUILDING] == ["ground", "first", "second"]
    assert [f.level for f in building.ESTABLISHED_BUILDING] == [0, 1, 2]
    for f in building.ESTABLISHED_BUILDING:
        assert {r.name for r in f.rooms} == PRD_ROOMS[f.code]
    every = [r for f in building.ESTABLISHED_BUILDING for r in f.rooms]
    every += [r for fs in building.STARTUP_OFFICES.values() for f in fs for r in f.rooms]
    assert all(r.screen and r.purpose for r in every)
    # Every department the game staffs sits somewhere; each office has a desk room.
    sat = {d for f in building.ESTABLISHED_BUILDING for r in f.rooms for d in r.departments}
    assert {"DATA_OPERATIONS", "COMPLIANCE", "SALES", "FINANCE", "DATA_ANALYTICS"} <= sat
    assert set(building.STARTUP_OFFICES) == set(startup.OFFICES)
    for fs in building.STARTUP_OFFICES.values():
        assert len(fs) == 1 and len(fs[0].rooms) < sum(
            len(f.rooms) for f in building.ESTABLISHED_BUILDING
        )
        assert any(building.EVERYONE in r.departments for r in fs[0].rooms)


@pytest.mark.django_db(transaction=True)
def test_a_floor_shows_who_is_where_the_queue_and_the_systems(world: World) -> None:
    """P3.2's trial, per floor: the 3D office is drawn from this, so it must follow the game."""
    owner = User.objects.create_user("player")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    client = _client(owner)
    base = f"/api/v1/games/{game.pk}/office/"

    plan = client.get(base).json()
    assert [f["code"] for f in plan["floors"]] == ["ground", "first", "second"]
    assert not plan["no_office"]

    calm = client.get(f"{base}first/").json()
    assert [s["activity"] for s in calm["staff"]] == ["FREE"] * 3
    assert {s["room"] for s in calm["staff"]} == {"DATA_OPERATIONS"}
    assert {s["desk"] for s in calm["staff"]} == {"DATA_OPERATIONS"}
    assert calm["systems"]["down"] is False and calm["queue"]["open"] == 0
    rooms = {r["code"]: r for r in calm["rooms"]}
    assert rooms["DATA_OPERATIONS"]["desks"] == 6  # three staff, room to hire
    assert rooms["DATA_OPERATIONS"]["summary"].startswith("3 staff: 0 working, 3 free;")
    assert rooms["SERVER_ROOM"]["summary"].startswith("Systems up")
    assert all(r["screen"] for r in calm["rooms"])

    # Only what the floor draws: no one sits on the ground floor; no queue or systems there.
    ground = client.get(f"{base}ground/").json()
    assert ground["staff"] == [] and "queue" not in ground and "systems" not in ground
    assert {r["name"] for r in ground["rooms"]} == PRD_ROOMS["ground"]
    assert client.get(f"{base}roof/").status_code == 404

    officer = Employee.objects.filter(organization=game.organization).order_by("pk")[1]
    controls.train_employee(game, officer.employee_number, "MATCH_REVIEW")
    it.start_outage(game, game.current_tick + 1, "Test outage.", lambda *a: None)
    busy = client.get(f"{base}first/").json()
    states = {s["number"]: s["activity"] for s in busy["staff"]}
    assert states[officer.employee_number] == "TRAINING"
    assert ", 1 out;" in next(r for r in busy["rooms"] if r["code"] == "DATA_OPERATIONS")["summary"]
    assert busy["systems"]["down"] is True and busy["systems"]["detail"] == "Test outage."
    server = next(r for r in busy["rooms"] if r["code"] == "SERVER_ROOM")
    assert server["summary"] == "Systems down: Test outage."

    # Once files are processed, the queue on the desks is the work items' own count.
    while controls.state(game).now.day < 7:
        game = controls.advance_by(game, "next_event")
    shown = client.get(f"{base}first/").json()
    items = WorkItem.objects.filter(organization=game.organization)
    assert shown["queue"]["open"] == items.filter(status=ItemStatus.OPEN).count()
    assert shown["queue"]["in_progress"] == items.filter(status=ItemStatus.IN_PROGRESS).count()
    for s in shown["staff"]:  # shown working only on their own item in progress
        if s["activity"] == "WORKING":
            assert items.get(item_number=s["item"]).status == ItemStatus.IN_PROGRESS
    assert sum(shown["queue"]["by_type"].values()) == shown["queue"]["open"]

    # A leaver is no longer in the building.
    officer.is_active = False
    officer.save(update_fields=["is_active"])
    gone = client.get(f"{base}first/").json()
    assert officer.employee_number not in {s["number"] for s in gone["staff"]}


@pytest.mark.django_db(transaction=True)
def test_a_startup_works_from_the_office_it_rents(world: World) -> None:
    owner = User.objects.create_user("founder")
    game = controls.set_pause_rules(
        start_game(world, owner=owner, scenario=scenarios.STARTUP), [], deadlines=False
    )
    client = _client(owner)
    base = f"/api/v1/games/{game.pk}/office/"

    none = client.get(base).json()
    assert none["floors"] == [] and none["no_office"]
    assert client.get(f"{base}first/").status_code == 404

    controls.rent_office(game, "SMALL")
    rented = client.get(base).json()
    assert [f["code"] for f in rented["floors"]] == ["office"]
    assert rented["name"] == startup.OFFICES["SMALL"].name
    floor = client.get(f"{base}office/").json()
    rooms = {r["code"]: r for r in floor["rooms"]}
    assert rooms["OPEN_PLAN"]["desks"] == startup.OFFICES["SMALL"].desks
    assert rooms["SERVER_ROOM"]["summary"] == "No systems yet: IT has not been set up."
    assert floor["staff"] == []
