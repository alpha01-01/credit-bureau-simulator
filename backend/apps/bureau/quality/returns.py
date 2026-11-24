"""The monthly return to the Bank of Ghana (P3.7; rule RETURN, A-077).

At each month's start the bureau owes a return on the month just ended, due by the
15th. It is a work item like any other: whoever files it gathers the month's figures
from the bureau's own records.
"""

from __future__ import annotations

from datetime import date, datetime

from apps.bureau.core.models import CreditAccount, Customer, Enquiry
from apps.org.models import Organization

from .models import CaseStatus, CaseType, Decision, Dispute, RegulatoryReturn, ReviewCase


class ReturnError(Exception):
    pass


def open_return(
    organization: Organization, period: date, due: date, at: datetime
) -> RegulatoryReturn:
    """The return for the month ending ``period``, as a case to work (once per month)."""
    existing = RegulatoryReturn.objects.filter(organization=organization, period=period).first()
    if existing is not None:
        return existing
    case = ReviewCase.objects.create(
        organization=organization,
        case_number=organization.allocate("last_case_seq"),
        case_type=CaseType.REGULATORY_RETURN,
        opened_at=at,
        evidence={"period": period.isoformat(), "due": due.isoformat()},
    )
    return RegulatoryReturn.objects.create(
        organization=organization, period=period, due_date=due, case=case
    )


def figures(organization: Organization, period: date) -> dict[str, int]:
    """What the return reports: the bureau's records and activity for the month."""
    start = period.replace(day=1)
    return {
        "customers": Customer.objects.filter(organization=organization).count(),
        "accounts": CreditAccount.objects.filter(organization=organization).count(),
        "enquiries": Enquiry.objects.filter(
            organization=organization, enquired_at__date__gte=start, enquired_at__date__lte=period
        ).count(),
        "disputes_received": Dispute.objects.filter(
            organization=organization, received_at__date__gte=start, received_at__date__lte=period
        ).count(),
        "disputes_settled": Dispute.objects.filter(
            organization=organization, resolved_at__date__gte=start, resolved_at__date__lte=period
        ).count(),
    }


def file_return(case: ReviewCase, decision: str, decided_by: str, at: datetime) -> RegulatoryReturn:
    if case.case_type != CaseType.REGULATORY_RETURN or decision != Decision.FILE_RETURN:
        raise ReturnError(f"Case {case.case_number} is not a return to file")
    found = RegulatoryReturn.objects.get(case=case)
    if found.filed_at is not None:
        raise ReturnError(f"The return for {found.period:%B %Y} is already filed")
    found.figures = figures(case.organization, found.period)
    found.filed_at, found.filed_by = at, decided_by[:120]
    found.save(update_fields=["figures", "filed_at", "filed_by"])
    case.status, case.decision = CaseStatus.RESOLVED, decision
    case.decided_by, case.decided_at = decided_by[:120], at
    case.save(update_fields=["status", "decision", "decided_by", "decided_at"])
    return found
