"""The ground floor: the public face (P4.5; Document 10).

Done when: a dispute brings a visitor to reception, and closing it ends the visit; an
outage's wave of tickets shows on the Support desks; selecting the cafeteria shows the
welfare figures; every object on the floor opens its 2D screen (the screens are checked
here, the clicks and the piles in the layout tests).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import Customer
from apps.bureau.providers.models import Institution
from apps.bureau.quality.disputes import open_dispute, resolve
from apps.bureau.quality.models import Decision, Dispute, ReviewCase
from apps.bureau.submissions.models import Submission
from apps.org.models import Employee
from apps.simulation import controls, ground, it, places, sales
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY
from apps.simulation.engine import calendar
from apps.simulation.models import Game, LenderResearch
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(83, "small")
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


def _ground(client: APIClient, game: Game) -> dict[str, Any]:
    shown: dict[str, Any] = client.get(f"/api/v1/games/{game.pk}/office/ground/").json()
    return shown


def _rooms(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["code"]: r for r in floor["rooms"]}


def _guests(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["number"]: p for p in floor["staff"] if p.get("visitor")}


def _team(floor: dict[str, Any], department: str) -> list[dict[str, Any]]:
    return [p for p in floor["staff"] if p.get("department") == department]


def _at(game: Game, tick: int) -> Game:
    """Stand the clock at ``tick`` (the office is drawn from the state alone)."""
    game.current_tick = tick
    game.save(update_fields=["current_tick"])
    return game


def _customer(game: Game) -> Customer:
    """A customer on file (a new game has none until its first file loads)."""
    org = game.organization
    found = Customer.objects.filter(organization=org).first()
    if found is not None:
        return found
    institution = Institution.objects.filter(organization=org).first() or (
        Institution.objects.create(organization=org, institution_code="TST",
                                   institution_name="Test Bank", institution_type="BANK")
    )  # fmt: skip
    when = calendar(game).tick_start(1)
    submission = Submission.objects.create(
        organization=org, institution=institution, submission_reference="TEST-1",
        reporting_period=when.date(), template_version="TEST", due_date=when.date(),
        received_at=when,
    )  # fmt: skip
    return Customer.objects.create(
        organization=org, customer_type="INDIVIDUAL", customer_reference="C-TEST",
        source_submission=submission,
    )  # fmt: skip


def _dispute(game: Game, name: str, came: int) -> Dispute:
    """A data subject's dispute, reaching the bureau during tick ``came``."""
    customer = _customer(game)
    at = calendar(game).tick_start(came) + timedelta(minutes=5)
    return open_dispute(
        game.organization, customer, None, name, "The loan on my report is not mine.", [],
        at, at.date() + timedelta(days=30),
    )  # fmt: skip


