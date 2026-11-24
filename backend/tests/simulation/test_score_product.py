"""P3.6 — The credit score product.

Done when (Document 09): a good score lowers subscribers' default rates more than
reports alone, on the same seed; a poor score loses them business; score revenue
posts to the ledger. With the mobile loan report from P3.3.

Within a test's few weeks the world's loans have not yet had time to default, so the
lending test judges by each applicant's true hidden risk, the world's cause of default.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.analytics import scoredata as sd
from apps.bureau.core.models import Enquiry
from apps.bureau.reports.models import CreditScore
from apps.commercial.models import Contract, UsageRecord
from apps.finance.models import InvoiceLine
from apps.simulation import controls, scorecards, scoreproduct
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, LendingDecision, ScoreModel, SubscriberView
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _scored_game(world: World, owner: User | None = None) -> Game:
    """A game with a scorecard for each term deployed, and the composite."""
    game = controls.set_pause_rules(
        start_game(world, owner=owner, history_months=12), [], deadlines=False
    )
    window = 6
    observation = date.fromisoformat(scorecards.observation_dates(game, window)[0])
    for term in sd.TERMS:
        model = controls.build_scorecard(game, term, observation, window, sd.recommended(term))
        controls.deploy_scorecard(game, model.number)
    controls.deploy_scorecard(game, controls.build_composite(game, observation, window).number)
    return game


def _everyone_buys(game: Game, uptake: float) -> None:
    SubscriberView.objects.filter(game=game).update(score_uptake=uptake)


def _days(game: Game, n: int) -> Game:
    for _ in range(n):
        game = controls.advance_by(game, "day")
    return game


def test_the_score_is_on_reports_billed_and_posted(world: World) -> None:
    owner = User.objects.create_user("lender-manager")
    game = _scored_game(world, owner)
    scores = CreditScore.objects.filter(organization=game.organization)
    assert scores.exists()
    assert {s.band for s in scores} <= set("ABCDE")
    assert all(s.model.startswith("COMPOSITE-") for s in scores)
    assert scores.exclude(reasons=[]).exists()

    # Scorecards, deployments, the scores and a few days' mobile-loan billing replay exactly.
    # (Before the test sets the subscribers' uptake by hand below, which is not an action.)
    played = _days(game, 2)
    copy = controls.replay(played, start_game(world, history_months=12))
    assert fingerprint(copy) == fingerprint(played), differences(copy, played)
    game = played

    _everyone_buys(game, 1.0)
    game = _days(game, 3)
    scored = [
        e
        for e in Enquiry.objects.filter(organization=game.organization)
        if (e.report.get("score") or {}).get("score")
    ]
    assert scored
    shown = scored[0].report["score"]
    assert shown["band"] in "ABCDE" and shown["band_label"] and shown["terms"]
    lines = UsageRecord.objects.filter(
        organization=game.organization, product__product_code=scoreproduct.SCORE
    )
    assert lines.count() == len(scored)  # billed only when a score was delivered
    assert {str(line.unit_price) for line in lines} == {"5.00"}
    # The score's contract goes with the report's: the screen and renewals follow the report.
    client = APIClient()
    client.force_authenticate(owner)
    market = client.get(f"/api/v1/games/{game.pk}/market/").json()["subscribers"]
    reports = {
        c.subscriber.subscriber_code: c
        for c in Contract.objects.filter(
            subscriber__organization=game.organization, product__product_code="CONSUMER_REPORT"
        ).select_related("subscriber")
    }
    for row in market:
        assert row["price"] == str(reports[row["code"]].unit_price) and row["renewals"] == 0

    # The month's invoices carry the score as its own line; revenue posts with it.
    month = controls.state(game).now.month
    while controls.state(game).now.month == month:
        game = controls.advance_by(game, "next_event")
    score_lines = InvoiceLine.objects.filter(
        invoice__organization=game.organization, product_code=scoreproduct.SCORE
    )
    assert score_lines.exists()
    billed = UsageRecord.objects.filter(  # a fresh query: ``lines`` holds the first days' rows
        organization=game.organization, product__product_code=scoreproduct.SCORE
    )
    assert sum(line.quantity for line in score_lines) == billed.count() > len(scored)


def test_a_good_score_lends_to_safer_applicants_than_reports_alone(world: World) -> None:
    with_score = _scored_game(world)
    _everyone_buys(with_score, 1.0)
    reports_only = controls.set_pause_rules(
        start_game(world, history_months=12), [], deadlines=False
    )
    with_score, reports_only = _days(with_score, 8), _days(reports_only, 8)

    def lent_risk(game: Game) -> tuple[float, int]:
        risks = [
            d.application.person.risk_z
            for d in LendingDecision.objects.filter(
                game=game, lent=True, checked=True
            ).select_related("application__person")
            if d.application.person is not None
        ]
        return float(np.mean(risks)), len(risks)

    scored_risk, scored_n = lent_risk(with_score)
    plain_risk, plain_n = lent_risk(reports_only)
    assert scored_n < plain_n  # the score declined some applicants the reports let through
    assert scored_risk < plain_risk  # and those it declined were riskier

    declined_by_score = [
        d.application.person.risk_z
        for d in LendingDecision.objects.filter(
            game=with_score, flagged=True, checked=True
        ).select_related("application__person")
        if d.application.person is not None
    ]
    assert np.mean(declined_by_score) > scored_risk


def test_a_poor_score_loses_its_buyers(world: World) -> None:
    game = _scored_game(world)
    good = scoreproduct.warranted_uptake(game)
    _everyone_buys(game, 0.0)
    scoreproduct.update_uptake(game)
    assert SubscriberView.objects.filter(game=game).first().score_uptake == pytest.approx(  # type: ignore[union-attr]
        scoreproduct.UPTAKE_SPEED * good
    )
    # Replace the composite with a scorecard that cannot rank anyone.
    ScoreModel.objects.filter(game=game, status="DEPLOYED").update(status="RETIRED")
    observation = date.fromisoformat(scorecards.observation_dates(game, 6)[0])
    poor = controls.build_scorecard(game, sd.LONG, observation, 6, ["enquiries_30d"])
    controls.deploy_scorecard(game, poor.number)
    poor.refresh_from_db()
    assert (poor.results["truth"].get("auc_against_truth") or 0.5) < scoreproduct.UPTAKE_FLOOR
    assert scoreproduct.warranted_uptake(game) == 0.0
    _everyone_buys(game, 1.0)
    for _ in range(4):
        scoreproduct.update_uptake(game)
    assert all(v.score_uptake < 0.1 for v in SubscriberView.objects.filter(game=game))


def test_mobile_lenders_check_their_mobile_loans_in_bulk(world: World) -> None:
    game = controls.set_pause_rules(start_game(world, history_months=12), [], deadlines=False)
    game = _days(game, 3)
    checks = UsageRecord.objects.filter(
        organization=game.organization, product__product_code=scoreproduct.MOBILE_REPORT
    )
    assert checks.exists() and not checks.filter(enquiry__isnull=False).exists()
    assert {str(c.unit_price) for c in checks} == {"2.00"}
    assert sum(c.quantity for c in checks) > len(checks)  # many loans to a line
