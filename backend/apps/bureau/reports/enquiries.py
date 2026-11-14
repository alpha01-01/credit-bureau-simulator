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

from django.db import transaction

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
from apps.org.models import Organization
from apps.standards.enquiry import PURPOSES
from apps.standards.submission_template import (
    CODE_LISTS,
    OPEN_STATUS_CODES,
    WRITTEN_OFF_STATUS_CODES,
)

REPORT_LAYOUT = "SIMB-R1"  # R1 adds dishonoured cheques and judgments (P2.0c)
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
) -> Enquiry:
    """Search for a subject and log the enquiry, with the report delivered on a hit."""
    if purpose not in PURPOSES:
        raise EnquiryError(f"{purpose!r} is not a permissible purpose")
    if not consent_reference:
        raise EnquiryError("An enquiry needs the subject's consent reference")
    with transaction.atomic():
        identifier = (
            CustomerIdentifier.objects.filter(
                organization=organization,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
            )
            .select_related("customer")
            .first()
        )
        customer = identifier.customer if identifier else None
        report = build_report(customer, at) if customer else {}
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
            accounts_reported=len(report.get("accounts", [])),
            report=report,
        )


def build_report(customer: Customer, at: datetime) -> dict[str, Any]:
    as_of = at.date()
    accounts = list(
        CreditAccount.objects.filter(customer=customer)
        .select_related("institution")
        .order_by("institution__institution_code", "facility_account_number")
    )
    since = (as_of.replace(day=1) - timedelta(days=HISTORY_MONTHS * 31)).replace(day=1)
    history: dict[int, list[AccountObservation]] = defaultdict(list)
    for obs in AccountObservation.objects.filter(
        credit_account__in=accounts, is_current=True, reporting_date__lte=as_of,
        reporting_date__gte=since,
    ).order_by("reporting_date"):  # fmt: skip
        history[obs.credit_account_id].append(obs)

    rows: list[dict[str, Any]] = []
    states: list[tuple[str, Decimal | None, int | None]] = []  # status, balance, days past due
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
                "history": [
                    {"month": f"{o.reporting_date:%Y-%m}", "days_past_due": o.days_past_due}
                    for o in observations
                ],
            }
        )

    open_states = [st for st in states if st[0] in OPEN_STATUS_CODES]
    total = sum((st[1] for st in open_states if st[1] is not None), Decimal("0"))
    previous_enquiries = Enquiry.objects.filter(
        customer=customer, enquired_at__gte=at - timedelta(days=365), enquired_at__lt=at
    ).count()
    cheques, judgments = cheques_on_file(customer, as_of), judgments_on_file(customer, as_of)
    return {
        "layout": REPORT_LAYOUT,
        "as_of": as_of.isoformat(),
        "subject": _subject(customer),
        "summary": {
            "accounts": len(rows),
            "open_accounts": len(open_states),
            "total_outstanding": str(total),
            "accounts_in_arrears": sum(1 for st in open_states if (st[2] or 0) > 0),
            "written_off": sum(1 for st in states if st[0] in WRITTEN_OFF_STATUS_CODES),
            "enquiries_last_12_months": previous_enquiries,
            "dishonoured_cheques": len(cheques),
            "judgments": len(judgments),
        },
        "accounts": rows,
        "dishonoured_cheques": cheques,
        "judgments": judgments,
    }


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


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
