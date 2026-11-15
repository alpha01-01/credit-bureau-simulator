"""P2.8 — The flywheel turns.

Done when (Document 08): with the same seed, a high-quality bureau's subscribers
end the year with measurably lower default rates and higher renewal than a
careless bureau's.

Two bureaus play a year in one world. The careful one has its providers' data;
the careless one lets none of it in (every provider's files go unprocessed), the
far end of carelessness. Lenders act on what the reports show; the shared world
is not changed (owner's decision: outcomes only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commercial.models import Contract, Subscriber
from apps.simulation import controls, lending
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import fingerprint
from apps.simulation.lending import serious_arrears
from apps.simulation.models import DataQualityReview, Game, LendingDecision, Notice
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


def _year(world: World, careful: bool, owner: Any = None) -> Game:
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    if careful:
        game = controls.set_matching_tooling(game, "ADVANCED")
    else:
        game.organization.institutions.update(is_active=False)  # no provider data comes in
    for _ in range(12):
        month = controls.state(game).now.month
        while controls.state(game).now.month == month:
            game = controls.advance_by(game, "next_event")
    return game


def _rates(game: Game) -> tuple[float, float]:
    as_of = controls.state(game).now.date()
    books = lending.books(game, as_of)
    lent = sum(b.lent for b in books)
    return (sum(b.fell_behind for b in books) / lent, sum(b.defaulted for b in books) / lent)


def test_a_careful_bureaus_lenders_lend_better_and_stay(world: World) -> None:
    careful = _year(world, careful=True)
    careless = _year(world, careful=False)

    # The same applications came to both bureaus' lenders.
    assert (
        LendingDecision.objects.filter(game=careful).count()
        == LendingDecision.objects.filter(game=careless).count()
        > 500
    )
    # The careful bureau's reports stopped applicants; the careless one's could not.
    declined = LendingDecision.objects.filter(game=careful, flagged=True)
    assert declined.count() > 50
    assert not LendingDecision.objects.filter(game=careless, flagged=True).exists()

    # Its lenders' books are better on both measures.
    careful_behind, careful_default = _rates(careful)
    careless_behind, careless_default = _rates(careless)
    assert careful_behind < careless_behind
    assert careful_default < careless_default

    # And at the year's end they renew; the careless bureau's lenders leave.
    renewed = Notice.objects.filter(game=careful, kind="CONTRACT_RENEWED").count()
    lost = Notice.objects.filter(game=careless, kind="CONTRACT_LOST").count()
    assert renewed == 3 and lost >= 2
    gone = Subscriber.objects.filter(organization=careless.organization, is_active=False)
    assert gone.count() == lost
    for subscriber in gone:
        ended = Contract.objects.get(subscriber=subscriber)
        assert ended.end_date is not None
    stayed = Subscriber.objects.filter(organization=careful.organization)
    assert all(Contract.objects.filter(subscriber=s).count() == 2 for s in stayed)

    # The year-end review shows the books.
    review = DataQualityReview.objects.filter(game=careful).order_by("-period").first()
    assert review is not None
    assert {b["subscriber"] for b in review.figures["lending"]} == {"ATB", "MRB", "UNS"}
    assert review.figures["reputation"]["subscribers"]["score"] > 0


def test_what_lenders_decline_on() -> None:
    assert serious_arrears({"accounts": [{"days_past_due": 30, "status": "A"}]})
    assert serious_arrears({"accounts": [{"days_past_due": 0, "status": "W"}]})
    assert serious_arrears(
        {"accounts": [{"days_past_due": 0, "status": "A", "worst_days_past_due_12m": 120}]}
    )
    assert not serious_arrears(
        {"accounts": [{"days_past_due": 15, "status": "A", "worst_days_past_due_12m": 60}]}
    )
    assert not serious_arrears({})


def test_reputation_and_contracts_are_shown_and_replay(world: World) -> None:
    owner = User.objects.create_user("player")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    game = controls.advance_by(game, "day", 10)
    client = APIClient()
    client.force_authenticate(owner)
    market = client.get(f"/api/v1/games/{game.pk}/market/").json()
    assert set(market["reputation"]) >= {"subscribers", "providers", "regulator"}
    assert all(
        0 <= market["reputation"][a]["score"] <= 100
        for a in ("subscribers", "providers", "regulator")
    )
    assert {s["code"] for s in market["subscribers"]} == {"ATB", "MRB", "UNS"}
    assert all(s["active"] and s["renews_on"] for s in market["subscribers"])

    copy = controls.replay(game, start_game(world))
    assert fingerprint(copy) == fingerprint(game)
