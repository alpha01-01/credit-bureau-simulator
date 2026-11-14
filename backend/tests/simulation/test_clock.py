"""S4 — Clock and tick engine.

Done when (roadmap S4): a replay test runs a month twice from the same seed
and action log and produces identical database state (compared by checksums
of ordered table contents).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from hypothesis import given, settings
from hypothesis import strategies as st
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import AccountObservation, Customer
from apps.bureau.submissions.models import ProcessingRun, Submission
from apps.org.models import Organization
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY, Calendar
from apps.simulation.engine import ClockError, advance, next_event_tick, run_tick
from apps.simulation.fingerprint import fingerprint
from apps.simulation.lifecycle import delete_game, delete_world_with_games
from apps.simulation.models import (
    EventStatus,
    EventType,
    Game,
    GameStatus,
    ScheduledEvent,
    TickLog,
)
from apps.standards.calendar import easter_sunday, is_working_day, public_holidays
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    generated = build_world(61, "tiny")
    world_id = write_world(
        generated.config,
        generated.people,
        generated.businesses,
        generated.branches,
        generated.result,
        generated.stats,
    )
    return World.objects.get(pk=world_id)


def _play_month(game: Game) -> Game:
    """A player's month: a few hours, a speed and policy change, pause/resume, then skip event
    to event."""
    game = controls.advance_by(game, "hour", 3)
    game = controls.set_speed(game, 4)
    game = controls.set_rejection_policy(game, "CORE")
    game = controls.resume(game)
    game = controls.pause(game)
    start_month = controls.state(game).now.month
    while controls.state(game).now.month == start_month:
        game = controls.advance_by(game, "next_event")
    return controls.advance_by(game, "day")


# --- Calendar ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "easter"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2027, date(2027, 3, 28))],
)
def test_easter(year: int, easter: date) -> None:
    assert easter_sunday(year) == easter


def test_ghana_public_holidays_2027() -> None:
    holidays = public_holidays(2027)
    expected = {
        date(2027, 1, 1): "New Year's Day",
        date(2027, 1, 7): "Constitution Day",
        date(2027, 3, 8): "Independence Day",  # 6 March is a Saturday
        date(2027, 3, 26): "Good Friday",
        date(2027, 3, 29): "Easter Monday",
        date(2027, 5, 3): "May Day",  # 1 May is a Saturday
        date(2027, 12, 3): "Farmers' Day",  # first Friday in December
        date(2027, 12, 27): "Christmas Day",  # Saturday, observed Monday
        date(2027, 12, 28): "Boxing Day",  # Sunday, observed Tuesday
    }
    for day, name in expected.items():
        assert holidays[day] == name
    assert all(day.weekday() < 5 for day in holidays)
    assert not is_working_day(date(2027, 1, 7))
    assert is_working_day(date(2027, 1, 8))


def test_ticks_cover_working_hours_only() -> None:
    cal = Calendar(date(2027, 1, 1))
    assert cal.tick_start(1) == datetime(2027, 1, 4, 8, 0, tzinfo=UTC)  # Fri 1st holiday, weekend
    assert cal.tick_start(TICKS_PER_DAY) == datetime(2027, 1, 4, 16, 45, tzinfo=UTC)
    assert cal.tick_end(TICKS_PER_DAY) == datetime(2027, 1, 4, 17, 0, tzinfo=UTC)
    assert cal.tick_start(TICKS_PER_DAY + 1) == datetime(2027, 1, 5, 8, 0, tzinfo=UTC)
    # Wednesday 6th, then Thursday 7th (Constitution Day) is skipped.
    assert cal.tick_start(3 * TICKS_PER_DAY + 1) == datetime(2027, 1, 8, 8, 0, tzinfo=UTC)
    # Outside working hours, the next tick is the next working morning.
    assert cal.tick_at(datetime(2027, 1, 4, 17, 30, tzinfo=UTC)) == TICKS_PER_DAY + 1
    assert cal.tick_at(datetime(2027, 1, 9, 10, 0, tzinfo=UTC)) == cal.tick_at(
        datetime(2027, 1, 11, 8, 0, tzinfo=UTC)
    )
    assert cal.is_first_tick_of_month(1)
    assert not cal.is_first_tick_of_month(2)


@given(st.integers(min_value=1, max_value=20_000))
@settings(max_examples=200)
def test_tick_at_inverts_tick_start(tick: int) -> None:
    cal = Calendar(date(2027, 1, 1))
    assert cal.tick_at(cal.tick_start(tick)) == tick


# --- Ticks ---------------------------------------------------------------------------


def test_ticks_are_idempotent_and_in_order(world: World) -> None:
    game = start_game(world)
    assert run_tick(game.pk, 1) is True
    assert run_tick(game.pk, 1) is False  # already done: nothing happens
    assert TickLog.objects.filter(game=game).count() == 1
    with pytest.raises(ClockError):
        run_tick(game.pk, 3)


def test_files_arrive_on_their_day_and_are_processed_overnight(world: World) -> None:
    game = _play_month(start_game(world))
    arrivals = ScheduledEvent.objects.filter(
        game=game, event_type=EventType.PROVIDER_FILES_ARRIVE, status=EventStatus.DONE
    )
    assert arrivals.exists()
    cal = Calendar(game.clock_start)
    for event in arrivals:
        submission = Submission.objects.get(
            organization=game.organization,
            institution__institution_code=event.payload["lender"],
            reporting_period=event.payload["period"],
        )
        arrival = datetime.fromisoformat(event.payload["arrival"])
        assert submission.received_at == arrival
        assert event.processed_tick == cal.tick_at(arrival)
        run = ProcessingRun.objects.get(submission=submission)
        # Processed in the overnight batch at the end of the arrival day.
        assert run.started_at == datetime.combine(arrival.date(), datetime.min.time(), UTC).replace(
            hour=17
        )
        assert run.reconciles
    assert AccountObservation.objects.filter(
        credit_account__organization=game.organization
    ).exists()


def test_the_world_lives_through_each_month_of_play(world: World) -> None:
    # Each month of play, the world lives through that month at its start (hidden until
    # providers report it the following month).
    game = _play_month(start_game(world))  # January, then into February
    advanced = ScheduledEvent.objects.filter(game=game, event_type=EventType.WORLD_ADVANCED)
    assert sorted(e.payload["period"] for e in advanced) == ["2027-01-31", "2027-02-28"]
    world.refresh_from_db()
    assert world.history_end == date(2027, 2, 28)

    # February: providers report January, on top of the December data loaded in January.
    game = _play_month(game)
    dates = set(
        AccountObservation.objects.filter(
            credit_account__organization=game.organization
        ).values_list("reporting_date", flat=True)
    )
    assert {date(2026, 12, 31), date(2027, 1, 31)} <= dates


def test_next_event_includes_the_first_tick(world: World) -> None:
    game = start_game(world)
    assert next_event_tick(game) == 1


# --- Replay ----------------------------------------------------------------------------


def test_replaying_the_action_log_reproduces_the_game_exactly(world: World) -> None:
    original = _play_month(start_game(world))
    assert Customer.objects.filter(organization=original.organization).exists()

    copy = controls.replay(original, start_game(world))

    assert copy.current_tick == original.current_tick
    assert fingerprint(copy) == fingerprint(original)


def test_fingerprint_notices_a_difference(world: World) -> None:
    one = controls.advance_by(start_game(world), "day", 3)
    two = controls.advance_by(start_game(world), "day", 2)
    assert fingerprint(one) != fingerprint(two)


# --- API --------------------------------------------------------------------------------


def test_clock_api(world: World) -> None:
    owner = User.objects.create_user("player")
    game = start_game(world, owner=owner)
    client = APIClient()

    assert client.get(f"/api/v1/games/{game.pk}/clock/").status_code == 403

    client.force_authenticate(owner)
    state = client.get(f"/api/v1/games/{game.pk}/clock/").json()
    assert (state["tick"], state["date"], state["time"]) == (0, "2027-01-04", "08:00")

    state = client.post(
        f"/api/v1/games/{game.pk}/clock/advance/", {"unit": "hour", "count": 2}, format="json"
    ).json()
    assert (state["tick"], state["time"]) == (8, "10:00")

    state = client.post(f"/api/v1/games/{game.pk}/clock/speed/", {"speed": 8}, format="json").json()
    assert state["speed"] == 8
    bad = client.post(f"/api/v1/games/{game.pk}/clock/speed/", {"speed": 3}, format="json")
    assert bad.status_code == 400
    assert client.post(f"/api/v1/games/{game.pk}/clock/resume/").json()["status"] == "RUNNING"
    assert client.post(f"/api/v1/games/{game.pk}/clock/pause/").json()["status"] == "PAUSED"

    other = User.objects.create_user("someone-else")
    client.force_authenticate(other)
    assert client.get(f"/api/v1/games/{game.pk}/clock/").status_code == 404


def test_rejection_policy_api(world: World) -> None:
    owner = User.objects.create_user("player")
    game = start_game(world, owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/rejection-policy/"

    current = client.get(url).json()
    assert current["policy"] == "STANDARD"
    assert {o["code"] for o in current["options"]} == {"STANDARD", "CORE"}
    assert client.post(url, {"policy": "CORE"}, format="json").json()["policy"] == "CORE"
    assert client.post(url, {"policy": "LAX"}, format="json").status_code == 400
    game.organization.refresh_from_db()
    assert game.organization.rejection_policy == "CORE"
    assert game.actions.filter(action_type="SET_REJECTION_POLICY").count() == 1


def test_clock_worker_advances_running_games_only(world: World) -> None:
    running = start_game(world)
    paused = start_game(world)
    controls.set_speed(running, 8)
    controls.resume(running)
    call_command("run_clock", max_ticks=2)
    running.refresh_from_db()
    paused.refresh_from_db()
    assert running.current_tick == 2
    assert paused.current_tick == 0
    assert running.status == GameStatus.RUNNING


# --- Deletion ---------------------------------------------------------------------------


def test_deleting_a_game_removes_its_bureau(
    world: World, tmp_path: Path, django_capture_on_commit_callbacks: Any
) -> None:
    game = _play_month(start_game(world))
    keep = controls.advance_by(start_game(world), "day", 5)
    folder = tmp_path / "bureau" / f"org_{game.organization_id}"
    assert folder.exists()

    with django_capture_on_commit_callbacks(execute=True):
        delete_game(game)

    assert not Game.objects.filter(pk=game.pk).exists()
    assert not Organization.objects.filter(pk=game.organization_id).exists()
    assert not Customer.objects.filter(organization_id=game.organization_id).exists()
    assert not folder.exists()
    assert Customer.objects.filter(organization=keep.organization).exists()


def test_deleting_a_world_with_games(world: World) -> None:
    controls.advance_by(start_game(world), "day", 5)
    delete_world_with_games(world.pk)
    assert not World.objects.filter(pk=world.pk).exists()
    assert not Game.objects.exists()


def test_batched_quiet_ticks_equal_running_every_tick(world: World) -> None:
    batched = start_game(world)
    single = start_game(world)
    ticks = 6 * TICKS_PER_DAY  # the first week: month start, arrivals, overnight batches
    controls_free = advance(batched, ticks)
    for tick in range(1, ticks + 1):
        run_tick(single.pk, tick)
    single.refresh_from_db()
    assert fingerprint(controls_free) == fingerprint(single)
