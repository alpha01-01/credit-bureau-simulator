"""Work items: judgement work and how well it was done (Document 07, Section 8).

A work item wraps one bureau review case. It carries what the bureau never
sees: the correct decision, taken from the world by the simulation when the
item is created. Employees (or the player) decide; the decision is applied to
the bureau exactly as given, and the item records whether it was right.
"""

from __future__ import annotations

from django.db import models

from apps.bureau.quality.models import ReviewCase
from apps.org.models import Employee, Organization


class ItemStatus(models.TextChoices):
    OPEN = "OPEN", "Waiting"
    IN_PROGRESS = "IN_PROGRESS", "Being worked on"
    DONE = "DONE", "Done"


class ResolvedBy(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "An employee"
    PLAYER = "PLAYER", "The player"


class WorkItem(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="work_items"
    )
    item_number = models.BigIntegerField()
    case = models.OneToOneField(ReviewCase, on_delete=models.CASCADE, related_name="work_item")
    item_type = models.CharField(max_length=30)
    difficulty = models.FloatField(help_text="0 (obvious) to 1 (very hard)")
    created_tick = models.BigIntegerField()
    status = models.CharField(max_length=15, choices=ItemStatus.choices, default=ItemStatus.OPEN)
    assignee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_items"
    )
    started_tick = models.BigIntegerField(null=True, blank=True)
    minutes_remaining = models.FloatField(null=True, blank=True)
    # The answer key. Hidden from the bureau and from the player until the debrief.
    correct_decision = models.CharField(max_length=30)
    correct_basis = models.CharField(max_length=300)
    # Outcome
    resolved_tick = models.BigIntegerField(null=True, blank=True)
    resolved_by = models.CharField(max_length=10, choices=ResolvedBy.choices, blank=True)
    decision = models.CharField(max_length=30, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    explanation = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "item_number"], name="workitem_unique_number"
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "item_number"])]

    def __str__(self) -> str:
        return f"Item {self.item_number} ({self.item_type})"
