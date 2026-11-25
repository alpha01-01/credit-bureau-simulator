"""P3.13 — Scenarios and difficulty.

Done when (Document 09): a Startup game can reach its first paid report; the same
strategy measurably fares better at Beginner than at Expert; every scenario replays
exactly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import CreditAccount
from apps.bureau.providers.models import Institution
from apps.bureau.quality.models import RegulatoryReturn
from apps.commercial.models import Product, Subscriber
from apps.finance.events import balance
from apps.finance.ledger import BANK
from apps.finance.models import BillStatus, JournalLine, Payment, SupplierBill
from apps.org.models import Employee
from apps.simulation import balancing, controls, hr, scenarios, startup
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, GameStatus, Notice, ProviderRelationship
from apps.simulation.sales import prospects
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Loan, World
from tests.roles import working_as

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world(size: str, economy: str, seed: int = 83) -> World:
    made = build_world(seed, size, economy=scenarios.economy_model(economy))
    return World.objects.get(
        pk=write_world(made.config, made.people, made.businesses, made.branches, made.result,
                       made.stats)
    )  # fmt: skip


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _approve_bills(game: Game) -> None:
    """The Head of Finance approves every bill waiting (bills above the limit wait)."""
    for number in SupplierBill.objects.filter(
        organization=game.organization, status=BillStatus.RECEIVED
    ).values_list("number", flat=True):
        controls.approve_bill(game, number)


def _replays(game: Game, fresh: Game) -> None:
    copy = controls.replay(Game.objects.get(pk=game.pk), fresh)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)


# --- Startup ------------------------------------------------------------------------------


def _build_the_bureau(game: Game) -> Game:
    """A founder's first days: office, IT, the report, agents, then the first team."""
    controls.rent_office(game, "SMALL")
    controls.set_up_it(game, "STANDARD")
    controls.develop_product(game, "CONSUMER_REPORT")
    controls.set_support_staff(game, 1)
    _approve_bills(game)
    game = controls.advance_by(game, "hour")  # the month starts: this month's candidates
    for candidate in hr.candidates_for(game, controls.this_month(game)):
        controls.hire_candidate(game, candidate.number)
    return game


def _sell(game: Game) -> None:
    """Propose to the two largest lenders, at list price, once the report is on sale."""
    sizes = {
        lender.code: Loan.objects.filter(lender=lender, disbursement_date__lt=game.clock_start)
        .count()
        for lender in prospects(game)
    }  # fmt: skip
    for code in sorted(sizes, key=lambda c: (-sizes[c], c))[:2]:
        controls.send_proposal(game, code, Decimal("15.00"))


def test_a_startup_reaches_its_first_paid_report_and_replays(db: None) -> None:
    world = _world("small", "STANDARD")
    owner = User.objects.create_user("founder")
    game = controls.set_pause_rules(
        start_game(world, owner=owner, scenario=scenarios.STARTUP), [], deadlines=False
    )
    org = game.organization
    eve = game.clock_start - timedelta(days=1)

    # Capital and nothing else.
    assert balance(org, BANK, eve) == scenarios.STARTUP_CAPITAL
    assert not Employee.objects.filter(organization=org).exists()
    assert not Institution.objects.filter(organization=org).exists()
    assert not Subscriber.objects.filter(organization=org).exists()
    assert (org.office, org.has_systems, org.support_staff) == ("", False, 0)
    assert not game.campaign  # the missions are written for an established bureau

    # Each step waits for the one before it.
    game = controls.advance_by(game, "hour")
    first = hr.candidates_for(game, controls.this_month(game))[0]
    with pytest.raises(ClockError, match="rent an office"):
        controls.hire_candidate(game, first.number)
    with pytest.raises(ClockError, match="rent one first"):
        controls.set_up_it(game, "STANDARD")
    with pytest.raises(ClockError, match="set up IT first"):
        controls.onboard_provider(game, "ATB")
    with pytest.raises(ClockError, match="develop the consumer credit report"):
        controls.send_proposal(game, "ATB", Decimal("15.00"))

    game = _build_the_bureau(game)
    # It owes no return, and no access review, for the time before it existed.
    assert not RegulatoryReturn.objects.filter(organization=org).exists()
    assert not Notice.objects.filter(game=game, kind="COMPLIANCE_FINDING").exists()
    # The first team at its desks; a year of rent billed in advance.
    assert Employee.objects.filter(organization=org, is_active=True).count() == 3
    lease = SupplierBill.objects.get(organization=org, supplier_code="RIDGEPROP")
    assert lease.amount == startup.OFFICES["SMALL"].monthly_rent * 12

    # IT is ready ten working days on; then the providers are onboarded.
    ready_on = Game.objects.get(pk=game.pk).organization.it_ready_on
    assert ready_on is not None
    while _today(game) < ready_on:
        game = controls.advance_by(game, "day")
    assert Notice.objects.filter(game=game, kind="SYSTEMS_READY").exists()
    for lender in startup.provider_prospects(game):
        controls.onboard_provider(game, lender.code)
    assert Institution.objects.filter(organization=org).count() == 5

    sold = False
    deadline = game.clock_start + timedelta(days=170)
    while not Payment.objects.filter(
        organization=org, invoice__lines__product_code="CONSUMER_REPORT"
    ).exists():
        assert _today(game) < deadline, startup.checklist(game, _today(game))
        game = controls.advance_by(game, "next_event")
        _approve_bills(game)
        balancing._onboard(game)
        if not sold and Product.objects.filter(organization=org).exists():
            _sell(game)
            sold = True
        if game.status == GameStatus.ENDED:
            pytest.fail(f"The startup failed: {game.ended_reason}")
    game = controls.advance_by(game, "day")  # to the evening...
    game = controls.advance_by(game, "hour")  # ...and the next morning's milestones

    # The database was built from the providers' first files.
    assert CreditAccount.objects.filter(organization=org).count() > 1000
    assert Notice.objects.filter(game=game, kind="FIRST_REPORT_SOLD").exists()
    assert Notice.objects.filter(game=game, kind="FIRST_PAYMENT").exists()
    assert all(step["done"] for step in startup.checklist(game, _today(game)))
    print(f"first report paid on {_today(game)}")  # noqa: T201

    _replays(game, start_game(world, scenario=scenarios.STARTUP))


