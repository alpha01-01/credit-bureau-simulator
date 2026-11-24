"""Supplier bills: recorded when they arrive, approved, and paid on their terms (P3.8).

A bill is recorded in the ledger the day it arrives (Dr the expense, or a prepayment;
Cr accounts payable), whether or not it is approved: the cost is the bureau's from the
day the service was supplied. Paying it clears the payable. A bill paid after its due
date carries the supplier's late charge (ASSUMPTION A-078).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Max

from apps.org.models import Organization

from .ledger import BANK, LATE_CHARGES, PAYABLES, cr, dr, money, post, reverse
from .models import BillStatus, SupplierBill

LATE_CHARGE_RATE = Decimal("0.02")  # of the bill, for each 30 days (or part) past due
DELEGATED = "Delegated authority"


class BillError(Exception):
    pass


def receive_bill(
    organization: Organization,
    supplier: tuple[str, str],
    reference: str,
    description: str,
    account_code: str,
    amount: Decimal,
    bill_date: date,
    due_date: date,
    at: datetime,
    duplicate_of: SupplierBill | None = None,
) -> SupplierBill:
    """Record a supplier's bill; one within the approval limit is approved at once."""
    code, name = supplier
    with transaction.atomic():
        number = (
            SupplierBill.objects.filter(organization=organization).aggregate(n=Max("number"))["n"]
            or 0
        ) + 1
        entry = post(
            organization, bill_date, f"Bill {number} from {name}: {description}",
            [dr(account_code, amount), cr(PAYABLES, amount)], "SUPPLIER_BILL", at, reference,
        )  # fmt: skip
        within = money(amount) <= organization.bill_approval_limit
        return SupplierBill.objects.create(
            organization=organization, number=number, supplier_code=code, supplier_name=name,
            reference=reference, description=description[:200], account_code=account_code,
            amount=money(amount), bill_date=bill_date, due_date=due_date,
            status=BillStatus.APPROVED if within else BillStatus.RECEIVED,
            approved_by=DELEGATED if within else "", journal=entry, duplicate_of=duplicate_of,
        )  # fmt: skip


def approve(bill: SupplierBill, by: str) -> SupplierBill:
    if bill.status != BillStatus.RECEIVED:
        raise BillError(f"Bill {bill.number} is {bill.get_status_display().lower()}")
    bill.status, bill.approved_by = BillStatus.APPROVED, by[:60]
    bill.save(update_fields=["status", "approved_by"])
    return bill


def reject(bill: SupplierBill, on: date, at: datetime, reason: str) -> SupplierBill:
    """Refuse a bill not owed (a duplicate, say): its recording is reversed."""
    if bill.status not in (BillStatus.RECEIVED, BillStatus.APPROVED):
        raise BillError(f"Bill {bill.number} is {bill.get_status_display().lower()}")
    reverse(bill.journal, on, f"bill {bill.number} rejected: {reason}"[:150], at)
    bill.status = BillStatus.REJECTED
    bill.save(update_fields=["status"])
    return bill


def late_charge(bill: SupplierBill, on: date) -> Decimal:
    days = (on - bill.due_date).days
    if days <= 0:
        return Decimal("0.00")
    periods = (days + 29) // 30
    return money(bill.amount * LATE_CHARGE_RATE * periods)


def pay(bill: SupplierBill, on: date, at: datetime) -> SupplierBill:
    """Pay an approved bill from the bank, with any late charge."""
    if bill.status != BillStatus.APPROVED:
        raise BillError(f"Bill {bill.number} is not approved for payment")
    fee = late_charge(bill, on)
    lines = [dr(PAYABLES, bill.amount), cr(BANK, bill.amount + fee)]
    if fee:
        lines.append(dr(LATE_CHARGES, fee, f"Late payment charge, due {bill.due_date:%d/%m/%Y}"))
    with transaction.atomic():
        entry = post(
            bill.organization, on, f"Payment of bill {bill.number} to {bill.supplier_name}",
            lines, "SUPPLIER_PAYMENT", at, f"BILL-{bill.number}",
        )  # fmt: skip
        bill.status, bill.paid_on, bill.late_fee, bill.payment_journal = (
            BillStatus.PAID, on, fee, entry,
        )  # fmt: skip
        bill.save(update_fields=["status", "paid_on", "late_fee", "payment_journal"])
    return bill
