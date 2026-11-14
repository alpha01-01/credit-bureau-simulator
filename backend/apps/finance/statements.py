"""Financial statements, derived only from posted journal lines (Document 04, Section 12.4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.org.models import Organization

from .ledger import BANK, PAYE_PAYABLE, RECEIVABLES, SSNIT_PAYABLE, VAT_PAYABLE
from .models import DEBIT_NORMAL, Account, AccountType, Invoice, JournalLine

ZERO = Decimal("0.00")


def _totals(
    organization: Organization, start: date | None, end: date
) -> dict[str, tuple[Account, Decimal, Decimal]]:
    lines = JournalLine.objects.filter(
        entry__organization=organization, entry__transaction_date__lte=end
    )
    if start is not None:
        lines = lines.filter(entry__transaction_date__gte=start)
    sums = {
        row["account_id"]: (row["d"] or ZERO, row["c"] or ZERO)
        for row in lines.values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    return {
        a.code: (a, *sums.get(a.pk, (ZERO, ZERO)))
        for a in Account.objects.filter(organization=organization).order_by("code")
    }


def _natural(account: Account, debit: Decimal, credit: Decimal) -> Decimal:
    return debit - credit if account.account_type in DEBIT_NORMAL else credit - debit


def trial_balance(organization: Organization, as_of: date) -> dict[str, Any]:
    rows = []
    total_dr = total_cr = ZERO
    for code, (account, debit, credit) in _totals(organization, None, as_of).items():
        net = debit - credit
        row_dr, row_cr = (net, ZERO) if net >= 0 else (ZERO, -net)
        if row_dr or row_cr:
            rows.append({"code": code, "name": account.name, "debit": row_dr, "credit": row_cr})
        total_dr += row_dr
        total_cr += row_cr
    return {"as_of": as_of, "rows": rows, "total_debit": total_dr, "total_credit": total_cr}


def income_statement(organization: Organization, start: date, end: date) -> dict[str, Any]:
    income: list[dict[str, Any]] = []
    expenses: list[dict[str, Any]] = []
    for code, (account, debit, credit) in _totals(organization, start, end).items():
        amount = _natural(account, debit, credit)
        if account.account_type == AccountType.INCOME:
            income.append({"code": code, "name": account.name, "amount": amount})
        elif account.account_type == AccountType.EXPENSE:
            expenses.append({"code": code, "name": account.name, "amount": amount})
    total_income = sum((r["amount"] for r in income), ZERO)
    total_expenses = sum((r["amount"] for r in expenses), ZERO)
    return {
        "start": start,
        "end": end,
        "income": income,
        "expenses": expenses,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_profit": total_income - total_expenses,
    }


def balance_sheet(organization: Organization, as_of: date) -> dict[str, Any]:
    sections: dict[str, list[dict[str, Any]]] = {"assets": [], "liabilities": [], "equity": []}
    earnings = ZERO
    for code, (account, debit, credit) in _totals(organization, None, as_of).items():
        amount = _natural(account, debit, credit)
        kind = account.account_type
        if kind == AccountType.ASSET:
            sections["assets"].append({"code": code, "name": account.name, "amount": amount})
        elif kind == AccountType.LIABILITY:
            sections["liabilities"].append({"code": code, "name": account.name, "amount": amount})
        elif kind == AccountType.EQUITY:
            sections["equity"].append({"code": code, "name": account.name, "amount": amount})
        elif kind == AccountType.INCOME:
            earnings += amount
        else:
            earnings -= amount
    sections["equity"].append(
        {"code": "", "name": "Earnings not yet closed to retained earnings", "amount": earnings}
    )
    totals = {k: sum((r["amount"] for r in rows), ZERO) for k, rows in sections.items()}
    return {
        "as_of": as_of,
        **sections,
        "total_assets": totals["assets"],
        "total_liabilities": totals["liabilities"],
        "total_equity": totals["equity"],
        "balances": totals["assets"] == totals["liabilities"] + totals["equity"],
    }


def cash_position(organization: Organization, as_of: date) -> dict[str, Any]:
    totals = _totals(organization, None, as_of)

    def natural(code: str) -> Decimal:
        account, debit, credit = totals[code]
        return _natural(account, debit, credit)

    overdue = [
        i
        for i in Invoice.objects.filter(organization=organization, due_date__lt=as_of)
        if i.total - sum((p.amount for p in i.payments.all()), ZERO) > 0
    ]
    return {
        "as_of": as_of,
        "bank": natural(BANK),
        "receivables": natural(RECEIVABLES),
        "overdue_invoices": len(overdue),
        "taxes_owed": natural(VAT_PAYABLE) + natural(PAYE_PAYABLE) + natural(SSNIT_PAYABLE),
    }
