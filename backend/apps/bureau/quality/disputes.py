"""Disputes and corrections (P2.7; Act 726, L.I. 2394 Regulations 23-26).

A subject who finds accounts on their report that are not theirs disputes them.
The bureau records the dispute, flags the accounts on reports while it is open,
and must settle it by its due date. Settling is a judgement (a work item):

* **uphold**: the accounts are not the subject's. Each provider customer behind
  them is moved off the subject to a customer of its own, made from the provider's
  own record of that person; every account moved gets a correction record
  (Document 04, Section 19), so the change is traceable and nothing is lost;
* **reject**: the accounts are the subject's; nothing changes.

The bureau never reads the world: it corrects with what providers sent it.
"""

from __future__ import annotations

from datetime import date, datetime

from django.db import transaction

from apps.bureau.core.models import (
    AccountObservation,
    BusinessProfile,
    CreditAccount,
    Customer,
    CustomerType,
    Enquiry,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.quality.rules import parse_date
from apps.bureau.submissions.models import StagingRecord
from apps.org.models import Organization

from .models import (
    CaseStatus,
    CaseType,
    CorrectionRecord,
    Decision,
    Dispute,
    DisputeStatus,
    ReviewCase,
)


class DisputeError(Exception):
    pass


def open_dispute(
    organization: Organization,
    customer: Customer,
    enquiry: Enquiry | None,
    subject_name: str,
    claim: str,
    accounts: list[list[str]],
    received_at: datetime,
    due_date: date,
) -> Dispute:
    """Record a dispute and open its case for the Data Operations team."""
    with transaction.atomic():
        dispute = Dispute.objects.create(
            organization=organization,
            dispute_number=organization.allocate("last_dispute_seq"),
            customer=customer,
            enquiry=enquiry,
            subject_name=subject_name[:200],
            claim=claim[:500],
            accounts=accounts,
            received_at=received_at,
            due_date=due_date,
        )
        ReviewCase.objects.create(
            organization=organization,
            case_number=organization.allocate("last_case_seq"),
            case_type=CaseType.DISPUTE,
            dispute=dispute,
            candidate_customer=customer,
            evidence={
                "claim": dispute.claim,
                "accounts": accounts,
                "due_date": due_date.isoformat(),
                "customer": customer.customer_reference,
            },
            opened_at=received_at,
        )
        return dispute


def disputed_accounts(organization_id: int) -> set[tuple[str, str]]:
    """Accounts under an open dispute, flagged on every report while it lasts."""
    out: set[tuple[str, str]] = set()
    for accounts in Dispute.objects.filter(
        organization_id=organization_id, status=DisputeStatus.OPEN
    ).values_list("accounts", flat=True):
        out.update((code, number) for code, number in accounts)
    return out


def resolve(case: ReviewCase, decision: str, decided_by: str, at: datetime) -> Dispute:
    """Settle a dispute case: correct the report (uphold) or leave it (reject)."""
    dispute = case.dispute
    if dispute is None or case.case_type != CaseType.DISPUTE:
        raise DisputeError(f"Case {case.case_number} is not a dispute")
    if dispute.status != DisputeStatus.OPEN:
        raise DisputeError(f"Dispute {dispute.dispute_number} is already settled")
    if decision == Decision.UPHOLD_DISPUTE:
        _correct(dispute, decided_by, at)
    dispute.status = DisputeStatus.RESOLVED
    dispute.outcome = "UPHELD" if decision == Decision.UPHOLD_DISPUTE else "REJECTED"
    dispute.resolved_at = at
    dispute.resolved_by = decided_by[:120]
    dispute.save(update_fields=["status", "outcome", "resolved_at", "resolved_by"])
    case.status = CaseStatus.RESOLVED
    case.decision = decision
    case.decided_by = decided_by[:120]
    case.decided_at = at
    case.save(update_fields=["status", "decision", "decided_by", "decided_at"])
    return dispute


def _correct(dispute: Dispute, decided_by: str, at: datetime) -> None:
    """Move each disputed provider customer, with its accounts, to a customer of its own."""
    subject = dispute.customer
    moved: dict[tuple[int, str], Customer] = {}  # (institution, provider customer) -> customer
    for code, number in dispute.accounts:
        account = CreditAccount.objects.filter(
            customer=subject,
            institution__institution_code=code,
            facility_account_number=number,
        ).first()
        if account is None:
            continue  # already moved by an earlier correction
        record = latest_record(account)
        if record is None:
            continue
        values = record.cleansed
        key = (account.institution_id, values.get("CustomerID", ""))
        if key not in moved:
            moved[key] = _customer_from(dispute.organization, subject, values, record)
            ProviderCustomerLink.objects.filter(
                institution_id=key[0], provider_customer_number=key[1], customer=subject
            ).update(customer=moved[key])
        # Every account of that provider customer on the subject goes with it.
        for other in CreditAccount.objects.filter(customer=subject, institution_id=key[0]).order_by(
            "facility_account_number"
        ):
            latest = latest_record(other)
            if latest is None or latest.cleansed.get("CustomerID", "") != key[1]:
                continue
            CorrectionRecord.objects.create(
                organization=dispute.organization,
                credit_account=other,
                from_customer=subject,
                to_customer=moved[key],
                dispute=dispute,
                reason=f"Dispute {dispute.dispute_number} upheld: not {dispute.subject_name}'s account",
                approved_by=decided_by[:120],
                corrected_at=at,
            )
            other.customer = moved[key]
            other.save(update_fields=["customer"])


def latest_record(account: CreditAccount) -> StagingRecord | None:
    observation = (
        AccountObservation.objects.filter(credit_account=account, is_current=True)
        .order_by("-reporting_date")
        .first()
    )
    if observation is None:
        return None
    return StagingRecord.objects.filter(
        file_id=observation.source_file_id, source_row_number=observation.source_row_number
    ).first()


def _customer_from(
    organization: Organization, subject: Customer, values: dict[str, str], record: StagingRecord
) -> Customer:
    """A new customer for the person the provider's record describes."""
    customer = Customer.objects.create(
        organization=organization,
        customer_type=subject.customer_type,
        customer_reference=f"CB{organization.allocate('last_customer_seq'):010d}",
        source_submission=record.run.submission,
    )
    if subject.customer_type == CustomerType.INDIVIDUAL:
        IndividualProfile.objects.create(
            customer=customer,
            first_name=values.get("FirstName", ""),
            middle_name=values.get("MiddleNames", ""),
            last_name=values.get("Surname", ""),
            date_of_birth=parse_date(values.get("DOB", "")),
            gender_code=values.get("Gender", ""),
            employment_status=values.get("EmpType", ""),
        )
    else:
        BusinessProfile.objects.create(
            customer=customer,
            registered_name=values.get("BusinessName", ""),
            trading_name=values.get("TradingName", ""),
            registration_number=values.get("BusRegNum", ""),
            tin_number=values.get("TINum", ""),
            sector_code=values.get("SubSecIndCode", ""),
            registration_date=parse_date(values.get("RegistrationDate", "")),
        )
    return customer
