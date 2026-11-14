"""An established bureau: pre-loaded history (Established scenario)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from apps.bureau.core.models import AccountObservation, Customer
from apps.bureau.submissions.models import RecordStatus, StagingRecord, Submission
from apps.dbcopy import copy_insert
from apps.org.models import Organization
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import fingerprint
from apps.simulation.history import history_periods
from apps.simulation.models import Game, SubscriberView
from apps.workitems.models import ItemStatus, ResolvedBy, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(101, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def test_history_covers_the_months_before_play_except_the_last(world: World) -> None:
    game = start_game(world)
    # The last generated month (December) arrives in January, during play.
    assert history_periods(game, 3) == [date(2026, 9, 30), date(2026, 10, 31), date(2026, 11, 30)]
    # Never earlier than the world's stored history.
    assert history_periods(game, 99)[0] == world.history_start


def test_an_established_bureau_starts_with_its_past_loaded_and_settled(world: World) -> None:
    game = start_game(world, history_months=3)
    org = game.organization
    periods = set(
        AccountObservation.objects.filter(credit_account__organization=org).values_list(
            "reporting_date", flat=True
        )
    )
    assert periods == {date(2026, 9, 30), date(2026, 10, 31), date(2026, 11, 30)}
    assert Submission.objects.filter(organization=org).count() == 3 * 5
    # The former team left an empty queue; every past case has a recorded decision.
    assert not WorkItem.objects.filter(organization=org).exclude(status=ItemStatus.DONE).exists()
    assert not StagingRecord.objects.filter(
        run__submission__organization=org, record_status=RecordStatus.PENDING_REVIEW
    ).exists()
    past = WorkItem.objects.filter(organization=org)
    assert past.exists()
    assert all(i.resolved_by == ResolvedBy.HISTORIC and i.explanation for i in past)
    assert game.current_tick == 0  # history is the past: the clock has not started


def test_history_makes_the_bureau_useful_from_day_one(world: World) -> None:
    def january_hits(months: int) -> int:
        game = start_game(world, history_months=months)
        while controls.state(game).now.month == 1:
            game = controls.advance_by(game, "day")
        return sum(v.hits for v in SubscriberView.objects.filter(game=game))

    assert january_hits(3) > january_hits(0)


def test_an_established_game_replays_exactly(world: World) -> None:
    original: Game = controls.advance_by(start_game(world, history_months=2), "day", 3)
    copy = controls.replay(original, start_game(world, history_months=2))
    assert Customer.objects.filter(organization=copy.organization).exists()
    assert fingerprint(copy) == fingerprint(original)


def test_copy_insert_behaves_like_bulk_create(db: None) -> None:
    rows = copy_insert(
        [Organization(name=f"Bureau {i}", organization_code=f"B{i}") for i in range(3)]
    )
    assert all(r.pk for r in rows)
    stored = Organization.objects.filter(pk__in=[r.pk for r in rows]).order_by("pk")
    assert [o.name for o in stored] == ["Bureau 0", "Bureau 1", "Bureau 2"]
    assert all(o.created_at is not None and o.public_id for o in stored)
    assert len({o.public_id for o in stored}) == 3
