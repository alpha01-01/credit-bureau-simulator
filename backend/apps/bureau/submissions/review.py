"""Applying a reviewer's decision to the bureau database (roadmap S5).

A decision is applied exactly as given, right or wrong. Linking a record to
the wrong customer really merges two people's credit histories; returning a
correctable record really leaves a gap in the bureau's data.
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction

from apps.bureau.quality.models import (
    ALLOWED_DECISIONS,
    CaseStatus,
    Decision,
    ReviewCase,
    TransformationLog,
    ValidationIssue,
)
from apps.bureau.quality.rules import Issue, validate
from apps.bureau.referencing.matching import DIFFERENT, SAME, Pending
from apps.standards.submission_template import FileKind

from .models import RecordStatus, StagingRecord
from .pipeline import (
    _reference,
    _Row,
    issue_rows,
    observation,
    open_cases,
    save_pending,
)


class ReviewError(Exception):
    pass


def apply_decision(case: ReviewCase, decision: str, decided_by: str, at: datetime) -> ReviewCase:
    """Settle a review case and apply the decision. Returns the case."""
    with transaction.atomic():
        case = ReviewCase.objects.select_for_update().get(pk=case.pk)
        if case.status != CaseStatus.OPEN:
            raise ReviewError(f"Case {case.case_number} is already resolved")
        if decision not in ALLOWED_DECISIONS[case.case_type]:
            raise ReviewError(f"{decision} is not a decision for a {case.case_type} case")

        record = StagingRecord.objects.select_related(
            "file", "run__submission__institution", "run__submission__organization"
        ).get(pk=case.record_id)
        if decision == Decision.RETURN_TO_PROVIDER:
            _return(record)
        elif decision == Decision.CORRECT_AND_LOAD:
            _correct_and_load(record, case.proposal, at)
        else:
            resolution = (
                (SAME, case.candidate_customer_id) if decision == SAME else (DIFFERENT, None)
            )
            _load(record, at, resolution)

        case.status = CaseStatus.RESOLVED
        case.decision = decision
        case.decided_by = decided_by[:120]
        case.decided_at = at
        case.save(update_fields=["status", "decision", "decided_by", "decided_at"])
        return case


def _return(record: StagingRecord) -> None:
    record.record_status = RecordStatus.UNLOADABLE
    record.save(update_fields=["record_status"])
    ValidationIssue.objects.bulk_create(
        issue_rows(record.run, record.file, record, record.source_row_number, [Issue("Q001")])
    )


def _correct_and_load(record: StagingRecord, proposal: dict[str, str], at: datetime) -> None:
    values = dict(record.cleansed)
    logs = []
    for name, value in proposal.items():
        logs.append(
            TransformationLog(
                record=record, field=name, rule_code="M001",
                value_before=values.get(name, "")[:200], value_after=value[:200],
            )
        )  # fmt: skip
        values[name] = value
    TransformationLog.objects.bulk_create(logs)
    record.cleansed = values
    submission = record.run.submission
    errors = [
        i
        for i in validate(
            FileKind(record.file.file_kind),
            values,
            submission.institution.institution_code,
            submission.reporting_period,
        )
        if i.severity == "ERROR"
    ]
    if errors:
        record.record_status = RecordStatus.UNLOADABLE
        record.save(update_fields=["cleansed", "record_status"])
        ValidationIssue.objects.bulk_create(
            issue_rows(record.run, record.file, record, record.source_row_number, errors)
        )
        return
    record.save(update_fields=["cleansed"])
    _load(record, at, None)


def _load(record: StagingRecord, at: datetime, resolution: tuple[str, int | None] | None) -> None:
    """Reference and load one staged record, as the pipeline would."""
    run = record.run
    submission = run.submission
    kind = FileKind(record.file.file_kind)
    row = _Row(record.file, record.source_row_number, record.raw, record.cleansed, [])
    pending = Pending()
    _reference(submission, kind, [row], pending, resolution)
    save_pending(submission.organization, pending)

    record.record_status = row.status
    record.save(update_fields=["record_status"])
    ValidationIssue.objects.bulk_create(
        issue_rows(run, record.file, record, record.source_row_number, row.issues)
    )
    if row.status == RecordStatus.ACCEPTED and row.account is not None:
        observation(
            row.cleansed, row.account, submission, record.file, record.source_row_number, run
        ).save()
    elif row.question is not None:
        open_cases(submission.organization, [(row, record)], at)
