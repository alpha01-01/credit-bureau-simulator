"""P3.12 — Economy.

Done when (Document 09): a shock raises defaults in the world, and lenders that use the
bureau well suffer less; costs rise with inflation; a scorecard deployed before a shock
shows drift in its monitoring.

The stages are brought forward here (they begin in the sixth and twelfth months of
play in a real game), so a few months of play reach them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.analytics import scoredata as sd
from apps.finance.models import SupplierBill
from apps.simulation import controls, economy, hr, lending, scorecards
from apps.simulation.bridge import start_game
from apps.simulation.finance_dept import HOSTING
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, LendingDecision, Notice, ScoreModel
from apps.world.generation import build_world
from apps.world.generation.config import EconomyModel
from apps.world.generation.persist import loan_month_partition, write_world
from apps.world.models import EconomyMonth, World

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]

SHOCK = EconomyModel(
    intermediate_from=1, advanced_from=2, cycle_amplitude=0.0, shock_month=2, shock_size=2.0
)
CALM = EconomyModel(intermediate_from=1, advanced_from=2, cycle_amplitude=0.0, shocks=False)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world(size: str, economy_model: EconomyModel) -> World:
    g = build_world(81, size, economy=economy_model)
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _until(game: Game, day: date) -> Game:
    while _today(game) < day:
        game = controls.advance_by(game, "next_event")
    return game


def _arrears_share(world: World, since: date, until: date) -> float:
    """Of the world's active loans each month, the share behind on payments."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT AVG((days_past_due > 0)::int) FROM {loan_month_partition(world.pk)} "  # noqa: S608
            "WHERE period >= %s AND period <= %s AND status = 'ACTIVE'",
            [since, until],
        )
        return float(cursor.fetchone()[0])


def test_a_shock_raises_defaults_and_lenders_using_the_bureau_suffer_less(db: None) -> None:
    played: dict[str, tuple[World, Game]] = {}
    for name, model in (("calm", CALM), ("shock", SHOCK)):
        world = _world("small", model)
        game = controls.set_pause_rules(start_game(world), [], deadlines=False)
        played[name] = (world, _until(game, date(2027, 6, 2)))

    # The shock struck in February: the world's stress jumped, and was published in March.
    shock_world, shock_game = played["shock"]
    feb = EconomyMonth.objects.get(world=shock_world, period=date(2027, 2, 28))
    calm_feb = EconomyMonth.objects.get(world=played["calm"][0], period=date(2027, 2, 28))
    assert "SHOCK" in feb.events and feb.stress_index > calm_feb.stress_index + 1.5
    assert feb.growth is not None and calm_feb.growth is not None
    assert feb.growth < calm_feb.growth
    assert Notice.objects.filter(game=shock_game, kind="ECONOMIC_SHOCK").exists()
    assert not Notice.objects.filter(game=played["calm"][1], kind="ECONOMIC_SHOCK").exists()

    # Borrowers miss more payments in the world after the shock.
    after = {
        n: _arrears_share(w, date(2027, 2, 28), date(2027, 5, 31)) for n, (w, _) in played.items()
    }
    before = {
        n: _arrears_share(w, date(2026, 11, 30), date(2027, 1, 31)) for n, (w, _) in played.items()
    }
    print(f"in arrears before {before}, after {after}")  # noqa: T201
    assert before["shock"] == pytest.approx(before["calm"])  # the same world until the shock
    assert after["shock"] > after["calm"] * 1.2

    # Lenders' loans made in play: those they checked first (and lent to only on a clean
    # report), those they lent to without checking, and every loan the world made for
    # their applicants, as if they had never used the bureau.
    def behind(game: Game, **which: Any) -> tuple[float, int]:
        loans = [
            loan
            for loan in LendingDecision.objects.filter(
                game=game, application__approved=True, application__loan__isnull=False, **which
            ).values_list("application__loan_id", flat=True)
            if loan is not None
        ]
        gone = lending._gone_bad(game, loans, date(2027, 5, 31), lending.CURRENT_ARREARS_DAYS)
        return len(gone) / len(loans), len(loans)

    rate = {
        (n, kind): behind(g, **which)
        for n, (_, g) in played.items()
        for kind, which in (
            ("checked", {"lent": True, "checked": True}),
            ("unchecked", {"lent": True, "checked": False}),
            ("without the bureau", {}),
        )
    }
    print(f"fell behind (rate, loans): {rate}")  # noqa: T201
    # The shock hurt lending: the world's loans to these lenders' applicants fell behind more.
    assert rate[("shock", "without the bureau")][0] > rate[("calm", "without the bureau")][0]
    # In the shock, the loans made after a check fell behind least.
    assert rate[("shock", "checked")][0] < rate[("shock", "unchecked")][0]
    assert rate[("shock", "checked")][0] < rate[("shock", "without the bureau")][0]

    copy = controls.replay(Game.objects.get(pk=shock_game.pk), start_game(shock_world))
    game = Game.objects.get(pk=shock_game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)