# --- Difficulty ---------------------------------------------------------------------------


def test_the_same_strategy_fares_better_at_beginner_than_at_expert(db: None) -> None:
    played = {}
    for difficulty in (scenarios.BEGINNER, scenarios.EXPERT):
        params = scenarios.DIFFICULTIES[difficulty][1]
        world = _world("small", params.economy)
        assert scenarios.economy_name(world) == params.economy
        game = balancing.play(world, "strict_quality", 6, difficulty)
        played[difficulty] = (world, game, balancing.outcomes(game))
    easy, hard = played[scenarios.BEGINNER][2], played[scenarios.EXPERT][2]
    for name in ("net_profit", "revenue", "bank", "expenses", "health", "loans_fell_behind"):
        print(f"{name}: beginner {easy[name]}, expert {hard[name]}")  # noqa: T201
    for difficulty, (_, g, _) in played.items():
        moved = (
            JournalLine.objects.filter(entry__organization=g.organization, account__code=BANK)
            .values("entry__source_type")
            .annotate(net=Sum("debit") - Sum("credit"))
            .order_by("entry__source_type")
        )
        print(difficulty, {m["entry__source_type"]: float(m["net"]) for m in moved})  # noqa: T201

    # The rules are the same; resources, costs and the economy are not.
    assert easy["expenses"] < hard["expenses"]
    assert easy["net_profit"] > hard["net_profit"]
    assert easy["bank"] > hard["bank"]
    # Expert's dearer bills cross the approval limit more often: left unapproved by this
    # strategy, they are owed rather than paid, so its bank flatters it.
    owed = {
        d: SupplierBill.objects.filter(organization=g.organization, status=BillStatus.RECEIVED)
        .aggregate(s=Sum("amount"))["s"] or Decimal("0")
        for d, (_, g, _) in played.items()
    }  # fmt: skip
    print(f"owed to suppliers: {owed}")  # noqa: T201
    assert easy["bank"] - float(owed[scenarios.BEGINNER]) > (
        hard["bank"] - float(owed[scenarios.EXPERT]) + 1_000_000
    )  # GHS 500,000 each way, and the costs
    assert easy["health"] > hard["health"]
    # Suppliers charge the difficulty's prices.
    hosting = {
        d: SupplierBill.objects.filter(organization=g.organization, supplier_code="NETCORE")
        .order_by("bill_date")
        .values_list("amount", flat=True)[0]
        for d, (_, g, _) in played.items()
    }  # fmt: skip
    assert hosting[scenarios.BEGINNER] == Decimal("12750.00")  # 15,000 x 0.85
    assert hosting[scenarios.EXPERT] == Decimal("17250.00")  # 15,000 x 1.15

    world, game, _ = played[scenarios.EXPERT]
    _replays(game, start_game(world, difficulty=scenarios.EXPERT))


