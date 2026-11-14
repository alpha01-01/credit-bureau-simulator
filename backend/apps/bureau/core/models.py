"""The bureau's credit database: what the bureau believes (Document 04, Sections 6-7).

Customers and accounts are persistent identities; monthly observations are
history and are never overwritten. Every record carries its source submission
(lineage, Document 04, Section 2.5).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q

from apps.bureau.providers.models import Institution, InstitutionBranch
from apps.bureau.submissions.models import ProcessingRun, Submission, SubmissionFile
from apps.org.models import Organization


class CustomerType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Individual"
    BUSINESS = "BUSINESS", "Business"


class Customer(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="customers"
    )
    customer_type = models.CharField(max_length=20, choices=CustomerType.choices)
    customer_reference = models.CharField(max_length=50)
    record_status = models.CharField(max_length=30, default="ACTIVE")
    source_submission = models.ForeignKey(
        Submission, on_delete=models.PROTECT, related_name="+", help_text="First seen in"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "customer_reference"], name="customer_unique_ref"
            )
        ]

    def __str__(self) -> str:
        return self.customer_reference


class IndividualProfile(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="individual")
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender_code = models.CharField(max_length=20, blank=True)
    employment_status = models.CharField(max_length=50, blank=True)

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class BusinessProfile(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="business")
    registered_name = models.CharField(max_length=200)
    trading_name = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    tin_number = models.CharField(max_length=100, blank=True)
    sector_code = models.CharField(max_length=30, blank=True)
    registration_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return self.registered_name


class IdentifierType(models.TextChoices):
    GHANA_CARD = "GHANA_CARD", "Ghana Card"
    VOTER_ID = "VOTER_ID", "Voter's ID"
    DRIVER_LICENCE = "DRIVER_LICENCE", "Driver's licence"
    PASSPORT = "PASSPORT", "Passport"
    SSNIT = "SSNIT", "Social security number"
    BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION", "Business registration number"
    TIN = "TIN", "Taxpayer identification number"


class CustomerIdentifier(models.Model):
    """Identifiers are stored in plain form for synthetic data (Document 07, D8)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="identifiers")
    identifier_type = models.CharField(max_length=30, choices=IdentifierType.choices)
    identifier_value = models.CharField(max_length=100)
    verification_status = models.CharField(max_length=20, default="UNVERIFIED")
    source_submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            # One bureau customer per identifier value.
            models.UniqueConstraint(
                fields=["organization", "identifier_type", "identifier_value"],
                name="identifier_unique_value",
            )
        ]

    def __str__(self) -> str:
        return f"{self.identifier_type} {self.identifier_value}"


class CustomerContact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="contacts")
    contact_type = models.CharField(max_length=20, default="MOBILE")
    contact_value = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    source_submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "contact_type", "contact_value"], name="contact_unique_value"
            )
        ]

    def __str__(self) -> str:
        return self.contact_value


