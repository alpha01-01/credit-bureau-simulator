"""P2.2 — The event feed, auto-pause and the real-time clock.

Done when (Document 08): a player can leave the game running at 1x and be
stopped for every critical event; nothing important happens silently.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.quality.models import CaseType
from apps.bureau.submissions.pipeline import process_submission
from apps.org.models import Employee
from apps.simulation import controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.clock import TICKS_PER_DAY
from apps.simulation.engine import ClockError, advance
from apps.simulation.feed import WORK_ITEM_DAYS, due_tick
from apps.simulation.fingerprint import fingerprint
from apps.simulation.judgement import sync_work_items
from apps.simulation.models import (
    EventType,
    Game,
    GameStatus,
    Notice,
    ScheduledEvent,
    Severity,
    SubscriberView,
)
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Lender, World
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import POOR

# Defects that need judgement and nothing that rejects whole files (as in the work-item tests).
TRICKY = replace(
    POOR,
    name="TRICKY",
    wrong_identifier=0.12, name_typo=0.10, date_format=0.12, amount_format=0.08,
    inconsistent_status=0.10, missing_field=0.02, duplicate_row=0.0, omit_account=0.0,
    template_drift=0.0, late_rate=0.0,
)  # fmt: skip


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world(seed: int) -> World:
    g = build_world(seed, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


@pytest.fixture
def world(db: None) -> World:
    return _world(81)


def _kinds(game: Game) -> set[str]:
    return set(Notice.objects.filter(game=game).values_list("kind", flat=True))


def _broke(game: Game) -> None:
    """Salaries the bank cannot cover: cash falls below a month's payroll."""
    Employee.objects.filter(organization=game.organization).update(
        monthly_salary=Decimal("10000000")
    )


def _step(game: Game) -> Game:
    """One real-time tick, without waiting for the wall clock."""
    Game.objects.filter(pk=game.pk).update(last_step_at=None)
    return controls.step(game)


# --- The feed ---------------------------------------------------------------------------


def test_the_feed_reports_what_happens(world: World) -> None:
    game = controls.set_pause_rules(start_game(world), [], deadlines=False)
    while controls.state(game).now.month < 3:
        game = controls.advance_by(game, "next_event")
    game = controls.advance_by(game, "day", 3)

    kinds = _kinds(game)
    assert {"FILES_ARRIVED", "RUN_FINISHED", "INVOICES_ISSUED", "PAYROLL_PAID",
            "TAXES_PAID", "INVOICE_OVERDUE"} <= kinds  # fmt: skip
    notices = list(Notice.objects.filter(game=game).order_by("pk"))
    assert [n.tick for n in notices] == sorted(n.tick for n in notices)
    for n in notices:
        assert n.title
        assert n.drill.get("screen"), n  # every notice has a "Why?" link
        assert n.severity in Severity.values
        assert not n.paused  # the rules were switched off
    arrived = next(n for n in notices if n.kind == "FILES_ARRIVED")
    assert arrived.drill["screen"] == "submission"
    assert arrived.drill["params"]["reference"].startswith("SUB-")
    overdue = next(n for n in notices if n.kind == "INVOICE_OVERDUE")
    assert overdue.severity == Severity.WARNING
    assert overdue.sim_time.time().hour == 8  # seen first thing in the morning


def test_a_late_provider_is_reported_once(db: None) -> None:
    late_world = _world(61)  # a provider is late in January
    game = controls.set_pause_rules(start_game(late_world), [], deadlines=False)
    game = controls.advance_by(game, "day", 25)
    late = Notice.objects.filter(game=game, kind="DATA_OVERDUE")
    providers = {n.title.split(" has not")[0] for n in late}
    assert len(late) == len(providers) >= 1  # one notice per late provider, not daily


# --- Auto-pause -----------------------------------------------------------------------------


