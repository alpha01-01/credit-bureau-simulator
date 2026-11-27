"""Where people are (P4.2; Document 10).

Done when: a test for each activity shows the person in the right place at the right
tick; a property test over a month of ticks finds nobody shown working on an item the
backend does not have in progress and assigned to them; a game replays exactly.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.org.models import Employee
from apps.simulation import building, controls, engine, places, sales
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import BoardReview, DataQualityReview, Game
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _start(world: World, owner: User | None = None) -> Game:
    return controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)


def _staff(game: Game) -> list[Employee]:
    return list(
        Employee.objects.filter(organization=game.organization, is_active=True).order_by(
            "employee_number"
        )
    )


def _where(game: Game) -> dict[str, places.Whereabouts]:
    found = places.whereabouts(game)
    return {e.employee_number: found[e.pk] for e in _staff(game)}


def _hours(game: Game, n: int) -> Game:
    return controls.advance_by(game, "hour", n)


def _floor(client: APIClient, game: Game, code: str) -> dict[str, Any]:
    shown: dict[str, Any] = client.get(f"/api/v1/games/{game.pk}/office/{code}/").json()
    return shown


def _people(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["number"]: p for p in floor["staff"]}


def _rooms(floor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["code"]: r for r in floor["rooms"]}


@pytest.mark.django_db(transaction=True)
def test_each_activity_puts_the_person_in_its_place_at_its_tick(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _start(world, owner)
    client = APIClient()
    client.force_authenticate(owner)
    staff = _staff(game)
    head = places._senior_first(staff)[0]
    seniors = {e.employee_number for e in staff if e.job_title == "Senior Data Officer"} or {
        head.employee_number
    }

    # 08:00 on the first morning: nothing to do yet, so everyone waits at their desk.
    assert game.current_tick == 0
    assert {w.activity for w in _where(game).values()} == {places.FREE}
    first = _floor(client, game, "first")
    assert {p["desk"] for p in first["staff"]} == {"DATA_OPERATIONS"}
    assert {p["room"] for p in first["staff"]} == {"DATA_OPERATIONS"}

    # A board review held at this tick: the head of Data Operations presents, for two hours.
    review = BoardReview.objects.create(
        game=game, period=date(2026, 12, 31), tick=1, confidence=70, verdict="CONFIDENT",
        detail="Test.",
    )  # fmt: skip
    where = _where(game)
    assert where[head.employee_number] == places.Whereabouts(places.BOARDROOM, places.BOARD)
    assert places.in_meetings(game, 1) == {head.pk}
    assert places.in_meetings(game, 8) == {head.pk}  # 09:45, the last quarter of it
    assert places.in_meetings(game, 9) == frozenset()  # 10:00: back at work
    second = _floor(client, game, "second")
    assert _people(second)[head.employee_number]["room"] == "BOARDROOM"
    assert _rooms(second)["BOARDROOM"]["summary"].startswith("The board review: ")
    mine = _people(_floor(client, game, "first"))[head.employee_number]
    assert mine["desk"] == "DATA_OPERATIONS" and mine["room"] is None
    assert mine["doing"] == "presenting to the board (Boardroom, second floor)"
    review.delete()

    # The Data Quality Review, the morning after a month's last tick, 10:00-11:00.
    game = _hours(game, 2)  # the clock at 10:00
    assert places.slot(game.current_tick + 1) == 8
    DataQualityReview.objects.create(game=game, period=date(2026, 11, 30), tick=0)
    where = _where(game)
    assert {n for n, w in where.items() if w.activity == places.REVIEW} == seniors
    assert all(where[n].place == places.MEETING_ROOM for n in seniors)
    meeting = _rooms(_floor(client, game, "first"))["TECH_MEETING"]
    assert meeting["summary"].startswith("The Data Quality Review: ")
    assert places.in_meetings(game, 12) == {e.pk for e in staff if e.employee_number in seniors}
    assert places.in_meetings(game, 13) == frozenset()  # 11:00
    DataQualityReview.objects.filter(game=game).delete()

    # The lunch hour: the free go to the cafeteria, on the ground floor.
    game = _hours(game, 2)  # 12:00
    assert {w.activity for w in _where(game).values()} == {places.BREAK}
    ground = _floor(client, game, "ground")
    assert {p["room"] for p in ground["staff"]} == {"CAFETERIA"}
    assert all(p["desk"] is None for p in ground["staff"])  # their desks are upstairs
    assert _rooms(ground)["CAFETERIA"]["summary"].startswith("On a break: ")
    assert ", 3 on a break" in _rooms(_floor(client, game, "first"))["DATA_OPERATIONS"]["summary"]

    # After lunch, back at their desks, but someone unhappy stays away from it.
    game = _hours(game, 2)  # 14:00
    low = staff[-1]
    low.morale = 0.4
    low.save(update_fields=["morale"])
    where = _where(game)
    assert where[low.employee_number].activity == places.BREAK
    assert {w.activity for n, w in where.items() if n != low.employee_number} == {places.FREE}
    low.morale = 0.7
    low.save(update_fields=["morale"])

    # On a course: out of the building for a working day's worth of ticks.
    controls.train_employee(game, staff[1].employee_number, "MATCH_REVIEW")
    assert _where(game)[staff[1].employee_number] == places.Whereabouts(places.OUT, places.TRAINING)
    trainee = _people(_floor(client, game, "first"))[staff[1].employee_number]
    assert trainee["room"] is None and trainee["desk"] == "DATA_OPERATIONS"
    assert staff[1].employee_number not in _people(_floor(client, game, "ground"))

    # After hours, everyone is out, and the floor says so.
    game = controls.advance_by(game, "day")
    assert game.current_tick % TICKS_PER_DAY == 0
    assert {w.activity for w in _where(game).values()} == {places.AFTER_HOURS}
    shown = _floor(client, game, "first")
    assert shown["after_hours"] and {p["room"] for p in shown["staff"]} == {None}


def test_a_startups_office_has_a_place_for_each_activity() -> None:
    """The places that are not desks, in each building (A-091)."""
    small = building.STARTUP_OFFICES["SMALL"][0]
    codes = {r.code for r in small.rooms}
    for place in building.PLACE_ROOMS:
        found = [c for c in building.PLACE_ROOMS[place] if c in codes]
        assert found, place
    established = {r.code for f in building.ESTABLISHED_BUILDING for r in f.rooms}
    for place, rooms in building.PLACE_ROOMS.items():
        assert rooms[0] in established, place


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_over_a_month_nobody_is_shown_working_on_what_they_do_not_hold(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Document 05 rule, checked after every tick of a month, and the meeting's time."""
    run_tick = engine.run_tick
    seen = {"ticks": 0, "working": 0, "meeting": 0}

    def checked(game_id: int, tick: int) -> bool:
        before = Game.objects.get(pk=game_id)
        absent = places.in_meetings(before, tick)
        held = {
            w.assignee_id: (w.item_number, w.minutes_remaining)
            for w in WorkItem.objects.filter(
                organization=before.organization, status=ItemStatus.IN_PROGRESS
            )
        }
        done = dict(Employee.objects.filter(pk__in=absent).values_list("pk", "done_today"))
        ran = run_tick(game_id, tick)
        after = Game.objects.get(pk=game_id)
        # In a meeting, nobody works: their items stand still and they finish none.
        for pk in absent:
            seen["meeting"] += 1
            if pk in held:
                item = WorkItem.objects.get(
                    organization=after.organization, item_number=held[pk][0]
                )
                assert item.minutes_remaining == held[pk][1], (tick, pk)
            assert Employee.objects.get(pk=pk).done_today == done[pk], (tick, pk)
        # Shown working only on an item in progress and assigned to them.
        for pk, w in places.whereabouts(after).items():
            if w.activity == places.WORKING:
                assert w.item is not None
                seen["working"] += 1
                assert WorkItem.objects.filter(
                    organization=after.organization, item_number=w.item, assignee_id=pk,
                    status=ItemStatus.IN_PROGRESS,
                ).exists(), (tick, pk, w)  # fmt: skip
            else:
                assert w.item is None
        seen["ticks"] += 1
        return ran

    monkeypatch.setattr(engine, "run_tick", checked)
    owner = User.objects.create_user("player")
    game = _start(world, owner)
    client = APIClient()
    client.force_authenticate(owner)

    # Sales researches a lender, then meets it: on that day Sales is out at the prospect.
    lender = sales.prospects(game)[0]
    controls.research_lender(game, lender.code)
    while not game.research.get(lender_code=lender.code).reported:
        game = controls.advance_by(game, "day")
    controls.meet_lender(game, lender.code)
    meeting_on = game.research.get(lender_code=lender.code).meeting_on
    assert meeting_on is not None
    while controls.state(game).now.date() < meeting_on or places.after_hours(game):
        game = _hours(game, 1)
    summary = _rooms(_floor(client, game, "ground"))["SALES"]["summary"]
    assert summary == f"Sales is out at the prospect today, meeting {lender.name}."

    # On to the month's end, then the next morning's Data Quality Review at 10:00.
    while not DataQualityReview.objects.filter(game=game).exists():
        game = controls.advance_by(game, "day")
    review = DataQualityReview.objects.get(game=game)
    assert game.current_tick == review.tick  # built at the month's last tick
    game = _hours(game, 2)  # 08:00-10:00 the next working morning
    assert game.current_tick + 1 == review.tick + places.REVIEW_AFTER[0]
    attendees = {
        p["number"] for p in _floor(client, game, "first")["staff"]
        if p["activity"] == places.REVIEW
    }  # fmt: skip
    assert attendees and all(
        _people(_floor(client, game, "first"))[n]["room"] == "TECH_MEETING" for n in attendees
    )
    game = _hours(game, 2)
    assert not any(w.activity == places.REVIEW for w in _where(game).values())

    print(f"places over a month: {seen}")  # noqa: T201
    assert seen["ticks"] > TICKS_PER_DAY and seen["working"]

    # The same actions replayed give the same game, meetings and all.
    replayed = controls.replay(game, start_game(world))
    assert fingerprint(replayed) == fingerprint(game), differences(replayed, game)
