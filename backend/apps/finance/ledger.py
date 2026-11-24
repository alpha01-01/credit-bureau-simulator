"""The posting service: the only way entries reach the ledger (Document 04, Section 12.3).

Every entry is checked inside the transaction that writes it: at least two
lines, each line on one side only and positive, accounts from this
organisation's chart, and total debits equal to total credits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.org.models import Organization

from .models import Account, AccountType, JournalEntry, JournalLine

CENT = Decimal("0.01")

# Chart of accounts (ASSUMPTION A-030: a minimal chart until the bureau's real chart is designed).
CHART: tuple[tuple[str, str, str], ...] = (
    ("1010", "Bank - operating account", AccountType.ASSET),
    ("1100", "Accounts receivable", AccountType.ASSET),
    ("1300", "Prepaid rent", AccountType.ASSET),
    ("2000", "Accounts payable", AccountType.LIABILITY),
    ("2100", "VAT and levies payable", AccountType.LIABILITY),
    ("2200", "PAYE payable", AccountType.LIABILITY),
    ("2210", "SSNIT contributions payable", AccountType.LIABILITY),
    ("3000", "Share capital", AccountType.EQUITY),
    ("3100", "Retained earnings", AccountType.EQUITY),
    ("4000", "Credit report revenue", AccountType.INCOME),
    ("5000", "Salaries and wages", AccountType.EXPENSE),
    ("5010", "Employer SSNIT contributions", AccountType.EXPENSE),
    ("5100", "Office rent", AccountType.EXPENSE),
    ("5200", "IT infrastructure and hosting", AccountType.EXPENSE),
    ("5300", "Provider relations and training", AccountType.EXPENSE),
    ("5400", "Regulatory penalties", AccountType.EXPENSE),
)
# Accounts added after games began (P3.8): made when first needed, in games of any age.
LATER_ACCOUNTS: dict[str, tuple[str, str]] = {
    "2000": ("Accounts payable", AccountType.LIABILITY),
    "5150": ("Utilities", AccountType.EXPENSE),
    "5700": ("Late payment charges", AccountType.EXPENSE),
    "5800": ("Bank charges", AccountType.EXPENSE),
}

BANK, RECEIVABLES, PREPAID_RENT = "1010", "1100", "1300"
VAT_PAYABLE, PAYE_PAYABLE, SSNIT_PAYABLE = "2100", "2200", "2210"
SHARE_CAPITAL, RETAINED = "3000", "3100"
REVENUE = "4000"
SALARIES, EMPLOYER_SSNIT, RENT, IT = "5000", "5010", "5100", "5200"
PAYABLES, UTILITIES, LATE_CHARGES, BANK_CHARGES = "2000", "5150", "5700", "5800"


class PostingError(Exception):
    pass


def ensure_account(organization: Organization, code: str) -> None:
    """Open one of the later accounts in this organisation's chart if it is not there yet."""
    name, kind = LATER_ACCOUNTS[code]
    Account.objects.get_or_create(
        organization=organization, code=code, defaults={"name": name, "account_type": kind}
    )


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Line:
    account: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    memo: str = ""


def dr(account: str, amount: Decimal, memo: str = "") -> Line:
    return Line(account, debit=money(amount), memo=memo)


def cr(account: str, amount: Decimal, memo: str = "") -> Line:
    return Line(account, credit=money(amount), memo=memo)


def create_chart(organization: Organization) -> None:
    Account.objects.bulk_create(
        Account(organization=organization, code=code, name=name, account_type=kind)
        for code, name, kind in CHART
    )


def post(
    organization: Organization,
    transaction_date: date,
    description: str,
    lines: list[Line],
    source_type: str,
    at: datetime,
    source_reference: str = "",
    reversal_of: JournalEntry | None = None,
    rules_version: str = "",
) -> JournalEntry:
    """Validate and post one balanced journal entry."""
    lines = [line for line in lines if line.debit or line.credit]
    if len(lines) < 2:
        raise PostingError("A journal entry needs at least two lines")
    for line in lines:
        if line.debit < 0 or line.credit < 0 or (line.debit and line.credit):
            raise PostingError(f"Line on {line.account} must be a positive debit or credit")
    debits = sum((line.debit for line in lines), Decimal("0"))
    credits = sum((line.credit for line in lines), Decimal("0"))
    if debits != credits:
        raise PostingError(f"Unbalanced entry: debits {debits} != credits {credits}")

    closed = (
        Organization.objects.filter(pk=organization.pk)
        .values_list("closed_through", flat=True)
        .first()
    )
    if closed is not None and transaction_date <= closed:
        raise PostingError(
            f"{transaction_date:%d %B %Y} is in a closed month (closed through {closed:%d %B %Y})"
        )
    with transaction.atomic():
        missing_later = {
            line.account for line in lines if line.account in LATER_ACCOUNTS
        }  # made on first use
        for code in sorted(missing_later):
            ensure_account(organization, code)
        accounts = {
            a.code: a
            for a in Account.objects.filter(
                organization=organization, code__in={line.account for line in lines}
            )
        }
        missing = {line.account for line in lines} - set(accounts)
        if missing:
            raise PostingError(f"Unknown account(s): {', '.join(sorted(missing))}")
        seq = organization.allocate("last_journal_seq")
        entry = JournalEntry.objects.create(
            organization=organization,
            journal_reference=f"JE{seq:08d}",
            transaction_date=transaction_date,
            description=description[:200],
            source_type=source_type,
            source_reference=source_reference[:60],
            posted_at=at,
            reversal_of=reversal_of,
            rules_version=rules_version,
        )
        JournalLine.objects.bulk_create(
            JournalLine(
                entry=entry,
                account=accounts[line.account],
                debit=line.debit,
                credit=line.credit,
                memo=line.memo[:200],
            )
            for line in lines
        )
        return entry


def reverse(entry: JournalEntry, transaction_date: date, reason: str, at: datetime) -> JournalEntry:
    """Cancel an entry with its mirror image. The original stays, untouched."""
    if JournalEntry.objects.filter(reversal_of=entry).exists():
        raise PostingError(f"{entry.journal_reference} has already been reversed")
    mirror = [
        Line(line.account.code, debit=line.credit, credit=line.debit, memo=line.memo)
        for line in entry.lines.select_related("account")
    ]
    return post(
        entry.organization,
        transaction_date,
        f"Reversal of {entry.journal_reference}: {reason}",
        mirror,
        "REVERSAL",
        at,
        entry.journal_reference,
        reversal_of=entry,
    )
