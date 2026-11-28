"""The second floor: the executive floor (P4.6; Document 10).

Done when: a board review fills the boardroom; a new compliance finding appears on the
floor within one refresh; the notice board shows the current mission and the
regulator's open actions; every object on the floor opens its 2D screen (the screens
are checked here, the clicks in the layout tests).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.finance import budget
from apps.simulation import controls, duties, executive, missions, places
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY
from apps.simulation.engine import calendar
from apps.simulation.models import BoardReview, Game, RegulatorFinding, RegulatorStanding
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(84, "small")
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


def _start(world: World, owner: User) -> Game:
    return controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)


def _second(client: APIClient, game: Game) -> dict[str, Any]:
    shown: dict[str, Any] = client.get(f"/api/v1/games/{game.pk}/office/second/").json()
    return shown


def _rooms(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["code"]: r for r in floor["rooms"]}


def _at(game: Game, tick: int) -> Game:
    """Stand the clock at ``tick`` (the office is drawn from the state alone)."""
    game.current_tick = tick
    game.save(update_fields=["current_tick"])
    return game


@pytest.mark.django_db(transaction=True)
def test_a_board_review_fills_the_boardroom(world: World, owner: User, client: APIClient) -> None:
    game = _start(world, owner)
    morning = TICKS_PER_DAY + 1  # 08:00 on the second working day
    BoardReview.objects.create(
        game=game, period=date(2026, 12, 31), tick=morning, confidence=72.4, parts={},
        verdict="CONFIDENT", detail="Every part of the bureau is in good health.",
    )  # fmt: skip
    game = _at(game, morning)  # 08:15 under way: the review has begun
    shown = _second(client, game)
    in_room = [p for p in shown["staff"] if p["room"] == "BOARDROOM"]
    board = [p for p in in_room if p.get("visitor")]
    assert [p["job_title"] for p in board] == list(executive.DIRECTORS)
    assert {p["activity"] for p in in_room} == {places.BOARD}
    assert {p["screen"] for p in board} == {"health#board"}
    ceo = next(p for p in shown["staff"] if p["number"] == "CEO")
    assert (ceo["room"], ceo["place"], ceo["desk"]) == ("BOARDROOM", places.BOARDROOM, "CEO_OFFICE")
    presenter = [p for p in in_room if not p.get("visitor") and not p.get("managed")]
    assert len(presenter) == 1  # Data Operations' most senior person, from the first floor
    assert len(in_room) == len(executive.DIRECTORS) + 2
    assert _rooms(shown)["BOARDROOM"]["summary"].startswith("The board review: ")
    assert shown["board"]["in_session"]

    # Two hours on the board has gone, and the chief executive is back at their desk.
    game = _at(game, morning + places.BOARD_TICKS)
    shown = _second(client, game)
    assert not [p for p in shown["staff"] if p["room"] == "BOARDROOM"]
    ceo = next(p for p in shown["staff"] if p["number"] == "CEO")
    assert (ceo["room"], ceo["place"]) == ("CEO_OFFICE", places.DESK)
    assert _rooms(shown)["BOARDROOM"]["summary"] == (
        "Last review, Q4 2026: confidence 72, confident. "
        "The next is due on the first working day of April 2027."
    )
    assert _rooms(shown)["CEO_OFFICE"]["summary"] == (
        "The chief executive (you): at their desk: the company at a glance."
    )

    # After hours everyone has gone home, the chief executive too.
    game = _at(game, 2 * TICKS_PER_DAY)
    shown = _second(client, game)
    assert {p["place"] for p in shown["staff"] if p.get("managed")} == {places.OUT}
    assert not [p for p in shown["staff"] if p.get("visitor")]


@pytest.mark.django_db(transaction=True)
def test_a_new_compliance_finding_appears_on_the_floor_within_one_refresh(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    before = _second(client, game)
    open_before = before["compliance"]["open"]
    officers = [p for p in before["staff"] if p.get("department") == "COMPLIANCE"]
    assert [p["job_title"] for p in officers] == ["Compliance officer"]

    at = calendar(game).tick_end(max(1, game.current_tick))
    finding = duties.raise_finding(
        game, "CONSENT_MISSING", "ATB-CHECK-1", "ATB could not show consent for 2 enquiries.",
        "Warn ATB, or suspend its enquiries for a month.", game.current_tick, at,
    )  # fmt: skip
    shown = _second(client, game)  # the very next refresh
    c = shown["compliance"]
    assert c["open"] == open_before + 1
    assert c["findings"][-1]["number"] == finding.number
    assert c["findings"][-1]["words"] == "enquiries without consent on file"
    assert _rooms(shown)["COMPLIANCE"]["summary"].startswith(f"{open_before + 1} finding(s) open")
    officer = next(p for p in shown["staff"] if p.get("department") == "COMPLIANCE")
    assert officer["activity"] == places.WORKING

    # Put right, it goes from the floor too.
    duties.resolve_findings(game, game.current_tick, number=finding.number)
    assert _second(client, game)["compliance"]["open"] == open_before


@pytest.mark.django_db(transaction=True)
def test_the_notice_board_shows_the_mission_the_targets_and_the_regulator(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    assert game.campaign
    notices = _second(client, game)["notices"]
    current = missions.current(game)
    assert current is not None
    assert notices["mission"]["code"] == current.code
    assert notices["mission"]["title"] == current.title
    assert notices["mission"]["objectives"]  # each with its text and whether it is done
    # The budget a game starts with is for costs; revenue has no target until one is set.
    assert [t.split(":")[0] for t in notices["targets"]] == ["Costs"]

    month = calendar(game).tick_end(max(1, game.current_tick)).date()
    budget.set_budget(game.organization, "SALES", Decimal("50000"), month)
    RegulatorStanding.objects.create(game=game, level=2)
    RegulatorFinding.objects.create(
        game=game, kind="MISSED_DISPUTE_DEADLINE", reference="7",
        raised_at=calendar(game).tick_end(max(1, game.current_tick)), detail="Dispute 7 late.",
    )  # fmt: skip
    shown = _second(client, game)
    notices = shown["notices"]
    assert notices["targets"][0].startswith("Revenue: GHS ")
    assert notices["targets"][0].endswith("of GHS 50,000 to reach")
    assert notices["regulator"][0] == (
        "Standing: directive. Formal directive: settle disputes within the statutory period."
    )
    assert "Five bring a financial penalty." in notices["regulator"]
    assert "1 regulator finding(s) in the last six months" in notices["regulator"]
    acts = len(notices["regulator"])
    assert _rooms(shown)["EXECUTIVE"]["summary"] == (
        f"Notice board: mission {current.code}, {current.title}; {acts} item(s) from the regulator."
    )

    # With the campaign off, the board says so.
    game.campaign = False
    game.save(update_fields=["campaign"])
    assert _second(client, game)["notices"]["mission"] is None


@pytest.mark.django_db(transaction=True)
def test_every_object_on_the_executive_floor_opens_its_screen(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    shown = _second(client, game)
    assert {r["code"]: r["screen"] for r in shown["rooms"]} == {
        "CEO_OFFICE": "dashboard", "EXECUTIVE": "health", "BOARDROOM": "health#board",
        "COMPLIANCE": "compliance", "EXEC_MEETING": "events",
    }  # fmt: skip
    by = {p["department"]: p["screen"] for p in shown["staff"] if p.get("managed")}
    assert by == {"CEO": "dashboard", "COMPLIANCE": "compliance"}
    assert _rooms(shown)["CEO_OFFICE"]["desks"] == 1  # the chief executive's desk
