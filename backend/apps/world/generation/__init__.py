"""World generation (Document 06, S1; Document 07, Section 7).

from apps.world.generation import generate_world
world_id = generate_world(seed=42, scale="default")
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from django.db import transaction

from .config import SCALES, EconomyModel, WorldConfig
from .engine import SimulationResult, simulate
from .mobile import generate as generate_mobile
from .persist import write_world
from .population import (
    Branch,
    Businesses,
    People,
    generate_branches,
    generate_businesses,
    generate_people,
)
from .stats import WorldStats, compute_stats


@dataclass
class GeneratedWorld:
    config: WorldConfig
    people: People
    businesses: Businesses
    branches: list[Branch]
    result: SimulationResult
    stats: WorldStats


def build_world(
    seed: int,
    scale: str = "default",
    history_end: date | None = None,
    extra_months: int = 0,
    mobile_loans: bool = True,
    economy: EconomyModel | None = None,
) -> GeneratedWorld:
    """Generate a world in memory. Pure: no database access.

    ``extra_months`` simulates that many months beyond ``history_end`` (used to
    advance a stored world during play); everything up to ``history_end`` is
    identical to a world generated without them. ``mobile_loans`` adds the mobile
    loan stream (P3.3); worlds made before it carry on without one. ``economy`` sets the
    economy's model (P3.12: its stages and shock); the default has stages.
    """
    if scale not in SCALES:
        raise ValueError(f"Unknown scale {scale!r}; choose from {', '.join(SCALES)}")
    config = WorldConfig(seed=seed, scale=SCALES[scale], extra_months=extra_months)
    if economy is not None:
        config = replace(config, economy=economy)
    if history_end is not None:
        config = replace(config, history_end=history_end)
    people = generate_people(config)
    businesses = generate_businesses(config, people)
    branches = generate_branches(config)
    result = simulate(config, people, businesses, branches)
    if mobile_loans:
        result.mobile = generate_mobile(config, people, result.months, result.stress)
    stats = compute_stats(config, result)
    return GeneratedWorld(config, people, businesses, branches, result, stats)


def generate_world(seed: int, scale: str = "default", history_end: date | None = None) -> int:
    """Generate a world and store it. Returns the new World id."""
    world = build_world(seed, scale, history_end)
    with transaction.atomic():
        return write_world(
            world.config, world.people, world.businesses, world.branches, world.result, world.stats
        )


__all__ = ["GeneratedWorld", "build_world", "generate_world"]
