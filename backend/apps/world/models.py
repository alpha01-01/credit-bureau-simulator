"""The world: hidden ground truth (Document 07, Section 7).

These tables hold what is *really* true in the simulated economy: who people
are, what they really borrowed, and how they really repaid. The bureau never
reads them. Only the simulation (to drive the world and produce provider
files) and work-item scoring (to judge decisions) may.

Rows are written in bulk by apps.world.generation.persist. `seq_no` gives
each entity a stable, seed-determined number within its world, independent
of database ids, so worlds can be compared across runs.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q


class World(models.Model):
    seed = models.BigIntegerField()
    scale = models.CharField(max_length=20)
    generator_version = models.CharField(max_length=20)
    history_start = models.DateField(help_text="First month-end with stored loan history")
    history_end = models.DateField(help_text="Last month-end with stored loan history")
    config = models.JSONField(help_text="Configuration snapshot used to generate this world")
    stats = models.JSONField(default=dict, help_text="Calibration statistics at generation")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"World {self.pk} (seed {self.seed}, {self.scale})"


class EconomyMonth(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="economy")
    period = models.DateField(help_text="Month-end date")
    stress_index = models.FloatField(help_text="National economic stress; positive = harder times")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "period"], name="world_economy_unique_period")
        ]

    def __str__(self) -> str:
        return f"{self.period}: stress {self.stress_index:+.2f}"


class Person(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="people")
    seq_no = models.IntegerField()
    ghana_card = models.CharField(max_length=20)
    first_name = models.CharField(max_length=60)
    middle_name = models.CharField(max_length=60, blank=True)
    last_name = models.CharField(max_length=60)
    gender = models.CharField(max_length=1)
    date_of_birth = models.DateField()
    phone_primary = models.CharField(max_length=15)
    phone_secondary = models.CharField(max_length=15, blank=True)
    region = models.CharField(max_length=30)
    town = models.CharField(max_length=60)
    name_group = models.CharField(max_length=20)
    employment_type = models.CharField(max_length=30)
    sector = models.CharField(max_length=40)
    monthly_income = models.DecimalField(max_digits=19, decimal_places=2)
    # Hidden attributes. Never visible to the bureau.
    risk_z = models.FloatField()
    income_stability = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "seq_no"], name="world_person_unique_seq"),
            models.UniqueConstraint(
                fields=["world", "ghana_card"], name="world_person_unique_card"
            ),
        ]

    def __str__(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


class Business(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="businesses")
    seq_no = models.IntegerField()
    owner = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="businesses")
    registered_name = models.CharField(max_length=200)
    trading_name = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=30)
    tin = models.CharField(max_length=20)
    sector = models.CharField(max_length=40)
    region = models.CharField(max_length=30)
    town = models.CharField(max_length=60)
    size_band = models.CharField(max_length=10)
    registration_date = models.DateField()
    monthly_revenue = models.DecimalField(max_digits=19, decimal_places=2)
    # Hidden attribute. Never visible to the bureau.
    health_z = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "seq_no"], name="world_business_unique_seq"),
            models.UniqueConstraint(
                fields=["world", "registration_number"], name="world_business_unique_reg"
            ),
        ]

    def __str__(self) -> str:
        return self.registered_name


class Lender(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="lenders")
    seq_no = models.IntegerField()
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=150)
    lender_type = models.CharField(max_length=30)
    founded = models.IntegerField()
    profile = models.JSONField(help_text="Lending policy and behaviour parameters")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "code"], name="world_lender_unique_code")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Branch(models.Model):
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="branches")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    region = models.CharField(max_length=30)
    town = models.CharField(max_length=60)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lender", "code"], name="world_branch_unique_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class LenderCustomer(models.Model):
    """A lender's own customer record. Each lender numbers its customers its own way."""

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="lender_customers")
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="customers")
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    customer_number = models.CharField(max_length=30)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lender", "customer_number"], name="world_lcust_unique_number"
            ),
            models.CheckConstraint(
                condition=(Q(person__isnull=False) & Q(business__isnull=True))
                | (Q(person__isnull=True) & Q(business__isnull=False)),
                name="world_lcust_one_borrower",
            ),
        ]

    def __str__(self) -> str:
        return self.customer_number


class Loan(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="loans")
    seq_no = models.IntegerField()
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="loans")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="loans")
    customer = models.ForeignKey(LenderCustomer, on_delete=models.CASCADE, related_name="loans")
    account_number = models.CharField(max_length=30)
    product = models.CharField(max_length=30)
    facility_type = models.CharField(max_length=30)
    currency = models.CharField(max_length=3, default="GHS")
    principal = models.DecimalField(max_digits=19, decimal_places=2)
    annual_rate = models.DecimalField(max_digits=7, decimal_places=4)
    term_months = models.IntegerField()
    installment = models.DecimalField(max_digits=19, decimal_places=2)
    disbursement_date = models.DateField()
    first_due_date = models.DateField()
    maturity_date = models.DateField()
    status = models.CharField(max_length=20, help_text="Status at the end of generated history")
    terminal_period = models.DateField(null=True, blank=True)
    first_default_period = models.DateField(
        null=True, blank=True, help_text="First month-end at 90+ days past due (truth label)"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "seq_no"], name="world_loan_unique_seq"),
            models.UniqueConstraint(
                fields=["lender", "account_number"], name="world_loan_unique_account"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account_number} ({self.product})"


