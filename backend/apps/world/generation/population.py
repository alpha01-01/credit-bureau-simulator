"""Generate the world's people, businesses, lenders and branches.

Everything is returned as plain arrays/lists in a deterministic order. The
loan engine works on these arrays; persistence writes them to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from . import identity
from .config import (
    DEFAULT_NAME_GROUPS,
    EMPLOYMENT_TYPES,
    REGION_NAME_GROUPS,
    REGION_TOWNS,
    REGIONS,
    SECTORS,
    LenderProfile,
    WorldConfig,
)
from .rng import stream

REGION_CODES: tuple[str, ...] = tuple(REGIONS)
SECTOR_CODES: tuple[str, ...] = tuple(SECTORS)
EMPLOYMENT_CODES: tuple[str, ...] = tuple(e.code for e in EMPLOYMENT_TYPES)

# Sectors people in each employment type tend to work in.
_EMPLOYMENT_SECTORS: dict[str, dict[str, float]] = {
    "SALARIED_PUBLIC": {"PUBLIC_ADMINISTRATION": 0.45, "EDUCATION": 0.30, "HEALTH": 0.25},
    "SALARIED_PRIVATE": {"FINANCE": 0.12, "SERVICES": 0.22, "MANUFACTURING": 0.14, "ICT": 0.10,
                         "TRADE": 0.14, "MINING": 0.08, "CONSTRUCTION": 0.08, "HOSPITALITY": 0.06,
                         "TRANSPORT": 0.06},
    "SELF_EMPLOYED": {"TRADE": 0.40, "SERVICES": 0.18, "TRANSPORT": 0.12, "AGRICULTURE": 0.12,
                      "CONSTRUCTION": 0.08, "HOSPITALITY": 0.10},
    "INFORMAL": {"TRADE": 0.45, "AGRICULTURE": 0.35, "SERVICES": 0.10, "TRANSPORT": 0.10},
    "RETIRED": {"PUBLIC_ADMINISTRATION": 0.5, "EDUCATION": 0.3, "SERVICES": 0.2},
    "UNEMPLOYED": {"SERVICES": 1.0},
}  # fmt: skip


@dataclass
class People:
    n: int
    risk_z: np.ndarray  # latent risk, ~N(0,1); higher = riskier
    income: np.ndarray  # int64 pesewas per month
    stability: np.ndarray  # float 0..1
    employment: np.ndarray  # index into EMPLOYMENT_CODES
    sector: np.ndarray  # index into SECTOR_CODES
    region: np.ndarray  # index into REGION_CODES
    birth_date: np.ndarray  # datetime64[D]
    gender: list[str]
    name_group: list[str]
    first_name: list[str]
    middle_name: list[str | None]
    last_name: list[str]
    ghana_card: list[str]
    phone_primary: list[str]
    phone_secondary: list[str | None]
    town: list[str]
    credit_demand: np.ndarray  # relative propensity to apply for credit


@dataclass
class Businesses:
    n: int
    owner: np.ndarray  # index into People
    health_z: np.ndarray  # latent risk, ~N(0,1); higher = riskier
    revenue: np.ndarray  # int64 pesewas per month
    sector: np.ndarray
    region: np.ndarray
    size_band: list[str]
    registered_name: list[str]
    trading_name: list[str | None]
    registration_number: list[str]
    tin: list[str]
    registration_date: list[date]
    town: list[str]


@dataclass
class Branch:
    lender: int
    code: str
    name: str
    region: int
    town: str


def _weighted_choice(rng: np.random.Generator, options: dict[str, float], n: int) -> list[str]:
    keys = list(options)
    p = np.array(list(options.values()), dtype=float)
    return [keys[i] for i in rng.choice(len(keys), size=n, p=p / p.sum()).tolist()]


def generate_people(config: WorldConfig) -> People:
    n = config.scale.individuals
    seed = config.seed

    rng = stream(seed, "people.core")
    region_p = np.array(list(REGIONS.values()))
    region = rng.choice(len(REGION_CODES), size=n, p=region_p / region_p.sum())

    emp_p = np.array([e.share for e in EMPLOYMENT_TYPES])
    employment = rng.choice(len(EMPLOYMENT_TYPES), size=n, p=emp_p / emp_p.sum())

    risk_z = rng.standard_normal(n)

    # Income: lognormal by employment type, slightly correlated with lower risk,
    # and higher in Greater Accra and Ashanti.
    medians = np.array([e.median_income for e in EMPLOYMENT_TYPES])[employment]
    sigmas = np.array([e.income_sigma for e in EMPLOYMENT_TYPES])[employment]
    urban = np.isin(region, [REGION_CODES.index("Greater Accra"), REGION_CODES.index("Ashanti")])
    log_income = (
        np.log(medians)
        + sigmas * rng.standard_normal(n)
        - 0.12 * risk_z
        + np.where(urban, 0.15, -0.05)
    )
    income = np.rint(np.exp(log_income) * 100).astype(np.int64)
    income = np.maximum(income, 20_000)  # at least GHS 200

    base_stability = np.array([e.stability for e in EMPLOYMENT_TYPES])[employment]
    stability = np.clip(base_stability + 0.08 * rng.standard_normal(n), 0.0, 1.0)

    demand = np.array([e.credit_demand for e in EMPLOYMENT_TYPES])[employment] * rng.uniform(
        0.3, 1.7, n
    )

    # Ages 18-75 at the end of history; retirees older.
    end = np.datetime64(config.history_end, "D")
    retired = employment == EMPLOYMENT_CODES.index("RETIRED")
    age_years = np.where(retired, rng.uniform(60, 80, n), 18 + rng.gamma(4.0, 4.2, n))
    age_years = np.clip(age_years, 18.2, 85)
    birth_date = end - np.rint(age_years * 365.25).astype("timedelta64[D]")

    # Sector by employment type
    sector = np.empty(n, dtype=np.int64)
    rng_sector = stream(seed, "people.sector")
    for e_idx, code in enumerate(EMPLOYMENT_CODES):
        mask = np.flatnonzero(employment == e_idx)
        options = _EMPLOYMENT_SECTORS[code]
        picks = _weighted_choice(rng_sector, options, len(mask))
        sector[mask] = [SECTOR_CODES.index(s) for s in picks]

    # Identity
    rng_id = stream(seed, "people.identity")
    gender = ["M" if g else "F" for g in (rng_id.random(n) < 0.49).tolist()]
    name_group = []
    for r_idx in region.tolist():
        groups = REGION_NAME_GROUPS.get(REGION_CODES[r_idx], DEFAULT_NAME_GROUPS)
        name_group.append(_weighted_choice(rng_id, groups, 1)[0])
    names = identity.person_names(rng_id, name_group, gender)
    cards = identity.ghana_card_numbers(stream(seed, "people.ghana_card"), n)
    phones = identity.phone_numbers(stream(seed, "people.phones"), 2 * n)
    rng_phone = stream(seed, "people.phone_second")
    has_second = rng_phone.random(n) < 0.35
    rng_town = stream(seed, "people.town")
    town = [
        REGION_TOWNS[REGION_CODES[r]][int(rng_town.integers(len(REGION_TOWNS[REGION_CODES[r]])))]
        for r in region.tolist()
    ]

    return People(
        n=n,
        risk_z=risk_z,
        income=income,
        stability=stability,
        employment=employment.astype(np.int64),
        sector=sector,
        region=region.astype(np.int64),
        birth_date=birth_date,
        gender=gender,
        name_group=name_group,
        first_name=[f for f, _, _ in names],
        middle_name=[m for _, m, _ in names],
        last_name=[last for _, _, last in names],
        ghana_card=cards,
        phone_primary=phones[:n],
        phone_secondary=[phones[n + i] if has_second[i] else None for i in range(n)],
        town=town,
        credit_demand=demand,
    )


def generate_businesses(config: WorldConfig, people: People) -> Businesses:
    n = config.scale.businesses
    seed = config.seed
    rng = stream(seed, "business.core")

    # Owners: self-employed adults preferred, some salaried.
    weights = np.where(
        people.employment == EMPLOYMENT_CODES.index("SELF_EMPLOYED"),
        6.0,
        np.where(people.employment == EMPLOYMENT_CODES.index("SALARIED_PRIVATE"), 1.5, 0.4),
    )
    owner = rng.choice(people.n, size=n, replace=False, p=weights / weights.sum())

    sector_options = {s: 1.0 for s in SECTOR_CODES if s != "PUBLIC_ADMINISTRATION"}
    sector_options.update({"TRADE": 4.0, "SERVICES": 2.5, "AGRICULTURE": 2.0, "CONSTRUCTION": 1.5})
    sector = np.array([SECTOR_CODES.index(s) for s in _weighted_choice(rng, sector_options, n)])

    # Businesses mostly operate where their owner lives.
    moved = rng.random(n) < 0.15
    region_p = np.array(list(REGIONS.values()))
    region = np.where(
        moved,
        rng.choice(len(REGION_CODES), size=n, p=region_p / region_p.sum()),
        people.region[owner],
    )

    size_roll = rng.random(n)
    size_band = [
        "MICRO" if r < 0.60 else "SMALL" if r < 0.88 else "MEDIUM" if r < 0.98 else "LARGE"
        for r in size_roll
    ]
    size_revenue = {"MICRO": 9_000, "SMALL": 45_000, "MEDIUM": 250_000, "LARGE": 1_500_000}
    medians = np.array([size_revenue[s] for s in size_band], dtype=float)
    health_z = 0.6 * people.risk_z[owner] + 0.8 * rng.standard_normal(n)
    revenue = np.rint(
        np.exp(np.log(medians) + 0.6 * rng.standard_normal(n) - 0.1 * health_z) * 100
    ).astype(np.int64)

    end = config.history_end
    age_days = np.rint(rng.gamma(2.0, 4.0, n) * 365.25).astype(int) + 200
    registration_date = [end - timedelta(days=int(d)) for d in age_days.tolist()]

    rng_id = stream(seed, "business.identity")
    owner_surnames = [people.last_name[i] for i in owner.tolist()]
    names = identity.business_names(
        rng_id, [SECTOR_CODES[s] for s in sector.tolist()], owner_surnames
    )
    trading = [None if rng_id.random() < 0.7 else nm.rsplit(" ", 1)[0] for nm in names]
    # ASSUMPTION A-008: registration and TIN formats.
    reg_numbers = rng_id.choice(9_000_000, size=n, replace=False) + 1_000_000
    tins = rng_id.choice(9_000_000, size=n, replace=False) + 1_000_000
    registration_number = [f"CS{v:09d}" for v in reg_numbers.tolist()]
    tin = [f"C000{v:07d}" for v in tins.tolist()]
    rng_town = stream(seed, "business.town")
    town = [
        REGION_TOWNS[REGION_CODES[r]][int(rng_town.integers(len(REGION_TOWNS[REGION_CODES[r]])))]
        for r in region.tolist()
    ]

    return Businesses(
        n=n,
        owner=owner.astype(np.int64),
        health_z=health_z,
        revenue=revenue,
        sector=sector.astype(np.int64),
        region=region.astype(np.int64),
        size_band=size_band,
        registered_name=names,
        trading_name=trading,
        registration_number=registration_number,
        tin=tin,
        registration_date=registration_date,
        town=town,
    )


def generate_branches(config: WorldConfig) -> list[Branch]:
    """Branches per lender. Branch 0 of each lender is its head office."""
    branches: list[Branch] = []
    region_p = np.array(list(REGIONS.values()))
    for l_idx, lender in enumerate(config.lenders):
        rng = stream(config.seed, f"branches.{lender.code}")
        footprint = _footprint(lender)
        hq_region = (
            accra if (accra := REGION_CODES.index("Greater Accra")) in footprint else footprint[0]
        )
        hq_town = REGION_TOWNS[REGION_CODES[hq_region]][0]
        branches.append(
            Branch(l_idx, f"{lender.code}-001", f"{hq_town} Head Office", hq_region, hq_town)
        )
        p = region_p[list(footprint)]
        for b in range(1, lender.branch_count):
            # Guarantee every footprint region gets a branch before doubling up.
            r = (
                footprint[b - 1]
                if b - 1 < len(footprint)
                else int(rng.choice(footprint, p=p / p.sum()))
            )
            towns = REGION_TOWNS[REGION_CODES[r]]
            town = towns[int(rng.integers(len(towns)))]
            name = f"{town} Branch"
            taken = {br.name for br in branches if br.lender == l_idx}
            suffix = 2
            while name in taken:
                name = f"{town} Branch {suffix}"
                suffix += 1
            branches.append(Branch(l_idx, f"{lender.code}-{b + 1:03d}", name, r, town))
    return branches


def _footprint(lender: LenderProfile) -> list[int]:
    if lender.regions is None:
        return list(range(len(REGION_CODES)))
    return [REGION_CODES.index(r) for r in lender.regions]


def footprint_mask(lender: LenderProfile, regions: np.ndarray) -> np.ndarray:
    return np.isin(regions, _footprint(lender))
