"""Turning bureau review cases into work items, with the answer key (roadmap S5).

Only the simulation may do this: the correct answer comes from the world.

  Match review:   is the record's real borrower the same person (or business)
                  as the candidate customer's real borrower?
  Triage:         do the proposed corrections restore the true values?
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np

from apps.bureau.core.models import ProviderCustomerLink
from apps.bureau.quality.models import CaseType, Decision, ReviewCase
from apps.org.models import Employee
from apps.standards.submission_template import FileKind
from apps.workitems.models import WorkItem
from apps.world.generation.identity import COMMON_FIRST_NAMES, FIRST_NAMES, SURNAMES
from apps.world.generation.rng import stream
from apps.world.models import Lender, LenderCustomer, ProviderFileRow
from apps.world.provider_files.truth import load_truth

from .models import Delivery, Game

Borrower = tuple[str, int]  # ("person" | "business", world id)

TRIAGE_DIFFICULTY = {"F004": 0.15, "F002": 0.45, "F011": 0.6}

# The Data Operations team a new bureau starts with (ASSUMPTION A-023).
STARTING_TEAM = (
    ("Senior Data Officer", {CaseType.MATCH_REVIEW: 0.88, CaseType.UNLOADABLE_TRIAGE: 0.9}, 0.75),
    ("Data Officer", {CaseType.MATCH_REVIEW: 0.72, CaseType.UNLOADABLE_TRIAGE: 0.78}, 0.7),
    ("Junior Data Officer", {CaseType.MATCH_REVIEW: 0.55, CaseType.UNLOADABLE_TRIAGE: 0.62}, 0.72),
)


def hire_starting_team(game: Game, hired_on: date) -> list[Employee]:
    rng = stream(game.world.seed, "staff.starting-team")
    groups = list(SURNAMES)
    first = game.organization.allocate("last_employee_seq", len(STARTING_TEAM))
    team = []
    for n, (title, skills, morale) in enumerate(STARTING_TEAM):
        group = groups[int(rng.integers(len(groups)))]
        gender = "F" if rng.random() < 0.5 else "M"
        names = FIRST_NAMES[group][gender] + COMMON_FIRST_NAMES[gender]
        team.append(
            Employee(
                organization=game.organization,
                employee_number=f"E{first + n:04d}",
                first_name=names[int(rng.integers(len(names)))],
                last_name=SURNAMES[group][int(rng.integers(len(SURNAMES[group])))],
                job_title=title,
                skills={str(k): v for k, v in skills.items()},
                morale=morale,
                hired_on=hired_on,
            )
        )
    return Employee.objects.bulk_create(team)


def rng_for(game: Game) -> Callable[[int], np.random.Generator]:
    seed = game.world.seed

    def make(item_number: int) -> np.random.Generator:
        return stream(seed, f"work-item:{item_number}")

    return make


def sync_work_items(game: Game, tick: int) -> int:
    """Create a work item, with its answer, for every review case that has none."""
    cases = list(
        ReviewCase.objects.filter(organization=game.organization, work_item__isnull=True)
        .select_related("record__file", "record__run__submission__institution")
        .order_by("case_number")
    )
    if not cases:
        return 0
    truth_cache: dict[tuple[str, date, str], dict[int, dict[str, str]]] = {}
    items = []
    for case in cases:
        if case.case_type == CaseType.MATCH_REVIEW:
            correct, basis = _match_answer(game, case)
            score = case.score if case.score is not None else 0.5
            difficulty = float(np.clip(1 - abs(score - 0.6) / 0.45, 0.1, 0.95))
        else:
            correct, basis = _triage_answer(game, case, truth_cache)
            difficulty = max(
                (TRIAGE_DIFFICULTY.get(e["rule"], 0.5) for e in case.evidence.get("errors", [])),
                default=0.5,
            )
        items.append(
            WorkItem(
                organization=game.organization,
                item_number=case.case_number,
                case=case,
                item_type=case.case_type,
                difficulty=round(difficulty, 3),
                created_tick=tick,
                correct_decision=correct,
                correct_basis=basis[:300],
            )
        )
    WorkItem.objects.bulk_create(items)
    return len(items)


# --- The answer key -----------------------------------------------------------------


def record_borrower(game: Game, file_id: int, row_number: int) -> Borrower:
    """The real borrower behind a row of a delivered file."""
    delivery = Delivery.objects.get(game=game, bureau_file_id=file_id)
    loan = (
        ProviderFileRow.objects.select_related("loan__customer")
        .get(file_id=delivery.world_file_id, row_number=row_number)
        .loan
    )
    return _borrower(loan.customer)


def customer_borrower(game: Game, customer_id: int) -> Borrower:
    """The real borrower behind a bureau customer: via the first provider link that created it."""
    link = (
        ProviderCustomerLink.objects.filter(customer_id=customer_id)
        .select_related("institution")
        .order_by("pk")
        .first()
    )
    if link is None:
        raise LookupError(f"Bureau customer {customer_id} has no provider link")
    lender_customer = LenderCustomer.objects.get(
        world=game.world,
        lender__code=link.institution.institution_code,
        customer_number=link.provider_customer_number,
    )
    return _borrower(lender_customer)


def _borrower(customer: LenderCustomer) -> Borrower:
    if customer.person_id is not None:
        return ("person", customer.person_id)
    if customer.business_id is None:
        raise LookupError(f"Lender customer {customer.pk} has no borrower")
    return ("business", customer.business_id)


def _match_answer(game: Game, case: ReviewCase) -> tuple[str, str]:
    record = case.record
    actual = record_borrower(game, record.file_id, record.source_row_number)
    if case.candidate_customer_id is None:
        return Decision.DIFFERENT_CUSTOMER, "no candidate customer"
    candidate = customer_borrower(game, case.candidate_customer_id)
    if actual == candidate:
        return Decision.SAME_CUSTOMER, f"same real {actual[0]} (world id {actual[1]})"
    return (
        Decision.DIFFERENT_CUSTOMER,
        f"record is world {actual[0]} {actual[1]}; candidate is world {candidate[0]} {candidate[1]}",
    )


def _triage_answer(
    game: Game, case: ReviewCase, cache: dict[tuple[str, date, str], dict[int, dict[str, str]]]
) -> tuple[str, str]:
    record = case.record
    submission = record.run.submission
    code = submission.institution.institution_code
    key = (code, submission.reporting_period, record.file.file_kind)
    if key not in cache:
        lender = Lender.objects.get(world=game.world, code=code)
        cache[key] = {
            r.loan_id: r.values
            for r in load_truth(
                game.world.pk, lender.pk, code, submission.reporting_period, FileKind(key[2])
            )
        }
    delivery = Delivery.objects.get(game=game, bureau_file_id=record.file_id)
    loan_id = ProviderFileRow.objects.get(
        file_id=delivery.world_file_id, row_number=record.source_row_number
    ).loan_id
    truth = cache[key][loan_id]
    wrong = {f: (v, truth.get(f)) for f, v in case.proposal.items() if truth.get(f) != v}
    if not wrong:
        return Decision.CORRECT_AND_LOAD, "the proposed corrections restore the true values"
    detail = ", ".join(f"{f}: proposed {p}, true {t}" for f, (p, t) in wrong.items())
    return Decision.RETURN_TO_PROVIDER, f"correction would load wrong data ({detail})"
