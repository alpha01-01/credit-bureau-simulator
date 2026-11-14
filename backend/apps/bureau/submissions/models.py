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
    columns of the data standard it was submitted under (D19).
    """

    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="records")
    file = models.ForeignKey(SubmissionFile, on_delete=models.CASCADE, related_name="records")
    source_row_number = models.IntegerField(help_text="1 = first row after the header")
    raw = models.JSONField()
    cleansed = models.JSONField()
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
