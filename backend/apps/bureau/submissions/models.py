"""Submission management (Document 04, Sections 8 and 18).

A submission is what one provider sends for one reporting month; it may hold
several files. Each processing attempt is a separate run, so reprocessing
never destroys history. Staging keeps every source row exactly as received,
with its row number, before anything is loaded to the core tables.
"""

from __future__ import annotations

from django.db import models

from apps.bureau.providers.models import Institution
from apps.org.models import Organization


class SubmissionStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSED = "PROCESSED", "Processed"
    REJECTED = "REJECTED", "Rejected"


class Submission(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="submissions"
    )
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, related_name="submissions"
    )
    submission_reference = models.CharField(max_length=60)
    reporting_period = models.DateField(help_text="Reporting month-end")
    template_version = models.CharField(
        max_length=20, help_text="Data standard in force for the reporting period (D19)"
    )
    due_date = models.DateField()
    received_at = models.DateTimeField()
    submission_status = models.CharField(
        max_length=30, choices=SubmissionStatus.choices, default=SubmissionStatus.RECEIVED
    )
    total_records = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "submission_reference"], name="submission_unique_ref"
            )
        ]
        indexes = [models.Index(fields=["institution", "reporting_period"])]

    def __str__(self) -> str:
        return self.submission_reference

    @property
    def is_late(self) -> bool:
        return self.received_at.date() > self.due_date


class FileStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    ACCEPTED = "ACCEPTED", "Accepted for processing"
    REJECTED = "REJECTED", "Rejected"


class TemplateMapping(models.Model):
    """How a provider's own column layout maps to the template (P2.5; D17).

    When a provider changes its extract, the file's columns no longer match and
    it is rejected (T001). The bureau maps the received headers to the template's
    columns once; the mapping is kept and applied to that provider's later files
    with the same headers.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="template_mappings"
    )
    file_kind = models.CharField(max_length=4)
    received = models.JSONField(help_text="The file's headers, as written, in order")
    columns = models.JSONField(help_text="The template column for each received header")
    created_at = models.DateTimeField(help_text="Game time")
    created_by = models.CharField(max_length=120)

    class Meta:
        indexes = [models.Index(fields=["institution", "file_kind"])]

    def __str__(self) -> str:
        return f"{self.institution_id} {self.file_kind} mapping"


class SubmissionFile(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="files")
    file_name = models.CharField(max_length=150)
    file_kind = models.CharField(max_length=4, help_text="CONC or BUSC, from the file name")
    file_format = models.CharField(max_length=10)
    file_size_bytes = models.BigIntegerField()
    file_hash = models.CharField(max_length=64, help_text="SHA-256 of the file as received")
    storage_path = models.CharField(max_length=300, help_text="Relative to STORAGE_ROOT")
    received_at = models.DateTimeField()
    file_status = models.CharField(
        max_length=20, choices=FileStatus.choices, default=FileStatus.RECEIVED
    )
    rejection_reason = models.CharField(max_length=300, blank=True)
    mapping = models.ForeignKey(
        TemplateMapping,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="files",
        help_text="The column mapping the file was read with, when its layout differed",
    )

    class Meta:
        indexes = [models.Index(fields=["file_hash"])]

    def __str__(self) -> str:
        return self.file_name


class RunStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class ProcessingRun(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="runs")
    run_number = models.IntegerField()
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    processing_status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.RUNNING
    )
    processing_version = models.CharField(max_length=20)
    template_version = models.CharField(
        max_length=20, help_text="Data standard the records were judged under (D19)"
    )
    records_received = models.IntegerField(default=0)
    records_accepted = models.IntegerField(default=0)
    records_unloadable = models.IntegerField(default=0)
    records_duplicated = models.IntegerField(default=0)
    records_pending = models.IntegerField(
        default=0, help_text="Held for review at the end of the run"
    )
    customers_created = models.IntegerField(default=0)
    accounts_created = models.IntegerField(default=0)
    observations_created = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["submission", "run_number"], name="run_unique_number")
        ]

    def __str__(self) -> str:
        return f"{self.submission_id} run {self.run_number}"

    @property
    def reconciles(self) -> bool:
        return self.records_received == (
            self.records_accepted
            + self.records_unloadable
            + self.records_duplicated
            + self.records_pending
        )


class RecordStatus(models.TextChoices):
    ACCEPTED = "ACCEPTED", "Accepted"
    UNLOADABLE = "UNLOADABLE", "Unloadable"
    DUPLICATE = "DUPLICATE", "Duplicate"
    PENDING_REVIEW = "PENDING_REVIEW", "Held for review"


class StagingRecord(models.Model):
    """One source row. ``raw`` is exactly as received; ``cleansed`` after cleansing rules.

    JSON keeps staging independent of the template edition: a record keeps the
    columns of the data standard it was submitted under (D19). Only the fields
    cleansing or a reviewer changed are stored (``changes``); ``cleansed`` is the
    raw row with those changes applied (P2.1: half the storage, faster copies).
    """

    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="records")
    file = models.ForeignKey(SubmissionFile, on_delete=models.CASCADE, related_name="records")
    source_row_number = models.IntegerField(help_text="1 = first row after the header")
    raw = models.JSONField()
    changes = models.JSONField(default=dict, help_text="Fields whose cleansed value differs")
    record_status = models.CharField(max_length=20, choices=RecordStatus.choices)
    duplicate_of_row = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "file", "source_row_number"], name="staging_unique_row"
            )
        ]

    def __str__(self) -> str:
        return f"{self.file_id}:{self.source_row_number}"

    @property
    def cleansed(self) -> dict[str, str]:
        return {**self.raw, **self.changes}

    @cleansed.setter
    def cleansed(self, values: dict[str, str]) -> None:
        self.changes = changes_from(self.raw, values)


def changes_from(raw: dict[str, str], cleansed: dict[str, str]) -> dict[str, str]:
    """The fields whose cleansed value differs from the raw one."""
    return {k: v for k, v in cleansed.items() if raw.get(k) != v}


class FeedbackReport(models.Model):
    """What the bureau told a provider about one submission (P2.5).

    ``report`` is the report as sent: the files rejected and why, and every record
    that could not be loaded with the rule, field and value at fault.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="feedback_reports"
    )
    sent_at = models.DateTimeField(help_text="Game time")
    report = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"Feedback on {self.submission_id} at {self.sent_at:%Y-%m-%d}"
