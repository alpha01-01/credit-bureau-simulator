"""P3.9 — Sales (Playable) and cross-department workflows.

Done when (Document 09): a new subscriber passes through every department's step with a
hand-off at each; a step left undone holds up the next, visibly; terms negotiated in
the deal show up in billing.
"""

from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commercial.models import Contract, Subscriber, UsageRecord
from apps.finance.events import SERVICE_CREDIT_RATE
from apps.finance.models import Invoice
from apps.simulation import controls, it, onboarding, roles, sales
from apps.simulation.bridge import start_game
from apps.simulation.compliance import add_working_days
from apps.simulation.demand import REFERENCE_PRICE
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, Notice, Onboarding, Proposal, Sanction
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _game(world: World, owner: User | None = None) -> Game:
    return controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _until(game: Game, day: date) -> Game:
    while _today(game) < day:
        game = controls.advance_by(game, "next_event")
    return game


def _days(game: Game, n: int) -> Game:
    return controls.advance_by(Game.objects.get(pk=game.pk), "day", n)


def _board(client: APIClient, game: Game) -> dict[str, Any]:
    found = client.get(f"/api/v1/games/{game.pk}/onboarding/").json()
    return dict(found["onboardings"][0])


def _steps(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["department"]: s for s in board["steps"]}


def _always(monkeypatch: Any, accept: bool) -> None:
    """Lenders answer one way, whatever the terms: the tests are about what follows."""
    p = 1.0 if accept else 0.0
    monkeypatch.setattr(sales, "MIN_P", p)
    monkeypatch.setattr(sales, "MAX_P", p)


