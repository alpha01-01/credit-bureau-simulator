"""S7 — Finance.

Done when (roadmap S7): every posted journal balances; statements derive only
from posted entries; a full month's events produce the expected ledger.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commercial.models import UsageRecord
from apps.finance.events import (
    MONTHLY_IT,
    MONTHLY_RENT,
    OPENING_BANK,
    SSNIT_EMPLOYEE,
    SSNIT_EMPLOYER,
    VAT_AND_LEVIES,
    balance,
    paye,
)
from apps.finance.ledger import (
    BANK,
    PAYE_PAYABLE,
    PREPAID_RENT,
    RECEIVABLES,
    RENT,
    REVENUE,
    SALARIES,
    SSNIT_PAYABLE,
    VAT_PAYABLE,
    PostingError,
    cr,
    dr,
    money,
    post,
    reverse,
)
from apps.finance.models import ImmutableError, Invoice, JournalEntry, JournalLine, Payment
from apps.finance.statements import balance_sheet, income_statement, trial_balance
from apps.org.models import Employee
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.models import Game
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

AT = datetime(2027, 1, 4, 9, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(111, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _play_until(game: Game, day: date) -> Game:
    while controls.state(game).now.date() < day:
        game = controls.advance_by(game, "day")
    return game


def _assert_every_journal_balances(game: Game) -> None:
    for entry in JournalEntry.objects.filter(organization=game.organization):
        totals = entry.lines.aggregate(d=Sum("debit"), c=Sum("credit"))
        assert totals["d"] == totals["c"] > 0, entry.journal_reference


# --- The posting service ------------------------------------------------------------------


def test_only_balanced_entries_are_posted(world: World) -> None:
    org = start_game(world).organization
    when = date(2027, 1, 4)
    with pytest.raises(PostingError, match="Unbalanced"):
        post(org, when, "x", [dr(BANK, Decimal("10")), cr(REVENUE, Decimal("9"))], "TEST", AT)
    with pytest.raises(PostingError, match="at least two"):
        post(org, when, "x", [dr(BANK, Decimal("10"))], "TEST", AT)
    with pytest.raises(PostingError, match="Unknown"):
        post(org, when, "x", [dr("9999", Decimal("1")), cr(BANK, Decimal("1"))], "TEST", AT)
    before = JournalEntry.objects.filter(organization=org).count()
    post(org, when, "ok", [dr(BANK, Decimal("10")), cr(REVENUE, Decimal("10"))], "TEST", AT)
    assert JournalEntry.objects.filter(organization=org).count() == before + 1


def test_posted_entries_are_reversed_never_edited(world: World) -> None:
    org = start_game(world).organization
    entry = post(
        org, date(2027, 1, 4), "Sale", [dr(BANK, Decimal("50")), cr(REVENUE, Decimal("50"))],
        "TEST", AT,
    )  # fmt: skip
    with pytest.raises(ImmutableError):
        entry.save()
    with pytest.raises(ImmutableError):
        entry.delete()
    line = entry.lines.first()
    assert line is not None
    with pytest.raises(ImmutableError):
        line.save()

    revenue_before = balance(org, REVENUE)
    mirror = reverse(entry, date(2027, 1, 5), "posted in error", AT)
    assert mirror.reversal_of == entry
    assert balance(org, REVENUE) == revenue_before + Decimal("50")  # credit cancelled by a debit
    with pytest.raises(PostingError, match="already been reversed"):
        reverse(entry, date(2027, 1, 5), "again", AT)


@pytest.mark.parametrize(
    ("chargeable", "tax"),
    [("490", "0.00"), ("600", "5.50"), ("730", "18.50"), ("4000", "598.50")],
)
def test_paye_bands(chargeable: str, tax: str) -> None:
    assert paye(Decimal(chargeable)) == Decimal(tax)


# --- A month of business produces the expected books ---------------------------------------


def test_a_month_of_play_produces_the_expected_ledger(world: World) -> None:
    game = _play_until(start_game(world), date(2027, 2, 17))  # past invoicing and remittances
    org = game.organization
    _assert_every_journal_balances(game)

    # Billing: January's usage invoiced on the first working day of February, plus taxes.
    january_usage = UsageRecord.objects.filter(
        organization=org, usage_at__date__lte=date(2027, 1, 31)
    )
    billed = sum((u.unit_price * u.quantity for u in january_usage), Decimal("0"))
    assert billed > 0 and all(u.invoiced for u in january_usage)
    invoices = Invoice.objects.filter(organization=org)
    assert sum((i.subtotal for i in invoices), Decimal("0")) == billed
    assert -balance(org, REVENUE) == billed
    assert -balance(org, VAT_PAYABLE) == money(billed * VAT_AND_LEVIES)  # not yet filed
    paid = Payment.objects.filter(organization=org).aggregate(s=Sum("amount"))["s"] or 0
    assert balance(org, RECEIVABLES) == sum((i.total for i in invoices), Decimal("0")) - paid

    # Payroll: January salaries paid on the last working day; taxes remitted by the 14th.
    staff = list(Employee.objects.filter(organization=org))
    gross = sum((e.monthly_salary for e in staff), Decimal("0"))
    assert balance(org, SALARIES) == gross
    assert balance(org, PAYE_PAYABLE) == 0 and balance(org, SSNIT_PAYABLE) == 0
    employee_ssnit = sum((money(e.monthly_salary * SSNIT_EMPLOYEE) for e in staff), Decimal("0"))
    employer_ssnit = sum((money(e.monthly_salary * SSNIT_EMPLOYER) for e in staff), Decimal("0"))
    income_tax = sum(
        (paye(e.monthly_salary - money(e.monthly_salary * SSNIT_EMPLOYEE)) for e in staff),
        Decimal("0"),
    )
    net_pay = gross - employee_ssnit - income_tax

    # Rent from the prepayment; IT hosting from the bank; two months of each.
    assert balance(org, RENT) == 2 * MONTHLY_RENT
    assert balance(org, PREPAID_RENT) == 10 * MONTHLY_RENT

    # The bank: opening, less costs paid, plus what subscribers paid.
    expected_bank = (
        OPENING_BANK
        - 2 * MONTHLY_IT
        - net_pay
        - income_tax
        - (employee_ssnit + employer_ssnit)
        + Decimal(paid)
    )
    assert balance(org, BANK) == expected_bank


def test_statements_come_from_posted_entries_and_balance(world: World) -> None:
    game = _play_until(start_game(world), date(2027, 3, 31))
    org = game.organization
    today = controls.state(game).now.date()
    _assert_every_journal_balances(game)

    sheet = balance_sheet(org, today)
    assert sheet["balances"]
    trial = trial_balance(org, today)
    assert trial["total_debit"] == trial["total_credit"]
    # The income statement equals income and expense lines summed straight from the ledger.
    year = income_statement(org, date(2027, 1, 1), today)
    lines = JournalLine.objects.filter(
        entry__organization=org, entry__transaction_date__gte="2027-01-01"
    )
    income = lines.filter(account__account_type="INCOME").aggregate(d=Sum("debit"), c=Sum("credit"))
    expense = lines.filter(account__account_type="EXPENSE").aggregate(
        d=Sum("debit"), c=Sum("credit")
    )
    assert year["total_income"] == income["c"] - income["d"]
    assert year["total_expenses"] == expense["d"] - expense["c"]
    # Subscribers have paid at least some February invoices by the end of March.
    assert Payment.objects.filter(organization=org).exists()


def test_finance_api(world: World) -> None:
    owner = User.objects.create_user("cfo")
    game = _play_until(start_game(world, owner=owner), date(2027, 2, 2))
    client = APIClient()
    client.force_authenticate(owner)
    body = client.get(f"/api/v1/games/{game.pk}/finance/").json()
    assert body["balance_sheet"]["balances"] is True
    assert Decimal(body["trial_balance"]["total_debit"]) == Decimal(
        body["trial_balance"]["total_credit"]
    )
    assert Decimal(body["cash"]["bank"]) > 0
