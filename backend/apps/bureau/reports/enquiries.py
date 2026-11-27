"""Enquiries and the basic credit report (roadmap S6).

A subscriber searches by the subject's identifier. On a hit the bureau
returns a report built from what it holds at that moment: the subject's
details, every account with its latest observation and recent payment
history, and how many times the subject was searched in the last year.

ASSUMPTION A-026: the report layout ("SIMB-R0") is a placeholder until a
real report layout (reference R9) is available.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import connection, transaction
from django.db.models import Max

from apps.bureau.core.models import (
    AccountObservation,
    CourtJudgment,
    CreditAccount,
    Customer,
    CustomerIdentifier,
    DishonouredCheque,
    Enquiry,
    EnquiryOutcome,
)
from apps.bureau.quality.disputes import disputed_accounts
from apps.bureau.reports.models import CreditScore
from apps.org.models import Organization
from apps.standards.compliance_rules import LEGAL_RETENTION_YEARS
from apps.standards.enquiry import PURPOSES
from apps.standards.submission_template import (
    CLOSED_STATUS_ON_FILE,
    CODE_LISTS,
    OPEN_STATUS_ON_FILE,
    WRITTEN_OFF_STATUS_ON_FILE,
)

REPORT_LAYOUT = "SIMB-R1"  # R1 adds dishonoured cheques and judgments (P2.0c)
BUSINESS_LAYOUT = "SIMB-B1"  # the business credit report (P3.11)
BUSINESS_REPORT = "BUSINESS_REPORT"
HISTORY_MONTHS = 12


class EnquiryError(Exception):
    pass


def enquire(
    organization: Organization,
    subscriber: Any,
    product_code: str,
    purpose: str,
    consent_reference: str,
    identifier_type: str,
    identifier_value: str,
    subject_name: str,
    at: datetime,
    include_score: bool = False,
    memo: dict[Any, Any] | None = None,
) -> Enquiry:
    """Search for a subject and log the enquiry, with the report delivered on a hit.

    ``memo`` carries lookups a caller knows cannot change meanwhile (P4.0: the
    simulation's tick), see ``build_report``.
    """
    if purpose not in PURPOSES:
        raise EnquiryError(f"{purpose!r} is not a permissible purpose")
    if not consent_reference:
        raise EnquiryError("An enquiry needs the subject's consent reference")
    with transaction.atomic(savepoint=False):
        identifier = (
            CustomerIdentifier.objects.filter(
                organization=organization,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
            )
            .select_related("customer__individual", "customer__business")
            .first()
        )
        customer = identifier.customer if identifier else None
        report: dict[str, Any] = {}
        if customer is not None and product_code == BUSINESS_REPORT:
            report = build_business_report(customer, at)
        elif customer is not None:
            report = build_report(customer, at, include_score, memo)
        seq = organization.allocate("last_enquiry_seq")
        return Enquiry.objects.create(
            organization=organization,
            enquiry_reference=f"EQ{seq:010d}",
            subscriber=subscriber,
            product_code=product_code,
            purpose=purpose,
            consent_reference=consent_reference,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            subject_name=subject_name[:200],
            enquired_at=at,
            outcome=EnquiryOutcome.HIT if customer else EnquiryOutcome.NO_HIT,
            customer=customer,
            accounts_reported=len(report.get("accounts", report.get("facilities", []))),
            report=report,
        )


# Keys in a caller's memo (P4.0): the bureau's retention period, and the accounts under
# an open dispute. A caller that files a dispute or changes the retention period while
# the memo lives drops the key.
RETENTION, DISPUTED, HOLDERS = "retention-years", "disputed-accounts", "cheque-holders"


def build_report(
    customer: Customer,
    at: datetime,
    include_score: bool = False,
    memo: dict[Any, Any] | None = None,
) -> dict[str, Any]:
    memo = {} if memo is None else memo
    as_of = at.date()
    if RETENTION not in memo:
        memo[RETENTION] = Organization.objects.values_list("retention_years", flat=True).get(
            pk=customer.organization_id
        )
    accounts, held_too_long = _retained(customer, as_of, memo[RETENTION])
    since = (as_of.replace(day=1) - timedelta(days=HISTORY_MONTHS * 31)).replace(day=1)
    history: dict[int, list[AccountObservation]] = defaultdict(list)
    for obs in AccountObservation.objects.filter(
        credit_account__in=accounts, is_current=True, reporting_date__lte=as_of,
        reporting_date__gte=since,
    ).order_by("reporting_date"):  # fmt: skip
        history[obs.credit_account_id].append(obs)

    rows: list[dict[str, Any]] = []
    states: list[tuple[str, Decimal | None, int | None]] = []  # status, balance, days past due
    if DISPUTED not in memo:
        memo[DISPUTED] = disputed_accounts(customer.organization_id)
    disputed = memo[DISPUTED]  # flagged while open (P2.7)
    for account in accounts:
        observations = history.get(account.pk, [])
        latest = observations[-1] if observations else None
        status = latest.facility_status if latest else account.account_status
        states.append(
            (
                status,
                latest.outstanding_balance if latest else None,
                latest.days_past_due if latest else None,
            )
        )
        rows.append(
            {
                "lender": account.institution.institution_name,
                "account": _mask(account.facility_account_number),
                "facility_type": account.facility_type,
                "opened": _iso(account.disbursement_date),
                "original_amount": str(account.original_amount),
                "status": status,
                "balance": str(latest.outstanding_balance) if latest else None,
                "arrears": str(latest.arrears_amount) if latest else None,
                "days_past_due": latest.days_past_due if latest else None,
                "last_reported": _iso(latest.reporting_date) if latest else None,
                "worst_days_past_due_12m": max(
                    (o.days_past_due for o in observations), default=None
                ),
                "disputed": (
                    account.institution.institution_code,
                    account.facility_account_number,
                )
                in disputed,
                "history": [
                    {"month": f"{o.reporting_date:%Y-%m}", "days_past_due": o.days_past_due}
                    for o in observations
                ],
            }
        )

    open_states = [st for st in states if st[0] in OPEN_STATUS_ON_FILE]
    total = sum((st[1] for st in open_states if st[1] is not None), Decimal("0"))
    previous_enquiries = Enquiry.objects.filter(
        customer=customer, enquired_at__gte=at - timedelta(days=365), enquired_at__lt=at
    ).count()
    cheques_held, judgments_held = _holders(customer.organization_id, memo)
    cheques = cheques_on_file(customer, as_of) if customer.pk in cheques_held else []
    judgments = judgments_on_file(customer, as_of) if customer.pk in judgments_held else []
    score = _score(customer) if include_score else None
    return {
        "layout": REPORT_LAYOUT,
        "as_of": as_of.isoformat(),
        "subject": _subject(customer),
        "summary": {
            "accounts": len(rows),
            "open_accounts": len(open_states),
            "total_outstanding": str(total),
            "accounts_in_arrears": sum(1 for st in open_states if (st[2] or 0) > 0),
            "written_off": sum(1 for st in states if st[0] in WRITTEN_OFF_STATUS_ON_FILE),
            "enquiries_last_12_months": previous_enquiries,
            "dishonoured_cheques": len(cheques),
            "judgments": len(judgments),
        },
        **({"score": score} if include_score else {}),
        # Closed accounts kept past the legal limit, by a longer retention (P3.7).
        **({"held_past_legal_limit": held_too_long} if held_too_long else {}),
        "accounts": rows,
        "dishonoured_cheques": cheques,
        "judgments": judgments,
    }


def build_business_report(customer: Customer, at: datetime) -> dict[str, Any]:
    """The business credit report (P3.11): the business as registered, then its
    facilities, dishonoured cheques and court judgments exactly as loaded.

    ASSUMPTION A-081: the layout ("SIMB-B1") is a placeholder until a real business
    report layout (reference R9) is available.
    """
    report = build_report(customer, at)
    business = getattr(customer, "business", None)
    report["layout"] = BUSINESS_LAYOUT
    if business is not None:
        report["subject"] |= {
            "registered_name": business.registered_name,
            "trading_name": business.trading_name or None,
            "registration_number": business.registration_number or None,
            "tin": business.tin_number or None,
        }
    report["facilities"] = report.pop("accounts")
    return report


# The customers with any dishonoured cheque or court judgment on file, for each bureau,
# with the (row count, latest id) of each table they were read at (P4.0: most customers
# have neither, and asking for each customer's was two queries a report). Only the
# pipeline adds these rows and nothing moves them, so the sets hold until either changes.
_HOLDERS: dict[int, tuple[tuple[int, ...], frozenset[int], frozenset[int]]] = {}
_VERSION = f"""
SELECT (SELECT COUNT(*) FROM {DishonouredCheque._meta.db_table} WHERE organization_id = %(org)s),
       (SELECT MAX(id) FROM {DishonouredCheque._meta.db_table} WHERE organization_id = %(org)s),
       (SELECT COUNT(*) FROM {CourtJudgment._meta.db_table} WHERE organization_id = %(org)s),
       (SELECT MAX(id) FROM {CourtJudgment._meta.db_table} WHERE organization_id = %(org)s)
"""  # noqa: S608 - table names only


def _holders(organization_id: int, memo: dict[Any, Any]) -> tuple[frozenset[int], frozenset[int]]:
    if HOLDERS not in memo:
        with connection.cursor() as cursor:
            cursor.execute(_VERSION, {"org": organization_id})
            version = tuple(int(v or 0) for v in cursor.fetchone())
        cached = _HOLDERS.get(organization_id)
        if cached is None or cached[0] != version:
            cached = (
                version,
                frozenset(
                    DishonouredCheque.objects.filter(organization_id=organization_id)
                    .values_list("customer_id", flat=True)
                    .distinct()
                ),
                frozenset(
                    CourtJudgment.objects.filter(organization_id=organization_id)
                    .values_list("customer_id", flat=True)
                    .distinct()
                ),
            )
            _HOLDERS[organization_id] = cached
        memo[HOLDERS] = (cached[1], cached[2])
    holders: tuple[frozenset[int], frozenset[int]] = memo[HOLDERS]
    return holders


def cheques_on_file(customer: Customer, as_of: date) -> list[dict[str, Any]]:
    return [
        {
            "lender": c.institution.institution_name,
            "account_number": c.account_number,
            "cheque_number": c.cheque_number,
            "date_issued": _iso(c.date_issued),
            "date_bounced": _iso(c.date_bounced),
            "reason": CODE_LISTS["ReasonReturned"].get(c.reason_code, c.reason_code),
            "currency": c.currency_code,
            "amount": str(c.amount),
        }
        for c in DishonouredCheque.objects.filter(customer=customer, date_bounced__lte=as_of)
        .select_related("institution")
        .order_by("-date_bounced", "cheque_number")
    ]


def judgments_on_file(customer: Customer, as_of: date) -> list[dict[str, Any]]:
    return [
        {
            "plaintiff": j.institution.institution_name,
            "court": j.court_name,
            "court_type": j.court_type,
            "case_number": j.case_number,
            "filing_date": _iso(j.filing_date),
            "case_type": CODE_LISTS["CaseType"].get(j.case_type, j.case_type),
            "case_reason": CODE_LISTS["CaseReason"].get(j.case_reason, j.case_reason),
            "currency": j.currency_code,
            "amount": str(j.amount),
        }
        for j in CourtJudgment.objects.filter(customer=customer, filing_date__lte=as_of)
        .select_related("institution")
        .order_by("-filing_date", "case_number")
    ]


def _subject(customer: Customer) -> dict[str, Any]:
    identifiers = [
        {"type": i.identifier_type, "value": i.identifier_value}
        for i in customer.identifiers.order_by("identifier_type", "identifier_value")
    ]
    subject: dict[str, Any] = {
        "reference": customer.customer_reference,
        "type": customer.customer_type,
        "identifiers": identifiers,
    }
    individual = getattr(customer, "individual", None)
    business = getattr(customer, "business", None)
    if individual is not None:
        subject |= {
            "name": " ".join(
                p
                for p in (individual.first_name, individual.middle_name, individual.last_name)
                if p
            ),
            "date_of_birth": _iso(individual.date_of_birth),
            "gender": individual.gender_code,
        }
    elif business is not None:
        subject |= {
            "name": business.registered_name,
            "registration_date": _iso(business.registration_date),
            "sector": business.sector_code,
        }
    return subject


def _mask(number: str) -> str:
    return "*" * max(len(number) - 4, 0) + number[-4:]


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _retained(customer: Customer, as_of: date, keep: int) -> tuple[list[CreditAccount], int]:
    """The customer's accounts a report may show (rule RETENTION, P3.7).

    A closed account goes once the bureau's retention period (``keep`` years) has passed
    since it was last reported. Also counts those shown although past the legal limit.
    """
    drop_before, legal_before = (
        years_before(as_of, keep),
        years_before(as_of, LEGAL_RETENTION_YEARS),
    )
    shown: list[CreditAccount] = []
    held = 0
    for account in (
        CreditAccount.objects.filter(customer=customer)
        .select_related("institution")
        .annotate(last_reported=Max("observations__reporting_date"))
        .order_by("institution__institution_code", "facility_account_number")
    ):
        closed_on = (
            account.last_reported if account.account_status in CLOSED_STATUS_ON_FILE else None
        )
        if closed_on is not None and closed_on < drop_before:
            continue
        if closed_on is not None and closed_on < legal_before:
            held += 1
        shown.append(account)
    return shown, held


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


BAND_LABELS = {"A": "Very low risk", "B": "Low risk", "C": "Medium risk", "D": "High risk",
               "E": "Very high risk"}  # fmt: skip


def _score(customer: Customer) -> dict[str, Any]:
    """The customer's credit score, as the deployed scorecards last computed it (P3.6)."""
    found = CreditScore.objects.filter(customer=customer).first()
    if found is None:
        return {"score": None, "note": "No score: no open account to score on."}
    return {
        "score": found.score,
        "band": found.band,
        "band_label": BAND_LABELS[found.band],
        "reasons": found.reasons,
        "terms": found.terms,
        "as_of": found.as_of.isoformat(),
    }
