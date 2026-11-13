"""Data quality records (Document 04, Section 9).

Validation issues explain why a file or row was rejected or flagged.
Transformation logs record every change cleansing made, with the value
before and after, so lineage can answer "was it changed during cleansing?".
"""

from __future__ import annotations

from django.db import models

from apps.bureau.submissions.models import ProcessingRun, StagingRecord, SubmissionFile


class Severity(models.TextChoices):
    ERROR = "ERROR", "Error (record not loaded)"
    WARNING = "WARNING", "Warning (record loaded)"


class ValidationIssue(models.Model):
    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="issues")
    file = models.ForeignKey(SubmissionFile, on_delete=models.CASCADE, related_name="issues")
    record = models.ForeignKey(
        StagingRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="issues"
    )
    source_row_number = models.IntegerField(null=True, blank=True)
    field = models.CharField(max_length=40, blank=True)
    rule_code = models.CharField(max_length=10)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    message = models.CharField(max_length=300)
    value = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["run", "rule_code"])]

    def __str__(self) -> str:
        return f"{self.rule_code} {self.field} @ {self.source_row_number}"


class TransformationLog(models.Model):
    record = models.ForeignKey(
        StagingRecord, on_delete=models.CASCADE, related_name="transformations"
    )
    field = models.CharField(max_length=40)
    rule_code = models.CharField(max_length=10)
    value_before = models.CharField(max_length=200)
    value_after = models.CharField(max_length=200)

    def __str__(self) -> str:
        return f"{self.rule_code} {self.field}: {self.value_before} -> {self.value_after}"
