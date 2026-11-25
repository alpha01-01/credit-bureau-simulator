"""Automatic posting from business events (roadmap S7).

Every figure here is a placeholder until the owner's references arrive and is
flagged in docs/assumptions.md:

  A-031  VAT and levies on services: one combined 20% (VAT 15%, NHIL 2.5%,
         GETFund 2.5%), filed and paid by the end of the following month.
  A-032  Payroll: SSNIT 13% employer and 5.5% employee; PAYE on monthly
         chargeable income (gross less employee SSNIT) in the bands below;
         salaries paid on the last working day; PAYE and SSNIT remitted by
         the 14th of the following month.
  A-033  Accra office rent GHS 45,000 a month, paid a year in advance (as
         landlords usually require); IT hosting GHS 15,000 a month.
  A-034  Opening position of an established bureau: bank GHS 1,800,000, a
         year's rent prepaid, share capital GHS 2,000,000.
  A-035  Invoices monthly in arrears, dated the last day of the month of
         service (so revenue is recognised in that month), payable within
         30 days.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.commercial.models import Contract, ServiceLevel, Subscriber, UsageRecord
from apps.org.models import Employee, Organization
from apps.standards.rulebook import TAX_RULES, TaxRules

from .ledger import (
    BANK,
    EMPLOYER_SSNIT,
    IT,
    PAYE_PAYABLE,
    PREPAID_RENT,
    RECEIVABLES,
    RENT,
    RETAINED,
    REVENUE,
    SALARIES,
    SHARE_CAPITAL,
    SSNIT_PAYABLE,
    VAT_PAYABLE,
    cr,
    create_chart,
    dr,
    money,
    post,
)
from .models import Account, AccountType, Invoice, InvoiceLine, JournalLine, Payment

# Tax and payroll rates come from the rule book edition in force (apps.standards.rulebook).
MONTHLY_RENT = Decimal("45000.00")
MONTHLY_IT = Decimal("15000.00")
# ASSUMPTION A-048: matching software licence per month, by tooling level (P2.4).
MATCHING_TOOLING_COST = {
    "BASIC": Decimal("0.00"),
    "STANDARD": Decimal("8000.00"),
    "ADVANCED": Decimal("20000.00"),
}
# ASSUMPTION A-064: extra hosting for overnight processing capacity per month (P2.9).
IT_CAPACITY_COST = {"STANDARD": Decimal("0.00"), "HIGH": Decimal("12000.00")}
OPENING_BANK = Decimal("1800000.00")
SHARE_CAPITAL_AMOUNT = Decimal("2000000.00")
PAYMENT_TERMS_DAYS = 30


def open_books(organization: Organization, on: date, at: datetime) -> None:
    """Chart of accounts and the opening position of an established bureau."""
    create_chart(organization)
    prepaid = MONTHLY_RENT * 12
    retained = OPENING_BANK + prepaid - SHARE_CAPITAL_AMOUNT
    post(
        organization, on, "Opening balances", [
            dr(BANK, OPENING_BANK, "Opening bank balance"),
            dr(PREPAID_RENT, prepaid, "Rent paid a year in advance"),
            cr(SHARE_CAPITAL, SHARE_CAPITAL_AMOUNT),
            cr(RETAINED, retained, "Accumulated earnings to date"),
        ], "OPENING", at,
    )  # fmt: skip


def open_startup_books(
    organization: Organization, capital: Decimal, on: date, at: datetime
) -> None:
    """Chart of accounts and a new company's only asset: its shareholders' capital (P3.13)."""
    create_chart(organization)
    post(
        organization, on, "Shareholders subscribe the founding capital",
        [dr(BANK, capital, "Capital paid in"), cr(SHARE_CAPITAL, capital)], "OPENING", at,
    )  # fmt: skip


def balance(organization: Organization, code: str, as_of: date | None = None) -> Decimal:
    """Debit-positive balance of one account from posted lines."""
    lines = JournalLine.objects.filter(entry__organization=organization, account__code=code)
    if as_of is not None:
        lines = lines.filter(entry__transaction_date__lte=as_of)
    totals = lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (totals["d"] or Decimal("0")) - (totals["c"] or Decimal("0"))


# --- Monthly costs -------------------------------------------------------------------------


def month_start_costs(
    organization: Organization, month_first: date, at: datetime, rent: Decimal = MONTHLY_RENT
) -> None:
    """The month's rent, from the prepayment.

    IT hosting, the matching software and the landlord's renewal of the prepayment
    arrive as suppliers' bills from P3.8 (``apps.finance.payables``), recorded when
    received and paid on their terms.
    """
    if rent <= 0:  # a startup without an office yet (P3.13)
        return
    post(
        organization, month_first, f"Office rent for {month_first:%B %Y}",
        [dr(RENT, rent), cr(PREPAID_RENT, rent)], "RENT", at,
    )  # fmt: skip


# --- Billing ---------------------------------------------------------------------------------


SERVICE_CREDIT_HOURS = 4.0  # premium service: more downtime than this in a month earns a credit
SERVICE_CREDIT_RATE = Decimal("0.10")  # of the month's usage (A-079)


def invoice_usage(
    organization: Organization,
    period_start: date,
    period_end: date,
    issue_date: date,
    at: datetime,
    downtime_hours: float = 0.0,
) -> list[Invoice]:
    """One invoice per subscriber for its uninvoiced usage, on its contract's terms.

    The terms Sales negotiated show on the invoice (P3.9): a volume discount on the
    reports above the threshold, the monthly minimum made up when usage falls short,
    and, for premium service, a credit for a month with more than
    ``SERVICE_CREDIT_HOURS`` of downtime. A subscriber whose billing Finance has not
    set up yet is left out; its usage waits and is billed with the next invoice.
    """
    invoices = []
    with transaction.atomic():
        usage = UsageRecord.objects.select_for_update().filter(
            organization=organization,
            invoiced=False,
            usage_at__date__lte=period_end,
            subscriber__billing_ready=True,
        )
        by_subscriber: dict[int, list[UsageRecord]] = defaultdict(list)
        for record in usage.select_related("product").order_by("subscriber_id", "usage_at", "pk"):
            by_subscriber[record.subscriber_id].append(record)
        # A monthly minimum is owed even in a month with no usage at all.
        for contract in Contract.objects.filter(
            subscriber__organization=organization,
            subscriber__is_active=True,
            subscriber__billing_ready=True,
            monthly_minimum__gt=0,
            start_date__lte=period_end,
        ):
            by_subscriber.setdefault(contract.subscriber_id, [])
        for subscriber_id in sorted(by_subscriber):
            records = by_subscriber[subscriber_id]
            subscriber = Subscriber.objects.get(pk=subscriber_id)
            # Each product's current contract: the one that started last.
            current: dict[int, Contract] = {}
            for contract in Contract.objects.filter(
                subscriber=subscriber, start_date__lte=period_end
            ).order_by("start_date", "pk"):
                current[contract.product_id] = contract
            groups: dict[tuple[str, str, Decimal], int] = defaultdict(int)
            for r in records:
                groups[(r.product.product_code, r.product.product_name, r.unit_price)] += r.quantity
            lines = [
                (code, name, qty, price, money(price * qty))
                for (code, name, price), qty in sorted(groups.items())
            ]
            for contract in current.values():
                lines += _terms(contract, lines, downtime_hours)
            if not lines:
                continue
            subtotal = money(sum((x[4] for x in lines), Decimal("0")))
            rules = TAX_RULES.at(issue_date)  # the rate in force when the invoice is issued
            tax = money(subtotal * rules.vat_and_levies)
            total = subtotal + tax
            seq = organization.allocate("last_invoice_seq")
            number = f"INV{seq:07d}"
            entry = post(
                organization, issue_date,
                f"Invoice {number}: {subscriber.subscriber_name}, {period_start:%B %Y}",
                [dr(RECEIVABLES, total), cr(REVENUE, subtotal), cr(VAT_PAYABLE, tax)],
                "INVOICE", at, number, rules_version=rules.version,
            )  # fmt: skip
            invoice = Invoice.objects.create(
                organization=organization,
                invoice_number=number,
                subscriber=subscriber,
                period_start=period_start,
                period_end=period_end,
                issue_date=issue_date,
                due_date=issue_date + timedelta(days=PAYMENT_TERMS_DAYS),
                subtotal=subtotal,
                tax=tax,
                total=total,
                journal=entry,
            )
            InvoiceLine.objects.bulk_create(
                InvoiceLine(
                    invoice=invoice, product_code=code, description=name, quantity=qty,
                    unit_price=price, amount=amount,
                )
                for code, name, qty, price, amount in lines
            )  # fmt: skip
            UsageRecord.objects.filter(pk__in=[r.pk for r in records]).update(invoiced=True)
            invoices.append(invoice)
    return invoices


Line = tuple[str, str, int, Decimal, Decimal]  # code, description, quantity, unit price, amount


def _terms(contract: Contract, usage: list[Line], downtime_hours: float) -> list[Line]:
    """The lines the contract's negotiated terms add to the usage (P3.9)."""
    added: list[Line] = []
    code = contract.product.product_code
    if contract.discount_rate and contract.discount_threshold is not None:
        units = sum(q for c, _, q, p, _ in usage if c == code and p == contract.unit_price)
        above = units - contract.discount_threshold
        if above > 0:
            off = money(contract.unit_price * contract.discount_rate)
            added.append((
                "VOLUME_DISCOUNT",
                f"Volume discount: {contract.discount_rate:.0%} off reports above "
                f"{contract.discount_threshold} a month",
                above, -off, -money(off * above),
            ))  # fmt: skip
    used = sum((x[4] for x in usage + added), Decimal("0"))
    if contract.monthly_minimum and used < contract.monthly_minimum:
        short = money(contract.monthly_minimum - used)
        added.append(("MINIMUM", f"Monthly minimum of GHS {contract.monthly_minimum:,.2f}",
                      1, short, short))  # fmt: skip
    if contract.service_level == ServiceLevel.PREMIUM and downtime_hours > SERVICE_CREDIT_HOURS:
        base = sum((x[4] for x in usage + added), Decimal("0"))
        credit = money(base * SERVICE_CREDIT_RATE)
        if credit:
            added.append((
                "SERVICE_CREDIT",
                f"Service credit: {downtime_hours:.1f} hours of downtime "
                f"(premium service, over {SERVICE_CREDIT_HOURS:.0f})",
                1, -credit, -credit,
            ))  # fmt: skip
    return added


