"""Receiving files: register the submission, store the original, record its hash.

Steps 1-3 of the loading strategy (Document 04, Section 18). Files that break
the naming convention or repeat a file already received are registered and
rejected, never silently dropped.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from openpyxl import load_workbook

from apps.bureau.providers.models import Institution
from apps.org.models import Organization
from apps.standards.calendar import next_working_day
from apps.standards.submission_template import FILE_NAME_PATTERN, SUBMISSION_DUE_DAY

from .models import FileStatus, Submission, SubmissionFile, SubmissionStatus


def due_date_for(period: date) -> date:
    """The deadline: the due day of the next month, or the next working day after it."""
    return next_working_day((period + timedelta(days=1)).replace(day=SUBMISSION_DUE_DAY))


def submission_folder(organization: Organization, reference: str) -> Path:
    return (
        Path(settings.STORAGE_ROOT)
        / "bureau"
        / f"org_{organization.pk}"
        / "submissions"
        / reference
    )


def receive_file(
    organization: Organization,
    institution: Institution,
    period: date,
    file_name: str,
    data: bytes,
    received_at: datetime,
) -> SubmissionFile:
    """Register one file for an institution's reporting period and store the original."""
    with transaction.atomic():
        submission = (
            Submission.objects.filter(
                institution=institution,
                reporting_period=period,
                submission_status=SubmissionStatus.RECEIVED,
            )
            .order_by("pk")
            .first()
        )
        if submission is None:
            seq = organization.allocate("last_submission_seq")
            submission = Submission.objects.create(
                organization=organization,
                institution=institution,
                submission_reference=f"SUB-{period:%Y%m}-{institution.institution_code}-{seq:06d}",
                reporting_period=period,
                due_date=due_date_for(period),
                received_at=received_at,
            )

        digest = hashlib.sha256(data).hexdigest()
        folder = submission_folder(organization, submission.submission_reference)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file_name
        copy = 1
        while path.exists():  # never overwrite an original
            copy += 1
            path = folder / f"{Path(file_name).stem}__{copy}{Path(file_name).suffix}"
        path.write_bytes(data)

        match = FILE_NAME_PATTERN.fullmatch(file_name)
        status, reason = FileStatus.RECEIVED, ""
        if (
            match is None
            or match["provider"] != institution.institution_code
            or match["period"] != f"{period:%Y%m}"
        ):
            status, reason = FileStatus.REJECTED, "T002"
        elif SubmissionFile.objects.filter(
            submission__institution=institution, file_hash=digest
        ).exists():
            status, reason = FileStatus.REJECTED, "T003"

        return SubmissionFile.objects.create(
            submission=submission,
            file_name=file_name,
            file_kind=match["kind"] if match else "",
            file_format=(match["ext"].upper() if match else Path(file_name).suffix[1:].upper()),
            file_size_bytes=len(data),
            file_hash=digest,
            storage_path=path.relative_to(Path(settings.STORAGE_ROOT)).as_posix(),
            received_at=received_at,
            file_status=status,
            rejection_reason=reason,
        )


def read_rows(stored: SubmissionFile) -> tuple[list[str], list[list[str]]]:
    """Read a stored file as text: header and data rows. Raises ValueError if unreadable."""
    path = Path(settings.STORAGE_ROOT) / stored.storage_path
    if stored.file_format == "CSV":
        text = path.read_bytes().decode("utf-8-sig")
        lines = list(csv.reader(io.StringIO(text, newline="")))
    elif stored.file_format == "XLSX":
        workbook = load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
        lines = [
            [_cell(v) for v in row] for row in workbook.worksheets[0].iter_rows(values_only=True)
        ]
    else:
        raise ValueError(f"Unsupported format {stored.file_format}")
    if not lines:
        raise ValueError("Empty file")
    width = len(lines[0])
    rows = [(row + [""] * width)[:width] for row in lines[1:] if any(cell.strip() for cell in row)]
    return [h.strip() for h in lines[0]], rows


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
