"""The event feed and auto-pause (P2.2; Document 07, Section 5.2).

While a tick runs, the simulation notes what happened (``Feed.add``): files
arriving, runs finishing, money moving, a lender losing faith in the bureau.
At the start of each working day it also looks at what is overdue or due
(``Feed.morning``). The notices are saved at the end of the tick; if any of
them matches the player's auto-pause rules, the clock stops there.

Severities (ASSUMPTION A-043):

* CRITICAL: the bureau's survival is at stake: cash below a month's payroll, a
  subscriber reconsidering its contract.
* WARNING: needs attention: a file rejected, many records unloadable, a report
  on the wrong person, data or an invoice overdue, work due or past its deadline.
* INFO: the ordinary course of business.

Notices say only what the bureau itself could know. A subscriber's private view
of the bureau stays hidden; the notice is the complaint it makes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.bureau.submissions.intake import due_date_for
from apps.bureau.submissions.models import FileStatus, ProcessingRun, Submission
from apps.finance.events import balance, outstanding
from apps.finance.ledger import BANK
from apps.finance.models import Invoice
from apps.org.models import Employee
from apps.standards.calendar import is_working_day
from apps.workitems.models import ItemStatus, WorkItem

from .clock import TICKS_PER_DAY, previous_month_end
from .models import Game, GameStatus, Notice, Severity

# ASSUMPTION A-044: a work item's decision is due five working days after it is opened.
WORK_ITEM_DAYS = 5
# Share of a file's records that could not be loaded above which a run is a warning.
UNLOADABLE_WARNING = 0.10
# ASSUMPTION A-045: a subscriber complains and reconsiders below this view of the bureau,
# and is satisfied again above the second (the gap stops it flickering).
AT_RISK, RECOVERED = 0.40, 0.50

CASH_LOW, CASH_RECOVERED = "CASH_LOW", "CASH_RECOVERED"


def due_tick(created_tick: int) -> int:
    """The last tick of the fifth working day after the item was opened."""
    return ((created_tick - 1) // TICKS_PER_DAY + 1 + WORK_ITEM_DAYS) * TICKS_PER_DAY


def money(amount: Decimal) -> str:
    return f"GHS {amount:,.2f}"


@dataclass
class Feed:
    """The notices of one tick."""

    game: Game
    tick: int
    at: datetime
    notices: list[Notice] = field(default_factory=list)

    def add(
        self,
        kind: str,
        severity: str,
        title: str,
        detail: str = "",
        drill: dict[str, Any] | None = None,
        *,
        deadline: bool = False,
    ) -> None:
        self.notices.append(
            Notice(
                game=self.game,
                tick=self.tick,
                sim_time=self.at,
                kind=kind,
                severity=severity,
                title=title[:200],
                detail=detail[:500],
                drill=drill or {},
                is_deadline=deadline,
            )
        )

    def save(self) -> bool:
        """Store the notices; stop the clock if the rules say so. True if they did."""
        game = self.game
        for notice in self.notices:
            notice.paused = notice.severity in game.pause_severities or (
                notice.is_deadline and game.pause_on_deadlines
            )
        Notice.objects.bulk_create(self.notices)
        pausing = any(n.paused for n in self.notices)
        if pausing and game.status == GameStatus.RUNNING:
            game.status = GameStatus.PAUSED
            game.save(update_fields=["status"])
        return pausing

    # --- Things that happen ---------------------------------------------------------

    def files_arrived(self, submission: Submission) -> None:
        name = submission.institution.institution_name
        self.add(
            "FILES_ARRIVED",
            Severity.INFO,
            f"Files arrived from {name}",
            f"{submission.submission_reference}: {submission.reporting_period:%B %Y} data, "
            f"{submission.files.count()} file(s). They will be processed overnight.",
            _submission(submission),
        )

    def run_finished(self, run: ProcessingRun) -> None:
        submission = run.submission
        name = submission.institution.institution_name
        rejected = submission.files.filter(file_status=FileStatus.REJECTED).count()
        if rejected:
            unmapped = submission.files.filter(
                file_status=FileStatus.REJECTED, rejection_reason="T001"
            ).count()
            self.add(
                "FILE_REJECTED",
                Severity.WARNING,
                f"File rejected: {name}" + (" (columns need mapping)" if unmapped else ""),
                f"{submission.submission_reference}: {rejected} file(s) failed the file checks "
                "and were not loaded."
                + (
                    " The provider changed its layout: map the columns to load it."
                    if unmapped
                    else ""
                ),
                _submission(submission),
            )
        received = run.records_received
        if rejected and not received:
            return  # nothing else was loaded
        detail = (
            f"{submission.submission_reference}: {run.records_accepted:,} of {received:,} "
            f"records loaded, {run.records_unloadable:,} unloadable, "
            f"{run.records_pending:,} waiting for review."
        )
        if received and run.records_unloadable / received >= UNLOADABLE_WARNING:
            self.add(
                "MANY_UNLOADABLE",
                Severity.WARNING,
                f"Many records from {name} could not be loaded",
                detail,
                _submission(submission),
            )
        else:
            self.add("RUN_FINISHED", Severity.INFO, f"{name}'s data was processed", detail,
                     _submission(submission))  # fmt: skip

    def invoices_issued(self, invoices: list[Invoice], month: date) -> None:
        if not invoices:
            return
        total = sum((i.total for i in invoices), Decimal("0"))
        self.add(
            "INVOICES_ISSUED",
            Severity.INFO,
            f"{len(invoices)} invoices issued for {month:%B}",
            f"Usage billed to subscribers: {money(total)} including taxes.",
            {"screen": "invoices", "params": {}},
        )

    def payment_received(self, invoice: Invoice, amount: Decimal) -> None:
        self.add(
            "PAYMENT_RECEIVED",
            Severity.INFO,
            f"{invoice.subscriber.subscriber_name} paid {money(amount)}",
            f"Invoice {invoice.invoice_number}, due {invoice.due_date:%d %B}.",
            {"screen": "invoices", "params": {}},
        )

    def money_out(self, kind: str, title: str, detail: str) -> None:
        self.add(kind, Severity.INFO, title, detail, {"screen": "ledger", "params": {}})

    def wrong_person(self, subscriber_name: str, reference: str) -> None:
        self.add(
            "WRONG_PERSON",
            Severity.WARNING,
            f"{subscriber_name} received a report on the wrong person",
            f"Enquiry {reference}: the lender found the report did not match its applicant.",
            {"screen": "enquiries", "params": {"outcome": "HIT"}},
        )

    def subscriber_mood(self, subscriber_name: str, *, at_risk: bool) -> None:
        if at_risk:
            self.add(
                "SUBSCRIBER_AT_RISK",
                Severity.CRITICAL,
                f"{subscriber_name} is reconsidering its contract",
                "Its credit team has complained that our reports are not helping them decide; "
                "it is checking the bureau less and may leave.",
                {"screen": "enquiries", "params": {}},
            )
        else:
            self.add(
                "SUBSCRIBER_SATISFIED",
                Severity.INFO,
                f"{subscriber_name} is satisfied with our reports again",
                "",
                {"screen": "enquiries", "params": {}},
            )

    # --- The morning look round -------------------------------------------------------

    def morning(self, today: date) -> None:
        """At the first tick of a working day: what has become overdue, and what is due."""
        yesterday = _previous_working_day(today)
        self._overdue_data(today, yesterday)
        self._overdue_invoices(today, yesterday)
        self._cash(today)
        self._deadlines()

    def _overdue_data(self, today: date, yesterday: date) -> None:
        period = previous_month_end(today)
        due = due_date_for(period)
        if not yesterday <= due < today:  # only on the first working day after the due date
            return
        org = self.game.organization
        for institution in org.institutions.filter(is_active=True).order_by("institution_code"):
            if not Submission.objects.filter(
                institution=institution, reporting_period=period
            ).exists():
                self.add(
                    "DATA_OVERDUE",
                    Severity.WARNING,
                    f"{institution.institution_name} has not sent its {period:%B} data",
                    f"It was due on {due:%d %B}.",
                    {"screen": "submissions", "params": {"provider": institution.institution_code}},
                )  # fmt: skip

    def _overdue_invoices(self, today: date, yesterday: date) -> None:
        invoices = Invoice.objects.filter(
            organization=self.game.organization, due_date__gte=yesterday, due_date__lt=today
        ).select_related("subscriber")
        for invoice in invoices.order_by("invoice_number"):
            owed = outstanding(invoice)
            if owed > 0:
                self.add(
                    "INVOICE_OVERDUE",
                    Severity.WARNING,
                    f"Invoice {invoice.invoice_number} is overdue",
                    f"{invoice.subscriber.subscriber_name} owes {money(owed)}, "
                    f"due {invoice.due_date:%d %B}.",
                    {"screen": "invoices", "params": {"unpaid": "1"}},
                )

    def _cash(self, today: date) -> None:
        org = self.game.organization
        payroll = Employee.objects.filter(organization=org, is_active=True).aggregate(
            total=Sum("monthly_salary")
        )["total"] or Decimal("0")
        bank = balance(org, BANK, today)
        low = bank < payroll
        last = (
            Notice.objects.filter(game=self.game, kind__in=[CASH_LOW, CASH_RECOVERED])
            .order_by("-tick", "-pk")
            .values_list("kind", flat=True)
            .first()
        )
        was_low = last == CASH_LOW
        if low and not was_low:
            self.add(
                CASH_LOW,
                Severity.CRITICAL,
                "Cash is below one month's payroll",
                f"The bank holds {money(bank)}; salaries are {money(payroll)} a month.",
                {"screen": "ledger", "params": {"account": BANK}},
            )
        elif was_low and not low:
            self.add(
                CASH_RECOVERED,
                Severity.INFO,
                "Cash is back above one month's payroll",
                f"The bank holds {money(bank)}.",
                {"screen": "ledger", "params": {"account": BANK}},
            )

    def _deadlines(self) -> None:
        items = WorkItem.objects.filter(organization=self.game.organization)
        today_end = self.tick + TICKS_PER_DAY - 1
        due_today = items.filter(
            status=ItemStatus.OPEN, assignee__isnull=True,
            due_tick__gte=self.tick, due_tick__lte=today_end,
        ).count()  # fmt: skip
        if due_today:
            self.add(
                "WORK_DUE",
                Severity.WARNING,
                f"{due_today} work item(s) are due today and no one has taken them",
                "Decide them yourself, or make sure the team can reach them.",
                {"screen": "queue", "params": {"status": "OPEN"}},
                deadline=True,
            )
        missed = (
            items.exclude(status=ItemStatus.DONE)
            .filter(due_tick__gte=self.tick - TICKS_PER_DAY, due_tick__lt=self.tick)
            .count()
        )
        if missed:
            self.add(
                "WORK_MISSED",
                Severity.WARNING,
                f"{missed} work item(s) missed their deadline yesterday",
                "The records behind them are still waiting.",
                {"screen": "queue", "params": {"status": "OPEN"}},
            )


def _submission(submission: Submission) -> dict[str, Any]:
    return {"screen": "submission", "params": {"reference": submission.submission_reference}}


def _previous_working_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day