def receive_payment(invoice: Invoice, amount: Decimal, received_on: date, at: datetime) -> Payment:
    organization = invoice.organization
    reference = f"PAY-{invoice.invoice_number}"
    entry = post(
        organization, received_on, f"Payment for {invoice.invoice_number}",
        [dr(BANK, amount), cr(RECEIVABLES, amount)], "PAYMENT", at, reference,
    )  # fmt: skip
    return Payment.objects.create(
        organization=organization, invoice=invoice, amount=money(amount),
        received_on=received_on, reference=reference, journal=entry,
    )  # fmt: skip


def outstanding(invoice: Invoice) -> Decimal:
    paid = invoice.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    return invoice.total - paid


# --- Payroll and taxes ------------------------------------------------------------------------


def paye(chargeable: Decimal, rules: TaxRules) -> Decimal:
    """Monthly PAYE on chargeable income, by the edition's bands."""
    tax = Decimal("0")
    remaining = chargeable
    for width, rate in rules.paye_bands:
        portion = remaining if width is None else min(remaining, width)
        if portion <= 0:
            break
        tax += portion * rate
        remaining -= portion
    return money(tax)


def run_payroll(organization: Organization, pay_date: date, at: datetime) -> Decimal:
    """Pay the month's salaries. Returns total gross pay."""
    staff = list(
        Employee.objects.filter(organization=organization, is_active=True).order_by(
            "employee_number"
        )
    )
    gross = money(sum((e.monthly_salary for e in staff), Decimal("0")))
    if not gross:
        return gross
    rules = TAX_RULES.at(pay_date)
    employee_ssnit = sum(
        (money(e.monthly_salary * rules.ssnit_employee) for e in staff), Decimal("0")
    )
    employer_ssnit = sum(
        (money(e.monthly_salary * rules.ssnit_employer) for e in staff), Decimal("0")
    )
    income_tax = sum(
        (paye(e.monthly_salary - money(e.monthly_salary * rules.ssnit_employee), rules)
         for e in staff),
        Decimal("0"),
    )  # fmt: skip
    net = gross - employee_ssnit - income_tax
    post(
        organization, pay_date, f"Salaries for {pay_date:%B %Y} ({len(staff)} staff)", [
            dr(SALARIES, gross),
            dr(EMPLOYER_SSNIT, employer_ssnit),
            cr(BANK, net, "Net pay"),
            cr(PAYE_PAYABLE, income_tax),
            cr(SSNIT_PAYABLE, employee_ssnit + employer_ssnit),
        ], "PAYROLL", at, rules_version=rules.version,
    )  # fmt: skip
    return gross


