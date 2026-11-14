"""The bureau's books: double-entry ledger, invoices and payments (Document 04, Section 12).

Posted journals are never edited or deleted (Document 04, Section 19): a
mistake is corrected by a reversal entry and a replacement. The models refuse
updates and deletes to make that rule hard to break by accident.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from apps.org.models import Organization


class AccountType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    EQUITY = "EQUITY", "Equity"
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


DEBIT_NORMAL = {AccountType.ASSET, AccountType.EXPENSE}


class Account(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="ledger_accounts"
    )
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=10, choices=AccountType.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="ledger_account_unique_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class ImmutableError(Exception):
    pass


class _Immutable(models.Model):
    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and not self._state.adding:
            raise ImmutableError(f"{type(self).__name__} rows are never changed once posted")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ImmutableError(f"{type(self).__name__} rows are never deleted; post a reversal")


class JournalEntry(_Immutable):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="journal_entries"
    )
    journal_reference = models.CharField(max_length=20)
    transaction_date = models.DateField()
    description = models.CharField(max_length=200)
    source_type = models.CharField(max_length=30, help_text="The business event that posted it")
    source_reference = models.CharField(max_length=60, blank=True)
    posted_at = models.DateTimeField(help_text="Game time of posting")
    rules_version = models.CharField(
        max_length=20, blank=True, help_text="Rule book edition used to compute it (D19)"
    )
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "journal_reference"], name="journal_unique_ref"
            )
        ]
        indexes = [models.Index(fields=["organization", "transaction_date"])]

    def __str__(self) -> str:
        return f"{self.journal_reference} {self.description}"


class JournalLine(_Immutable):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    memo = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(debit__gt=0) & models.Q(credit=0))
                | (models.Q(credit__gt=0) & models.Q(debit=0)),
                name="journal_line_one_side",
            )
        ]

    def __str__(self) -> str:
        return f"{self.account_id} Dr {self.debit} Cr {self.credit}"


class Invoice(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invoices"
    )
    invoice_number = models.CharField(max_length=20)
    subscriber = models.ForeignKey(
        "commercial.Subscriber", on_delete=models.PROTECT, related_name="invoices"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    issue_date = models.DateField()
    due_date = models.DateField()
    subtotal = models.DecimalField(max_digits=19, decimal_places=2)
    tax = models.DecimalField(max_digits=19, decimal_places=2)
    total = models.DecimalField(max_digits=19, decimal_places=2)
    journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="invoice")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "invoice_number"], name="invoice_unique_number"
            )
        ]

    def __str__(self) -> str:
        return self.invoice_number


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    product_code = models.CharField(max_length=30)
    description = models.CharField(max_length=200)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=19, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.product_code} x{self.quantity}"


class Payment(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="payments"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    received_on = models.DateField()
    reference = models.CharField(max_length=60)
    journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="payment")

    def __str__(self) -> str:
        return f"{self.reference} {self.amount}"
