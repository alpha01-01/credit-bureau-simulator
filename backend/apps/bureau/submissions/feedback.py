"""Provider feedback reports: what was rejected and why (P2.5).

A report covers one submission: each file the bureau could not read or rejected,
and each record that could not be loaded, with the rules it broke, the field and
the value as sent. Records loaded with a warning are counted but not listed: the
provider need not resend them. ASSUMPTION A-053: the report format is the game's
own until real bureau error reports (reference R3) are available.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime
from typing import Any

from django.db.models import Max

from apps.bureau.quality.models import Severity, ValidationIssue
from apps.bureau.quality.rules import RULES

from .models import FeedbackReport, FileStatus, RecordStatus, StagingRecord, Submission

LISTED = 2000  # records listed in one report


def build_report(submission: Submission) -> dict[str, Any]:
    """The feedback for a submission as it stands now."""
    files = [
        {
            "file": f.file_name,
            "status": f.file_status,
            "rule": f.rejection_reason,
            "reason": RULES.get(f.rejection_reason, "") if f.rejection_reason else "",
        }
        for f in submission.files.order_by("file_name")
    ]
    # A file may have been read more than once (e.g. after mapping): report its latest run.
    latest_runs = dict(
        StagingRecord.objects.filter(run__submission=submission)
        .values("file_id")
        .annotate(latest=Max("run__run_number"))
        .values_list("file_id", "latest")
    )
    unloadable = (
        StagingRecord.objects.filter(
            run__submission=submission, record_status=RecordStatus.UNLOADABLE
        )
        .select_related("file", "run")
        .order_by("file__file_name", "source_row_number")
    )
    records = [r for r in unloadable if r.run.run_number == latest_runs.get(r.file_id)]
    issues = ValidationIssue.objects.filter(record__in=records, severity=Severity.ERROR).order_by(
        "record_id", "rule_code", "field"
    )
    by_record: dict[int, list[ValidationIssue]] = {}
    for issue in issues:
        by_record.setdefault(issue.record_id or 0, []).append(issue)
    rules: Counter[str] = Counter()
    rows = []
    for record in records:
        found = by_record.get(record.pk, [])
        rules.update({i.rule_code for i in found})
        values = record.raw
        rows.append(
            {
                "file": record.file.file_name,
                "row": record.source_row_number,
                "account": values.get("FacilityAccNum") or values.get("CaseNumber", ""),
                "customer": values.get("CustomerID", ""),
                "problems": [
                    {"rule": i.rule_code, "field": i.field, "value": i.value, "message": i.message}
                    for i in found
                ],
            }
        )
    warned = (
        ValidationIssue.objects.filter(
            run__submission=submission, severity=Severity.WARNING, record__isnull=False
        )
        .values("record_id")
        .distinct()
        .count()
    )
    return {
        "submission": submission.submission_reference,
        "provider": submission.institution.institution_code,
        "period": submission.reporting_period.isoformat(),
        "files": files,
        "files_rejected": sum(f["status"] == FileStatus.REJECTED for f in files),
        "records_unloadable": len(rows),
        "records_with_warnings": warned,
        "rules": [
            {"rule": code, "description": RULES.get(code, code), "records": n}
            for code, n in sorted(rules.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "rows": rows[:LISTED],
        "more_rows": max(len(rows) - LISTED, 0),
    }


def send_report(submission: Submission, at: datetime) -> FeedbackReport:
    """Send the provider its feedback, as it stands now."""
    return FeedbackReport.objects.create(
        organization_id=submission.organization_id,
        submission=submission,
        sent_at=at,
        report=build_report(submission),
    )


def as_csv(report: dict[str, Any]) -> str:
    """The records to resend, one line per problem, for the provider's own systems."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter="|", lineterminator="\n")
    writer.writerow(["File", "Row", "Account", "CustomerID", "Rule", "Field", "Value", "Problem"])
    for row in report["rows"]:
        for problem in row["problems"] or [{"rule": "", "field": "", "value": "", "message": ""}]:
            writer.writerow(
                [
                    row["file"],
                    row["row"],
                    row["account"],
                    row["customer"],
                    problem["rule"],
                    problem["field"],
                    problem["value"],
                    problem["message"],
                ]
            )
    return out.getvalue()