def remit_payroll_taxes(organization: Organization, on: date, at: datetime) -> None:
    """Pay PAYE to the GRA and contributions to SSNIT (balances owed at the end of last month)."""
    month_end = on.replace(day=1) - timedelta(days=1)
    for code, payee in ((PAYE_PAYABLE, "GRA (PAYE)"), (SSNIT_PAYABLE, "SSNIT")):
        owed = -balance(organization, code, month_end)
        if owed > 0:
            post(
                organization, on, f"Remittance to {payee} for {month_end:%B %Y}",
                [dr(code, owed), cr(BANK, owed)], "REMITTANCE", at,
            )  # fmt: skip


def file_vat(organization: Organization, on: date, at: datetime) -> None:
    """Pay last month's VAT and levies to the GRA."""
    month_end = on.replace(day=1) - timedelta(days=1)
    owed = -balance(organization, VAT_PAYABLE, month_end)
    if owed > 0:
        post(
            organization, on, f"VAT and levies return for {month_end:%B %Y}",
            [dr(VAT_PAYABLE, owed), cr(BANK, owed)], "VAT_RETURN", at,
        )  # fmt: skip


def account_exists(organization: Organization) -> bool:
    return Account.objects.filter(organization=organization).exists()


PROVIDER_TRAINING = ("5300", "Provider relations and training")