def test_a_subscriber_passes_through_every_department_on_its_terms(
    world: World, monkeypatch: Any
) -> None:
    _always(monkeypatch, accept=True)
    monkeypatch.setattr(onboarding, "CONCERN_MISSING", 0)  # the staff pass the check up
    owner = User.objects.create_user("head")
    game = working_as(_game(world, owner), roles.SALES)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/sales/"
    lender = sales.prospects(game)[0].code

    # Research, then a meeting: the lender's needs, then what it would pay.
    assert client.post(url, {"action": "meet", "lender": lender}).status_code == 400
    assert client.post(url, {"action": "research", "lender": lender}).status_code == 200
    game = _days(game, sales.RESEARCH_DAYS + 1)
    shown = next(p for p in client.get(url).json()["prospects"] if p["code"] == lender)
    wants = sales.needs(game, lender)
    assert shown["research"]["findings"]["priority"] == wants["priority"]
    assert shown["research"]["findings"]["volume"] > 0
    assert client.post(url, {"action": "meet", "lender": lender}).status_code == 200
    game = _days(game, sales.MEETING_DAYS + 1)
    shown = next(p for p in client.get(url).json()["prospects"] if p["code"] == lender)
    assert shown["research"]["meeting"]["price"] and shown["research"]["met_recently"]
    assert Notice.objects.filter(game=game, kind="LENDER_MET").exists()

    # A deal off the price list: two years, premium service, a minimum and a discount.
    price = Decimal("14.00")
    terms = {
        "lender": lender, "price": str(price), "term_months": 24, "service_level": "PREMIUM",
        "monthly_minimum": "500000", "discount_threshold": 0, "discount_rate": "0.10",
    }  # fmt: skip
    assert client.post(url, terms, format="json").status_code == 200
    game = _days(game, sales.ANSWER_DAYS + 1)
    proposal = Proposal.objects.get(game=game, lender_code=lender)
    assert proposal.status == "ACCEPTED"

    # Sales has handed over; the Compliance check found a concern and waits for its head.
    board = _board(client, game)
    steps = _steps(board)
    assert steps["SALES"]["status"] == "DONE" and steps["SALES"]["done_by"] == "Sales"
    assert steps["COMPLIANCE"]["status"] == "ESCALATED" and steps["COMPLIANCE"]["held"]
    assert steps["COMPLIANCE"]["evidence"]["sample"] == onboarding.CONSENT_SAMPLE
    assert Notice.objects.filter(game=game, kind="ONBOARDING_CHECK").exists()
    # Left undone, it holds up IT, and so everything after: visibly, and for days.
    game = _days(game, 5)
    board = _board(client, game)
    steps = _steps(board)
    assert board["at"] == "COMPLIANCE" and steps["COMPLIANCE"]["waited"] >= 5
    assert steps["IT"]["status"] == "WAITING" and steps["IT"]["waiting_for"] == "COMPLIANCE"
    assert not Subscriber.objects.filter(organization=game.organization, subscriber_code=lender)
    number = board["number"]
    decide = {"action": "decide", "number": number, "decision": onboarding.WARN}
    onboard_url = f"/api/v1/games/{game.pk}/onboarding/"
    assert client.post(onboard_url, decide).status_code == 403  # not the Head of Sales's call
    game = working_as(Game.objects.get(pk=game.pk), roles.COMPLIANCE)
    assert client.post(onboard_url, decide).status_code == 200
    assert Sanction.objects.filter(game=game, subscriber_code=lender, kind="WARNING").exists()

    # IT connects it in five working days on which the systems are up.
    game = _days(game, 2)
    assert _steps(_board(client, game))["IT"]["progress"] >= 1
    it.start_outage(game, game.current_tick + 1, "Test outage.", lambda *a: None)
    game = _days(game, 1)
    held = _steps(_board(client, game))["IT"]
    assert held["held"] == "The systems are down"
    progress = held["progress"]
    game = _days(game, 1)
    assert _steps(_board(client, game))["IT"]["progress"] == progress  # nothing done while down
    o = Onboarding.objects.get(game=game, number=number)
    while o.live_on is None:
        game = _days(game, 1)
        o.refresh_from_db()
    subscriber = Subscriber.objects.get(organization=game.organization, subscriber_code=lender)
    assert subscriber.is_active and not subscriber.billing_ready
    contract = Contract.objects.filter(
        subscriber=subscriber, product__product_code=sales.PRODUCT
    ).latest("start_date", "pk")
    assert (contract.unit_price, contract.term_months, contract.service_level) == (
        price, 24, "PREMIUM",
    )  # fmt: skip
    assert contract.monthly_minimum == Decimal("500000") and contract.discount_rate == Decimal(
        "0.1"
    )
    assert Notice.objects.filter(game=game, kind="SUBSCRIBER_LIVE").exists()

    # Finance must check the terms. Until it does, the subscriber's use is not billed.
    board = _board(client, game)
    assert board["at"] == "FINANCE" and _steps(board)["FINANCE"]["status"] == "ESCALATED"
    game = _until(game, add_working_days(date(2027, o.live_on.month + 1, 1), 1))
    assert UsageRecord.objects.filter(subscriber=subscriber).exists()
    assert not Invoice.objects.filter(subscriber=subscriber).exists()
    assert Decimal(_board(client, game)["unbilled"]) > 0
    game = working_as(Game.objects.get(pk=game.pk), roles.FINANCE)
    billing = {"action": "billing", "number": number}
    assert client.post(onboard_url, billing).status_code == 200
    subscriber.refresh_from_db()
    assert subscriber.billing_ready
    # Support answers its first questions: then every department has done its part.
    game = _days(game, onboarding.DAYS["WELCOME"] + 1)
    o.refresh_from_db()
    assert o.status == "COMPLETE"
    done_by = [s.done_by for s in o.steps.order_by("position")]
    assert done_by == ["Sales", "Head of Compliance", "IT", "Head of Finance", "Support"]

    # A month with long downtime: premium service earns a credit.
    it.start_outage(game, game.current_tick + 1, "Test outage.", lambda *a: None)
    month = _today(game).month
    game = _until(game, add_working_days(date(2027, month + 1, 1), 1))
    invoice = Invoice.objects.get(subscriber=subscriber)
    lines = {x.product_code: x for x in invoice.lines.all()}
    used = UsageRecord.objects.filter(
        subscriber=subscriber, product__product_code="CONSUMER_REPORT", invoiced=True
    )
    # The held-up month is billed now, at the negotiated price.
    assert {u.unit_price for u in used} == {price}
    assert lines["CONSUMER_REPORT"].quantity == used.count()
    assert min(u.usage_at for u in used).month < month  # last month's use, held until now
    discount = lines["VOLUME_DISCOUNT"]
    assert discount.quantity == used.count() and discount.unit_price == -(price * Decimal("0.1"))
    spent = sum(x.amount for c, x in lines.items() if c not in ("MINIMUM", "SERVICE_CREDIT"))
    assert lines["MINIMUM"].amount == Decimal("500000") - spent  # it used less than promised
    credit = lines["SERVICE_CREDIT"]
    assert credit.amount == -(Decimal("500000") * SERVICE_CREDIT_RATE).quantize(Decimal("0.01"))
    assert invoice.subtotal == sum(x.amount for x in invoice.lines.all())


