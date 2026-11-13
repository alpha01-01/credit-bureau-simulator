"""S1 — World generator: determinism, invariants, identity formats and calibration.

In-memory tests use the "tiny" and "small" scales so the suite stays fast.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from dataclasses import replace
from functools import cache

import numpy as np
import pytest

from apps.standards.submission_template import luhn_check_digit
from apps.world.generation import GeneratedWorld, build_world
from apps.world.generation.config import SCALES, EconomyModel, WorldConfig
from apps.world.generation.engine import (
    ACTIVE,
    PAID_OFF,
    SETTLED,
    WRITTEN_OFF,
    scheduled_balance,
    simulate,
)
from apps.world.generation.identity import MOBILE_PREFIXES
from apps.world.generation.population import generate_branches, generate_businesses, generate_people
from apps.world.generation.stats import compute_stats


@cache
def small_world(seed: int = 3) -> GeneratedWorld:
    return build_world(seed, "small")


def digest(world: GeneratedWorld) -> str:
    """Fingerprint of everything the generator produces."""
    h = hashlib.sha256()
    p = world.people
    for arr in (p.risk_z, p.income, p.stability, p.employment, p.sector, p.region, p.birth_date):
        h.update(np.ascontiguousarray(arr).tobytes())
    h.update("|".join(p.ghana_card + p.first_name + p.last_name + p.phone_primary).encode())
    b = world.businesses
    h.update(np.ascontiguousarray(b.health_z).tobytes())
    h.update("|".join(b.registered_name + b.tin).encode())
    book = world.result.book
    for name in book.SCHEMA:
        h.update(np.ascontiguousarray(book[name]).tobytes())
    for name in world.result.snapshots.FIELDS:
        h.update(np.ascontiguousarray(world.result.snapshots.column(name)).tobytes())
    h.update(np.ascontiguousarray(world.result.stress).tobytes())
    return h.hexdigest()


# --- Determinism ---------------------------------------------------------------


def test_same_seed_produces_identical_world() -> None:
    assert digest(build_world(11, "tiny")) == digest(build_world(11, "tiny"))


def test_different_seeds_produce_different_worlds() -> None:
    assert digest(build_world(11, "tiny")) != digest(build_world(12, "tiny"))


# --- Identity formats (ASSUMPTIONS A-002, A-003) -----------------------------------


def test_ghana_card_numbers_are_unique_and_check_digit_valid() -> None:
    cards = small_world().people.ghana_card
    assert len(set(cards)) == len(cards)
    for card in cards:
        match = re.fullmatch(r"GHA-(\d{9})-(\d)", card)
        assert match, card
        assert luhn_check_digit(match.group(1)) == int(match.group(2))


def test_phone_numbers_are_unique_ten_digit_mobile_numbers() -> None:
    people = small_world().people
    phones = people.phone_primary + [p for p in people.phone_secondary if p]
    assert len(set(phones)) == len(phones)
    for phone in phones:
        assert re.fullmatch(r"0\d{9}", phone), phone
        assert phone[:3] in MOBILE_PREFIXES


def test_people_are_adults_with_positive_income() -> None:
    world = small_world()
    end = np.datetime64(world.config.history_end, "D")
    ages = (end - world.people.birth_date).astype(int) / 365.25
    assert ages.min() >= 18
    assert (world.people.income > 0).all()


# --- Loan book invariants --------------------------------------------------------


def test_instalment_counts_are_consistent() -> None:
    book = small_world().result.book
    assert (book["k_paid"] >= 0).all()
    assert (book["k_paid"] <= book["k_due"] + (book["status"] == SETTLED) * book["term"]).all()
    assert (book["k_due"] <= book["term"]).all()
    # Instalments repay at least the principal: interest is never negative.
    assert (book["installment"] * book["term"] >= book["principal"]).all()


def test_closed_loans_have_zero_balance_and_live_loans_never_negative() -> None:
    snaps = small_world().result.snapshots
    status = snaps.column("status")
    outstanding = snaps.column("outstanding")
    closed = (status == PAID_OFF) | (status == SETTLED)
    assert (outstanding[closed] == 0).all()
    assert (outstanding >= 0).all()
    assert (snaps.column("principal_balance") >= 0).all()


def test_days_past_due_match_arrears() -> None:
    world = small_world()
    snaps = world.result.snapshots
    live = snaps.column("status") == ACTIVE
    dpd = snaps.column("dpd")[live]
    arrears = snaps.column("arrears")[live]
    assert (dpd >= 0).all()
    # Days past due only when something is owed.
    assert ((dpd > 0) <= (arrears > 0)).all()
    # Owed but 0 DPD only when the instalment fell due on the reporting date itself:
    # due day 28 and a month that ends on the 28th (February in a non-leap year).
    zero_dpd_in_arrears = (dpd == 0) & (arrears > 0)
    months = world.result.months[snaps.column("month")[live][zero_dpd_in_arrears]]
    month_ends = (months + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    assert all(str(d).endswith("-02-28") for d in month_ends)


def test_written_off_loans_reached_their_lenders_threshold() -> None:
    world = small_world()
    snaps = world.result.snapshots
    written = snaps.column("status") == WRITTEN_OFF
    loans = snaps.column("loan")[written]
    thresholds = np.array([lp.writeoff_dpd for lp in world.config.lenders])[
        world.result.book["lender"][loans]
    ]
    assert written.any()
    assert (snaps.column("dpd")[written] >= thresholds).all()


def test_each_loan_has_one_contiguous_monthly_history_ending_at_closure() -> None:
    world = small_world()
    snaps = world.result.snapshots
    loan = snaps.column("loan")
    month = snaps.column("month")
    order = np.lexsort((month, loan))
    loan, month = loan[order], month[order]
    status = snaps.column("status")[order]
    same_loan = loan[1:] == loan[:-1]
    # Consecutive months, no gaps, no duplicates.
    assert (month[1:][same_loan] - month[:-1][same_loan] == 1).all()
    # Nothing is recorded after a loan's terminal month.
    last_of_loan = np.append(~same_loan, True)
    terminal = status != ACTIVE
    assert (terminal <= last_of_loan).all()


def test_scheduled_balance_amortises_to_zero() -> None:
    principal = np.array([1_000_000.0])
    rate = np.array([0.025])
    term = np.array([24])
    inst = np.array([float(np.ceil(principal[0] * rate[0] / (1 - (1 + rate[0]) ** -24)))])
    balances = [scheduled_balance(principal, rate, inst, np.array([k]), term)[0] for k in range(25)]
    assert balances[0] == 1_000_000
    assert balances[-1] == 0
    assert all(a > b for a, b in itertools.pairwise(balances))


# --- Calibration and behaviour (ASSUMPTION A-009) ----------------------------------


@pytest.mark.parametrize("seed", [1, 2])
def test_default_rate_is_plausible(seed: int) -> None:
    stats = build_world(seed, "small").stats
    assert 0.03 <= stats.default_rate_12m <= 0.18


def test_hidden_risk_predicts_default() -> None:
    """The point of a credit bureau: riskier people really do default more."""
    world = small_world()
    book = world.result.book
    persons = book["kind"] == 0
    defaulted = book["first_90_month"] >= 0
    z = world.people.risk_z[book["borrower"][persons]]
    gap = z[defaulted[persons]].mean() - z[~defaulted[persons]].mean()
    assert gap > 0.5


def test_economic_stress_raises_defaults() -> None:
    def rate(stress_mean: float) -> float:
        config = replace(
            WorldConfig(seed=5, scale=SCALES["small"]),
            economy=replace(EconomyModel(), stress_mean=stress_mean),
        )
        people = generate_people(config)
        businesses = generate_businesses(config, people)
        result = simulate(config, people, businesses, generate_branches(config))
        return compute_stats(config, result).default_rate_12m

    assert rate(1.0) > rate(-1.0) + 0.02


def test_microfinance_loans_default_more_than_bank_personal_loans() -> None:
    """Pooled over several seeds so the comparison is not at the mercy of one economy."""
    micro, personal = [], []
    for seed in (1, 2, 3):
        rates = build_world(seed, "small").stats.default_rate_by_product
        micro.append(rates["MICRO_BUSINESS_LOAN"])
        personal.append(rates["PERSONAL_LOAN"])
    assert np.mean(micro) > np.mean(personal)
