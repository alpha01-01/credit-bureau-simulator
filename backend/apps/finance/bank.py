"""Bank reconciliation: the bank's statement against the ledger's bank account (P3.8).

Statement lines the bank made from the bureau's own payments and receipts are matched
to their ledger entries by reference. What is left is the difference to explain:

* **timing**: entries in the ledger the bank has not yet cleared (they clear next month);
* **missing entries**: bank charges the ledger does not have yet; Finance posts them;
* **errors**: a charge the bank should not have made; Finance queries it, and the bank
  reverses it on a later statement.

For any month: ledger balance + statement items not yet in the ledger - ledger entries
not yet on a statement = the statement's closing balance.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum

from apps.org.models import Organization

from .ledger import BANK, BANK_CHARGES, cr, dr, post
from .models import BankStatement, JournalEntry, JournalLine, LineCause, LineStatus, StatementLine

# Ledger entries the bank never sees as lines of their own: the opening position, and
# Finance's own postings of statement items.
NOT_ON_STATEMENTS = ("OPENING", "BANK_STATEMENT_ITEM")
STILL_OPEN = (LineStatus.OPEN, LineStatus.QUERIED, LineStatus.BANK_ERROR)


class ReconciliationError(Exception):
    pass


def bank_amounts(organization: Organization, entries: Any = None) -> dict[int, Decimal]:
    """Each journal entry's net movement on the bank account (+ in, - out)."""
    lines = JournalLine.objects.filter(entry__organization=organization, account__code=BANK)
    if entries is not None:
        lines = lines.filter(entry__in=entries)
    return {
        row["entry_id"]: (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
        for row in lines.values("entry_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }


def ledger_balance(organization: Organization, as_of: date) -> Decimal:
    totals = JournalLine.objects.filter(
        entry__organization=organization, account__code=BANK, entry__transaction_date__lte=as_of
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (totals["d"] or Decimal("0")) - (totals["c"] or Decimal("0"))


def uncleared(organization: Organization, period: date) -> list[tuple[JournalEntry, Decimal]]:
    """Ledger bank entries to ``period`` that no statement to ``period`` has cleared."""
    cleared = StatementLine.objects.filter(
        statement__organization=organization, statement__period__lte=period, entry__isnull=False
    ).values("entry_id")
    entries = (
        JournalEntry.objects.filter(
            organization=organization, transaction_date__lte=period, lines__account__code=BANK
        )
        .exclude(source_type__in=NOT_ON_STATEMENTS)
        .exclude(pk__in=cleared)
        .distinct()
        .order_by("transaction_date", "journal_reference")
    )
    amounts = bank_amounts(organization, entries)
    return [(e, amounts[e.pk]) for e in entries if amounts.get(e.pk)]


def unrecorded(organization: Organization, period: date) -> list[StatementLine]:
    """Statement items to ``period`` not in the ledger as at the end of ``period``."""
    lines = (
        StatementLine.objects.filter(
            statement__organization=organization, statement__period__lte=period
        )
        .exclude(cause=LineCause.LEDGER)
        .filter(
            Q(status__in=STILL_OPEN)
            | Q(status=LineStatus.POSTED, resolution__transaction_date__gt=period)
            | Q(status=LineStatus.MATCHED, corrected_by__statement__period__gt=period)
            | Q(status=LineStatus.MATCHED, corrects__statement__period__gt=period)
        )
        .select_related("statement")
        .order_by("statement__period", "line_number")
    )
    return list(lines)


def summary(statement: BankStatement) -> dict[str, Any]:
    org, period = statement.organization, statement.period
    waiting = uncleared(org, period)
    items = unrecorded(org, period)
    ledger = ledger_balance(org, period)
    explained = (
        ledger
        + sum((x.amount for x in items), Decimal("0"))
        - sum((amount for _, amount in waiting), Decimal("0"))
    )
    return {
        "period": period,
        "statement_balance": statement.closing_balance,
        "ledger_balance": ledger,
        "difference": statement.closing_balance - ledger,
        "uncleared": [
            {
                "reference": e.journal_reference,
                "date": e.transaction_date,
                "description": e.description,
                "amount": amount,
                "cause": "TIMING",
            }
            for e, amount in waiting
        ],
        "unrecorded": items,
        "explained_balance": explained,
        "reconciles": explained == statement.closing_balance,
        "open_items": sum(1 for x in items if x.status == LineStatus.OPEN),
    }


def post_line(line: StatementLine, at: datetime) -> StatementLine:
    """Record a statement item the ledger does not have (a charge, or a bank's correction)."""
    if line.cause == LineCause.LEDGER or line.status not in (LineStatus.OPEN, LineStatus.QUERIED):
        raise ReconciliationError(f"Line {line.line_number} needs no posting")
    if line.status == LineStatus.QUERIED and line.answer_tick is not None and not line.answer:
        raise ReconciliationError("The bank has not answered the query yet")
    org = line.statement.organization
    amount = abs(line.amount)
    lines = (
        [dr(BANK_CHARGES, amount), cr(BANK, amount)]
        if line.amount < 0
        else [dr(BANK, amount), cr(BANK_CHARGES, amount)]
    )
    entry = post(
        org, line.value_date, f"Bank statement: {line.description}", lines,
        "BANK_STATEMENT_ITEM", at, f"STMT-{line.statement.period:%Y%m}-{line.line_number}",
    )  # fmt: skip
    line.status, line.resolution = LineStatus.POSTED, entry
    line.save(update_fields=["status", "resolution"])
    return line


def query_line(line: StatementLine, answer_tick: int) -> StatementLine:
    if line.cause == LineCause.LEDGER or line.status != LineStatus.OPEN:
        raise ReconciliationError(f"Line {line.line_number} cannot be queried")
    line.status, line.answer_tick, line.answer = LineStatus.QUERIED, answer_tick, ""
    line.save(update_fields=["status", "answer_tick", "answer"])
    return line


def complete(statement: BankStatement, at: datetime) -> BankStatement:
    if statement.reconciled_at is not None:
        raise ReconciliationError(f"The {statement.period:%B %Y} statement is already reconciled")
    found = summary(statement)
    if found["open_items"]:
        raise ReconciliationError(
            f"{found['open_items']} statement item(s) are neither posted nor queried"
        )
    if not found["reconciles"]:
        raise ReconciliationError("The statement and the ledger do not reconcile")
    statement.reconciled_at = at
    statement.save(update_fields=["reconciled_at"])
    return statement
