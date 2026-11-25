"""The Finance department's world: suppliers, the bank, and the month-end close (P3.8).

ASSUMPTION A-078 (placeholders until the owner's references give real terms):

* **Suppliers** bill at each month's start: IT hosting (GHS 15,000, with GHS 12,000 more
  for high capacity; 30 days), the matching software licence (by tooling level; 30
  days), electricity (GHS 2,500-4,500; 14 days), internet (GHS 1,800; 30 days), and the
  landlord's year of rent in advance when the prepayment runs out (14 days).
* Bills up to the approval limit (GHS 20,000 to start) are approved by delegated
  authority; larger ones wait for the Head of Finance. Approved bills are paid on their
  due date. A bill paid late carries a 2% charge for each 30 days (or part) past due;
  the hosting company suspends service once its bill is 10 working days overdue, and
  restores it the day it is paid.
* Now and then (1 month in 10) the electricity company or the internet provider sends
  last month's bill again, under the same reference. Within the limit it is approved
  and paid like any other, unless Finance rejects it first.
* **The bank** sends each month's statement at the next month's start. Receipts clear
  the day they are made; supplier payments, tax payments and the VAT return clear 0-2
  working days later, salaries the next working day. It charges GHS 150 a month and
  GHS 10 for each transfer out, and in 1 month in 4 charges the transfer fees twice. A
  query is answered in 3 working days; an error it agrees to is reversed on the next
  statement.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Max

from apps.finance import bank, budget, payables
from apps.finance.events import (
    IT_CAPACITY_COST,
    MATCHING_TOOLING_COST,
    MONTHLY_IT,
    balance,
)
from apps.finance.ledger import IT, PREPAID_RENT, UTILITIES
from apps.finance.models import (
    BankStatement,
    BillStatus,
    JournalEntry,
    LineCause,
    LineStatus,
    MonthClose,
    StatementLine,
    SupplierBill,
)
from apps.org.models import Employee
from apps.standards.calendar import is_working_day
from apps.standards.rulebook import TAX_RULES
from apps.world.generation.rng import stream

from . import economy, scenarios
from .clock import Calendar, previous_month_end
from .compliance import add_working_days
from .models import Game, Incident, Severity

HOSTING = ("NETCORE", "NetCore Data Centres Ltd")
SOFTWARE = ("MATCHSOFT", "MatchSoft Systems Ltd")
POWER = ("ECG", "Electricity Company of Ghana")
INTERNET = ("NETLINK", "NetLink Business Internet")
LANDLORD = ("RIDGEPROP", "Ridge Properties Ltd")
CONTACT_CENTRE = ("CALLPOINT", "CallPoint Contact Centre Ltd")
AGENT_MONTHLY = Decimal("4500.00")  # a contact-centre agent a month (A-080)
SUPPORT_ACCOUNT = "5250"
DUPLICATE_CHANCE = 0.1
HOLD = "SUPPLIER_HOLD"
MONTHLY_FEE, TRANSFER_FEE = Decimal("150.00"), Decimal("10.00")
BANK_ERROR_CHANCE = 0.25
QUERY_WORKING_DAYS = 3
CLEARING_DELAY = {"SUPPLIER_PAYMENT": 2, "REMITTANCE": 2, "VAT_RETURN": 2}  # up to, working days
UTILITIES_BUDGET = Decimal("5300.00")
FINANCE_BUDGET = Decimal("500.00")


class FinanceError(Exception):
    """Finance cannot do this; the message says why."""


def _drill(tab: str) -> dict[str, Any]:
    return {"screen": "finance", "params": {"tab": tab}}


def last_working_day(month_end: date) -> date:
    day = month_end
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day


# --- Budgets ---------------------------------------------------------------------------


def ensure_budget(game: Game, month_first: date) -> None:
    """A starting budget for each cost centre, from the bureau's running costs."""
    org = game.organization
    if org.budgets.exists():
        return
    rules = TAX_RULES.at(month_first)
    pay = sum(
        (e.monthly_salary for e in Employee.objects.filter(organization=org, is_active=True)),
        Decimal("0"),
    )
    systems = (
        MONTHLY_IT + IT_CAPACITY_COST[org.it_capacity] + MATCHING_TOOLING_COST[org.matching_tooling]
    )
    plan = {
        "DATA_OPERATIONS": pay * (1 + rules.ssnit_employer),
        # A startup has no office or systems yet (P3.13).
        "PREMISES": monthly_rent(game) + (scenarios.cost(game, UTILITIES_BUDGET)
                                           if org.office else Decimal("0")),
        "IT": scenarios.cost(game, systems) if org.has_systems else Decimal("0"),
        "COMPLIANCE": Decimal("0"),
        "FINANCE": FINANCE_BUDGET,
        "SUPPORT": scenarios.cost(game, AGENT_MONTHLY * org.support_staff),
        "PRODUCT": Decimal("0"),
    }  # fmt: skip
    for centre, amount in plan.items():
        budget.set_budget(org, centre, amount, month_first)


