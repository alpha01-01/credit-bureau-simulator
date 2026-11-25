"""P3.8 — Finance.

Done when (Document 09): every reconciliation difference traces to a real cause
(timing, an error, a missing entry); the budget report agrees with the ledger; a late
supplier payment has a consequence (a penalty, or a supplier holding back service).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.finance import bank, budget
from apps.finance.events import MONTHLY_IT
from apps.finance.ledger import BANK, LATE_CHARGES, PAYABLES, PostingError, cr, dr, post
from apps.finance.models import (
    AccountType,
    BankStatement,
    BillStatus,
    JournalLine,
    LineCause,
    LineStatus,
    StatementLine,
    SupplierBill,
)
from apps.simulation import controls, finance_dept, it, roles, scenarios
from apps.simulation.bridge import start_game
from apps.simulation.compliance import add_working_days
from apps.simulation.engine import ClockError, advance, calendar
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, Notice
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _game(world: World, owner: User | None = None) -> Game:
    return controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)


def _until(game: Game, day: date) -> Game:
    while controls.state(game).now.date() < day:
        game = controls.advance_by(game, "next_event")
    return game


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def test_late_bills_cost_a_charge_and_the_hosting_company_holds_back(world: World) -> None:
    owner = User.objects.create_user("finance-head")
    game = working_as(_game(world, owner), roles.FINANCE)
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}/finance"
    # Every bill must wait for the Head of Finance.
    assert client.post(f"{base}/bills/", {"action": "limit", "amount": "0"}).status_code == 200
    game = advance(Game.objects.get(pk=game.pk), 1)  # the month's bills arrive
    bills = SupplierBill.objects.filter(organization=game.organization)
    assert {b.supplier_code for b in bills} >= {"NETCORE", "ECG", "NETLINK"}
    assert all(b.status == BillStatus.RECEIVED for b in bills)
    hosting = bills.get(supplier_code="NETCORE")
    assert hosting.amount == MONTHLY_IT and hosting.due_date == hosting.bill_date + timedelta(30)
    # Recorded the day it arrived: the cost is the bureau's, the payable owed.
    owed = -JournalLine.objects.filter(
        entry__organization=game.organization, account__code=PAYABLES
    ).aggregate(s=Sum("debit") - Sum("credit"))["s"]
    assert owed == sum(b.amount for b in bills)
    assert Notice.objects.filter(game=game, kind="BILL_TO_APPROVE").count() == bills.count()

    # Left unapproved past its due date, the hosting bill stops the systems once it is
    # ten working days overdue.
    hold_day = add_working_days(hosting.due_date, scenarios.parameters(game).supplier_patience_days)
    game = _until(game, hold_day)  # the morning of that day
    hold = it.active_incident(game, game.current_tick)
    assert hold is not None and hold.kind == finance_dept.HOLD
    assert calendar(game).tick_start(hold.started_tick).date() == hold_day
    assert Notice.objects.filter(game=game, kind="SUPPLIER_HOLD").exists()
    with pytest.raises(it.ITError, match="hosting company"):
        it.respond(game, "BACKUP", game.current_tick, _today(game), controls.state(game).now)

    # Approved, it is paid the next morning with the late charge, and service returns.
    assert (
        client.post(f"{base}/bills/", {"action": "approve", "number": hosting.number}).status_code
        == 200
    )
    game = controls.advance_by(Game.objects.get(pk=game.pk), "day", 2)
    hosting.refresh_from_db()
    assert hosting.status == BillStatus.PAID
    assert hosting.late_fee == (hosting.amount * Decimal("0.02")).quantize(Decimal("0.01"))
    assert JournalLine.objects.filter(
        entry=hosting.payment_journal, account__code=LATE_CHARGES, debit=hosting.late_fee
    ).exists()
    assert not it.systems_down(game, game.current_tick + 1)
    assert Notice.objects.filter(game=game, kind="SUPPLIER_RESTORED").exists()

    # A bill not owed is rejected: its recording is reversed.
    power = bills.get(supplier_code="ECG", bill_date=hosting.bill_date, duplicate_of__isnull=True)
    assert (
        client.post(f"{base}/bills/", {"action": "reject", "number": power.number}).status_code
        == 200
    )
    power.refresh_from_db()
    assert power.status == BillStatus.REJECTED
    listing = client.get(f"{base}/bills/").json()
    assert any(b["status"] == "REJECTED" for b in listing["bills"])

    # Others may not approve.
    working_as(Game.objects.get(pk=game.pk), roles.SALES)
    net = bills.get(supplier_code="NETLINK", bill_date=hosting.bill_date)
    assert (
        client.post(f"{base}/bills/", {"action": "approve", "number": net.number}).status_code
        == 403
    )

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world))
    assert fingerprint(copy) == fingerprint(Game.objects.get(pk=game.pk)), differences(copy, game)


def test_the_budget_report_agrees_with_the_ledger(world: World) -> None:
    game = _until(_game(world), date(2027, 2, 2))
    org = game.organization
    january = date(2027, 1, 1)
    found = budget.report(org, january)
    first, last = budget.month_bounds(january)
    by_account = {
        row["account__code"]: (row["d"] or 0) - (row["c"] or 0)
        for row in JournalLine.objects.filter(
            entry__organization=org,
            entry__transaction_date__gte=first,
            entry__transaction_date__lte=last,
            account__account_type__in=[AccountType.INCOME, AccountType.EXPENSE],
        )
        .values("account__code")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    }
    rows = {r["centre"]: r for r in found["rows"]}
    for centre, _, accounts in budget.COST_CENTRES:
        ledger = sum((by_account.get(a, 0) for a in accounts), Decimal("0"))
        assert rows[centre]["actual"] == (-ledger if centre == "SALES" else ledger)
    income = -sum((v for a, v in by_account.items() if a.startswith("4")), Decimal("0"))
    costs = sum((v for a, v in by_account.items() if not a.startswith("4")), Decimal("0"))
    assert found["revenue"] == income and found["costs"] == costs
    assert found["result"] == income - costs
    # The starting budget covers the running costs; the report shows where it was missed.
    assert rows["IT"]["budget"] == MONTHLY_IT and rows["IT"]["variance"] == 0
    assert rows["DATA_OPERATIONS"]["budget"] > 0


def test_every_reconciliation_difference_has_a_cause(world: World, monkeypatch: Any) -> None:
    monkeypatch.setattr(finance_dept, "BANK_ERROR_CHANCE", 1.0)  # the bank errs every month
    owner = User.objects.create_user("finance-head")
    game = working_as(_game(world, owner), roles.FINANCE)
    game = _until(game, date(2027, 2, 2))  # January's statement has come
    org = game.organization
    statement = BankStatement.objects.get(organization=org, period=date(2027, 1, 31))
    lines = list(statement.lines.order_by("line_number"))
    assert statement.closing_balance == statement.opening_balance + sum(x.amount for x in lines)
    assert statement.opening_balance == bank.ledger_balance(org, game.clock_start - timedelta(1))

    found = bank.summary(statement)
    # Each difference is one of: timing (in the ledger, not yet cleared), a charge the
    # ledger lacks, or the bank's error. Together they explain the whole difference.
    assert {x.cause for x in found["unrecorded"]} == {LineCause.CHARGE, LineCause.BANK_ERROR}
    assert found["uncleared"] and all(u["cause"] == "TIMING" for u in found["uncleared"])
    assert any(u["description"].startswith("Salaries") for u in found["uncleared"])
    assert found["difference"] == sum(x.amount for x in found["unrecorded"]) - sum(
        u["amount"] for u in found["uncleared"]
    )
    assert found["reconciles"]
    # Every line from the ledger is matched to its entry, with the same amount.
    amounts = bank.bank_amounts(org)
    for line in lines:
        if line.cause == LineCause.LEDGER:
            assert line.entry_id is not None
            assert line.status == LineStatus.MATCHED and amounts[line.entry_id] == line.amount

    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/finance/bank/"
    period = "2027-01-31"
    refused = client.post(url, {"action": "complete", "period": period})
    assert refused.status_code == 400 and "neither posted nor queried" in refused.json()["detail"]
    for line in found["unrecorded"]:
        action = "query" if line.cause == LineCause.BANK_ERROR else "post"
        body = {"action": action, "period": period, "line": line.line_number}
        assert client.post(url, body).status_code == 200
    done = client.post(url, {"action": "complete", "period": period}).json()
    assert done["statement"]["reconciled_at"] and done["statement"]["reconciles"]

    # The bank agrees it erred, and reverses it on February's statement.
    game = controls.advance_by(Game.objects.get(pk=game.pk), "day", 4)
    error = StatementLine.objects.get(statement=statement, cause=LineCause.BANK_ERROR)
    assert error.status == LineStatus.BANK_ERROR and "reverse" in error.answer
    game = _until(game, date(2027, 3, 2))
    error.refresh_from_db()
    correction = error.corrected_by
    assert correction.amount == -error.amount and error.status == LineStatus.MATCHED
    february = BankStatement.objects.get(organization=org, period=date(2027, 2, 28))
    assert bank.summary(february)["reconciles"]
    assert bank.summary(statement)["reconciles"]  # January still explains itself

    # Closing January: the checklist, then no more postings into it.
    close = f"/api/v1/games/{game.pk}/finance/close/"
    shown = client.get(close).json()
    assert shown["period"] == period
    assert {i["code"]: i["done"] for i in shown["checklist"]}["BUDGET"] is False
    assert client.post(close, {"period": period}).status_code == 400
    budget_url = f"/api/v1/games/{game.pk}/finance/budget/?month=2027-01-01"
    assert client.post(budget_url, {"action": "review", "month": "2027-01-01"}).status_code == 200
    assert client.post(close, {"period": period}).status_code == 200
    with pytest.raises(PostingError, match="closed month"):
        post(org, date(2027, 1, 20), "late adjustment", [dr(BANK, Decimal(1)), cr("4000", Decimal(1))], "TEST",
             controls.state(game).now)  # fmt: skip
    with pytest.raises(ClockError, match="next month to close"):
        controls.close_month(Game.objects.get(pk=game.pk), date(2027, 1, 31))

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world))
    game = Game.objects.get(pk=game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)