class LoanMonth(models.Model):
    """True month-end state of a loan.

    By far the largest table (millions of rows per world). It is a PostgreSQL
    table partitioned by world: each world's history lives in its own
    partition, loaded in bulk and indexed once, and dropped instantly when the
    world is deleted. The partitioned parent is created by migration SQL, so
    Django does not manage it (managed = False). Rows are written only by
    apps.world.generation.persist; `world` and `lender` are denormalised from
    the loan, and integrity is guaranteed by the generator and its tests.
    """

    pk = models.CompositePrimaryKey("loan", "period")
    world = models.ForeignKey(
        World, on_delete=models.DO_NOTHING, related_name="+", db_constraint=False
    )
    lender = models.ForeignKey(
        Lender, on_delete=models.DO_NOTHING, related_name="+", db_constraint=False
    )
    loan = models.ForeignKey(
        Loan, on_delete=models.DO_NOTHING, related_name="months", db_constraint=False
    )
    period = models.DateField(help_text="Month-end date")
    installments_due = models.IntegerField()
    installments_paid = models.IntegerField()
    outstanding_balance = models.DecimalField(max_digits=19, decimal_places=2)
    principal_balance = models.DecimalField(max_digits=19, decimal_places=2)
    arrears_amount = models.DecimalField(max_digits=19, decimal_places=2)
    days_past_due = models.IntegerField()
    amount_paid = models.DecimalField(max_digits=19, decimal_places=2)
    status = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "world_loanmonth"

    def __str__(self) -> str:
        return f"{self.loan_id} @ {self.period}"


LOAN_MONTH_PARENT_SQL = """
CREATE TABLE world_loanmonth (
    world_id bigint NOT NULL,
    lender_id bigint NOT NULL,
    loan_id bigint NOT NULL,
    period date NOT NULL,
    installments_due integer NOT NULL,
    installments_paid integer NOT NULL,
    outstanding_balance numeric(19, 2) NOT NULL,
    principal_balance numeric(19, 2) NOT NULL,
    arrears_amount numeric(19, 2) NOT NULL,
    days_past_due integer NOT NULL CHECK (days_past_due >= 0),
    amount_paid numeric(19, 2) NOT NULL,
    status varchar(20) NOT NULL
) PARTITION BY LIST (world_id);
"""


# --- Dishonoured cheques and court judgments (P2.0c) ----------------------------
#
# Events in a person's financial life that lenders report on their own files
# (COND, CONJ). They grow out of the credit history: bank customers under
# stress write cheques that bounce; lenders sue some borrowers whose loans they
# wrote off. Each event is tied to the borrower's loan at the reporting lender,
# which keeps lineage and the answer key working as for credit records.


class EventMonth(models.Model):
    """Marks a month whose cheques and judgments have been generated (possibly none)."""

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    period = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "period"], name="world_eventmonth_unique")
        ]

    def __str__(self) -> str:
        return f"{self.world_id} {self.period:%Y-%m}"


class DishonouredCheque(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="+")
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name="+", help_text="The drawer's facility"
    )
    period = models.DateField(help_text="Month-end of the month the cheque bounced")
    account_number = models.CharField(max_length=30, help_text="Current account drawn on")
    account_opened = models.DateField()
    cheque_number = models.CharField(max_length=20)
    date_issued = models.DateField()
    date_bounced = models.DateField()
    reason = models.CharField(max_length=2, help_text="11 insufficient funds, 12 fraud")
    amount = models.DecimalField(max_digits=19, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lender", "account_number", "cheque_number"],
                name="world_cheque_unique_number",
            )
        ]
        indexes = [models.Index(fields=["world", "lender", "period"])]

    def __str__(self) -> str:
        return f"{self.account_number}/{self.cheque_number}"


class CourtJudgment(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="+")
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="+")
    period = models.DateField(help_text="Month-end of the month the case was filed")
    court_name = models.CharField(max_length=50)
    court_location = models.CharField(max_length=50)
    court_type = models.CharField(max_length=50)
    case_number = models.CharField(max_length=15)
    filing_date = models.DateField()
    case_type = models.CharField(max_length=1)
    case_reason = models.CharField(max_length=1)
    amount = models.DecimalField(max_digits=19, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "case_number"], name="world_case_unique")
        ]
        indexes = [models.Index(fields=["world", "lender", "period"])]

    def __str__(self) -> str:
        return self.case_number


