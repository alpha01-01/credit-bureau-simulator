"""P2.1 — Month-end and on-demand checkpoints (Document 07, Section 12.3).

A checkpoint plus the action log reproduces the game at that point: replaying
the actions taken before it, on a fresh game, reaches the same state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command

from apps.bureau.core.models import AccountObservation
from apps.bureau.submissions.models import StagingRecord
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.checkpoints import digest, summarise
from apps.simulation.engine import calendar
from apps.simulation.lifecycle import delete_game
from apps.simulation.models import Checkpoint, CheckpointKind, Game
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


def _into_next_month(game: Game) -> Game:
    start_month = controls.state(game).now.month
    while controls.state(game).now.month == start_month:
        game = controls.advance_by(game, "next_event")
    return game


def test_a_checkpoint_is_taken_at_each_month_end(world: World) -> None:
    game = _into_next_month(start_game(world))
    game = _into_next_month(game)

    month_ends = list(game.checkpoints.filter(kind=CheckpointKind.MONTH_END).order_by("tick"))
    cal = calendar(game)
    assert [cp.sim_time.strftime("%Y-%m") for cp in month_ends] == ["2027-01", "2027-02"]
    for cp in month_ends:
        assert cal.is_last_tick_of_month(cp.tick)
        assert cp.digest == digest(cp.summary)
    # The summary covers the bureau's data, not just the clock.
    first = month_ends[0].summary
    assert first["counts"]["bureau_submissions_submission"] > 0
    assert first["counts"]["bureau_core_accountobservation"] > 0
    assert first["totals"]["balances_on_file"] != "0"
    # Staging records are counted from their runs; the runs' counts are the rows (P3.0).
    staged = StagingRecord.objects.filter(run__submission__organization=game.organization)
    assert summarise(game)["totals"]["staging_records"] == str(staged.count()) != "0"
    # Later months hold more.
    later = month_ends[1].summary["counts"]["bureau_core_accountobservation"]
    assert later > first["counts"]["bureau_core_accountobservation"]


def test_a_checkpoint_and_the_action_log_reproduce_the_game_there(world: World) -> None:
    original = start_game(world)
    original = controls.advance_by(original, "hour", 3)
    original = controls.set_rejection_policy(original, "CORE")
    original = controls.advance_by(original, "day", 2)
    actions_before = original.actions.count()
    on_demand = controls.checkpoint(original, "after two days")
    assert on_demand.kind == CheckpointKind.ON_DEMAND
    assert original.actions.count() == actions_before  # taking one is not an action
    original = controls.set_speed(original, 4)
    original = _into_next_month(original)  # passes the month-end
    original = controls.set_rejection_policy(original, "STANDARD")  # after it: not replayed
    original = controls.advance_by(original, "day", 2)
    month_end = original.checkpoints.get(kind=CheckpointKind.MONTH_END)

    for cp in (on_demand, month_end):
        copy = controls.replay_to(cp, start_game(world))
        assert copy.current_tick == cp.tick
        assert summarise(copy) == cp.summary, cp
    # The month-end replay stopped there, with the policy then in force.
    copy.organization.refresh_from_db()
    assert copy.organization.rejection_policy == "CORE"


def test_the_summary_notices_a_difference(world: World) -> None:
    game = controls.advance_by(start_game(world), "day", 8)
    before = summarise(game)
    AccountObservation.objects.filter(
        credit_account__organization=game.organization, is_current=True
    ).order_by("pk").first().delete()  # type: ignore[union-attr]
    after = summarise(game)
    assert after != before
    assert digest(after) != digest(before)


def test_checkpoints_belong_to_their_game(world: World, capsys: Any) -> None:
    game = controls.advance_by(start_game(world), "day", 1)
    call_command("checkpoint", "--game", str(game.pk), "--take", "bug report")
    call_command("checkpoint", "--game", str(game.pk))
    assert "bug report" in capsys.readouterr().out

    delete_game(game)
    assert not Checkpoint.objects.filter(game_id=game.pk).exists()
