"""The bureau organisation (Document 04, Section 4.1).

Every bureau-side record belongs to one organisation, so a database can hold
several games (and, later, several bureaus) without their data mixing.
"""

from __future__ import annotations

import uuid

from django.db import models, transaction

COUNTERS = ("last_customer_seq", "last_submission_seq", "last_case_seq", "last_employee_seq")


class Organization(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=150)
    organization_code = models.CharField(max_length=30, unique=True)
    organization_type = models.CharField(max_length=30, default="CREDIT_BUREAU")
    country_code = models.CharField(max_length=2, default="GH")
    base_currency = models.CharField(max_length=3, default="GHS")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Counters for the bureau's own reference numbers.
    last_customer_seq = models.BigIntegerField(default=0)
    last_submission_seq = models.BigIntegerField(default=0)
    last_case_seq = models.BigIntegerField(default=0)
    last_employee_seq = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return self.name

    def allocate(self, counter: str, count: int = 1) -> int:
        """Reserve ``count`` numbers from a counter; returns the first. Locks the row."""
        if counter not in COUNTERS:
            raise ValueError(counter)
        with transaction.atomic():
            row = Organization.objects.select_for_update().only(counter).get(pk=self.pk)
            first = int(getattr(row, counter)) + 1
            Organization.objects.filter(pk=self.pk).update(**{counter: first + count - 1})
        setattr(self, counter, first + count - 1)
        return first


class Employee(models.Model):
    """A member of staff (Document 04, Section 4.3; Document 07, Section 8.3).

    ``skills`` holds a 0-1 skill per work-item type: the probability-scale
    ability to judge that kind of item correctly. ``experience`` counts items
    resolved per type; skill grows with it.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="employees"
    )
    employee_number = models.CharField(max_length=20)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    department = models.CharField(max_length=40, default="DATA_OPERATIONS")
    job_title = models.CharField(max_length=60)
    skills = models.JSONField(default=dict)
    experience = models.JSONField(default=dict)
    morale = models.FloatField(default=0.7)
    is_active = models.BooleanField(default=True)
    hired_on = models.DateField()
    # Work state, advanced by the simulation each tick.
    work_day = models.IntegerField(default=-1, help_text="Working-day index of done_today")
    done_today = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee_number"], name="employee_unique_number"
            )
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.job_title})"
