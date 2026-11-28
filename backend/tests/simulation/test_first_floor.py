"""The first floor: data and technology (P4.4; Document 10).

Done when: every department on the floor is drawn from its own state; an outage shows on
the racks and draws IT staff to the server room within one refresh; selecting each
object opens its 2D screen (the screens are checked here, the clicks in the layout tests).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.org.models import Employee
from apps.simulation import controls, it, scenarios, teams
from apps.simulation.bridge import start_game
from apps.simulation.models import Game, ScoreModel
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(82, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_user("player")


@pytest.fixture
def client(owner: User) -> APIClient:
    c = APIClient()
    c.force_authenticate(owner)
    return c


def _start(world: World, owner: User, **kw: Any) -> Game:
    return controls.set_pause_rules(start_game(world, owner=owner, **kw), [], deadlines=False)


def _first(client: APIClient, game: Game, floor: str = "first") -> dict[str, Any]:
    shown: dict[str, Any] = client.get(f"/api/v1/games/{game.pk}/office/{floor}/").json()
    return shown


def _rooms(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["code"]: r for r in floor["rooms"]}


def _team(floor: dict[str, Any], department: str) -> list[dict[str, Any]]:
    return [p for p in floor["staff"] if p.get("department") == department]


def _model(game: Game, number: int, status: str, term: str = "SHORT") -> ScoreModel:
    return ScoreModel.objects.create(
        game=game, number=number, term=term, observation_date=date(2026, 6, 30),
        window_months=12, seed=number, status=status, built_tick=game.current_tick,
    )  # fmt: skip


def _no_news(*_: Any) -> None:
    return None


@pytest.mark.django_db(transaction=True)
def test_every_department_on_the_first_floor_is_drawn_from_its_own_state(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    shown = _first(client, game)
    rooms = _rooms(shown)
    assert set(rooms) == {
        "DATA_OPERATIONS", "DATA_ANALYTICS", "IT", "PRODUCT", "SERVER_ROOM", "TECH_MEETING",
    }  # fmt: skip

    # Data Operations: its own staff, as before.
    assert {p["desk"] for p in shown["staff"] if not p.get("managed")} == {"DATA_OPERATIONS"}

    # Analytics: one analyst and no scorecard yet; then one for each scorecard kept.
    assert [p["activity"] for p in _team(shown, "DATA_ANALYTICS")] == ["FREE"]
    assert rooms["DATA_ANALYTICS"]["summary"].startswith("No scorecard yet")
    _model(game, 1, ScoreModel.Status.DEPLOYED)
    _model(game, 2, ScoreModel.Status.DRAFT, "COMPOSITE")
    _model(game, 3, ScoreModel.Status.RETIRED)
    shown = _first(client, game)
    analysts = _team(shown, "DATA_ANALYTICS")
    assert [p["model"]["number"] for p in analysts] == [1, 2]  # deployed first, retired gone
    assert [p["screen"] for p in analysts] == ["scorecards/1", "scorecards/2"]
    assert "watching scorecard 1 (short term), deployed" in analysts[0]["doing"]
    assert _rooms(shown)["DATA_ANALYTICS"]["summary"] == "2 scorecard(s): 1 deployed, 1 draft(s)."
    assert _rooms(shown)["DATA_ANALYTICS"]["desks"] == 2
    assert shown["analytics"]["models"] == [
        {"number": 1, "term": "SHORT", "status": "DEPLOYED"},
        {"number": 2, "term": "COMPOSITE", "status": "DRAFT"},
    ]

    # IT: two on standard capacity, three on high, at their desks while systems are up.
    assert [p["number"] for p in _team(shown, "IT")] == ["IT-1", "IT-2"]
    assert {p["desk"] for p in _team(shown, "IT")} == {"IT"}
    controls.set_it_capacity(game, "HIGH")
    shown = _first(client, game)
    assert len(_team(shown, "IT")) == 3
    assert shown["systems"]["racks"] == it.CAPACITY["HIGH"]

    # Product Development: nobody until something is in development, then its progress.
    assert _team(shown, "PRODUCT") == []
    assert _rooms(shown)["PRODUCT"]["summary"].startswith("Nothing in development")
    controls.develop_product(game, "BUSINESS_REPORT")
    shown = _first(client, game)
    product = _team(shown, "PRODUCT")
    assert [p["product"] for p in product] == ["BUSINESS_REPORT"]
    assert shown["developments"][0]["progress"] == 0.0
    assert _rooms(shown)["PRODUCT"]["summary"] == "Developing the business credit report (0%)."
    controls.advance_by(game, "day", 10)
    game.refresh_from_db()
    later = _first(client, game)["developments"][0]
    assert 0.1 < later["progress"] < 0.5  # 10 working days of 40, as calendar days go

    # The server room: utilisation, storage, availability and maintenance (PRD 6.3).
    systems = _first(client, game)["systems"]
    assert systems["utilisation"] == min(1.0, systems["files_waiting"] / 5)
    assert systems["storage"]["accounts"] > 0 and systems["storage"]["customers"] > 0
    assert systems["availability"] == 1.0
    assert systems["maintenance"] == "Running normally: no outage so far."

    # The managed teams are not on the payroll, and real staff of a department replace them.
    assert (
        not Employee.objects.filter(organization=game.organization)
        .exclude(department="DATA_OPERATIONS")
        .exists()
    )
    hire = Employee.objects.filter(organization=game.organization).first()
    assert hire is not None
    hire.department = "IT"
    hire.save(update_fields=["department"])
    shown = _first(client, game)
    assert _team(shown, "IT") == []
    assert hire.employee_number in {p["number"] for p in shown["staff"] if p["desk"] == "IT"}


@pytest.mark.django_db(transaction=True)
def test_an_outage_lights_the_racks_and_draws_it_to_the_server_room_within_one_refresh(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    controls.advance_by(game, "hour", 1)
    game.refresh_from_db()
    before = _first(client, game)
    assert not before["systems"]["down"]
    assert {p["place"] for p in _team(before, "IT")} == {"DESK"}

    it.start_outage(game, game.current_tick + 1, "The database server failed.", _no_news)
    shown = _first(client, game)  # the very next refresh
    assert shown["systems"]["down"]  # the racks' lights go red
    it_team = _team(shown, "IT")
    assert {p["place"] for p in it_team} == {teams.SERVER_ROOM}
    assert {p["room"] for p in it_team} == {"SERVER_ROOM"}
    assert {p["desk"] for p in it_team} == {"IT"}  # their desks stay theirs, empty
    assert {p["activity"] for p in it_team} == {teams.RESTORING}
    rooms = _rooms(shown)
    assert rooms["SERVER_ROOM"]["summary"].startswith("Systems down: The database server")
    assert "IT team 1, IT team 2 at the racks" in rooms["SERVER_ROOM"]["summary"]
    assert rooms["IT"]["summary"] == "IT team of 2: 2 in the server room, restoring the systems."
    assert shown["systems"]["maintenance"] == "Outage 1 under way: no response yet."

    # The vendor fixes it within two working hours; IT goes back to its desks.
    controls.respond_to_outage(game, "VENDOR")
    assert _first(client, game)["systems"]["maintenance"].endswith("the vendor is fixing it.")
    controls.advance_by(game, "hour", 3)
    game.refresh_from_db()
    after = _first(client, game)
    assert not after["systems"]["down"]
    assert {p["place"] for p in _team(after, "IT")} == {"DESK"}
    assert after["systems"]["availability"] < 1.0
    assert after["systems"]["maintenance"] == ("Running normally: the last outage was number 1.")


@pytest.mark.django_db(transaction=True)
def test_each_object_on_the_floor_opens_its_screen(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    _model(game, 1, ScoreModel.Status.DEPLOYED)
    controls.develop_product(game, "BATCH_ENQUIRY")
    shown = _first(client, game)
    screens = {r["code"]: r["screen"] for r in shown["rooms"]}
    assert screens == {
        "DATA_OPERATIONS": "queue", "DATA_ANALYTICS": "analytics", "IT": "it",
        "PRODUCT": "products", "SERVER_ROOM": "it", "TECH_MEETING": "reviews",
    }  # fmt: skip
    by = {p["department"]: p["screen"] for p in shown["staff"] if p.get("managed")}
    assert by == {"DATA_ANALYTICS": "scorecards/1", "IT": "it", "PRODUCT": "products"}


@pytest.mark.django_db(transaction=True)
def test_teams_go_home_after_hours_and_a_startup_draws_none(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    controls.advance_by(game, "day", 1)
    game.refresh_from_db()
    if not _first(client, game)["after_hours"]:
        controls.advance_by(game, "hour", 9)
        game.refresh_from_db()
    shown = _first(client, game)
    assert shown["after_hours"]
    managed = [p for p in shown["staff"] if p.get("managed")]
    assert managed and {p["place"] for p in managed} == {"OUT"}
    assert {p["room"] for p in managed} == {None}

    startup = _start(world, owner, scenario=scenarios.STARTUP)
    assert teams.team(startup, None, teams.today_of(startup)) == []
