"""P2.6 — Providers respond.

Done when (Document 08): a provider given good feedback and training sends
measurably cleaner files over three months; one penalised repeatedly becomes
slower to respond.

Three games share one world. In the first, ATB is trained and sent feedback on
every submission; in the second it is left alone; in the third it is penalised
every month. Each game's ATB files are a variant of the world's own, so one
game's provider improving does not change another's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.submissions.models import FeedbackReport, Submission
from apps.finance.models import JournalEntry
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import Delivery, Game, ProviderRelationship
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import FileDefect, World

PROVIDER = "ATB"
MONTHS = 4  # January's files are as usual; three months to respond


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _play(world: World, treatment: str, owner: Any = None) -> Game:
    """Four months in which the bureau treats ATB one way, every month."""
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    # The first hour: January's files are already on their way, as usual.
    game = controls.advance_by(game, "hour")
    month = controls.state(game).now.month
    for _ in range(MONTHS):
        if treatment == "nurture":
            controls.train_provider(game, PROVIDER)
        elif treatment == "penalise":
            controls.penalise_provider(game, PROVIDER)
        while controls.state(game).now.month == month:
            game = controls.advance_by(game, "next_event")
            if treatment == "nurture":
                for sub in Submission.objects.filter(
                    organization=game.organization,
                    institution__institution_code=PROVIDER,
                    feedback_reports__isnull=True,
                    runs__isnull=False,
                ).distinct():
                    controls.send_feedback(game, sub.submission_reference)
        month = controls.state(game).now.month
    return game


def _defect_rates(game: Game) -> list[float]:
    """Row defects per data row in ATB's credit files, month by month."""
    rates = []
    deliveries = (
        Delivery.objects.filter(game=game, world_file__kind="CONC")
        .filter(world_submission__lender__code=PROVIDER)
        .select_related("world_file", "world_submission")
        .order_by("world_submission__period")
    )
    for d in deliveries:
        rows = d.world_file.row_count
        defects = FileDefect.objects.filter(file=d.world_file, row_number__isnull=False).count()
        rates.append(defects / rows)
    return rates


def _days_late(game: Game) -> list[int]:
    return [
        (s.received_at.date() - s.due_date).days
        for s in Submission.objects.filter(
            organization=game.organization, institution__institution_code=PROVIDER
        ).order_by("reporting_period")
    ]


@pytest.mark.slow
def test_feedback_and_training_make_cleaner_files_and_penalties_slower_ones(world: World) -> None:
    nurtured = _play(world, "nurture")
    left = _play(world, "none")
    penalised = _play(world, "penalise")

    # Nurtured: the provider's data improves step by step, and its files show it.
    rel = ProviderRelationship.objects.get(game=nurtured, provider_code=PROVIDER)
    assert [h["quality"] for h in rel.history][:MONTHS] == sorted(
        h["quality"] for h in rel.history[:MONTHS]
    )
    assert rel.quality >= 3
    cleaner, usual = _defect_rates(nurtured), _defect_rates(left)
    assert len(cleaner) == len(usual) == MONTHS
    assert cleaner[0] == pytest.approx(usual[0])  # January's files: nothing done yet
    assert cleaner[-1] < 0.6 * usual[-1]
    assert sum(cleaner[1:]) < sum(usual[1:])

    # Left alone: nothing changes.
    alone = ProviderRelationship.objects.get(game=left, provider_code=PROVIDER)
    assert alone.quality == 0 and alone.goodwill == pytest.approx(0.7)

    # Penalised every month: goodwill sinks and the files come later and later.
    sour = ProviderRelationship.objects.get(game=penalised, provider_code=PROVIDER)
    assert sour.goodwill < 0.3
    slow, normal = _days_late(penalised), _days_late(left)
    assert slow[0] == normal[0]
    assert slow[-1] >= normal[-1] + 10
    assert slow == sorted(slow) or slow[-1] > slow[1]

    # Another provider in the same games is untouched.
    other = Delivery.objects.filter(game=nurtured, world_submission__lender__code="MRB")
    assert all(d.world_submission.variant == "" for d in other)


def test_training_costs_money_once_a_month(world: World) -> None:
    game = start_game(world)
    controls.train_provider(game, PROVIDER)
    with pytest.raises(ClockError):
        controls.train_provider(game, PROVIDER)
    with pytest.raises(ClockError):
        controls.penalise_provider(game, "NOPE")
    cost = JournalEntry.objects.get(organization=game.organization, source_type="PROVIDER_TRAINING")
    assert PROVIDER in cost.description


@pytest.mark.slow
def test_providers_screen_and_replay(world: World) -> None:
    owner = User.objects.create_user("player")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/providers/"
    assert (
        client.post(url, {"action": "penalise", "provider": PROVIDER}, format="json").status_code
        == 200
    )
    assert (
        client.post(url, {"action": "penalise", "provider": PROVIDER}, format="json").status_code
        == 200
    )
    assert (
        client.post(url, {"action": "train", "provider": PROVIDER}, format="json").status_code
        == 200
    )
    assert (
        client.post(url, {"action": "bribe", "provider": PROVIDER}, format="json").status_code
        == 400
    )
    while controls.state(game).now.month < 3:
        game = controls.advance_by(game, "next_event")
    screen = client.get(url).json()
    atb = next(p for p in screen["providers"] if p["code"] == PROVIDER)
    assert atb["cooperation"] in ("lukewarm", "strained")  # two penalties outweigh a session
    assert "goodwill" not in atb and "quality" not in atb  # the provider's mind stays hidden
    assert atb["recent"] and {"days_late", "unloadable", "feedback_sent"} <= set(atb["recent"][0])
    assert FeedbackReport.objects.count() == 0

    copy = controls.replay(game, start_game(world))
    assert fingerprint(copy) == fingerprint(game)