def test_costs_rise_with_inflation(db: None) -> None:
    rising = EconomyModel(intermediate_from=1, advanced_from=99, inflation_range=(0.30, 0.30))
    flat = EconomyModel(stages=False)
    games = {}
    owner = User.objects.create_user("chief")
    for name, model in (("rising", rising), ("flat", flat)):
        world = _world("tiny", model)
        game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
        games[name] = _until(game, date(2027, 4, 2))

    def hosting(game: Game, month: str) -> Decimal:
        return SupplierBill.objects.get(
            organization=game.organization, supplier_code=HOSTING[0], reference=f"NC-{month}"
        ).amount

    # January's prices are those play began with; from then on, the published index.
    for name in games:
        assert hosting(games[name], "202701") == hosting(games["flat"], "202701")
    assert hosting(games["flat"], "202704") == hosting(games["flat"], "202701")
    factor = economy.price_factor(games["rising"], date(2027, 4, 2))
    assert factor > Decimal("1.05")  # about 2.2% a month at 30% a year, for three months
    assert hosting(games["rising"], "202704") == economy.priced(
        hosting(games["flat"], "202704"), factor
    )
    assert hosting(games["rising"], "202704") > hosting(games["rising"], "202703")
    # The bills replay exactly (checked before looking at next month's candidates below,
    # who are made when first looked at).
    world = games["rising"].world
    copy = controls.replay(Game.objects.get(pk=games["rising"].pk), start_game(world))
    game = Game.objects.get(pk=games["rising"].pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)

    # The market for staff moves with wages: candidates ask more, the going rate is higher.
    wages = economy.wage_factor(games["rising"], date(2027, 4, 1))
    assert wages > Decimal("1.05")
    asked = {
        n: sum(c.asking_salary for c in hr.candidates_for(g, date(2027, 4, 30)))
        for n, g in games.items()
    }
    assert asked["rising"] > asked["flat"]
    assert hr.market_salary("Data Officer", wages) > hr.market_salary("Data Officer")
    assert Notice.objects.filter(game=games["rising"], kind="ECONOMY_STAGE").exists()

    # The indicators page: what has been published, and the rule behind each figure.
    client = APIClient()
    client.force_authenticate(owner)
    shown = client.get(f"/api/v1/games/{games['rising'].pk}/economy/").json()
    assert shown["stage"] == "INTERMEDIATE" and set(shown["rules"]) >= {"inflation", "wages"}
    published = [m for m in shown["months"] if m["period"] >= "2027-01-01"]
    assert [m["period"] for m in published] == ["2027-01-31", "2027-02-28", "2027-03-31"]
    assert all(m["inflation"] > 0.25 for m in published)
    assert "stress_index" not in str(shown)  # the bureau never sees the world's state


def test_a_scorecard_deployed_before_a_shock_drifts(db: None) -> None:
    """Short-term borrowers feel a shock first: the short-term scorecard's population moves."""
    since = {}
    for name, model in (("calm", CALM), ("shock", SHOCK)):
        world = _world("small", model)
        game = controls.set_pause_rules(start_game(world, history_months=12), [], deadlines=False)
        window = 6
        observation = date.fromisoformat(scorecards.observation_dates(game, window)[0])
        built = controls.build_scorecard(
            game, sd.SHORT, observation, window, sd.recommended(sd.SHORT)
        )
        controls.deploy_scorecard(game, built.number)
        deployed = ScoreModel.objects.get(pk=built.pk)
        assert deployed.results["deployed"]["as_of"] < "2027-01-01"  # the population at launch
        game = _until(game, date(2027, 4, 20))  # March's files are in
        before = scorecards.monitor(game, deployed, date(2027, 1, 31))  # before the shock
        after = scorecards.monitor(game, deployed, date(2027, 3, 31))
        assert before is not None and after is not None
        since[name] = (before["since_deployment"], after["since_deployment"])
    print(f"since deployment: {since}")  # noqa: T201
    assert since["calm"][1]["shift"] == "stable"
    assert since["shock"][0]["shift"] == "stable"  # nothing before the shock
    assert since["shock"][1]["shift"] == "major" and since["shock"][1]["psi"] > scorecards.DRIFT_PSI
    assert since["shock"][1]["psi"] > 3 * since["calm"][1]["psi"]
