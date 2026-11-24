"""Budgets against actuals, by month and cost centre (P3.8).

Each account in the chart belongs to one cost centre, so a centre's actual for a month
is the sum of its accounts' postings that month: the report agrees with the ledger by
construction. An expense account not given a centre is reported as unallocated, never
left out.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.org.models import Organization

from .models import AccountType, Budget, JournalLine

# (code, name, accounts). Revenue is a budget to reach; the others, budgets to keep within.
COST_CENTRES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("SALES", "Sales (revenue)", ("4000",)),
    ("DATA_OPERATIONS", "Data Operations", ("5000", "5010", "5300", "5500")),
    ("PREMISES", "Premises", ("5100", "5150")),
    ("IT", "IT", ("5200",)),
    ("COMPLIANCE", "Compliance", ("5400",)),
    ("FINANCE", "Finance", ("5600", "5700", "5800")),
    ("SUPPORT", "Customer Support", ("5250",)),
    ("PRODUCT", "Product Development", ("5900",)),
)
UNALLOCATED = "UNALLOCATED"
CENTRE_OF = {account: code for code, _, accounts in COST_CENTRES for account in accounts}
CENTRE_NAMES = {code: name for code, name, _ in COST_CENTRES} | {UNALLOCATED: "Unallocated"}


class BudgetError(Exception):
    pass


def month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


def set_budget(organization: Organization, centre: str, amount: Decimal, month: date) -> Budget:
    if centre not in CENTRE_NAMES or centre == UNALLOCATED:
        raise BudgetError(f"{centre} is not a cost centre")
    if amount < 0:
        raise BudgetError("A budget cannot be negative")
    found, _ = Budget.objects.update_or_create(
        organization=organization, cost_centre=centre, effective_from=month.replace(day=1),
        defaults={"amount": amount.quantize(Decimal("0.01"))},
    )  # fmt: skip
    return found


def budget_for(organization: Organization, centre: str, month: date) -> Decimal | None:
    row = (
        Budget.objects.filter(
            organization=organization, cost_centre=centre, effective_from__lte=month.replace(day=1)
        )
        .order_by("-effective_from")
        .values_list("amount", flat=True)
        .first()
    )
    return row


def actuals(organization: Organization, month: date) -> dict[str, Decimal]:
    """Each centre's postings for the month: income credit-positive, expenses debit-positive."""
    first, last = month_bounds(month)
    rows = (
        JournalLine.objects.filter(
            entry__organization=organization,
            entry__transaction_date__gte=first,
            entry__transaction_date__lte=last,
            account__account_type__in=[AccountType.INCOME, AccountType.EXPENSE],
        )
        .values("account__code", "account__account_type")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    out: dict[str, Decimal] = {}
    for row in rows:
        net = (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
        if row["account__account_type"] == AccountType.INCOME:
            net = -net
        centre = CENTRE_OF.get(row["account__code"], UNALLOCATED)
        out[centre] = out.get(centre, Decimal("0")) + net
    return out


def report(organization: Organization, month: date) -> dict[str, Any]:
    actual = actuals(organization, month)
    rows: list[dict[str, Any]] = []
    costs = revenue = Decimal("0")
    for code, name in CENTRE_NAMES.items():
        if code == UNALLOCATED and code not in actual:
            continue
        budget = None if code == UNALLOCATED else budget_for(organization, code, month)
        spent = actual.get(code, Decimal("0.00"))
        income = code == "SALES"
        if income:
            revenue += spent
        else:
            costs += spent
        variance = None if budget is None else (spent - budget if income else budget - spent)
        rows.append(
            {
                "centre": code, "name": name, "income": income, "budget": budget,
                "actual": spent, "variance": variance,
                "variance_share": float(variance / budget) if variance is not None and budget
                else None,
            }
        )  # fmt: skip
    return {"month": month_bounds(month)[1], "rows": rows, "revenue": revenue, "costs": costs,
            "result": revenue - costs}  # fmt: skip