@pytest.mark.django_db(transaction=True)
def test_a_dispute_brings_a_visitor_to_reception_and_closing_it_ends_the_visit(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    morning = TICKS_PER_DAY + 1  # the second working day's first tick
    game = _at(game, morning + 7)  # 10:00 under way
    assert _rooms(_ground(client, game))["RECEPTION"]["summary"] == "No visitors yet today."

    first = _dispute(game, "Ama Serwaa", game.current_tick + 1)  # in during the tick under way
    shown = _ground(client, game)
    ama = _guests(shown)[f"V-D{first.dispute_number}"]
    assert (ama["room"], ama["place"], ama["activity"]) == ("RECEPTION", "VISIT", "VISITING")
    assert ama["screen"] == "disputes"
    assert f"dispute {first.dispute_number}" in ama["doing"]
    assert _rooms(shown)["RECEPTION"]["summary"] == "Signing in: Ama Serwaa."
    assert shown["visits"] == [
        f"Ama Serwaa, about dispute {first.dispute_number}, came at 10:00: signing in"
    ]

    # Half an hour later she waits in the waiting area, until the day ends.
    game = _at(game, game.current_tick + ground.SIGN_IN_TICKS)
    shown = _ground(client, game)
    assert _guests(shown)[f"V-D{first.dispute_number}"]["room"] == "WAITING"
    assert _rooms(shown)["WAITING"]["summary"] == "Waiting: Ama Serwaa."
    assert _rooms(shown)["RECEPTION"]["summary"].startswith("1 visit(s) in the book today")

    # Closing the dispute ends the visit at once; reception's book keeps it.
    case = ReviewCase.objects.get(dispute=first)
    resolve(case, Decision.REJECT_DISPUTE, "Test", calendar(game).tick_end(game.current_tick))
    shown = _ground(client, game)
    assert _guests(shown) == {}
    assert _rooms(shown)["WAITING"]["summary"] == "Nobody is waiting."
    assert shown["visits"][0].endswith("settled, gone")

    # A dispute still open is gone after hours, and is not brought back the next day.
    second = _dispute(game, "Kwame Boateng", game.current_tick)
    assert f"V-D{second.dispute_number}" in _guests(_ground(client, game))
    game = _at(game, 2 * TICKS_PER_DAY)  # 17:00
    assert _guests(_ground(client, game)) == {}
    game = _at(game, 2 * TICKS_PER_DAY + 4)
    assert _guests(_ground(client, game)) == {}

    # A visitor shows on the ground floor only.
    other = _dispute(game, "Yaw Darko", game.current_tick + 1)
    first_floor = client.get(f"/api/v1/games/{game.pk}/office/first/").json()
    assert f"V-D{other.dispute_number}" not in {p["number"] for p in first_floor["staff"]}


@pytest.mark.django_db(transaction=True)
def test_a_prospect_comes_to_meet_sales_on_the_meetings_day(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    lender = sales.prospects(game)[0]
    day = TICKS_PER_DAY  # the second working day: ticks 37-72
    meeting_on = calendar(game).day(1)
    LenderResearch.objects.create(
        game=game, lender_code=lender.code, requested_tick=1, ready_on=meeting_on,
        reported=True, meeting_requested_tick=2, meeting_on=meeting_on,
    )  # fmt: skip
    rep = f"V-L{lender.code}"
    game = _at(game, day + 4)  # 09:00
    shown = _ground(client, game)
    assert rep not in _guests(shown)
    assert _rooms(shown)["SALES"]["summary"] == f"Meeting {lender.name} here today, 14:00-15:00."
    assert shown["visits"] == [
        f"{lender.name}'s representative: expected at 13:45 to meet Sales, 14:00-15:00"
    ]
    assert [p["prospect"] for p in _team(shown, "SALES")] == [lender.code]

    game = _at(game, day + ground.ARRIVE_SLOT)  # 13:45 under way
    assert _guests(_ground(client, game))[rep]["room"] == "RECEPTION"
    game = _at(game, day + ground.MEETING_SLOTS[0])  # 14:00
    shown = _ground(client, game)
    visitor = _guests(shown)[rep]
    assert (visitor["room"], visitor["screen"]) == ("SALES", "sales")
    assert _rooms(shown)["SALES"]["summary"] == (
        f"Meeting {lender.name}'s representative, until 15:00."
    )
    game = _at(game, day + ground.MEETING_SLOTS[-1] + 1)  # 15:00
    assert rep not in _guests(_ground(client, game))


@pytest.mark.django_db(transaction=True)
def test_an_outages_wave_of_tickets_shows_on_the_support_desks(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    controls.advance_by(game, "hour", 1)
    game.refresh_from_db()
    before = _ground(client, game)
    support = _rooms(before)["SUPPORT"]
    assert support["desks"] == 2
    assert [p["number"] for p in _team(before, "CUSTOMER_SUPPORT")] == [
        "CUSTOMER_SUPPORT-1", "CUSTOMER_SUPPORT-2",
    ]  # fmt: skip
    quiet = before["tickets"]["outage_today"]
    assert quiet == 0

    # Down for the rest of the day: the next morning brings the subscribers' tickets.
    it.start_outage(game, game.current_tick + 1, "The database server failed.", lambda *_: None)
    controls.advance_by(game, "day", 1)
    game.refresh_from_db()
    if places.after_hours(game):
        controls.advance_by(game, "hour", 1)
        game.refresh_from_db()
    shown = _ground(client, game)
    t = shown["tickets"]
    assert t["outage_today"] > 0 and t["open"] >= t["outage_today"] - t["per_day"]
    line = _rooms(shown)["SUPPORT"]["summary"]
    assert f"{t['outage_today']} about the outage" in line
    if t["open"]:
        assert {p["activity"] for p in _team(shown, "CUSTOMER_SUPPORT")} == {places.WORKING}
        assert "tickets" in _team(shown, "CUSTOMER_SUPPORT")[0]["doing"]

    # With no agents, nobody answers: the room still has its desks for the pile.
    controls.set_support_staff(game, 0)
    shown = _ground(client, game)
    assert _team(shown, "CUSTOMER_SUPPORT") == []
    assert _rooms(shown)["SUPPORT"]["desks"] == 2


@pytest.mark.django_db(transaction=True)
def test_the_cafeteria_shows_the_welfare_figures_and_finance_the_close(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    staff = list(Employee.objects.filter(organization=game.organization, is_active=True))
    low = staff[0]
    low.morale = 0.35
    low.save(update_fields=["morale"])
    w = _ground(client, game)["welfare"]
    assert w["staff"] == len(staff)
    assert w["lowest"] == {"name": f"{low.first_name} {low.last_name}", "morale": 0.35}
    assert (w["low"], w["at_risk"]) == (1, 1)
    assert w["morale"] == round(sum(e.morale for e in staff) / len(staff), 2)
    assert 0.5 < w["pay"] < 2.0
    assert {"queue_per_person", "heavy", "done_today", "on_course", "day", "lunch"} <= set(w)
    shown = _ground(client, game)
    assert _rooms(shown)["CAFETERIA"]["summary"].endswith(
        f"Morale {w['morale']:.2f} on average across {len(staff)} staff."
    )

    # Finance's desks show the month-end close checklist's progress.
    close = shown["close"]
    assert close["total"] == len(close["items"]) == 5
    finance = _team(shown, "FINANCE")
    assert len(finance) == 2
    assert {p["progress"] for p in finance} == {round(close["done"] / close["total"], 2)}
    assert _rooms(shown)["FINANCE"]["summary"].endswith(
        f"({close['done']} of {close['total']} done)."
    )
    assert _rooms(shown)["HR"]["summary"] == f"{len(staff)} staff on the payroll."


@pytest.mark.django_db(transaction=True)
def test_every_object_on_the_ground_floor_opens_its_screen(
    world: World, owner: User, client: APIClient
) -> None:
    game = _start(world, owner)
    game = _at(game, TICKS_PER_DAY + 8)
    _dispute(game, "Ama Serwaa", game.current_tick + 1)
    shown = _ground(client, game)
    assert {r["code"]: r["screen"] for r in shown["rooms"]} == {
        "RECEPTION": "onboarding", "WAITING": "disputes", "SUPPORT": "support",
        "SALES": "sales", "FINANCE": "finance", "HR": "staff", "CAFETERIA": "staff",
    }  # fmt: skip
    by = {p["department"]: p["screen"] for p in shown["staff"] if p.get("managed")}
    assert by == {
        "CUSTOMER_SUPPORT": "support",
        "SALES": "sales",
        "FINANCE": "close",
        "HR": "staff",
    }
    assert {p["screen"] for p in shown["staff"] if p.get("visitor")} == {"disputes"}
    # Nobody on the payroll sits on the ground floor: the teams are not staff.
    assert not [p for p in shown["staff"] if not p.get("managed") and not p.get("visitor")]
