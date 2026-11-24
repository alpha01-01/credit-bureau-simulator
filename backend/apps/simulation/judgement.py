"""Turning bureau review cases into work items, with the answer key (roadmap S5).

Only the simulation may do this: the correct answer comes from the world.

  Match review:   is the record's real borrower the same person (or business)
                  as the candidate customer's real borrower?
  Triage:         do the proposed corrections restore the true values?
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from functools import lru_cache

import numpy as np

from apps.bureau.core.models import ProviderCustomerLink
from apps.bureau.quality.disputes import latest_record
from apps.bureau.quality.models import CaseType, CorrectionRecord, Decision, ReviewCase
from apps.org.models import Employee
from apps.standards.submission_template import FileKind
from apps.workitems.models import WorkItem
from apps.world.generation.identity import COMMON_FIRST_NAMES, FIRST_NAMES, SURNAMES
from apps.world.generation.rng import stream
from apps.world.models import Lender, LenderCustomer, Loan, ProviderFileRow
from apps.world.provider_files.truth import load_truth

from .assist import EXTENDED_DAYS
from .clock import TICKS_PER_DAY, Calendar
from .feed import WORK_ITEM_DAYS, due_tick
from .models import Delivery, EnquiryJudgement, Game

Borrower = tuple[str, int]  # ("person" | "business", world id)

TRIAGE_DIFFICULTY = {"F004": 0.15, "F002": 0.45, "F011": 0.6}

# The Data Operations team a new bureau starts with (ASSUMPTION A-023).
# Monthly gross salaries are placeholders (ASSUMPTION A-032, until reference R13).
STARTING_TEAM = (
    ("Senior Data Officer", {CaseType.MATCH_REVIEW: 0.88, CaseType.UNLOADABLE_TRIAGE: 0.9}, 0.75, "9500.00"),
    ("Data Officer", {CaseType.MATCH_REVIEW: 0.72, CaseType.UNLOADABLE_TRIAGE: 0.78}, 0.7, "6800.00"),
    ("Junior Data Officer", {CaseType.MATCH_REVIEW: 0.55, CaseType.UNLOADABLE_TRIAGE: 0.62}, 0.72, "4800.00"),
)  # fmt: skip


def hire_starting_team(game: Game, hired_on: date) -> list[Employee]:
    rng = stream(game.world.seed, "staff.starting-team")
    groups = list(SURNAMES)
    first = game.organization.allocate("last_employee_seq", len(STARTING_TEAM))
    team = []
    for n, (title, skills, morale, salary) in enumerate(STARTING_TEAM):
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
                monthly_salary=Decimal(salary),
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
    """Create a work item, with its answer, for every review case that has none.

    Only this function makes work items, one per case and numbered as the case, and
    case numbers only grow; so cases without one all come after the highest item
    number. Looking there first keeps the every-tick check cheap (P2.1).
    """
    last = (
        WorkItem.objects.filter(organization=game.organization)
        .order_by("-item_number")
        .values_list("item_number", flat=True)
        .first()
    )
    cases = list(
        ReviewCase.objects.filter(
            organization=game.organization, case_number__gt=last or 0, work_item__isnull=True
        )
        .select_related("record__file", "record__run__submission__institution", "dispute")
        .order_by("case_number")
    )
    if not cases:
        return 0
    truth_cache: dict[tuple[str, date, str], dict[int, dict[str, str]]] = {}
    items = []
    days = EXTENDED_DAYS if game.assist_extended_deadlines else WORK_ITEM_DAYS
    for case in cases:
        due = due_tick(tick, days)
        if case.case_type == CaseType.DISPUTE:
            correct, basis = _dispute_answer(game, case)
            difficulty = DISPUTE_DIFFICULTY
            if case.dispute is not None:  # due by the end of its statutory deadline
                cal = Calendar(game.clock_start)
                due = cal.first_tick_of_day(cal.index_of(case.dispute.due_date)) + TICKS_PER_DAY - 1
        elif case.case_type == CaseType.REGULATORY_RETURN:  # P3.7: one thing to do, by a date
            correct, basis = Decision.FILE_RETURN, "a return is filed, never refused"
            difficulty = 0.3
            cal = Calendar(game.clock_start)
            filed_by = date.fromisoformat(case.evidence["due"])
            due = cal.first_tick_of_day(cal.index_of(filed_by)) + TICKS_PER_DAY - 1
        elif case.case_type == CaseType.MATCH_REVIEW:
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
                due_tick=due,
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
    return _customer_borrower(game.world_id, customer_id)


def customer_borrowers(game: Game, customer_ids: list[int]) -> dict[int, Borrower]:
    """``customer_borrower`` for many customers at once (P3.5: the scorecard's debrief)."""
    firsts: dict[int, tuple[int, str, str]] = {}
    for pk, customer, code, number in ProviderCustomerLink.objects.filter(
        customer_id__in=customer_ids
    ).values_list("pk", "customer_id", "institution__institution_code", "provider_customer_number"):
        if customer not in firsts or pk < firsts[customer][0]:
            firsts[customer] = (pk, code, number)
    # Customers that lost a link to a correction: their first link may be the one moved.
    corrected = set(
        CorrectionRecord.objects.filter(from_customer_id__in=customer_ids).values_list(
            "from_customer_id", flat=True
        )
    )
    for customer in corrected:
        link = first_link(customer)
        if link is not None:
            firsts[customer] = (
                link.pk,
                link.institution.institution_code,
                link.provider_customer_number,
            )
    numbers = {number for _, _, number in firsts.values()}
    world = {
        (code, number): ("person", person)
        if person is not None
        else ("business", int(business or 0))
        for code, number, person, business in LenderCustomer.objects.filter(
            world_id=game.world_id, customer_number__in=numbers
        ).values_list("lender__code", "customer_number", "person_id", "business_id")
    }
    return {
        customer: world[(code, number)]
        for customer, (_, code, number) in firsts.items()
        if (code, number) in world
    }


def first_link(customer_id: int) -> ProviderCustomerLink | None:
    """The first provider link a bureau customer ever had: the one that created it.

    An upheld dispute moves a provider customer's link to a new customer (P2.7), so
    the links on a customer now are not always the ones it had. The links it lost are
    named by its corrections; the first of all of them, by id, never changes (P3.3).
    """
    ids = set(
        ProviderCustomerLink.objects.filter(customer_id=customer_id).values_list("pk", flat=True)
    )
    for correction in CorrectionRecord.objects.filter(from_customer_id=customer_id).select_related(
        "credit_account"
    ):
        record = latest_record(correction.credit_account)
        if record is None:
            continue
        moved = ProviderCustomerLink.objects.filter(
            institution_id=correction.credit_account.institution_id,
            provider_customer_number=record.cleansed.get("CustomerID", ""),
        ).values_list("pk", flat=True)
        ids.update(moved)
    return (
        ProviderCustomerLink.objects.filter(pk__in=ids)
        .select_related("institution")
        .order_by("pk")
        .first()
    )


# A customer's first provider link never changes, so neither does its answer (P2.1).
@lru_cache(maxsize=1 << 17)
def _customer_borrower(world_id: int, customer_id: int) -> Borrower:
    link = first_link(customer_id)
    if link is None:
        raise LookupError(f"Bureau customer {customer_id} has no provider link")
    lender_customer = LenderCustomer.objects.get(
        world_id=world_id,
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
    if record is None:
        raise ValueError(f"Case {case.case_number} has no record")
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
    if record is None:
        raise ValueError(f"Case {case.case_number} has no record")
    submission = record.run.submission
    code = submission.institution.institution_code
    delivery = Delivery.objects.get(game=game, bureau_file_id=record.file_id)
    loan_id = ProviderFileRow.objects.get(
        file_id=delivery.world_file_id, row_number=record.source_row_number
    ).loan_id
    key = (code, submission.reporting_period, record.file.file_kind)
    if key not in cache:
        cache[key] = {}
    if loan_id not in cache[key]:
        # Only this record's truth: rebuilding the provider's whole month is far slower.
        lender = Lender.objects.get(world=game.world, code=code)
        for r in load_truth(
            game.world.pk, lender.pk, code, submission.reporting_period, FileKind(key[2]),
            loan_ids=[loan_id],
        ):  # fmt: skip
            cache[key][r.loan_id] = r.values
    truth = cache[key][loan_id]
    wrong = {f: (v, truth.get(f)) for f, v in case.proposal.items() if truth.get(f) != v}
    if not wrong:
        return Decision.CORRECT_AND_LOAD, "the proposed corrections restore the true values"
    detail = ", ".join(f"{f}: proposed {p}, true {t}" for f, (p, t) in wrong.items())
    return Decision.RETURN_TO_PROVIDER, f"correction would load wrong data ({detail})"


# A dispute is a judgement on evidence the subject brings and the provider confirms;
# ASSUMPTION A-057: of middling difficulty.
DISPUTE_DIFFICULTY = 0.45


def _dispute_answer(game: Game, case: ReviewCase) -> tuple[str, str]:
    """Uphold if any disputed account is truly someone else's; else reject."""
    dispute = case.dispute
    if dispute is None or dispute.enquiry_id is None:
        raise ValueError(f"Case {case.case_number} is not a dispute about a report")
    judgement = EnquiryJudgement.objects.select_related("application").get(
        enquiry_id=dispute.enquiry_id
    )
    app = judgement.application
    subject: Borrower = (
        ("person", app.person_id) if app.person_id else ("business", int(app.business_id or 0))
    )
    foreign = []
    for code, number in dispute.accounts:
        loan = Loan.objects.select_related("customer").get(
            lender__world=game.world, lender__code=code, account_number=number
        )
        if _borrower(loan.customer) != subject:
            foreign.append(f"{code} {number}")
    if foreign:
        return Decision.UPHOLD_DISPUTE, f"not the subject's: {', '.join(foreign)}"
    return Decision.REJECT_DISPUTE, "every disputed account is the subject's own"
