"""P2.12 — Balancing.

Done when (Document 08): two clearly different strategies lead to measurably
different outcomes and neither dominates (Document 07, Section 13.2, criterion 3).

"Strict quality" and "fast coverage" play four months in one small world. The
strict bureau pays for tooling, a senior officer and provider training; the
fast one links readily and rejects little. Strict should have the cleaner data
and the better health; fast should have the better result. Neither should win
on both. The full comparison, across seeds and on the default world, is in
``docs/balancing`` (manage.py balance).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.simulation import balancing
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

MONTHS = 4


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    """``a`` is at least as good as ``b`` on every measure and better on one."""
    return all(a[k] >= b[k] for k in a) and any(a[k] > b[k] for k in a)


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_strict_quality_and_fast_coverage_differ_and_neither_dominates(world: World) -> None:
    strict = balancing.outcomes(balancing.play(world, "strict_quality", MONTHS))
    fast = balancing.outcomes(balancing.play(world, "fast_coverage", MONTHS))
    for name, o in (("strict", strict), ("fast", fast)):
        print(name, {k: o[k] for k in ("net_profit", "false_merge_rate", "accuracy_true",  # noqa: T201
                                       "disputes", "health", "health_parts")})  # fmt: skip

    # Measurably different: cleaner data, at a price.
    assert strict["false_merge_rate"] < fast["false_merge_rate"]
    assert strict["accuracy_true"] > fast["accuracy_true"]
    assert strict["disputes"] <= fast["disputes"]
    assert strict["health_parts"]["data_quality"] > fast["health_parts"]["data_quality"]
    assert strict["expenses"] > fast["expenses"]
    assert fast["net_profit"] > strict["net_profit"]

    # Neither dominates on what the game rewards: money and the bureau's health.
    def score(o: dict[str, Any]) -> dict[str, float]:
        return {"result": o["net_profit"], "health": o["health"]}

    assert not dominates(score(strict), score(fast))
    assert not dominates(score(fast), score(strict))