# --- Provider submissions (Document 07, Section 7.3) ---------------------------
#
# What each provider *sent* for a month, generated by passing its true book
# through its Data Quality Profile. The files themselves are written to
# storage; these tables record where they are and, crucially, every defect
# that was injected and the correct value (the defect ledger). The bureau sees
# only the files. The ledger is the answer key for scoring and debriefs.


class ProviderSubmission(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="submissions")
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="submissions")
    period = models.DateField(help_text="Reporting month-end")
    due_date = models.DateField(help_text="Submission deadline")
    arrival_date = models.DateField(help_text="Date the provider actually sends the files")
    profile = models.JSONField(help_text="Data Quality Profile in force for this submission")
    template_version = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lender", "period"], name="world_submission_unique_period"
            )
        ]

    def __str__(self) -> str:
        return f"{self.lender_id} {self.period:%Y-%m}"


class ProviderFile(models.Model):
    submission = models.ForeignKey(
        ProviderSubmission, on_delete=models.CASCADE, related_name="files"
    )
    kind = models.CharField(max_length=4, help_text="CONC or BUSC (standard file identifier)")
    file_name = models.CharField(max_length=100)
    file_format = models.CharField(max_length=10)
    storage_path = models.CharField(max_length=300, help_text="Relative to STORAGE_ROOT")
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    header = models.JSONField(help_text="Column names exactly as written")
    row_count = models.IntegerField(help_text="Data rows, excluding the header")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["submission", "kind"], name="world_file_unique_kind")
        ]

    def __str__(self) -> str:
        return self.file_name


class ProviderFileRow(models.Model):
    """Which true loan each data row describes (row 1 is the first row after the header)."""

    file = models.ForeignKey(ProviderFile, on_delete=models.CASCADE, related_name="rows")
    row_number = models.IntegerField()
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["file", "row_number"], name="world_filerow_unique")
        ]

    def __str__(self) -> str:
        return f"{self.file_id}:{self.row_number}"


class DefectType(models.TextChoices):
    MISSING_FIELD = "MISSING_FIELD", "Mandatory field left blank"
    PHONE_FORMAT = "PHONE_FORMAT", "Phone number in a non-standard format"
    AMOUNT_FORMAT = "AMOUNT_FORMAT", "Amount in a non-standard format"
    NAME_TYPO = "NAME_TYPO", "Typo in a name"
    NAME_SWAP = "NAME_SWAP", "First name and surname swapped"
    WRONG_IDENTIFIER = "WRONG_IDENTIFIER", "Another customer's identifier"
    STALE_VALUE = "STALE_VALUE", "Value not updated since last month"
    INCONSISTENT_STATUS = "INCONSISTENT_STATUS", "Closed status with a balance outstanding"
    DATE_FORMAT = "DATE_FORMAT", "Date written month-first"
    FUTURE_DATE = "FUTURE_DATE", "Date after the reporting date"
    DUPLICATE_ROW = "DUPLICATE_ROW", "Row repeated in the file"
    OMITTED_ACCOUNT = "OMITTED_ACCOUNT", "Account left out of the file"
    TEMPLATE_DRIFT = "TEMPLATE_DRIFT", "Column renamed or moved"
    LATE_SUBMISSION = "LATE_SUBMISSION", "Submitted after the deadline"


class FileDefect(models.Model):
    """The defect ledger: one row per injected defect, with the correct value.

    ``file`` is empty for submission-level defects (lateness). ``row_number`` is
    empty for file-level defects (template drift) and omitted accounts.
    ``field`` is the template field name the defect affects, if any.
    """

    submission = models.ForeignKey(
        ProviderSubmission, on_delete=models.CASCADE, related_name="defects"
    )
    file = models.ForeignKey(
        ProviderFile, on_delete=models.CASCADE, null=True, blank=True, related_name="defects"
    )
    row_number = models.IntegerField(null=True, blank=True)
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    defect_type = models.CharField(max_length=30, choices=DefectType.choices)
    field = models.CharField(max_length=40, blank=True)
    true_value = models.CharField(max_length=200, blank=True)
    submitted_value = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["file", "row_number"], name="world_defect_file_row")]

    def __str__(self) -> str:
        return f"{self.defect_type} {self.field} @ {self.row_number}"


class LoanApplication(models.Model):
    """A credit application made to a world lender (Document 07, Section 6.4).

    Every loan began as an approved application; declined applications are
    generated alongside them. These are the moments a lender may check the
    bureau. Created for months of play, not for the generated history.
    """

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="applications")
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="applications")
    period = models.DateField(help_text="Month-end of the month the application was made")
    seq = models.IntegerField(help_text="Order within the lender and month")
    application_date = models.DateField()
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    product = models.CharField(max_length=30)
    approved = models.BooleanField()
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lender", "period", "seq"], name="world_application_unique_seq"
            )
        ]
        indexes = [models.Index(fields=["world", "period"])]

    def __str__(self) -> str:
        return f"{self.lender_id} {self.period:%Y-%m} #{self.seq}"
