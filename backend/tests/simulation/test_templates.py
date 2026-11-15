"""P2.1 — History templates: an established bureau built once per world, copied into games.

The copy must be the same game as one built directly (equal fingerprints,
which ignore database ids), now and as play goes on; copies are independent of
each other and of the template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from apps.bureau.core.models import Customer, CustomerIdentifier, ProviderCustomerLink
from apps.bureau.submissions.models import SubmissionFile
from apps.simulation import controls
from apps.simulation.bridge import new_game, set_up_bureau, start_game
from apps.simulation.fingerprint import fingerprint
from apps.simulation.history import preload_history
from apps.simulation.lifecycle import delete_game
from apps.simulation.models import Game, HistoryTemplate
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world() -> World:
    g = build_world(73, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _built_directly(world: World, months: int) -> Game:
    game = new_game(world)
    set_up_bureau(game)
    preload_history(game, months)
    return game


def _by_id(model: Any, natural: str, game: Game) -> list[str]:
    return list(
        model.objects.filter(organization=game.organization)
        .order_by("pk")
        .values_list(natural, flat=True)
    )


def test_a_copied_history_is_the_same_game_as_one_built_directly(world: World) -> None:
    direct = _built_directly(world, 2)
    copied = start_game(world, history_months=2)
    assert Customer.objects.filter(organization=copied.organization).exists()
    assert fingerprint(copied) == fingerprint(direct)
    # Ids keep their relative order, so whatever is ordered by id (the first link
    # made for a customer, say) comes out the same.
    for model, natural in (
        (ProviderCustomerLink, "provider_customer_number"),
        (CustomerIdentifier, "identifier_value"),
        (Customer, "customer_reference"),
    ):
        assert _by_id(model, natural, copied) == _by_id(model, natural, direct)

    # And they play on identically.
    for game in (direct, copied):
        controls.advance_by(game, "day", 6)
    direct.refresh_from_db()
    copied.refresh_from_db()
    assert copied.current_tick == direct.current_tick > 0
    assert fingerprint(copied) == fingerprint(direct)


def test_the_template_is_built_once_and_copies_are_independent(world: World) -> None:
    first = start_game(world, history_months=2)
    second = start_game(world, history_months=2)
    templates = HistoryTemplate.objects.filter(world=world, months=2)
    assert templates.count() == 1
    template = templates.get()
    assert template.game.owner is None  # hidden from every player
    assert fingerprint(first) == fingerprint(second)
    assert first.organization_id != second.organization_id

    # Each copy has its own stored files, with the same bytes as the template's.
    root = Path(settings.STORAGE_ROOT)
    for game in (first, second):
        files = SubmissionFile.objects.filter(submission__organization=game.organization)
        assert files.exists()
        for stored in files:
            assert f"org_{game.organization_id}/" in stored.storage_path
            assert (root / stored.storage_path).is_file()

    # Playing or deleting one copy touches neither the other nor the template.
    before = fingerprint(second)
    controls.advance_by(first, "day", 3)
    delete_game(first)
    assert fingerprint(second) == before
    assert Customer.objects.filter(organization=template.game.organization).exists()
    for stored in SubmissionFile.objects.filter(submission__organization=second.organization):
        assert (root / stored.storage_path).is_file()
