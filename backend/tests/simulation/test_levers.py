"""P3.15 — Balancing: the levers Phase 3 added each move the outcomes.

Done when (Document 09): every PRD criterion in Section 6 is met and recorded in
``docs/exit-criteria-v1.md``. This test is the evidence that the strategy runs were
widened to the new levers: each pair of strategies differs from the other in one lever
only (``apps/simulation/balancing.py``), and the pair's outcomes differ where that lever
should move them, at a price elsewhere. The runs across seeds, scenarios and
difficulties are in ``docs/balancing`` (manage.py balance).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.simulation import balancing, scenarios
from apps.world.models import World

MONTHS, HISTORY = 3, 12


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    return scenarios.make_world(81, "small", "STANDARD")


def _pair(world: World, a: str, b: str) -> tuple[dict[str, Any], dict[str, Any]]:
    runs = [
        balancing.outcomes(balancing.play(world, name, MONTHS, history_months=HISTORY))
        for name in (a, b)
    ]
    for name, o in zip((a, b), runs, strict=True):
        print(name, {k: o[k] for k in (  # noqa: T201
            "net_profit", "revenue", "reports_sold", "report_price", "scores_sold", "score_auc",
            "subscribers", "findings", "findings_by_kind", "compliance_findings",
            "consent_checks", "improper_enquiry_rate", "health",
        )})  # fmt: skip
    return runs[0], runs[1]


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_each_new_lever_moves_the_outcomes(world: World) -> None:
    # Score quality: a careful scorecard predicts the truth and lenders buy it; a careless
    # one does not. Both paid to develop the score.
    careful, careless = _pair(world, "score_careful", "score_careless")
    assert careful["score_auc"] > 0.75 > careless["score_auc"]
    assert careful["scores_sold"] > 0 == careless["scores_sold"]
    assert careful["revenue"] > careless["revenue"]

    # Compliance effort: diligence finds subscribers enquiring without consent and puts
    # it right in time; laxity leaves its findings to reach the regulator.
    diligent, lax = _pair(world, "compliance_diligent", "compliance_lax")
    assert diligent["consent_checks"] > 0 == lax["consent_checks"]
    assert diligent["findings_by_kind"].get("UNRESOLVED_FINDING", 0) < lax["findings_by_kind"].get(
        "UNRESOLVED_FINDING", 0
    )
    assert diligent["health"] >= lax["health"]

    # Pricing: a higher price earns more a report and sells fewer; neither wins on both.
    high, low = _pair(world, "price_high", "price_low")
    assert high["report_price"] > low["report_price"]
    assert high["reports_sold"] < low["reports_sold"]
