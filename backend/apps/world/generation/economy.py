"""The economy's path through the game, in progressive stages (P3.12; PRD, Section 15).

Each stage's variables follow defined rules from the seed:

* **History** (before play) and **Initial** (the first months of play): the national
  stress index moves as it always has (an AR(1) process); prices and wages hold still.
* **Intermediate** (from play month ``intermediate_from``): inflation, the policy
  interest rate and wage pressure. Inflation follows an AR(1) process around a level
  drawn from the seed; the policy rate follows inflation; wages grow with inflation
  plus a premium drawn from the seed. Dearer credit lowers lending.
* **Advanced** (from play month ``advanced_from``): a business cycle in the stress
  index, and a shock: in a month drawn from the seed, stress and inflation jump, and
  fade as the process carries them.

Every series is prefix-stable: month ``t`` depends only on the seed and months before
it, so a stored world extended month by month stays exactly the same.

ASSUMPTION A-082 (placeholders until economic reference data is chosen): the levels,
speeds and sizes are the ``EconomyModel`` defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import EconomyModel
from .rng import stream

HISTORY, INITIAL, INTERMEDIATE, ADVANCED = "HISTORY", "INITIAL", "INTERMEDIATE", "ADVANCED"


@dataclass
class EconomyPath:
    stress: np.ndarray  # national stress index (positive = harder times)
    stage: list[str]
    inflation: np.ndarray  # annual rate
    price_index: np.ndarray  # 1.0 until inflation begins
    wage_index: np.ndarray  # 1.0 until wage pressure begins
    policy_rate: np.ndarray  # annual rate
    growth: np.ndarray  # annual growth in economic activity, as published
    lending: np.ndarray  # multiplier on lending volume from the economy
    events: list[list[str]] = field(default_factory=list)


def stage_of(econ: EconomyModel, play_month: int) -> str:
    if play_month <= 0:
        return HISTORY
    if not econ.stages or play_month < econ.intermediate_from:
        return INITIAL
    if play_month < econ.advanced_from:
        return INTERMEDIATE
    return ADVANCED


def economy_path(econ: EconomyModel, seed: int, months: int, anchor_t: int) -> EconomyPath:
    """The economy for ``months`` simulated months; ``anchor_t`` is the last history month."""
    rng = stream(seed, "economy.stress")
    shocks = rng.standard_normal(months) * econ.stress_sigma
    # Draws of their own, so the stress index of worlds without stages is unchanged.
    noise = stream(seed, "economy.inflation").standard_normal(months)
    growth_noise = stream(seed, "economy.growth").standard_normal(months)
    levels = stream(seed, "economy.levels")
    inflation_mean = float(levels.uniform(*econ.inflation_range))
    wage_premium = float(levels.uniform(*econ.wage_premium_range))
    neutral_rate = float(levels.uniform(*econ.policy_rate_range))
    cycle_phase = float(levels.uniform(0, 2 * np.pi))
    shock_at = econ.shock_month or econ.advanced_from + int(levels.integers(0, 12))
    shock_size = econ.shock_size or float(levels.uniform(*econ.shock_range))

    stress = np.zeros(months)
    inflation = np.zeros(months)
    price = np.ones(months)
    wages = np.ones(months)
    rate = np.full(months, neutral_rate)
    growth = np.zeros(months)
    lending = np.ones(months)
    stages: list[str] = []
    events: list[list[str]] = []
    level = econ.stress_mean
    infl = inflation_mean
    for t in range(months):
        p = t - anchor_t
        stage = stage_of(econ, p)
        happened: list[str] = []
        shocked = econ.stages and econ.shocks and stage == ADVANCED and p == shock_at
        if shocked:
            level += shock_size
            happened.append("SHOCK")
        level = econ.stress_mean + econ.stress_phi * (level - econ.stress_mean) + shocks[t]
        cycle = 0.0
        if stage == ADVANCED:
            cycle = econ.cycle_amplitude * np.sin(
                2 * np.pi * (p - econ.advanced_from) / econ.cycle_months + cycle_phase
            )
        stress[t] = level + cycle

        if stage in (INTERMEDIATE, ADVANCED):
            if stage == INTERMEDIATE and stages and stages[-1] in (HISTORY, INITIAL):
                happened.append("INTERMEDIATE")
            infl = (
                inflation_mean
                + econ.inflation_phi * (infl - inflation_mean)
                + (noise[t] * econ.inflation_sigma)
            )
            if shocked:
                infl += econ.shock_inflation
            infl = max(infl, 0.0)
            inflation[t] = infl
            rate[t] = max(0.05, neutral_rate + econ.rate_response * (infl - inflation_mean))
        if stage == ADVANCED and stages and stages[-1] != ADVANCED:
            happened.append("ADVANCED")
        if t > 0:
            price[t] = price[t - 1] * (1 + inflation[t]) ** (1 / 12)
            wage_growth = inflation[t] + wage_premium if inflation[t] > 0 else 0.0
            wages[t] = wages[t - 1] * (1 + wage_growth) ** (1 / 12)
        growth[t] = (
            econ.growth_mean
            - econ.growth_per_stress * stress[t]
            + (growth_noise[t] * econ.growth_sigma)
        )
        lending[t] = np.exp(-econ.lending_stress_elasticity * stress[t]) * np.exp(
            -econ.rate_elasticity * (rate[t] - neutral_rate)
        )
        stages.append(stage)
        events.append(happened)
    return EconomyPath(
        stress=stress, stage=stages, inflation=inflation, price_index=price, wage_index=wages,
        policy_rate=rate, growth=growth, lending=lending, events=events,
    )  # fmt: skip
