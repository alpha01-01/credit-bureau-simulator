"""The bureau organisation (Document 04, Section 4.1).

Every bureau-side record belongs to one organisation, so a database can hold
several games (and, later, several bureaus) without their data mixing.
"""

from __future__ import annotations

import uuid

from django.db import connection, models

COUNTERS = (
    "last_customer_seq",
    "last_submission_seq",
    "last_case_seq",
    "last_employee_seq",
    "last_enquiry_seq",
    "last_journal_seq",
    "last_invoice_seq",
    "last_dispute_seq",
)


class Organization(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=150)
    organization_code = models.CharField(max_length=30, unique=True)
    organization_type = models.CharField(max_length=30, default="CREDIT_BUREAU")
    country_code = models.CharField(max_length=2, default="GH")
    base_currency = models.CharField(max_length=3, default="GHS")
    rejection_policy = models.CharField(
        max_length=10,
        choices=[("STANDARD", "Standard"), ("CORE", "Core fields only")],
        default="STANDARD",
        help_text="How strictly incoming records are rejected (D18)",
    )
    # Customer matching (P2.4; Document 07, Section 8.2): the tooling the bureau has
    # bought, and the thresholds it sets.
    matching_tooling = models.CharField(
        max_length=10,
        choices=[
            ("BASIC", "Identifiers only"),
            ("STANDARD", "Fuzzy matching on name and date of birth"),
            ("ADVANCED", "Fuzzy matching with phone numbers"),
        ],
        default="BASIC",
    )
    match_auto_link = models.FloatField(
        default=0.92, help_text="Link without review at or above this similarity"
    )
    it_capacity = models.CharField(
        max_length=10,
        choices=[("STANDARD", "Standard"), ("HIGH", "High")],
        default="STANDARD",
        help_text="Overnight processing capacity (P2.9)",
    )
    rule_overrides = models.JSONField(
        default=dict,
        help_text="Validation rules the bureau has relaxed: code -> WARNING or OFF (P2.5)",
    )
    match_review = models.FloatField(
        default=0.75, help_text="Below auto-link, hold for review at or above this similarity"
    )
    retention_years = models.PositiveSmallIntegerField(
        default=5, help_text="How long closed accounts stay on reports (P3.7; the law: 5)"
    )
    bill_approval_limit = models.DecimalField(
        max_digits=19, decimal_places=2, default=20000,
        help_text="Supplier bills up to this are approved by delegated authority (P3.8)",
    )  # fmt: skip
    closed_through = models.DateField(
        null=True, blank=True, help_text="The last month-end closed: no posting on or before it"
    )
    support_staff = models.IntegerField(
        default=2, help_text="Contact-centre agents answering tickets (P3.10)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Counters for the bureau's own reference numbers.
    last_customer_seq = models.BigIntegerField(default=0)
    last_submission_seq = models.BigIntegerField(default=0)
    last_case_seq = models.BigIntegerField(default=0)
    last_employee_seq = models.BigIntegerField(default=0)
    last_enquiry_seq = models.BigIntegerField(default=0)
    last_journal_seq = models.BigIntegerField(default=0)
    last_invoice_seq = models.BigIntegerField(default=0)
    last_dispute_seq = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return self.name

    def allocate(self, counter: str, count: int = 1) -> int:
        """Reserve ``count`` numbers from a counter; returns the first. Locks the row."""
        if counter not in COUNTERS:
            raise ValueError(counter)
        # One statement: the row lock is taken and the new value returned together.
        table, column = Organization._meta.db_table, connection.ops.quote_name(counter)
        sql = f"UPDATE {table} SET {column} = {column} + %s WHERE id = %s RETURNING {column}"  # noqa: S608 - a known counter
        with connection.cursor() as cursor:
            cursor.execute(sql, [count, self.pk])
            row = cursor.fetchone()
        if row is None:
            raise Organization.DoesNotExist(self.pk)
        last = int(row[0])
        setattr(self, counter, last)
        return last - count + 1


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
    monthly_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Gross, GHS"
    )
    is_active = models.BooleanField(default=True)
    has_system_access = models.BooleanField(
        default=True, help_text="Can reach the bureau's data; a leaver keeps it until reviewed"
    )
    hired_on = models.DateField()
    # Work state, advanced by the simulation each tick.
    away_until_tick = models.BigIntegerField(
        default=0, help_text="On training until the end of this tick (P2.9)"
    )
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
