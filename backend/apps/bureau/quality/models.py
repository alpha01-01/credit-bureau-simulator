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


class CaseType(models.TextChoices):
    MATCH_REVIEW = "MATCH_REVIEW", "Uncertain customer match"
    UNLOADABLE_TRIAGE = "UNLOADABLE_TRIAGE", "Unloadable record with a possible correction"


class CaseStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"


class Decision(models.TextChoices):
    SAME_CUSTOMER = "SAME_CUSTOMER", "Same customer: link the record"
    DIFFERENT_CUSTOMER = "DIFFERENT_CUSTOMER", "Different customer: create a new one"
    CORRECT_AND_LOAD = "CORRECT_AND_LOAD", "Apply the proposed correction and load"
    RETURN_TO_PROVIDER = "RETURN_TO_PROVIDER", "Return to the provider for correction"


ALLOWED_DECISIONS: dict[str, tuple[str, ...]] = {
    CaseType.MATCH_REVIEW: (
        Decision.SAME_CUSTOMER,
        Decision.DIFFERENT_CUSTOMER,
        Decision.RETURN_TO_PROVIDER,
    ),
    CaseType.UNLOADABLE_TRIAGE: (Decision.CORRECT_AND_LOAD, Decision.RETURN_TO_PROVIDER),
}


class ReviewCase(models.Model):
    """A record the pipeline could not settle on its own: the Data Operations queue.

    ``evidence`` is what a reviewer sees: the record, the candidate customer,
    the comparison and any proposed corrections. Nothing here knows the right
    answer; the bureau finds out only through consequences.
    """

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="review_cases"
    )
    case_number = models.BigIntegerField()
    case_type = models.CharField(max_length=30, choices=CaseType.choices)
    record = models.ForeignKey(StagingRecord, on_delete=models.CASCADE, related_name="cases")
    candidate_customer = models.ForeignKey(
        "bureau_core.Customer", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    score = models.FloatField(null=True, blank=True)
    evidence = models.JSONField(default=dict)
    proposal = models.JSONField(default=dict, help_text="Proposed corrections: field -> value")
    status = models.CharField(max_length=10, choices=CaseStatus.choices, default=CaseStatus.OPEN)
    opened_at = models.DateTimeField()
    decision = models.CharField(max_length=30, choices=Decision.choices, blank=True)
    decided_by = models.CharField(max_length=120, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "case_number"], name="case_unique_number"
            )
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"Case {self.case_number} ({self.case_type})"