def test_a_critical_event_stops_a_running_clock(world: World) -> None:
    game = start_game(world)
    assert game.pause_severities == ["CRITICAL"]  # the default rule
    _broke(game)
    game = controls.resume(game)

    game = _step(game)  # the first morning: cash is checked
    game.refresh_from_db()
    assert game.status == GameStatus.PAUSED
    stop = controls.stopped_by(game)
    assert stop is not None and stop.kind == "CASH_LOW" and stop.severity == Severity.CRITICAL
    state = controls.state(game).as_dict()
    assert state["stopped_by"]["title"] == stop.title

    # Resumed, it carries on; the same shortfall is not reported again.
    game = controls.resume(game)
    for _ in range(TICKS_PER_DAY + 2):
        game = _step(game)
    game.refresh_from_db()
    assert game.status == GameStatus.RUNNING
    assert Notice.objects.filter(game=game, kind="CASH_LOW").count() == 1


def test_an_advance_stops_where_the_player_asked_to_be_stopped(world: World) -> None:
    game = start_game(world)
    _broke(game)
    game = controls.advance_by(game, "day", 3)
    assert game.current_tick == 1  # stopped on the first morning, not three days later
    assert controls.stopped_by(game).kind == "CASH_LOW"  # type: ignore[union-attr]

    quiet = controls.set_pause_rules(start_game(world), [], deadlines=False)
    _broke(quiet)
    quiet = controls.advance_by(quiet, "day", 3)
    assert quiet.current_tick == 3 * TICKS_PER_DAY  # noted, but not stopped
    assert Notice.objects.filter(game=quiet, kind="CASH_LOW", paused=False).exists()


def test_a_subscriber_losing_faith_is_critical(db: None) -> None:
    busy_world = _world(91)  # lenders check the bureau from the first weeks
    game = controls.set_pause_rules(start_game(busy_world), [], deadlines=False)
    SubscriberView.objects.filter(game=game).update(perceived_value=0.41)
    while not Notice.objects.filter(game=game, kind="SUBSCRIBER_AT_RISK").exists():
        game = controls.advance_by(game, "next_event")
        assert controls.state(game).now.month < 3, "no subscriber ever complained"
    notice = Notice.objects.get(game=game, kind="SUBSCRIBER_AT_RISK")
    assert notice.severity == Severity.CRITICAL
    assert "reconsidering" in notice.title
    assert "0.4" not in notice.detail  # its private view of the bureau stays hidden
    view = SubscriberView.objects.get(game=game, at_risk=True)
    assert view.perceived_value < 0.40


def test_pause_rules_are_a_replayable_action(world: World) -> None:
    original = start_game(world)
    _broke(original)
    original = controls.advance_by(original, "day", 2)  # stops at the cash warning
    original = controls.set_pause_rules(original, ["WARNING", "CRITICAL"], deadlines=True)
    original = controls.advance_by(original, "day", 6)
    original = controls.set_pause_rules(original, [], deadlines=False)
    original = controls.advance_by(original, "day", 4)
    assert original.actions.filter(action_type="SET_PAUSE_RULES").count() == 2

    copy = start_game(world)
    _broke(copy)
    copy = controls.replay(original, copy)
    assert fingerprint(copy) == fingerprint(original)


def test_unknown_severities_are_refused(world: World) -> None:
    game = start_game(world)
    with pytest.raises(ClockError):
        controls.set_pause_rules(game, ["URGENT"], deadlines=True)


# --- Decision deadlines ----------------------------------------------------------------------


def _queue(world: World) -> Game:
    """Open work items and no staff to take them.

    After the month's first tick, two providers' files are swapped for tricky ones
    (lots of defects that need judgement) and processed straight away.
    """
    game = advance(start_game(world), 1)
    codes = ("ATB", "MRB")
    ScheduledEvent.objects.filter(
        game=game, event_type=EventType.PROVIDER_FILES_ARRIVE, payload__lender__in=codes
    ).delete()
    for code in codes:
        lender = Lender.objects.get(world=world, code=code)
        world_sub = generate_submission(
            world, lender, world.history_end, TRICKY, replace=True
        ).submission
        process_submission(deliver(game, world_sub), at=datetime(2027, 1, 4, 9, 0, tzinfo=UTC))
    sync_work_items(game, game.current_tick)
    Employee.objects.filter(organization=game.organization).update(is_active=False)
    return game


