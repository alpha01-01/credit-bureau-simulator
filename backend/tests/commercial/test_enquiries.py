"""S6 — Enquiries and demand.

Done when (roadmap S6): enquiry volume responds to coverage and price in the
expected direction; every enquiry is logged with its purpose.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import CreditAccount, Customer, Enquiry, EnquiryOutcome, IdentifierType
from apps.bureau.reports.enquiries import EnquiryError, enquire
from apps.commercial.models import Contract, Subscriber, UsageRecord
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.demand import REFERENCE_PRICE, p_enquire, update_perception
from apps.simulation.models import (
    EnquiryJudgement,
    EventStatus,
    EventType,
    Game,
    ScheduledEvent,
    SubscriberView,
)
from apps.standards.enquiry import PURPOSES
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(91, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _play(game: Game, months: int = 1) -> Game:
    for _ in range(months):
        month = controls.state(game).now.month
        while controls.state(game).now.month == month:
            game = controls.advance_by(game, "day")
    return game


def _rate(game: Game) -> float:
    views = SubscriberView.objects.filter(game=game)
    seen = sum(v.opportunities for v in views)
    return sum(v.enquiries for v in views) / seen if seen else 0.0


# --- The demand model --------------------------------------------------------------------


def test_demand_falls_with_price_and_rises_with_perceived_value() -> None:
    assert (
        p_enquire(0.6, REFERENCE_PRICE / 2)
        > p_enquire(0.6, REFERENCE_PRICE)
        > p_enquire(0.6, REFERENCE_PRICE * 2)
    )
    assert (
        p_enquire(0.9, REFERENCE_PRICE)
        > p_enquire(0.6, REFERENCE_PRICE)
        > p_enquire(0.2, REFERENCE_PRICE)
    )


def test_wrong_reports_hurt_perception_most() -> None:
    start = 0.6
    assert update_perception(start, "CORRECT_HIT") > start
    assert start > update_perception(start, "NO_HIT") > update_perception(start, "WRONG_PERSON")


# --- Volume responds to price and coverage, in play --------------------------------------


def test_higher_prices_mean_fewer_enquiries(world: World) -> None:
    normal = start_game(world)
    dear = start_game(world)
    Contract.objects.filter(subscriber__organization=dear.organization).update(
        unit_price=REFERENCE_PRICE * 3
    )
    normal, dear = _play(normal), _play(dear)
    assert _rate(normal) > _rate(dear) + 0.3
    # The opportunities are the same world applications: only the decision differs.
    assert sum(v.opportunities for v in SubscriberView.objects.filter(game=normal)) == sum(
        v.opportunities for v in SubscriberView.objects.filter(game=dear)
    )


def test_a_bureau_without_data_loses_demand(world: World) -> None:
    loaded = start_game(world)
    empty = start_game(world)
    empty.organization.institutions.update(is_active=False)  # no provider ever reports
    loaded, empty = _play(loaded, 2), _play(empty, 2)

    empty_views = SubscriberView.objects.filter(game=empty)
    loaded_views = SubscriberView.objects.filter(game=loaded)
    assert sum(v.hits for v in empty_views) == 0
    assert sum(v.hits for v in loaded_views) > 0
    for code in ("ATB", "MRB", "UNS"):
        assert (
            empty_views.get(subscriber_code=code).perceived_value
            < loaded_views.get(subscriber_code=code).perceived_value
        )
    assert _rate(empty) < _rate(loaded)


# --- Every enquiry is logged, billed and judged --------------------------------------------


def test_every_enquiry_is_logged_with_purpose_consent_usage_and_judgement(world: World) -> None:
    game = _play(start_game(world))
    enquiries = Enquiry.objects.filter(organization=game.organization)
    assert enquiries.exists()
    for e in enquiries:
        assert e.purpose in PURPOSES
        assert e.consent_reference
        usage = UsageRecord.objects.get(enquiry=e)
        assert usage.unit_price == REFERENCE_PRICE and usage.quantity == 1
        judgement = EnquiryJudgement.objects.get(enquiry=e)
        assert judgement.hit == (e.outcome == EnquiryOutcome.HIT)
    # Every application to a subscribing lender that has happened was an opportunity.
    happened = ScheduledEvent.objects.filter(
        game=game, event_type=EventType.CREDIT_APPLICATION, status=EventStatus.DONE
    ).count()
    assert happened > 0
    assert sum(v.opportunities for v in SubscriberView.objects.filter(game=game)) == happened


def test_a_hit_returns_a_report_of_what_the_bureau_holds(world: World) -> None:
    game = _play(start_game(world))
    hit = (
        Enquiry.objects.filter(organization=game.organization, outcome=EnquiryOutcome.HIT)
        .order_by("enquiry_reference")
        .first()
    )
    assert hit is not None and hit.customer is not None
    report = hit.report
    held = CreditAccount.objects.filter(customer=hit.customer).count()
    assert report["summary"]["accounts"] == held == len(report["accounts"]) == hit.accounts_reported
    assert report["subject"]["reference"] == hit.customer.customer_reference
    assert all(a["account"].startswith("*") for a in report["accounts"])  # account numbers masked


def test_enquiries_need_a_permissible_purpose_and_consent(world: World) -> None:
    game = start_game(world)
    subscriber = Subscriber.objects.get(organization=game.organization, subscriber_code="ATB")
    at = datetime(2027, 1, 4, 9, tzinfo=UTC)
    args = (IdentifierType.GHANA_CARD, "GHA-000000000-0", "Nobody", at)
    with pytest.raises(EnquiryError):
        enquire(game.organization, subscriber, "CONSUMER_REPORT", "MARKETING", "C1", *args)
    with pytest.raises(EnquiryError):
        enquire(game.organization, subscriber, "CONSUMER_REPORT", "NEW_CREDIT", "", *args)
    miss = enquire(game.organization, subscriber, "CONSUMER_REPORT", "NEW_CREDIT", "C1", *args)
    assert miss.outcome == EnquiryOutcome.NO_HIT and miss.report == {}
    assert not Customer.objects.filter(organization=game.organization).exists()


def test_enquiry_api(world: World) -> None:
    owner = User.objects.create_user("ceo")
    game = _play(start_game(world, owner=owner))
    client = APIClient()
    client.force_authenticate(owner)
    listing = client.get(f"/api/v1/games/{game.pk}/enquiries/").json()
    assert listing
    reference = listing[0]["reference"]
    detail = client.get(f"/api/v1/games/{game.pk}/enquiries/{reference}/").json()
    assert detail["reference"] == reference
    assert "correct" not in str(listing)  # the judgement stays hidden
    assert Decimal(str(REFERENCE_PRICE)) > 0
