"""The bureau organisation (Document 04, Section 4.1).

Every bureau-side record belongs to one organisation, so a database can hold
several games (and, later, several bureaus) without their data mixing.
"""

from __future__ import annotations

import uuid

from django.db import models, transaction


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

    def __str__(self) -> str:
        return self.name

    def allocate(self, counter: str, count: int = 1) -> int:
        """Reserve ``count`` numbers from a counter; returns the first. Locks the row."""
        if counter not in ("last_customer_seq", "last_submission_seq"):
            raise ValueError(counter)
        with transaction.atomic():
            row = Organization.objects.select_for_update().only(counter).get(pk=self.pk)
            first = int(getattr(row, counter)) + 1
            Organization.objects.filter(pk=self.pk).update(**{counter: first + count - 1})
        setattr(self, counter, first + count - 1)
        return first
