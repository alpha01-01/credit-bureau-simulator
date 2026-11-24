"""Subscribers, products, contracts and usage (Document 04, Sections 5.3 and 11).

A subscriber is an institution that buys bureau products. It may also be a
data provider; the relationships are kept separate. Every billable enquiry
leaves a usage record, which invoicing (S7) turns into revenue.
"""

from __future__ import annotations

from django.db import models

from apps.org.models import Organization


class Product(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="products"
    )
    product_code = models.CharField(max_length=30)
    product_name = models.CharField(max_length=100)
    list_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="GHS per unit")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product_code"], name="product_unique_code"
            )
        ]

    def __str__(self) -> str:
        return self.product_name


class Subscriber(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="subscribers"
    )
    subscriber_code = models.CharField(max_length=30)
    subscriber_name = models.CharField(max_length=150)
    institution = models.ForeignKey(
        "bureau_providers.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Set when the subscriber is also a data provider",
    )
    is_active = models.BooleanField(default=True)
    since = models.DateField()
    # Finance has set up its billing (P3.9): until then its usage waits, unbilled.
    billing_ready = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "subscriber_code"], name="subscriber_unique_code"
            )
        ]

    def __str__(self) -> str:
        return self.subscriber_name


class ContractType(models.TextChoices):
    PAY_PER_REPORT = "PAY_PER_REPORT", "Pay per report"


class ServiceLevel(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    PREMIUM = "PREMIUM", "Premium: a service credit for a month with long downtime"


class Contract(models.Model):
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="contracts")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="contracts")
    contract_type = models.CharField(
        max_length=30, choices=ContractType.choices, default=ContractType.PAY_PER_REPORT
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="GHS per report")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    # Terms negotiated by Sales (P3.9); the defaults are the standard price list's.
    term_months = models.IntegerField(default=12)
    service_level = models.CharField(
        max_length=10, choices=ServiceLevel.choices, default=ServiceLevel.STANDARD
    )
    monthly_minimum = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="GHS a month, billed if not used"
    )
    discount_threshold = models.IntegerField(
        null=True, blank=True, help_text="Reports a month above which the discount applies"
    )
    discount_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)

    def __str__(self) -> str:
        return f"{self.subscriber} / {self.product} @ {self.unit_price}"

    @property
    def standard(self) -> bool:
        """On the standard price list's terms: nothing for Finance to check by hand."""
        return (
            self.term_months == 12
            and self.service_level == ServiceLevel.STANDARD
            and not self.monthly_minimum
            and not self.discount_rate
        )


class UsageRecord(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.PROTECT, related_name="usage")
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="usage")
    # A report and the score sold with it are two lines of one enquiry; mobile-loan checks,
    # billed in bulk, have none (P3.6).
    enquiry = models.ForeignKey(
        "bureau_core.Enquiry", on_delete=models.CASCADE, related_name="usage", null=True, blank=True
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    usage_at = models.DateTimeField()
    invoiced = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.subscriber_id} {self.product_id} x{self.quantity}"