# --- Suppliers' bills ------------------------------------------------------------------


def month_start(game: Game, today: date, tick: int, at: datetime, add: Any) -> None:
    """The month's bills arrive, and the bank's statement for last month."""
    ensure_budget(game, today.replace(day=1))
    _bills(game, today, at, add)
    _statement(game, today, at, add)


def monthly_rent(game: Game) -> Decimal:
    """A month of the rent prepaid at the last renewal (P3.12: renewals follow prices).

    A startup pays none until it rents an office (P3.13)."""
    from .startup import OFFICES

    if not game.organization.office:
        return Decimal("0.00")
    renewal = (
        SupplierBill.objects.filter(organization=game.organization, supplier_code=LANDLORD[0])
        .exclude(status=BillStatus.REJECTED)
        .order_by("-bill_date", "-number")
        .first()
    )
    if renewal is not None:
        return (renewal.amount / 12).quantize(Decimal("0.01"))
    return OFFICES[game.organization.office].monthly_rent


def _bills(game: Game, today: date, at: datetime, add: Any) -> None:
    org = game.organization
    seed = game.world.seed
    month = f"{today:%Y%m}"
    from .startup import OFFICES

    due = []  # (supplier, reference, description, account, amount, days to pay)
    if org.has_systems:  # a startup's IT is billed once it is set up (P3.13)
        due += [
            (HOSTING, f"NC-{month}", f"Hosting for {today:%B %Y}", IT,
             MONTHLY_IT + IT_CAPACITY_COST[org.it_capacity], 30),
            (SOFTWARE, f"MS-{month}",
             f"Matching software ({org.matching_tooling.lower()}) for {today:%B %Y}", IT,
             MATCHING_TOOLING_COST[org.matching_tooling], 30),
        ]  # fmt: skip
    if org.office:
        due += [
            (POWER, f"ECG-{month}", f"Electricity for {today:%B %Y}", UTILITIES,
             Decimal(int(stream(seed, f"power:{month}").integers(2500, 4501))), 14),
            (INTERNET, f"NL-{month}", f"Internet for {today:%B %Y}", UTILITIES,
             Decimal("1800.00"), 30),
        ]  # fmt: skip
    due.append(
        (CONTACT_CENTRE, f"CP-{month}",
         f"Customer support: {org.support_staff} agent(s) for {today:%B %Y}", SUPPORT_ACCOUNT,
         AGENT_MONTHLY * org.support_staff, 30)
    )  # fmt: skip
    if org.office and balance(org, PREPAID_RENT) < monthly_rent(game):
        due.insert(0, (LANDLORD, f"RP-{month}", "Office rent: the next 12 months in advance",
                       PREPAID_RENT, OFFICES[org.office].monthly_rent * 12, 14))  # fmt: skip
    prices = economy.price_factor(game, today)  # suppliers charge today's prices (P3.12)
    for supplier, reference, description, account, list_amount, days in due:
        # ... at the difficulty's level (P3.13)
        amount = economy.priced(scenarios.cost(game, list_amount), prices)
        if amount <= 0:
            continue
        bill = payables.receive_bill(
            org, supplier, reference, description, account, amount, today,
            today + timedelta(days=days), at,
        )  # fmt: skip
        _announce(bill, add)
    # A supplier that sends last month's bill again.
    for supplier in (POWER, INTERNET):
        if stream(seed, f"duplicate:{supplier[0]}:{month}").random() >= DUPLICATE_CHANCE:
            continue
        last = (
            SupplierBill.objects.filter(
                organization=org,
                supplier_code=supplier[0],
                bill_date__lt=today,
                duplicate_of__isnull=True,
            )
            .order_by("-bill_date")
            .first()
        )
        if last is None:
            continue
        copy = payables.receive_bill(
            org, supplier, last.reference, last.description, last.account_code, last.amount,
            today, today + (last.due_date - last.bill_date), at, duplicate_of=last,
        )  # fmt: skip
        _announce(copy, add)


