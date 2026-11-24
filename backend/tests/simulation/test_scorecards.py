"""P3.5 — the scorecard workbench.

Done when (Document 09): AUC, Gini and KS agree with an independent calculation
(``tests/bureau/test_scoremath.py``); a model built on a restricted attribute is flagged
and, once deployed, produces a Compliance finding. The comparisons between clean and
carelessly loaded data, term and single scorecards, and the composite are measured on a
full-size world by ``manage.py scorecard_study`` (``docs/scorecards``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.analytics import scoredata as sd
from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.simulation import controls, scorecards
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import ComplianceFinding, Game, Notice, ScoreModel
from apps.standards.submission_template import OPEN_STATUS_CODES
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world(seed: int, size: str) -> World:
    g = build_world(seed, size)
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def test_the_dataset_follows_the_records() -> None:
    """Each customer's population, label and features, recomputed from the records."""
    game = start_game(_world(61, "tiny"), history_months=6)
    window = 3
    observation = date.fromisoformat(scorecards.observation_dates(game, window)[0])
    data = sd.dataset(game.organization_id, sd.ALL, observation, window)
    assert len(data.customers) > 20
    window_end = sd.months_back(observation, -window)
    for i, customer in enumerate(data.customers.tolist()):
        accounts = CreditAccount.objects.filter(
            customer_id=customer, disbursement_date__lte=observation
        )
        rows = AccountObservation.objects.filter(
            credit_account__customer_id=customer, is_current=True
        )
        at_t = rows.filter(reporting_date=observation)
        assert at_t.filter(facility_status__in=OPEN_STATUS_CODES).exists()  # in the population
        assert not at_t.filter(
            facility_status__in=OPEN_STATUS_CODES, days_past_due__gte=90
        ).exists()
        later = rows.filter(reporting_date__gt=observation, reporting_date__lte=window_end)
        assert bool(data.bad[i]) == later.filter(days_past_due__gte=90).exists()
        assert (
            data.features["open_accounts"][i]
            == at_t.filter(facility_status__in=OPEN_STATUS_CODES).count()
        )
        assert data.features["facilities_ever"][i] == accounts.count()
        worst = (
            rows.filter(
                reporting_date__lte=observation, reporting_date__gt=sd.months_back(observation, 12)
            )
            .order_by("-days_past_due")
            .values_list("days_past_due", flat=True)
            .first()
        )
        assert data.features["worst_dpd_12m"][i] == (worst or 0)


@pytest.mark.slow
def test_the_workbench_end_to_end() -> None:
    world = _world(81, "small")
    owner = User.objects.create_user("analyst")
    game = start_game(world, owner=owner, history_months=12)
    window = 6
    observation = date.fromisoformat(scorecards.observation_dates(game, window)[0])

    # Build a scorecard for each term and deploy it; then the composite.
    built = {}
    for term in sd.TERMS:
        model = controls.build_scorecard(game, term, observation, window, sd.recommended(term))
        assert model.results["holdout"]["customers"] > 0
        assert model.results["truth"]["customers"] > 0
        labels = model.results["truth"]["labels"]
        assert sum(labels.values()) == model.results["truth"]["customers"]
        controls.deploy_scorecard(game, model.number)
        built[term] = model
    composite = controls.build_composite(game, observation, window)
    assert {c["term"] for c in composite.results["components"]} == set(sd.TERMS)
    assert composite.results["holdout"]["auc"] is not None
    single = controls.build_scorecard(game, sd.ALL, observation, window, sd.recommended(sd.ALL))
    assert ScoreModel.objects.filter(game=game, status="DEPLOYED").count() == 3

    # A restricted attribute: flagged when built, a Compliance finding when deployed.
    assert not ComplianceFinding.objects.filter(game=game).exists()
    gendered = controls.build_scorecard(
        game, sd.LONG, observation, window, [*sd.recommended(sd.LONG), "gender"]
    )
    assert gendered.results["fairness"]["restricted_used"] == ["gender"]
    assert {g["group"] for g in gendered.results["fairness"]["groups"]} == {"Women", "Men"}
    controls.deploy_scorecard(game, gendered.number)
    finding = ComplianceFinding.objects.get(game=game)
    assert finding.kind == "RESTRICTED_ATTRIBUTE_IN_SCORECARD" and "gender" in finding.detail
    assert finding.due_date is not None and "Retire scorecard" in finding.remedy  # P3.7
    assert Notice.objects.filter(game=game, kind="COMPLIANCE_FINDING").exists()
    assert ScoreModel.objects.get(pk=built[sd.LONG].pk).status == "RETIRED"
    with pytest.raises(ClockError, match="already in use"):
        controls.deploy_scorecard(game, gendered.number)
    with pytest.raises(ClockError, match="outcomes on file"):
        controls.build_scorecard(game, sd.SHORT, date(2030, 1, 31), window, ["enquiries_30d"])

    # The workbench through the API: the analyst's actions, refused to other roles.
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}/scorecards/"
    listing = client.get(base).json()
    assert (
        len(listing["models"]) == 6
        and listing["findings"][0]["reference"] == f"SCORECARD-{gendered.number}"
    )
    assert any(w["observation_dates"] for w in listing["options"]["windows"])
    body = {"action": "build", "term": "MID", "observation": observation.isoformat(), "window": window,
            "features": sd.recommended(sd.MID)}  # fmt: skip
    assert client.post(base, body, format="json").status_code == 403  # the CEO does not build
    working_as(Game.objects.get(pk=game.pk), "DATA_ANALYTICS")
    assert client.post(base, body, format="json").status_code == 200
    # Retiring the gendered scorecard settles the finding (P3.7); the term goes unscored.
    retired = client.post(base, {"action": "retire", "number": gendered.number}, format="json")
    assert retired.status_code == 200 and retired.json()["status"] == "RETIRED"
    assert ComplianceFinding.objects.get(game=game).resolved_tick is not None
    detail = client.get(f"{base}{single.number}/").json()
    first = detail["results"]["characteristics"][0]
    assert first["bins"] and "points" in first["bins"][0]
    assert detail["results"]["truth"]["customers"] > 0
    assert detail["monitoring"] is None or "psi" in detail["monitoring"]

    # Every model, deployment and finding replays exactly.
    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world, history_months=12))
    assert fingerprint(copy) == fingerprint(Game.objects.get(pk=game.pk)), differences(copy, game)
