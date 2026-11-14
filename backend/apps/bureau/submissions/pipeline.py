"""Pipeline: process a received submission into the bureau database (roadmap S3, S5).

Stages (Document 04, Section 18):
  structural validation  - file columns must match the template exactly (T001)
  staging                - every row kept as received, with its row number
  cleansing              - phones, dates, amounts and codes normalised (C001-C004)
  duplicate detection    - same account, customer and disbursement date: the lower
                           balance is kept (D001); repeated accounts (D002)
  field validation       - mandatory and conditional fields, formats, code lists,
                           financial logic (F001-F014), under the bureau's policy
  referencing            - customer and account matching; weak identifier
                           matches are held for review (S5)
  loading                - accepted records become observations; conflicts (L001)
  review cases           - uncertain matches, and unloadable records with a
                           plausible correction, go to the Data Operations queue
  summary                - received = accepted + unloadable + duplicate + pending

A run is atomic: it either completes in full or leaves nothing behind.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.bureau.core.models import (
    AccountObservation,
    CreditAccount,
)
from apps.bureau.quality.models import (
    CaseType,
    ReviewCase,
    Severity,
    TransformationLog,
    ValidationIssue,
)
from apps.bureau.quality.rules import Issue, cleanse, parse_date, propose_corrections, validate
from apps.bureau.referencing.matching import (
    MatchQuestion,
    NewCustomer,
    Pending,
    Referencer,
    observed_accounts,
)
from apps.dbcopy import copy_insert
from apps.org.models import Organization
from apps.standards.submission_template import FileKind, header

from .intake import read_rows
from .models import (
    FileStatus,
    ProcessingRun,
    RecordStatus,
    RunStatus,
    StagingRecord,
    Submission,
    SubmissionFile,
    SubmissionStatus,
)

PROCESSING_VERSION = "pipeline-v2"
BATCH = 2000


@dataclass
class _Row:
    file: SubmissionFile
    number: int
    raw: dict[str, str]
    cleansed: dict[str, str]
    transformations: list[tuple[str, str, str, str]]
    status: str = RecordStatus.ACCEPTED
    duplicate_of: int | None = None
    issues: list[Issue] = field(default_factory=list)
    account: CreditAccount | None = None
    question: MatchQuestion | None = None
    proposal: dict[str, str] = field(default_factory=dict)


def process_submission(submission: Submission, at: datetime | None = None) -> ProcessingRun:
    """Process a submission. ``at`` is the (game) time of the run; default: now."""
    at = at or timezone.now()
    with transaction.atomic():
        submission = (
            Submission.objects.select_for_update()
            .select_related("institution", "organization")
            .get(pk=submission.pk)
        )
        number = (submission.runs.aggregate(n=Max("run_number"))["n"] or 0) + 1
        run = ProcessingRun.objects.create(
            submission=submission,
            run_number=number,
            started_at=at,
            processing_version=PROCESSING_VERSION,
        )
        file_issues: list[ValidationIssue] = []
        rows: list[_Row] = []
        for stored in submission.files.order_by("file_name", "pk"):
            if stored.file_status == FileStatus.REJECTED:
                continue
            rows.extend(_stage_file(run, stored, file_issues))

        pending = Pending()
        for kind in FileKind:
            batch = [
                r
                for r in rows
                if r.status == RecordStatus.ACCEPTED and r.file.file_kind == kind.value
            ]
            if batch:
                _reference(submission, kind, batch, pending)
        save_pending(submission.organization, pending)
        records = _save_rows(run, submission, rows, file_issues)
        _open_cases(submission.organization, rows, records, at)

        counts = Counter(r.status for r in rows)
        run.records_received = len(rows)
        run.records_accepted = counts[RecordStatus.ACCEPTED]
        run.records_unloadable = counts[RecordStatus.UNLOADABLE]
        run.records_duplicated = counts[RecordStatus.DUPLICATE]
        run.records_pending = counts[RecordStatus.PENDING_REVIEW]
        run.customers_created = len(pending.customers)
        run.accounts_created = len(pending.accounts)
        run.observations_created = run.records_accepted
        run.completed_at = at
        run.processing_status = RunStatus.COMPLETED
        run.save()

        accepted_any = submission.files.filter(file_status=FileStatus.ACCEPTED).exists()
        submission.submission_status = (
            SubmissionStatus.PROCESSED if accepted_any else SubmissionStatus.REJECTED
        )
        submission.total_records = len(rows)
        submission.save(update_fields=["submission_status", "total_records"])
        return run


def _stage_file(
    run: ProcessingRun, stored: SubmissionFile, file_issues: list[ValidationIssue]
) -> list[_Row]:
    def reject(code: str, value: str = "") -> list[_Row]:
        stored.file_status = FileStatus.REJECTED
        stored.rejection_reason = code
        stored.save(update_fields=["file_status", "rejection_reason"])
        issue = Issue(code, value=value[:200])
        file_issues.append(
            ValidationIssue(
                run=run, file=stored, rule_code=code, severity=Severity.ERROR,
                message=issue.message, value=issue.value,
            )
        )  # fmt: skip
        return []

    try:
        names, raw_rows = read_rows(stored)
    except (ValueError, OSError, KeyError) as exc:
        return reject("T004", str(exc))
    kind = FileKind(stored.file_kind)
    if names != list(header(kind)):
        return reject("T001", ",".join(names))

    stored.file_status = FileStatus.ACCEPTED
    stored.save(update_fields=["file_status"])
    period = run.submission.reporting_period

    policy = run.submission.organization.rejection_policy
    rows: list[_Row] = []
    for n, values in enumerate(raw_rows, start=1):
        raw = dict(zip(names, values, strict=True))
        cleansed, logs = cleanse(kind, raw)
        rows.append(_Row(stored, n, raw, cleansed, logs))
    _mark_duplicates(kind, rows)

    account_rows: dict[str, int] = {}
    for row in rows:
        if row.status == RecordStatus.DUPLICATE:
            continue
        checked = validate(kind, row.cleansed, period, policy)
        row.issues.extend(checked.issues)
        for name, value in checked.blanked.items():
            row.cleansed[name] = ""
            row.transformations.append((name, "C005", value, ""))
        account = row.cleansed["FacilityAccNum"]
        if account and account in account_rows:
            row.issues.append(Issue("D002", "FacilityAccNum", account))
        elif account:
            account_rows[account] = row.number
        if any(i.severity == Severity.ERROR for i in row.issues):
            row.status = RecordStatus.UNLOADABLE
            row.proposal = propose_corrections(row.cleansed, row.issues, period)
    return rows


def _balance(values: dict[str, str]) -> int | None:
    balance = values.get("CurBal", "")
    return int(balance) if balance.isdigit() else None


def _mark_duplicates(kind: FileKind, rows: list[_Row]) -> None:
    """The standard's duplicate rule (D18): the same account, customer and disbursement date.

    The names must agree as well. Of a set of duplicates the record with the
    lower balance is kept (owner's rule, strictly enforced); on equal balances,
    the first. A provider who disagrees raises a dispute.
    """
    names = ("BusinessName",) if kind is FileKind.COMMERCIAL else ("Surname", "FirstName")
    groups: dict[tuple[str, ...], list[_Row]] = {}
    for row in rows:
        v = row.cleansed
        names_agreed = (v[n].upper() for n in names)
        key = (v["FacilityAccNum"], v["CustomerID"], v["DisbursementDate"], *names_agreed)
        if all(key[:3]):
            groups.setdefault(key, []).append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        kept = min(
            group, key=lambda r: (_balance(r.cleansed) is None, _balance(r.cleansed) or 0, r.number)
        )
        for row in group:
            if row is kept:
                continue
            row.status = RecordStatus.DUPLICATE
            row.duplicate_of = kept.number
            row.issues.append(Issue("D001", value=f"row {kept.number}", severity="WARNING"))


def _reference(
    submission: Submission,
    kind: FileKind,
    rows: list[_Row],
    pending: Pending,
    resolution: tuple[str, int | None] | None = None,
) -> None:
    referencer = Referencer(submission, kind, [r.cleansed for r in rows], pending)
    # An observation already loaded for this date is a load conflict, not a new row.
    existing = {a.facility_account_number: a.pk for a in referencer.accounts.values() if a.pk}
    clashes = observed_accounts(list(existing.values()), submission.reporting_period)
    for row in rows:
        if existing.get(row.cleansed["FacilityAccNum"]) in clashes:
            row.status = RecordStatus.UNLOADABLE
            row.issues.append(Issue("L001", "FacilityAccNum", row.cleansed["FacilityAccNum"]))
            continue
        customer, issues = referencer.customer_for(row.cleansed, resolution)
        if isinstance(customer, MatchQuestion):
            row.status = RecordStatus.PENDING_REVIEW
            row.question = customer
            continue
        row.account, account_issues = referencer.account_for(row.cleansed, customer)
        row.issues.extend(issues + account_issues)
        row.status = (
            RecordStatus.UNLOADABLE
            if any(i.severity == Severity.ERROR for i in account_issues)
            else RecordStatus.ACCEPTED
        )


def save_pending(organization: Organization, pending: Pending) -> None:
    """Create the customers, links and accounts referencing decided on, parents first."""
    if pending.customers:
        first = organization.allocate("last_customer_seq", len(pending.customers))
        for i, customer in enumerate(pending.customers):
            customer.customer_reference = f"CB{first + i:010d}"
        copy_insert(pending.customers)
    copy_insert(pending.individual_profiles)
    copy_insert(pending.business_profiles)
    copy_insert(pending.identifiers)
    copy_insert(pending.contacts)
    copy_insert(pending.links)
    copy_insert(pending.accounts)
    CreditAccount.objects.bulk_update(
        list(pending.updated_accounts.values()), ["account_status"], batch_size=BATCH
    )


def observation(
    values: dict[str, str],
    account: CreditAccount,
    submission: Submission,
    stored: SubmissionFile,
    row_number: int,
    run: ProcessingRun,
) -> AccountObservation:
    period = submission.reporting_period
    paid = parse_date(values.get("LastPaymentDate", ""))
    in_period = paid is not None and (paid.year, paid.month) == (period.year, period.month)
    return AccountObservation(
        credit_account=account,
        reporting_date=period,
        outstanding_balance=_amount(values, "CurBal"),
        arrears_amount=_amount(values, "AmountInArrears"),
        days_past_due=int(values.get("NDIA") or 0),
        instalment_amount=_amount(values, "SchdInstalAmount"),
        amount_paid=_amount(values, "LastPaymentAmount") if in_period else Decimal(0),
        facility_status=values["FacilityStatusCode"],
        asset_classification=values.get("AssetClassification", ""),
        is_written_off=values["FacilityStatusCode"] == "W",
        source_submission=submission,
        source_file=stored,
        source_row_number=row_number,
        processing_run=run,
    )


def _amount(values: dict[str, str], name: str) -> Decimal:
    return Decimal(values.get(name) or 0)


def issue_rows(
    run: ProcessingRun,
    stored: SubmissionFile,
    record: StagingRecord,
    number: int,
    issues: list[Issue],
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            run=run, file=stored, record=record, source_row_number=number, field=i.field,
            rule_code=i.rule_code, severity=i.severity, message=i.message, value=i.value[:200],
        )
        for i in issues
    ]  # fmt: skip


def _save_rows(
    run: ProcessingRun,
    submission: Submission,
    rows: list[_Row],
    file_issues: list[ValidationIssue],
) -> list[StagingRecord]:
    records = [
        StagingRecord(
            run=run,
            file=row.file,
            source_row_number=row.number,
            raw=row.raw,
            cleansed=row.cleansed,
            record_status=row.status,
            duplicate_of_row=row.duplicate_of,
        )
        for row in rows
    ]
    copy_insert(records)

    issues = list(file_issues)
    transformations = []
    observations = []
    for row, record in zip(rows, records, strict=True):
        issues.extend(issue_rows(run, row.file, record, row.number, row.issues))
        for name, rule, before, after in row.transformations:
            transformations.append(
                TransformationLog(
                    record=record, field=name, rule_code=rule,
                    value_before=before[:200], value_after=after[:200],
                )
            )  # fmt: skip
        if row.status == RecordStatus.ACCEPTED:
            if row.account is None:
                raise RuntimeError(f"Accepted row {row.number} has no account")
            observations.append(
                observation(row.cleansed, row.account, submission, row.file, row.number, run)
            )
    copy_insert(issues)
    copy_insert(transformations)
    copy_insert(observations)
    return records


def _open_cases(
    organization: Organization, rows: list[_Row], records: list[StagingRecord], at: datetime
) -> None:
    wanted = [
        (row, record)
        for row, record in zip(rows, records, strict=True)
        if row.question is not None or (row.status == RecordStatus.UNLOADABLE and row.proposal)
    ]
    open_cases(organization, wanted, at)


def open_cases(
    organization: Organization, wanted: list[tuple[Any, StagingRecord]], at: datetime
) -> list[ReviewCase]:
    """Create review cases for rows with a match question or a proposed correction."""
    if not wanted:
        return []
    first = organization.allocate("last_case_seq", len(wanted))
    cases = []
    for n, (row, record) in enumerate(wanted):
        question: MatchQuestion | None = row.question
        if question is not None:
            candidate = question.candidate
            candidate_id = (
                candidate.customer.pk if isinstance(candidate, NewCustomer) else candidate
            )
            cases.append(
                ReviewCase(
                    organization=organization,
                    case_number=first + n,
                    case_type=CaseType.MATCH_REVIEW,
                    record=record,
                    candidate_customer_id=candidate_id,
                    score=question.comparison.score,
                    evidence={
                        "identifier_field": question.identifier_field,
                        "identifier": row.cleansed.get(question.identifier_field, ""),
                        "reasons": question.comparison.reasons,
                    },
                    opened_at=at,
                )
            )
        else:
            cases.append(
                ReviewCase(
                    organization=organization,
                    case_number=first + n,
                    case_type=CaseType.UNLOADABLE_TRIAGE,
                    record=record,
                    evidence={
                        "errors": [
                            {"rule": i.rule_code, "field": i.field, "value": i.value}
                            for i in row.issues
                            if i.severity == Severity.ERROR
                        ]
                    },
                    proposal=row.proposal,
                    opened_at=at,
                )
            )
    return copy_insert(cases)