def test_work_items_are_due_five_working_days_after_they_open() -> None:
    assert due_tick(1) == (1 + WORK_ITEM_DAYS) * TICKS_PER_DAY  # opened on day 1
    assert due_tick(TICKS_PER_DAY) == (1 + WORK_ITEM_DAYS) * TICKS_PER_DAY  # same day, later
    assert due_tick(TICKS_PER_DAY + 1) == (2 + WORK_ITEM_DAYS) * TICKS_PER_DAY


def test_untaken_work_due_today_stops_the_clock(world: World) -> None:
    # Only deadlines stop the clock here: the test is about work falling due, not about
    # whatever else the month brings (a subscriber reconsidering, say).
    game = controls.set_pause_rules(_queue(world), [], deadlines=True)
    items = WorkItem.objects.filter(organization=game.organization, status=ItemStatus.OPEN).exclude(
        item_type=CaseType.REGULATORY_RETURN  # due on the 15th by rule, not in five days (P3.7)
    )
    assert items.exists()
    assert {i.due_tick for i in items} == {due_tick(1)}

    game = controls.advance_by(game, "day", 10)
    stop = controls.stopped_by(game)
    assert stop is not None and stop.kind == "WORK_DUE" and stop.is_deadline
    assert game.current_tick == due_tick(1) - TICKS_PER_DAY + 1  # the morning of the due day
    # Everything open and due today, including items opened since the first count.
    due_now = WorkItem.objects.filter(
        organization=game.organization, status=ItemStatus.OPEN, due_tick=due_tick(1)
    )
    assert str(due_now.count()) in stop.title

    game = controls.set_pause_rules(game, ["CRITICAL"], deadlines=False)
    game = controls.advance_by(game, "day", 2)
    missed = Notice.objects.get(game=game, kind="WORK_MISSED")
    assert missed.severity == Severity.WARNING and not missed.paused


# --- The real-time clock and the API ------------------------------------------------------


def test_real_time_ticks_keep_to_the_speed(world: World) -> None:
    game = controls.resume(start_game(world))
    game = controls.step(game)
    assert game.current_tick == 1
    game = controls.step(game)  # straight away: too soon, nothing happens
    assert game.current_tick == 1
    Game.objects.filter(pk=game.pk).update(
        last_step_at=game.last_step_at - timedelta(seconds=10)  # type: ignore[operator]
    )
    game = controls.step(game)
    assert game.current_tick == 2
    paused = controls.pause(game)
    assert _step(paused).current_tick == 2  # a paused clock does not move


def test_feed_and_clock_api(world: World) -> None:
    owner = User.objects.create_user("player")
    game = start_game(world, owner=owner)
    _broke(game)
    client = APIClient()
    assert client.get(f"/api/v1/games/{game.pk}/feed/").status_code == 403
    client.force_authenticate(owner)

    client.post(f"/api/v1/games/{game.pk}/clock/resume/")
    Game.objects.filter(pk=game.pk).update(last_step_at=None)
    state = client.post(f"/api/v1/games/{game.pk}/clock/step/").json()
    assert state["status"] == "PAUSED"
    assert state["stopped_by"]["kind"] == "CASH_LOW"
    assert state["pause_rules"] == {"severities": ["CRITICAL"], "deadlines": True}
    assert state["latest_notice"] == state["stopped_by"]["id"]

    feed = client.get(f"/api/v1/games/{game.pk}/feed/").json()
    assert feed["notices"][0]["kind"] == "CASH_LOW"
    assert feed["notices"][0]["drill"]["screen"] == "ledger"
    info = client.get(f"/api/v1/games/{game.pk}/feed/?severity=INFO").json()["notices"]
    assert [n["kind"] for n in info] == ["RETURN_OWED"]  # the month's return (P3.7), nothing else
    assert client.get(f"/api/v1/games/{game.pk}/feed/?before=x").status_code == 400

    rules = client.post(
        f"/api/v1/games/{game.pk}/clock/pause-rules/",
        {"severities": ["WARNING", "CRITICAL"], "deadlines": False},
        format="json",
    ).json()
    assert rules["pause_rules"] == {"severities": ["WARNING", "CRITICAL"], "deadlines": False}
    bad = client.post(
        f"/api/v1/games/{game.pk}/clock/pause-rules/", {"severities": ["SOON"]}, format="json"
    )
    assert bad.status_code == 400