class ProviderCustomerLink(models.Model):
    """A provider's own customer number, linked to the bureau customer (Document 07, D4)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="customer_links"
    )
    provider_customer_number = models.CharField(max_length=50)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="provider_links")
    source_submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "provider_customer_number"], name="link_unique_number"
            )
        ]

    def __str__(self) -> str:
        return f"{self.institution_id}:{self.provider_customer_number}"


class CreditAccount(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="credit_accounts"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="accounts")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="accounts")
    branch = models.ForeignKey(
        InstitutionBranch, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    facility_account_number = models.CharField(max_length=100)
    facility_type = models.CharField(max_length=10)
    currency_code = models.CharField(max_length=3)
    disbursement_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    original_amount = models.DecimalField(max_digits=19, decimal_places=2)
    account_status = models.CharField(max_length=10, help_text="Latest reported status code")
    source_submission = models.ForeignKey(
        Submission, on_delete=models.PROTECT, related_name="+", help_text="First reported in"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Document 07, D4: one account per institution and account number.
            models.UniqueConstraint(
                fields=["institution", "facility_account_number"], name="account_unique_number"
            )
        ]

    def __str__(self) -> str:
        return self.facility_account_number


class AccountObservation(models.Model):
    """The state of an account at a reporting date, as reported (Document 04, Section 7.2)."""

    credit_account = models.ForeignKey(
        CreditAccount, on_delete=models.PROTECT, related_name="observations"
    )
    reporting_date = models.DateField()
    outstanding_balance = models.DecimalField(max_digits=19, decimal_places=2)
    arrears_amount = models.DecimalField(max_digits=19, decimal_places=2)
    days_past_due = models.IntegerField()
    instalment_amount = models.DecimalField(max_digits=19, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=19, decimal_places=2)
    facility_status = models.CharField(max_length=10)
    asset_classification = models.CharField(max_length=10)
    is_written_off = models.BooleanField()
    is_current = models.BooleanField(default=True)
    source_submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")
    source_file = models.ForeignKey(SubmissionFile, on_delete=models.PROTECT, related_name="+")
    source_row_number = models.IntegerField()
    processing_run = models.ForeignKey(ProcessingRun, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Document 07, D4: one current observation per account and date.
            models.UniqueConstraint(
                fields=["credit_account", "reporting_date"],
                condition=Q(is_current=True),
                name="observation_one_current",
            )
        ]

    def __str__(self) -> str:
        return f"{self.credit_account_id} @ {self.reporting_date}"


class _ReportedEvent(models.Model):
    """A one-off adverse event about a customer, as a provider reported it (P2.0c)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="%(class)ss")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="+")
    currency_code = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    source_submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")
    source_file = models.ForeignKey(SubmissionFile, on_delete=models.PROTECT, related_name="+")
    source_row_number = models.IntegerField()
    processing_run = models.ForeignKey(ProcessingRun, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class DishonouredCheque(_ReportedEvent):
    """A cheque returned unpaid, from a Consumer Dishonoured Cheque (COND) file."""

    account_number = models.CharField(max_length=30, help_text="Account the cheque was drawn on")
    cheque_number = models.CharField(max_length=20)
    account_opened = models.DateField(null=True, blank=True)
    date_issued = models.DateField()
    date_bounced = models.DateField()
    reason_code = models.CharField(max_length=2, help_text="11 insufficient funds, 12 fraud")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "account_number", "cheque_number"],
                name="cheque_unique_number",
            )
        ]

    def __str__(self) -> str:
        return f"{self.account_number}/{self.cheque_number}"


class CourtJudgment(_ReportedEvent):
    """A court case and its judgment, from a Consumer Judgment (CONJ) file."""

    court_name = models.CharField(max_length=50)
    court_location = models.CharField(max_length=50)
    court_type = models.CharField(max_length=50)
    case_number = models.CharField(max_length=15)
    filing_date = models.DateField()
    case_type = models.CharField(max_length=1)
    case_reason = models.CharField(max_length=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "case_number"], name="judgment_unique_case"
            )
        ]

    def __str__(self) -> str:
        return self.case_number


class EnquiryOutcome(models.TextChoices):
    HIT = "HIT", "Subject found"
    NO_HIT = "NO_HIT", "No record found"


class Enquiry(models.Model):
    """A subscriber's search for a subject, and the report returned (Document 07, D4)."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="enquiries"
    )
    enquiry_reference = models.CharField(max_length=30)
    subscriber = models.ForeignKey(
        "commercial.Subscriber", on_delete=models.PROTECT, related_name="enquiries"
    )
    product_code = models.CharField(max_length=30)
    purpose = models.CharField(max_length=30)
    consent_reference = models.CharField(max_length=60)
    identifier_type = models.CharField(max_length=30, choices=IdentifierType.choices)
    identifier_value = models.CharField(max_length=100)
    subject_name = models.CharField(max_length=200, help_text="As given by the subscriber")
    enquired_at = models.DateTimeField()
    outcome = models.CharField(max_length=10, choices=EnquiryOutcome.choices)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True, related_name="enquiries"
    )
    accounts_reported = models.IntegerField(default=0)
    report = models.JSONField(default=dict, help_text="The report as delivered")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "enquiry_reference"], name="enquiry_unique_ref"
            )
        ]
        indexes = [models.Index(fields=["customer", "enquired_at"])]

    def __str__(self) -> str:
        return self.enquiry_reference