def _announce(bill: SupplierBill, add: Any) -> None:
    if bill.status == BillStatus.RECEIVED:
        add(
            "BILL_TO_APPROVE", Severity.WARNING,
            f"A bill from {bill.supplier_name} needs approval",
            f"GHS {bill.amount:,.2f} ({bill.description}), due {bill.due_date:%d %B}. It is "
            "above the approval limit.", _drill("bills"),
        )  # fmt: skip


def morning(game: Game, today: date, tick: int, at: datetime, add: Any) -> None:
    """Approved bills due are paid; the bank answers queries; late bills have consequences."""
    org = game.organization
    _answer_queries(game, tick, add)
    paid_hosting = False
    for bill in SupplierBill.objects.filter(
        organization=org, status=BillStatus.APPROVED, due_date__lte=today
    ).order_by("number"):
        payables.pay(bill, today, at)
        paid_hosting |= bill.supplier_code == HOSTING[0]
        if bill.late_fee:
            add(
                "BILL_PAID_LATE", Severity.WARNING, f"Bill {bill.number} paid late",
                f"{bill.supplier_name} charged GHS {bill.late_fee:,.2f} for late payment.",
                _drill("bills"),
            )  # fmt: skip
    late = SupplierBill.objects.filter(
        organization=org, status=BillStatus.RECEIVED, due_date__lt=today
    ).order_by("number")
    yesterday = _previous_working_day(today)
    for bill in late:
        if yesterday <= bill.due_date < today:
            add(
                "BILL_OVERDUE", Severity.WARNING, f"Bill {bill.number} is overdue",
                f"{bill.supplier_name}, GHS {bill.amount:,.2f}, was due {bill.due_date:%d %B} "
                "and is not approved. Late payment costs 2% for each month.", _drill("bills"),
            )  # fmt: skip
    hold = _hold(game, tick)
    if hold is not None and paid_hosting and not late.filter(supplier_code=HOSTING[0]).exists():
        hold.ends_tick = tick
        hold.save(update_fields=["ends_tick"])
        add(
            "SUPPLIER_RESTORED", Severity.INFO, "The hosting company has restored service",
            "Its bill is paid.", {"screen": "it", "params": {}},
        )  # fmt: skip
    patience = scenarios.parameters(game).supplier_patience_days  # P3.13
    if hold is None and any(
        add_working_days(b.due_date, patience) <= today
        for b in late.filter(supplier_code=HOSTING[0])
    ):
        number = (Incident.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1
        Incident.objects.create(
            game=game, number=number, kind=HOLD, started_tick=tick, ends_tick=tick + 10**7,
            detail="The hosting company has suspended service: its bill is unpaid.",
        )  # fmt: skip
        add(
            "SUPPLIER_HOLD", Severity.CRITICAL, "The hosting company has suspended service",
            f"Its bill is more than {patience} working days overdue. Systems are "
            "down until it is approved and paid.", _drill("bills"),
        )  # fmt: skip


def _hold(game: Game, tick: int) -> Incident | None:
    return Incident.objects.filter(game=game, kind=HOLD, ends_tick__gte=tick).first()


def _previous_working_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day


def approve_bill(game: Game, number: int) -> SupplierBill:
    bill = _bill(game, number)
    try:
        return payables.approve(bill, "Head of Finance")
    except payables.BillError as exc:
        raise FinanceError(str(exc)) from exc


def reject_bill(game: Game, number: int, on: date, at: datetime) -> SupplierBill:
    bill = _bill(game, number)
    try:
        return payables.reject(bill, on, at, "not owed")
    except payables.BillError as exc:
        raise FinanceError(str(exc)) from exc


def _bill(game: Game, number: int) -> SupplierBill:
    bill = SupplierBill.objects.filter(organization=game.organization, number=number).first()
    if bill is None:
        raise FinanceError(f"There is no bill {number}")
    return bill


def set_approval_limit(game: Game, amount: Decimal) -> None:
    if amount < 0:
        raise FinanceError("The approval limit cannot be negative")
    game.organization.bill_approval_limit = amount.quantize(Decimal("0.01"))
    game.organization.save(update_fields=["bill_approval_limit"])


# --- The bank --------------------------------------------------------------------------


def _clears_on(game: Game, entry: JournalEntry, amount: Decimal) -> date:
    if amount > 0:
        return entry.transaction_date
    if entry.source_type == "PAYROLL":
        return add_working_days(entry.transaction_date, 1)
    most = CLEARING_DELAY.get(entry.source_type, 0)
    if not most:
        return entry.transaction_date
    days = int(stream(game.world.seed, f"clearing:{entry.journal_reference}").integers(most + 1))
    return add_working_days(entry.transaction_date, days) if days else entry.transaction_date


def _statement(game: Game, today: date, at: datetime, add: Any) -> BankStatement | None:
    org = game.organization
    period = previous_month_end(today)
    if (
        period < game.clock_start
        or BankStatement.objects.filter(organization=org, period=period).exists()
    ):
        return None
    previous = BankStatement.objects.filter(organization=org).order_by("-period").first()
    opening = (
        previous.closing_balance
        if previous is not None
        else bank.ledger_balance(org, game.clock_start - timedelta(days=1))
    )
    lines: list[dict[str, Any]] = []
    for entry, amount in bank.uncleared(org, period):
        cleared = _clears_on(game, entry, amount)
        if cleared <= period:
            lines.append({
                "value_date": cleared, "description": entry.description[:200],
                "reference": entry.source_reference or entry.journal_reference, "amount": amount,
                "cause": LineCause.LEDGER, "entry": entry, "status": LineStatus.MATCHED,
            })  # fmt: skip
    month_last = last_working_day(period)
    transfers = sum(1 for x in lines if x["amount"] < 0)
    fees = [("Account maintenance fee", MONTHLY_FEE)]
    if transfers:
        fees.append((f"Transfer fees ({transfers} transfers)", TRANSFER_FEE * transfers))
    for description, fee in fees:
        lines.append({"value_date": month_last, "description": description, "reference": "",
                      "amount": -fee, "cause": LineCause.CHARGE, "status": LineStatus.OPEN})  # fmt: skip
    if transfers and stream(game.world.seed, f"bank-error:{period:%Y%m}").random() < (
        BANK_ERROR_CHANCE
    ):
        description, fee = fees[-1]
        lines.append({"value_date": month_last, "description": description, "reference": "",
                      "amount": -fee, "cause": LineCause.BANK_ERROR, "status": LineStatus.OPEN})  # fmt: skip
    errors = StatementLine.objects.filter(
        statement__organization=org, status=LineStatus.BANK_ERROR, corrected_by__isnull=True
    ).order_by("statement__period", "line_number")
    for error in errors:
        lines.append({
            "value_date": month_last,
            "description": f"Correction: {error.description} charged in error",
            "reference": f"CORR-{error.statement.period:%Y%m}-{error.line_number}",
            "amount": -error.amount, "cause": LineCause.BANK_CORRECTION,
            "status": LineStatus.MATCHED, "corrects": error,
        })  # fmt: skip
    lines.sort(key=lambda x: (x["value_date"], x["amount"] < 0, x["description"]))
    statement = BankStatement.objects.create(
        organization=org, period=period, opening_balance=opening,
        closing_balance=opening + sum((x["amount"] for x in lines), Decimal("0")), received_at=at,
    )  # fmt: skip
    StatementLine.objects.bulk_create(
        StatementLine(statement=statement, line_number=n, **x) for n, x in enumerate(lines, 1)
    )
    StatementLine.objects.filter(pk__in=[e.pk for e in errors]).update(status=LineStatus.MATCHED)
    open_items = sum(1 for x in lines if x["status"] == LineStatus.OPEN)
    add(
        "BANK_STATEMENT", Severity.INFO, f"The bank's statement for {period:%B %Y} has arrived",
        f"{len(lines)} lines; {open_items} not in the ledger. Reconcile it before closing the month.",
        _drill("bank"),
    )  # fmt: skip
    return statement


def statement_line(game: Game, period: date, number: int) -> StatementLine:
    line = (
        StatementLine.objects.filter(
            statement__organization=game.organization, statement__period=period, line_number=number
        )
        .select_related("statement")
        .first()
    )
    if line is None:
        raise FinanceError(f"There is no line {number} on the {period:%B %Y} statement")
    return line


def query_line(game: Game, period: date, number: int, tick: int) -> StatementLine:
    line = statement_line(game, period, number)
    cal = Calendar(game.clock_start)
    today = cal.tick_start(max(tick, 1)).date()
    answer_day = add_working_days(today, QUERY_WORKING_DAYS)
    try:
        return bank.query_line(line, cal.first_tick_of_day(cal.index_of(answer_day)))
    except bank.ReconciliationError as exc:
        raise FinanceError(str(exc)) from exc


def _answer_queries(game: Game, tick: int, add: Any) -> None:
    for line in StatementLine.objects.filter(
        statement__organization=game.organization,
        status=LineStatus.QUERIED,
        answer_tick__lte=tick,
        answer="",
    ).order_by("statement__period", "line_number"):
        if line.cause == LineCause.BANK_ERROR:
            line.status = LineStatus.BANK_ERROR
            line.answer = "The bank agrees it charged this in error; it will reverse it on the next statement."
        else:
            line.status = LineStatus.OPEN
            line.answer = "The bank says the charge is correct: post it to the ledger."
        line.save(update_fields=["status", "answer"])
        add(
            "BANK_ANSWER", Severity.INFO, "The bank has answered a query",
            f"{line.description} (GHS {abs(line.amount):,.2f}): {line.answer}", _drill("bank"),
        )  # fmt: skip


def post_line(game: Game, period: date, number: int, at: datetime) -> StatementLine:
    try:
        return bank.post_line(statement_line(game, period, number), at)
    except bank.ReconciliationError as exc:
        raise FinanceError(str(exc)) from exc


def complete_reconciliation(game: Game, period: date, at: datetime) -> BankStatement:
    statement = BankStatement.objects.filter(organization=game.organization, period=period).first()
    if statement is None:
        raise FinanceError(f"No statement for {period:%B %Y} has arrived")
    try:
        return bank.complete(statement, at)
    except bank.ReconciliationError as exc:
        raise FinanceError(str(exc)) from exc


# --- The month-end close ---------------------------------------------------------------


def checklist(game: Game, period: date) -> list[dict[str, Any]]:
    """What must be done before ``period`` closes, and whether it is."""
    from apps.commercial.models import UsageRecord

    org = game.organization
    first = period.replace(day=1)
    staff = Employee.objects.filter(organization=org).exists()
    statement = BankStatement.objects.filter(organization=org, period=period).first()
    record = MonthClose.objects.filter(organization=org, period=period).first()
    waiting = SupplierBill.objects.filter(
        organization=org, status=BillStatus.RECEIVED, bill_date__lte=period
    ).count()
    return [
        {"code": "INVOICES", "title": "The month's usage invoiced",
         "done": not UsageRecord.objects.filter(
             organization=org, invoiced=False, usage_at__date__gte=first,
             usage_at__date__lte=period).exists(),
         "how": "Invoices go out at the next month's start."},
        {"code": "PAYROLL", "title": "Salaries paid",
         "done": not staff or JournalEntry.objects.filter(
             organization=org, source_type="PAYROLL", transaction_date__gte=first,
             transaction_date__lte=period).exists(),
         "how": "Paid on the month's last working day."},
        {"code": "BILLS", "title": "Every bill received approved or rejected", "done": not waiting,
         "how": f"{waiting} bill(s) wait for approval." if waiting else ""},
        {"code": "BANK", "title": "The bank statement reconciled",
         "done": statement is not None and statement.reconciled_at is not None,
         "how": "The statement arrives at the next month's start." if statement is None else ""},
        {"code": "BUDGET", "title": "Budget against actuals reviewed",
         "done": record is not None and record.budget_reviewed_at is not None, "how": ""},
    ]  # fmt: skip


def next_to_close(game: Game) -> date:
    closed = game.organization.closed_through
    if closed is None:
        start = game.clock_start
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return budget.month_bounds(closed + timedelta(days=1))[1]


def review_budget(game: Game, period: date, at: datetime) -> MonthClose:
    record, _ = MonthClose.objects.get_or_create(organization=game.organization, period=period)
    record.budget_reviewed_at = at
    record.save(update_fields=["budget_reviewed_at"])
    return record


def close_month(game: Game, period: date, today: date, at: datetime) -> MonthClose:
    if period != next_to_close(game):
        raise FinanceError(f"The next month to close is {next_to_close(game):%B %Y}")
    if period >= today:
        raise FinanceError(f"{period:%B %Y} has not ended yet")
    undone = [item["title"] for item in checklist(game, period) if not item["done"]]
    if undone:
        raise FinanceError("Still to do: " + "; ".join(undone))
    record, _ = MonthClose.objects.get_or_create(organization=game.organization, period=period)
    record.closed_at = at
    record.save(update_fields=["closed_at"])
    game.organization.closed_through = period
    game.organization.save(update_fields=["closed_through"])
    return record
