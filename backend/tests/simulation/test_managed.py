"""P3.10 — Customer Support and Product Development (managed).

Done when (Document 09): an outage produces a measurable wave of tickets; a product
becomes saleable only once it has been developed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import Enquiry
from apps.commercial.models import UsageRecord
from apps.finance.models import SupplierBill
from apps.simulation import controls, it, products, roles, scoreproduct, support
from apps.simulation.bridge import start_game
from apps.simulation.compliance import add_working_days
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, Notice, SubscriberView, SupportTicket
from apps.simulation.reputation import reputation
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world(size: str) -> World:
    g = build_world(81, size)
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _until(game: Game, day: date) -> Game:
    while _today(game) < day:
        game = controls.advance_by(game, "next_event")
    return game


def _tickets(game: Game, day: date, **kw: Any) -> int:
    return SupportTicket.objects.filter(game=game, opened_on=day, **kw).count()


def test_an_outage_brings_a_wave_of_tickets_and_staffing_moves_satisfaction(
    db: None, monkeypatch: Any
) -> None:
    monkeypatch.setitem(it.DAILY_OUTAGE_CHANCE, "STANDARD", 0.0)  # only the outage we start
    world = _world("tiny")
    games = {}
    for name, agents in (("calm", 2), ("thin", 1), ("staffed", 6)):
        game = controls.set_pause_rules(start_game(world), [], deadlines=False)
        game = controls.set_support_staff(game, agents)
        games[name] = _until(game, date(2027, 1, 11))
    for name in ("thin", "staffed"):  # the systems go down for two working days
        game = games[name]
        it.start_outage(game, game.current_tick + 1, "Test outage.", lambda *a: None)
    for name in games:
        games[name] = _until(games[name], date(2027, 1, 20))

    days = [date(2027, 1, d) for d in (12, 13, 14)]  # the mornings after each day down
    calm = sum(_tickets(games["calm"], d) for d in days)
    wave = sum(_tickets(games["thin"], d) for d in days)
    outage = sum(_tickets(games["thin"], d, topic="OUTAGE") for d in days)
    print(f"tickets in three days: calm {calm}, with the outage {wave} ({outage} about it)")  # noqa: T201
    assert _tickets(games["calm"], days[0], topic="OUTAGE") == 0
    assert outage >= 20 and wave >= calm + outage  # the wave is the outage's
    assert wave >= 3 * max(calm, 1)
    # Same world, same days: the outage's tickets are the same whatever the staffing.
    assert sum(_tickets(games["staffed"], d) for d in days) == wave

    # One agent cannot keep up: tickets wait, answers come late, subscribers notice.
    thin, staffed = (support.satisfaction(games[n], controls.state(games[n]).now)
                     for n in ("thin", "staffed"))  # fmt: skip
    print(f"on time: one agent {thin}, six agents {staffed}")  # noqa: T201
    assert staffed["score"] == 1.0 and staffed["late"] == 0
    assert thin["score"] is not None and thin["score"] < staffed["score"] and thin["late"] > 0
    assert Notice.objects.filter(game=games["thin"], kind="SUPPORT_BACKLOG").exists()
    rep = {n: reputation(games[n], controls.state(games[n]).now)["subscribers"] for n in games}
    assert rep["thin"]["support_on_time"] < rep["staffed"]["support_on_time"]
    # Agents cost money: the contact centre bills for them from the next month.
    staffed_game = _until(games["staffed"], date(2027, 2, 2))
    bill = SupplierBill.objects.get(organization=staffed_game.organization, reference="CP-202702")
    assert bill.amount == 6 * Decimal("4500.00")

    copy = controls.replay(Game.objects.get(pk=games["calm"].pk), start_game(world))
    calm_game = Game.objects.get(pk=games["calm"].pk)
    assert fingerprint(copy) == fingerprint(calm_game), differences(copy, calm_game)


def test_a_product_is_sold_only_once_developed(db: None) -> None:
    world = _world("small")
    owner = User.objects.create_user("chief")
    game = controls.set_pause_rules(
        start_game(world, owner=owner, history_months=12), [], deadlines=False
    )
    # A good scorecard is deployed, but there is no score product to sell yet.
    from apps.bureau.analytics import scoredata as sd
    from apps.simulation import scorecards

    window = 6
    observation = date.fromisoformat(scorecards.observation_dates(game, window)[0])
    for term in sd.TERMS:
        model = controls.build_scorecard(game, term, observation, window, sd.recommended(term))
        controls.deploy_scorecard(game, model.number)
    controls.deploy_scorecard(game, controls.build_composite(game, observation, window).number)
    assert not products.launched(game, scoreproduct.SCORE)
    assert scoreproduct.warranted_uptake(game) == 0.0

    # Others may not start a product; the chief executive does, and pays for it.
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/products/"
    working_as(game, roles.SALES)
    assert client.post(url, {"code": scoreproduct.SCORE}).status_code == 403
    game = working_as(Game.objects.get(pk=game.pk), roles.CEO)
    assert client.post(url, {"code": scoreproduct.SCORE}).status_code == 200
    shown = {p["code"]: p for p in client.get(url).json()["products"]}
    assert shown[scoreproduct.SCORE]["status"] == "IN_DEVELOPMENT"
    assert shown["BUSINESS_REPORT"]["status"] == "AVAILABLE"
    bill = SupplierBill.objects.get(organization=game.organization, supplier_code="DEVWORKS")
    assert bill.amount == products.MENU[scoreproduct.SCORE].cost and bill.account_code == "5900"
    with pytest.raises(ClockError, match="already being developed"):
        controls.develop_product(game, scoreproduct.SCORE)

    # While it is being built, the month's end brings no buyers, and no score is sold.
    month = _today(game).month
    while _today(game).month == month:
        game = controls.advance_by(game, "next_event")
    assert all(v.score_uptake == 0 for v in SubscriberView.objects.filter(game=game))
    assert not products.launched(game, scoreproduct.SCORE)
    assert not UsageRecord.objects.filter(
        organization=game.organization, product__product_code=scoreproduct.SCORE
    ).exists()
    started = date.fromisoformat(str(shown[scoreproduct.SCORE]["started_on"]))
    ready = date.fromisoformat(str(shown[scoreproduct.SCORE]["ready_on"]))
    assert ready == add_working_days(started, products.MENU[scoreproduct.SCORE].working_days)
    game = _until(game, ready)
    assert products.launched(game, scoreproduct.SCORE)
    assert Notice.objects.filter(game=game, kind="PRODUCT_LAUNCHED").exists()
    assert scoreproduct.warranted_uptake(game) > 0

    # Launched: at the next month's end lenders take it up, and scores are sold.
    month = _today(game).month
    while _today(game).month == month:
        game = controls.advance_by(game, "next_event")
    assert any(v.score_uptake > 0 for v in SubscriberView.objects.filter(game=game))
    game = controls.advance_by(game, "day", 3)
    sold = UsageRecord.objects.filter(
        organization=game.organization, product__product_code=scoreproduct.SCORE
    )
    assert sold.exists()
    assert min(u.usage_at for u in sold).date() > ready
    assert any((e.report.get("score") or {}).get("score")
               for e in Enquiry.objects.filter(organization=game.organization))  # fmt: skip

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world, history_months=12))
    game = Game.objects.get(pk=game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)
