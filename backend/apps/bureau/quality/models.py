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


class RuleAction(models.TextChoices):
    REPLACE = "REPLACE", "Replace a whole value (letter case ignored)"
    REMOVE = "REMOVE", "Remove these characters wherever they appear"


class CleansingRule(models.Model):
    """A cleansing rule the bureau wrote itself (P2.5): applied after the built-in ones.

    ``code`` (U01, U02, ...) is how its changes appear in the transformation log.
    A rule may apply to every provider or to one (``institution``).
    """

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="cleansing_rules"
    )
    code = models.CharField(max_length=10)
    field = models.CharField(max_length=40)
    action = models.CharField(max_length=10, choices=RuleAction.choices)
    find = models.CharField(max_length=100)
    replace = models.CharField(max_length=100, blank=True)
    institution = models.ForeignKey(
        "bureau_providers.Institution",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(help_text="Game time")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="cleansing_rule_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.field}"

    def apply(self, value: str) -> str:
        if self.action == RuleAction.REPLACE:
            return self.replace if value.upper() == self.find.upper() else value
        for character in self.find:
            value = value.replace(character, "")
        return value


class CaseType(models.TextChoices):
    MATCH_REVIEW = "MATCH_REVIEW", "Uncertain customer match"
    UNLOADABLE_TRIAGE = "UNLOADABLE_TRIAGE", "Unloadable record with a possible correction"
    DISPUTE = "DISPUTE", "A subject disputes accounts on their report"
    REGULATORY_RETURN = "REGULATORY_RETURN", "The monthly return to the Bank of Ghana"


class CaseStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"


class Decision(models.TextChoices):
    SAME_CUSTOMER = "SAME_CUSTOMER", "Same customer: link the record"
    DIFFERENT_CUSTOMER = "DIFFERENT_CUSTOMER", "Different customer: create a new one"
    CORRECT_AND_LOAD = "CORRECT_AND_LOAD", "Apply the proposed correction and load"
    RETURN_TO_PROVIDER = "RETURN_TO_PROVIDER", "Return to the provider for correction"
    UPHOLD_DISPUTE = "UPHOLD_DISPUTE", "Uphold: the accounts are not the subject's; correct"
    REJECT_DISPUTE = "REJECT_DISPUTE", "Reject: the accounts are the subject's"
    FILE_RETURN = "FILE_RETURN", "File the return"


ALLOWED_DECISIONS: dict[str, tuple[str, ...]] = {
    CaseType.MATCH_REVIEW: (
        Decision.SAME_CUSTOMER,
        Decision.DIFFERENT_CUSTOMER,
        Decision.RETURN_TO_PROVIDER,
    ),
    CaseType.UNLOADABLE_TRIAGE: (Decision.CORRECT_AND_LOAD, Decision.RETURN_TO_PROVIDER),
    CaseType.DISPUTE: (Decision.UPHOLD_DISPUTE, Decision.REJECT_DISPUTE),
    CaseType.REGULATORY_RETURN: (Decision.FILE_RETURN,),
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
    record = models.ForeignKey(
        StagingRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="cases"
    )
    dispute = models.ForeignKey(
        "Dispute", on_delete=models.CASCADE, null=True, blank=True, related_name="cases"
    )
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


class DisputeStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"


class Dispute(models.Model):
    """A subject says their credit report is wrong (P2.7; L.I. 2394, Regulations 23-26).

    ``accounts`` are the disputed accounts as (institution code, account number).
    While a dispute is open its accounts are flagged on reports. It must be settled
    by ``due_date`` (ASSUMPTION A-056 until reference R7 gives the statutory period).
    """

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="disputes"
    )
    dispute_number = models.BigIntegerField()
    customer = models.ForeignKey(
        "bureau_core.Customer", on_delete=models.CASCADE, related_name="disputes"
    )
    enquiry = models.ForeignKey(
        "bureau_core.Enquiry", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    subject_name = models.CharField(max_length=200)
    claim = models.CharField(max_length=500)
    accounts = models.JSONField(default=list)
    received_at = models.DateTimeField()
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=DisputeStatus.choices, default=DisputeStatus.OPEN
    )
    outcome = models.CharField(max_length=30, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "dispute_number"], name="dispute_unique_number"
            )
        ]

    def __str__(self) -> str:
        return f"Dispute {self.dispute_number}"


class CorrectionRecord(models.Model):
    """A controlled correction (Document 04, Section 19): nothing is silently overwritten.

    One row per account moved off a customer it did not belong to: what moved, from
    and to whom, why, on whose authority, and from which dispute.
    """

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="corrections"
    )
    kind = models.CharField(max_length=30, default="ACCOUNT_REASSIGNED")
    credit_account = models.ForeignKey(
        "bureau_core.CreditAccount", on_delete=models.CASCADE, related_name="corrections"
    )
    from_customer = models.ForeignKey(
        "bureau_core.Customer", on_delete=models.CASCADE, related_name="+"
    )
    to_customer = models.ForeignKey(
        "bureau_core.Customer", on_delete=models.CASCADE, related_name="+"
    )
    dispute = models.ForeignKey(
        Dispute, on_delete=models.CASCADE, null=True, blank=True, related_name="corrections"
    )
    reason = models.CharField(max_length=300)
    approved_by = models.CharField(max_length=120)
    corrected_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.kind} {self.credit_account_id}"


class RegulatoryReturn(models.Model):
    """The bureau's monthly return to the Bank of Ghana (P3.7; rule RETURN)."""

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="returns"
    )
    period = models.DateField(help_text="The month-end the return is for")
    due_date = models.DateField()
    case = models.OneToOneField(
        ReviewCase,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="regulatory_return",
    )
    filed_at = models.DateTimeField(null=True, blank=True)
    filed_by = models.CharField(max_length=120, blank=True)
    figures = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "period"], name="return_one_per_month")
        ]

    def __str__(self) -> str:
        return f"Return for {self.period:%B %Y}"
