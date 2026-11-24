"""Models for credit reports."""

from __future__ import annotations

from django.db import models

from apps.bureau.core.models import Customer
from apps.org.models import Organization


class CreditScore(models.Model):
    """A customer's current credit score (P3.6): refreshed from the deployed scorecards.

    ``score`` and ``band`` are the score a report shows (the composite, if one is in use);
    ``terms`` the scores of each term scorecard the customer is scored on, and ``reasons``
    the characteristics that cost the customer most points, in plain words.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="scores")
    as_of = models.DateField(help_text="The reporting month-end the score was computed at")
    score = models.IntegerField()
    band = models.CharField(max_length=1)
    reasons = models.JSONField(default=list)
    terms = models.JSONField(default=dict)
    model = models.CharField(max_length=40, help_text="The scorecard(s) it came from")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["customer"], name="credit_score_one_per_customer")
        ]
        indexes = [models.Index(fields=["organization", "customer"])]

    def __str__(self) -> str:
        return f"{self.customer_id}: {self.score} ({self.band})"


class BatchFile(models.Model):
    """A subscriber's file of applicants, answered record by record (P3.11)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    subscriber = models.ForeignKey(
        "commercial.Subscriber", on_delete=models.PROTECT, related_name="batches"
    )
    reference = models.CharField(max_length=30)
    received_at = models.DateTimeField()
    records = models.IntegerField(default=0)
    hits = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "reference"], name="batch_unique_ref")
        ]

    def __str__(self) -> str:
        return self.reference


class BatchRecord(models.Model):
    """One applicant in a batch file, and the enquiry that answered it."""

    batch = models.ForeignKey(BatchFile, on_delete=models.CASCADE, related_name="rows")
    row_number = models.IntegerField()
    identifier_type = models.CharField(max_length=30)
    identifier_value = models.CharField(max_length=100)
    subject_name = models.CharField(max_length=200)
    enquiry = models.OneToOneField(
        "bureau_core.Enquiry", on_delete=models.CASCADE, related_name="batch_record"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="batch_row_unique")
        ]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.row_number}"