def test_a_lender_held_up_too_long_walks_away(world: World, monkeypatch: Any) -> None:
    _always(monkeypatch, accept=True)
    monkeypatch.setattr(onboarding, "CONCERN_MISSING", 0)
    game = _game(world)
    lender = sales.prospects(game)[0].code
    controls.send_proposal(game, lender, REFERENCE_PRICE)
    game = _days(game, sales.ANSWER_DAYS + 1)
    o = Onboarding.objects.get(game=game)
    assert lender not in {x.code for x in sales.prospects(game)}  # being taken on
    game = _until(game, add_working_days(o.give_up_on, 1))
    o.refresh_from_db()
    assert o.status == "WITHDRAWN" and o.live_on is None
    assert {s.status for s in o.steps.exclude(code="HANDOVER")} == {"CANCELLED"}
    assert Notice.objects.filter(game=game, kind="ONBOARDING_WITHDRAWN").exists()
    with pytest.raises(ClockError, match="walked away"):
        controls.send_proposal(game, lender, REFERENCE_PRICE)


def test_a_counter_offer_and_a_standard_deal_handled_by_the_staff(
    world: World, monkeypatch: Any
) -> None:
    _always(monkeypatch, accept=False)  # it declines; the price decides whether it counters
    monkeypatch.setattr(onboarding, "CONCERN_MISSING", 1000)  # nothing for the heads to settle
    game = _game(world)
    lender = sales.prospects(game)[0].code
    appetite = Decimal(str(sales.needs(game, lender)["appetite"]))
    high = (REFERENCE_PRICE * appetite / Decimal("0.9")).quantize(Decimal("0.01"))
    controls.send_proposal(game, lender, high)  # 10% more than it would pay
    game = _days(game, sales.ANSWER_DAYS + 1)
    proposal = Proposal.objects.get(game=game, lender_code=lender)
    assert proposal.status == "COUNTERED" and proposal.counter_price is not None
    assert proposal.counter_price < high
    assert Notice.objects.filter(game=game, kind="PROPOSAL_COUNTERED").exists()
    controls.accept_counter(Game.objects.get(pk=game.pk), proposal.number)
    o = Onboarding.objects.get(game=game)
    assert o.unit_price == proposal.counter_price

    # On standard terms with no concerns, every step is done by the staff, in turn.
    total = sum(onboarding.DAYS.values())
    game = _days(game, total + 3)
    o.refresh_from_db()
    assert o.status == "COMPLETE", [(s.code, s.status, s.held) for s in o.steps.all()]
    steps = list(o.steps.order_by("position"))
    assert [s.done_by for s in steps] == ["Sales", "Compliance staff", "IT", "Finance staff",
                                         "Support"]  # fmt: skip
    for before, after in itertools.pairwise(steps):  # each hand-off in order
        assert before.done_on is not None and after.done_on is not None
        assert after.ready_on == before.done_on and after.done_on >= before.done_on
    subscriber = Subscriber.objects.get(organization=game.organization, subscriber_code=lender)
    assert subscriber.billing_ready
    assert (
        Contract.objects.filter(subscriber=subscriber, product__product_code=sales.PRODUCT)
        .latest("start_date", "pk")
        .unit_price
        == proposal.counter_price
    )

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world))
    game = Game.objects.get(pk=game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)
