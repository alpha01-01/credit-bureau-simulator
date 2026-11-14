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

from apps.commercial.models import Subscriber, UsageRecord
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
from .models import Account, Invoice, InvoiceLine, JournalLine, Payment

# Tax and payroll rates come from the rule book edition in force (apps.standards.rulebook).
MONTHLY_RENT = Decimal("45000.00")
MONTHLY_IT = Decimal("15000.00")
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


def balance(organization: Organization, code: str, as_of: date | None = None) -> Decimal:
    """Debit-positive balance of one account from posted lines."""
    lines = JournalLine.objects.filter(entry__organization=organization, account__code=code)
    if as_of is not None:
        lines = lines.filter(entry__transaction_date__lte=as_of)
    totals = lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (totals["d"] or Decimal("0")) - (totals["c"] or Decimal("0"))


# --- Monthly costs -------------------------------------------------------------------------


def month_start_costs(organization: Organization, month_first: date, at: datetime) -> None:
    """Rent for the month (from the prepayment, renewing it when used up) and IT hosting."""
    with transaction.atomic():
        if balance(organization, PREPAID_RENT) < MONTHLY_RENT:
            post(
                organization, month_first, "Office rent: next 12 months paid in advance",
                [dr(PREPAID_RENT, MONTHLY_RENT * 12), cr(BANK, MONTHLY_RENT * 12)],
                "RENT_ADVANCE", at,
            )  # fmt: skip
        post(
            organization, month_first, f"Office rent for {month_first:%B %Y}",
            [dr(RENT, MONTHLY_RENT), cr(PREPAID_RENT, MONTHLY_RENT)], "RENT", at,
        )  # fmt: skip
        post(
            organization, month_first, f"IT hosting for {month_first:%B %Y}",
            [dr(IT, MONTHLY_IT), cr(BANK, MONTHLY_IT)], "IT_HOSTING", at,
        )  # fmt: skip


# --- Billing ---------------------------------------------------------------------------------


def invoice_usage(
    organization: Organization, period_start: date, period_end: date, issue_date: date, at: datetime
) -> list[Invoice]:
    """One invoice per subscriber for the period's uninvoiced usage."""
    invoices = []
    with transaction.atomic():
        usage = UsageRecord.objects.select_for_update().filter(
            organization=organization,
            invoiced=False,
            usage_at__date__gte=period_start,
            usage_at__date__lte=period_end,
        )
        by_subscriber: dict[int, list[UsageRecord]] = defaultdict(list)
        for record in usage.select_related("product").order_by("subscriber_id", "usage_at", "pk"):
            by_subscriber[record.subscriber_id].append(record)
        for subscriber_id in sorted(by_subscriber):
            records = by_subscriber[subscriber_id]
            groups: dict[tuple[str, str, Decimal], int] = defaultdict(int)
            for r in records:
                groups[(r.product.product_code, r.product.product_name, r.unit_price)] += r.quantity
            subtotal = money(sum((p * q for (_, _, p), q in groups.items()), Decimal("0")))
            rules = TAX_RULES.at(issue_date)  # the rate in force when the invoice is issued
            tax = money(subtotal * rules.vat_and_levies)
            total = subtotal + tax
            seq = organization.allocate("last_invoice_seq")
            number = f"INV{seq:07d}"
            subscriber = Subscriber.objects.get(pk=subscriber_id)
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
                    unit_price=price, amount=money(price * qty),
                )
                for (code, name, price), qty in sorted(groups.items())
            )  # fmt: skip
            UsageRecord.objects.filter(pk__in=[r.pk for r in records]).update(invoiced=True)
            invoices.append(invoice)
    return invoices


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
