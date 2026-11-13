"""Data providers the bureau has onboarded (Document 04, Section 5)."""

from __future__ import annotations

from django.db import models

from apps.org.models import Organization


class Institution(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="institutions"
    )
    institution_code = models.CharField(max_length=30)
    institution_name = models.CharField(max_length=150)
    institution_type = models.CharField(max_length=50)
    submission_frequency = models.CharField(max_length=30, default="MONTHLY")
    onboarding_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "institution_code"], name="provider_unique_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.institution_name} ({self.institution_code})"


class InstitutionBranch(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="branches")
    branch_code = models.CharField(max_length=30)
    branch_name = models.CharField(max_length=100)
    region = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "branch_code"], name="provider_branch_unique_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.branch_code} {self.branch_name}"
