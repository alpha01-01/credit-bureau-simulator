"""Loan applications for a month of play.

Approved applications are the month's new loans. Declined applications are
added at a rate that depends on the kind of lender (ASSUMPTION A-024), drawn
from the lender's footprint with riskier borrowers more likely to be among
them: lenders decline the applicants they judge riskiest.
"""

from __future__ import annotations

import calendar
from datetime import date

import numpy as np
from django.db import transaction

from apps.world.models import Business, Lender, LoanApplication, Person, World

from .config import LENDERS, PRODUCTS
from .rng import stream

# Declined applications per approved loan (ASSUMPTION A-024).
DECLINES_PER_APPROVAL = {
    "COMMERCIAL_BANK": 0.6,
    "SAVINGS_AND_LOANS": 0.45,
    "MICROFINANCE": 0.35,
    "DIGITAL_LENDER": 1.0,
}
_PROFILES = {lp.code: lp for lp in LENDERS}


def ensure_applications(world: World, period: date) -> int:
    """Create the month's applications if they do not exist yet. Returns how many exist."""
    existing = LoanApplication.objects.filter(world=world, period=period).count()
    if existing:
        return existing
    if period > world.history_end:
        raise ValueError(f"The world has not lived through {period:%B %Y} yet")
    first = period.replace(day=1)
    people = list(
        Person.objects.filter(world=world).order_by("seq_no").values_list("id", "risk_z", "region")
    )
    businesses = list(
        Business.objects.filter(world=world)
        .order_by("seq_no")
        .values_list("id", "health_z", "region")
    )
    month_index = period.year * 12 + period.month - 1
    applications = []
    with transaction.atomic():
        for lender in Lender.objects.filter(world=world).order_by("seq_no"):
            profile = _PROFILES.get(lender.code)
            loans = list(
                lender.loans.filter(disbursement_date__gte=first, disbursement_date__lte=period)
                .select_related("customer")
                .order_by("account_number")
            )
            seq = 0
            for loan in loans:
                seq += 1
                applications.append(
                    LoanApplication(
                        world=world, lender=lender, period=period, seq=seq,
                        application_date=loan.disbursement_date,
                        person_id=loan.customer.person_id, business_id=loan.customer.business_id,
                        product=loan.product, approved=True, loan=loan,
                    )
                )  # fmt: skip
            if profile is None or not loans:
                continue
            rng = stream(world.seed, f"applications.declined:{lender.code}", month_index)
            declined = int(rng.poisson(len(loans) * DECLINES_PER_APPROVAL[lender.lender_type]))
            codes = list(profile.products)
            shares = np.array([profile.products[c] for c in codes])
            footprint = set(profile.regions) if profile.regions else None
            days = calendar.monthrange(period.year, period.month)[1]
            for _ in range(declined):
                product = codes[int(rng.choice(len(codes), p=shares / shares.sum()))]
                pool = businesses if PRODUCTS[product].borrower == "BUSINESS" else people
                applicant = _risky_pick(pool, footprint, rng)
                if applicant is None:
                    continue
                seq += 1
                is_business = pool is businesses
                applications.append(
                    LoanApplication(
                        world=world, lender=lender, period=period, seq=seq,
                        application_date=first.replace(day=int(rng.integers(1, days + 1))),
                        person_id=None if is_business else applicant,
                        business_id=applicant if is_business else None,
                        product=product, approved=False,
                    )
                )  # fmt: skip
        LoanApplication.objects.bulk_create(applications, batch_size=2000)
    return len(applications)


def _risky_pick(
    pool: list[tuple[int, float, str]], footprint: set[str] | None, rng: np.random.Generator
) -> int | None:
    """One applicant, with probability rising with hidden risk (weight e^(0.8 z))."""
    for _ in range(20):
        idx = int(rng.integers(len(pool)))
        pk, risk, region = pool[idx]
        if footprint is not None and region not in footprint:
            continue
        if rng.random() < min(1.0, float(np.exp(0.8 * risk)) / 4.0):
            return pk
    return None