def test_board_patience_follows_the_difficulty(db: None, monkeypatch: Any) -> None:
    """Expert removes the management at its first review with no confidence; Beginner
    after the third."""
    from apps.simulation import board
    from apps.simulation.models import BoardReview

    monkeypatch.setattr(board, "health", lambda game, at: {"overall": 0.0, "parts": {}})
    world = _world("tiny", "STILL")
    verdicts = {}
    for difficulty in (scenarios.BEGINNER, scenarios.EXPERT):
        game = start_game(world, difficulty=difficulty)
        Game.objects.filter(pk=game.pk).update(clock_start=date(2026, 1, 1))
        game.refresh_from_db()
        for n, quarter in enumerate((date(2027, 4, 1), date(2027, 7, 1), date(2027, 10, 1))):
            at = datetime.combine(quarter, time(8), tzinfo=UTC)
            review = board.quarterly_review(game, quarter, at, n + 1, _ignore)
            assert review is not None
            if review.verdict == "REMOVED":
                break
        verdicts[difficulty] = list(
            BoardReview.objects.filter(game=game)
            .order_by("period")
            .values_list("verdict", flat=True)
        )
    assert verdicts[scenarios.EXPERT] == ["REMOVED"]
    assert verdicts[scenarios.BEGINNER] == ["NO_CONFIDENCE", "NO_CONFIDENCE", "REMOVED"]


def _ignore(*args: Any) -> None:
    pass


# --- Sandbox and the new-game form --------------------------------------------------------


def test_a_sandbox_takes_its_own_settings_and_replays(db: None) -> None:
    world = _world("tiny", "STILL")
    settings = {"starting_cash": "3000000", "provider_quality": 2, "economy": "STILL"}
    # With a pre-loaded history, so the cash is set against the history's bank balance.
    game = start_game(world, scenario=scenarios.SANDBOX, settings=settings, history_months=2)
    game = controls.set_pause_rules(game, [], deadlines=False)
    eve = game.clock_start - timedelta(days=1)
    assert balance(game.organization, BANK, eve) == Decimal("3000000.00")
    assert set(
        ProviderRelationship.objects.filter(game=game).values_list("quality", flat=True)
    ) == {2}
    assert not game.campaign
    with pytest.raises(scenarios.ScenarioError):
        scenarios.resolve(scenarios.ESTABLISHED, scenarios.BEGINNER, {"provider_quality": 2})
    with pytest.raises(scenarios.ScenarioError):
        scenarios.resolve(scenarios.SANDBOX, scenarios.BEGINNER, {"provider_quality": 9})

    while _today(game) < game.clock_start + timedelta(days=40):
        game = controls.advance_by(game, "next_event")
    _replays(
        game,
        start_game(world, scenario=scenarios.SANDBOX, settings=settings, history_months=2),
    )


def test_a_new_game_is_played_in_a_world_with_its_difficultys_economy(db: None) -> None:
    still = _world("tiny", "STILL", seed=91)
    client = APIClient()
    client.force_authenticate(User.objects.create_user("player"))
    catalogue = client.get("/api/v1/scenarios/").json()
    assert [d["code"] for d in catalogue["difficulties"]] == [
        "BEGINNER", "INTERMEDIATE", "EXPERT",
    ]  # fmt: skip
    worlds = {w["id"]: w for w in client.get("/api/v1/worlds/").json()}
    assert worlds[still.pk]["economy"] == "STILL"

    # A Sandbox on the still economy plays in the world chosen.
    made = client.post(
        "/api/v1/games/",
        {"world": still.pk, "scenario": "SANDBOX", "difficulty": "INTERMEDIATE",
         "history_months": 0, "settings": {"economy": "STILL"}},
        format="json",
    ).json()  # fmt: skip
    assert made["world"] == still.pk and made["setup_status"] == "READY"

    # A Beginner startup asks for the gentle economy: a world of the same seed and size is
    # made with it, and a second game finds that world rather than making another.
    first = client.post(
        "/api/v1/games/", {"world": still.pk, "scenario": "STARTUP", "difficulty": "BEGINNER"},
        format="json",
    ).json()  # fmt: skip
    game = Game.objects.get(pk=first["id"])
    assert game.setup_status == "READY" and game.world_id != still.pk
    assert (game.world.seed, game.world.scale) == (still.seed, still.scale)
    assert scenarios.economy_name(game.world) == "GENTLE"
    assert balance(game.organization, BANK, game.clock_start - timedelta(days=1)) == Decimal(
        "2500000.00"
    )
    second = client.post(
        "/api/v1/games/", {"world": still.pk, "scenario": "STARTUP", "difficulty": "BEGINNER"},
        format="json",
    ).json()  # fmt: skip
    assert second["world"] == game.world_id

    # The startup's decisions are the chief executive's, through the API.
    url = f"/api/v1/games/{game.pk}/startup/"
    view = client.get(url).json()
    assert view["startup"] and [s["done"] for s in view["steps"]] == [False] * 9
    working_as(game, "FINANCE")
    refused = client.post(url, {"action": "rent_office", "office": "SMALL"}, format="json")
    assert refused.status_code == 403
    working_as(Game.objects.get(pk=game.pk), "CEO")
    done = client.post(url, {"action": "rent_office", "office": "SMALL"}, format="json").json()
    assert done["office"] == "SMALL" and done["steps"][0]["done"]
    again = client.post(url, {"action": "rent_office", "office": "STANDARD"}, format="json")
    assert again.status_code == 400