def provider_training(
    organization: Organization, provider: str, amount: Decimal, on: date, at: datetime
) -> None:
    """A data-quality training session for a provider's staff, paid by the bureau (P2.6)."""
    code, name = PROVIDER_TRAINING
    Account.objects.get_or_create(
        organization=organization, code=code,
        defaults={"name": name, "account_type": AccountType.EXPENSE},
    )  # fmt: skip
    post(
        organization, on, f"Data quality training for {provider}",
        [dr(code, amount), cr(BANK, amount)], "PROVIDER_TRAINING", at,
    )  # fmt: skip


REGULATORY_PENALTIES = ("5400", "Regulatory penalties")


def regulatory_penalty(organization: Organization, amount: Decimal, on: date, at: datetime) -> None:
    """A financial penalty imposed by the regulator (P2.7)."""
    code, name = REGULATORY_PENALTIES
    Account.objects.get_or_create(
        organization=organization, code=code,
        defaults={"name": name, "account_type": AccountType.EXPENSE},
    )  # fmt: skip
    post(
        organization, on, "Regulatory penalty: repeated breaches of dispute deadlines",
        [dr(code, amount), cr(BANK, amount)], "REGULATORY_PENALTY", at,
    )  # fmt: skip


STAFF_TRAINING = ("5500", "Staff training")


def staff_training(
    organization: Organization, employee: str, amount: Decimal, on: date, at: datetime
) -> None:
    """A training course for one of the bureau's own staff (P2.9)."""
    code, name = STAFF_TRAINING
    Account.objects.get_or_create(
        organization=organization, code=code,
        defaults={"name": name, "account_type": AccountType.EXPENSE},
    )  # fmt: skip
    post(
        organization, on, f"Training course for {employee}",
        [dr(code, amount), cr(BANK, amount)], "STAFF_TRAINING", at,
    )  # fmt: skip


def incident_vendor(organization: Organization, amount: Decimal, on: date, at: datetime) -> None:
    """Emergency support from the IT vendor during an outage (P2.9)."""
    post(
        organization, on, "Emergency IT vendor support for an outage",
        [dr(IT, amount), cr(BANK, amount)], "IT_INCIDENT", at,
    )  # fmt: skip


FINANCE_COSTS = ("5600", "Overdraft interest")


def overdraft_interest(organization: Organization, amount: Decimal, on: date, at: datetime) -> None:
    """A month's interest on the overdrawn bank balance (P2.10)."""
    code, name = FINANCE_COSTS
    Account.objects.get_or_create(
        organization=organization, code=code,
        defaults={"name": name, "account_type": AccountType.EXPENSE},
    )  # fmt: skip
    post(
        organization, on, f"Overdraft interest for {on:%B %Y}",
        [dr(code, amount), cr(BANK, amount)], "OVERDRAFT_INTEREST", at,
    )  # fmt: skip


def dividend_paid(organization: Organization, amount: Decimal, on: date, at: datetime) -> None:
    """A dividend paid to the shareholders from retained earnings (P3.13: Expert's cash)."""
    post(
        organization, on, "Dividend paid to shareholders",
        [dr(RETAINED, amount), cr(BANK, amount)], "DIVIDEND", at,
    )  # fmt: skip


def capital_injection(organization: Organization, amount: Decimal, on: date, at: datetime) -> None:
    """New shares issued to the shareholders for cash (P2.10)."""
    post(
        organization, on, "Shareholders subscribe new capital",
        [dr(BANK, amount), cr(SHARE_CAPITAL, amount)], "CAPITAL_INJECTION", at,
    )  # fmt: skip
