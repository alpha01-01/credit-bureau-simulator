# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""The flywheel (P2.8; Document 07, Sections 6 and 7.2, property 3).

**Lenders act on reports.** When a subscriber checks the bureau and the report
shows adverse information (an account 30 or more days past due now, or 90 or more
in the last year, or written off), it declines the applicant (ASSUMPTION A-059). Otherwise it lends as the world says.
Each game keeps its own record of these decisions; the shared world is not
changed (owner's decision, 15 November 2026: outcomes only).

**The lender's book.** The loans a subscriber made in this game, and their true
fate from the world: a loan has **fallen behind** once it has been 30 or more days
past due, and has **defaulted** once 90 or more or written off. In a year few new
loans get as far as default, so a lender judges its book (and the bureau) by how
many fell behind. Declined applicants are judged the same way: a decline was
**right** if the loan the world made fell behind.

**Contracts renew yearly** (ASSUMPTION A-060). On each anniversary after the game
begins, a subscriber renews if it values the bureau (view 0.5 or more), or if it
values it a little (0.35 or more) and its book has done better than the lender's
own record in the world; otherwise it leaves and stops checking the bureau.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from django.db import connection, models

from apps.commercial.models import Contract, Subscriber
from apps.standards.submission_template import WRITTEN_OFF_STATUS_CODES
from apps.world.generation.persist import loan_month_partition
from apps.world.models import LoanApplication

from .models import Game, LendingDecision, SubscriberView

SERIOUS_DAYS = 90
CURRENT_ARREARS_DAYS = 30
CONTRACT_MONTHS = 12
RENEW_AT, RENEW_IF_BETTER_AT = 0.5, 0.35


def _t(model: type[models.Model]) -> str:
    return model._meta.db_table


def serious_arrears(report: dict[str, Any]) -> bool:
    """Does a credit report show what a lender would decline on?

    An account in arrears now (30 or more days past due), or one that has been 90 or
    more days past due in the last year or written off.
    """
    for account in report.get("accounts", []):
        if (account.get("days_past_due") or 0) >= CURRENT_ARREARS_DAYS:
            return True
        if account.get("status") in WRITTEN_OFF_STATUS_CODES:
            return True
        if (account.get("worst_days_past_due_12m") or 0) >= SERIOUS_DAYS:
            return True
    return False


def decide(
    game: Game,
    application: LoanApplication,
    subscriber_code: str,
    report: dict[str, Any] | None,
    tick: int,
) -> LendingDecision:
    """Record what the lender does with an application in this game."""
    checked = report is not None
    flagged = bool(report) and serious_arrears(report or {})
    return LendingDecision.objects.create(
        game=game,
        application=application,
        subscriber_code=subscriber_code,
        checked=checked,
        flagged=flagged,
        lent=application.approved and not flagged,
        tick=tick,
    )


# --- The book ------------------------------------------------------------------------


@dataclass(frozen=True)
class Book:
    """A lender's lending in this game, as at a date, judged by the world's truth."""

    subscriber: str
    lent: int
    fell_behind: int
    defaulted: int
    declined: int  # applicants the world would have lent to but the report stopped
    declined_fell_behind: int
    usual_rate: float | None  # share of all the lender's loans in the world that fell behind

    @property
    def behind_rate(self) -> float | None:
        return self.fell_behind / self.lent if self.lent else None

    @property
    def default_rate(self) -> float | None:
        return self.defaulted / self.lent if self.lent else None


def _gone_bad(game: Game, loan_ids: list[int], as_of: date, days: int) -> set[int]:
    """The loans that have been ``days`` or more past due (or written off) by ``as_of``."""
    if not loan_ids:
        return set()
    sql = (
        f"SELECT DISTINCT loan_id FROM {loan_month_partition(game.world_id)} "
        "WHERE loan_id = ANY(%(loans)s) AND period <= %(as_of)s "
        "AND (days_past_due >= %(days)s OR status = 'WRITTEN_OFF')"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, {"loans": loan_ids, "as_of": as_of, "days": days})
        return {row[0] for row in cursor.fetchall()}


def book(game: Game, subscriber: str, as_of: date) -> Book:
    rows = list(
        LendingDecision.objects.filter(
            game=game, subscriber_code=subscriber, application__approved=True
        ).values_list("lent", "application__loan_id")
    )
    lent = [loan for made, loan in rows if made and loan]
    declined = [loan for made, loan in rows if not made and loan]
    behind = _gone_bad(game, lent + declined, as_of, CURRENT_ARREARS_DAYS)
    defaulted = _gone_bad(game, lent, as_of, SERIOUS_DAYS)
    every = list(
        LoanApplication.objects.filter(
            world=game.world, lender__code=subscriber, approved=True, loan__isnull=False,
            period__lte=as_of,
        ).values_list("loan_id", flat=True)
    )  # fmt: skip
    usual = _gone_bad(game, every, as_of, CURRENT_ARREARS_DAYS)
    return Book(
        subscriber=subscriber,
        lent=len(lent),
        fell_behind=sum(loan in behind for loan in lent),
        defaulted=len(defaulted),
        declined=len(declined),
        declined_fell_behind=sum(loan in behind for loan in declined),
        usual_rate=len(usual) / len(every) if every else None,
    )


def books(game: Game, as_of: date) -> list[Book]:
    codes = (
        LendingDecision.objects.filter(game=game)
        .order_by("subscriber_code")
        .values_list("subscriber_code", flat=True)
        .distinct()
    )
    return [book(game, code, as_of) for code in codes]


# --- Contracts ---------------------------------------------------------------------------


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def renewal_date(contract: Contract, clock_start: date) -> date:
    """The contract's next anniversary after the game's first month.

    Contracts of an established bureau began with its history; their anniversary in
    the first month of play passes without a decision (the lender has seen nothing
    of this bureau yet), so the first one that counts is a year later.
    """
    years = 1
    due = _add_months(contract.start_date, CONTRACT_MONTHS)
    while due.replace(day=1) <= clock_start.replace(day=1):
        years += 1
        due = _add_months(contract.start_date, CONTRACT_MONTHS * years)
    return due


def renewals(game: Game, today: date, at: datetime, add: Any) -> None:
    """At a month start: subscribers whose contract year ended last month decide."""
    first = today.replace(day=1)
    for subscriber in Subscriber.objects.filter(
        organization=game.organization, is_active=True
    ).order_by("subscriber_code"):
        contract = (
            Contract.objects.filter(subscriber=subscriber, end_date__isnull=True)
            .order_by("-start_date")
            .first()
        )
        if contract is None:
            continue
        due = renewal_date(contract, game.clock_start)
        if due.replace(day=1) > first:
            continue
        view = SubscriberView.objects.get(game=game, subscriber_code=subscriber.subscriber_code)
        b = book(game, subscriber.subscriber_code, first - timedelta(days=1))
        better = (
            b.behind_rate is not None and b.usual_rate is not None and b.behind_rate < b.usual_rate
        )
        renews = view.perceived_value >= RENEW_AT or (
            view.perceived_value >= RENEW_IF_BETTER_AT and better
        )
        contract.end_date = due - timedelta(days=1)
        contract.save(update_fields=["end_date"])
        if renews:
            Contract.objects.create(
                subscriber=subscriber, product=contract.product, unit_price=contract.unit_price,
                contract_type=contract.contract_type, start_date=due,
            )  # fmt: skip
            add(
                "CONTRACT_RENEWED", "INFO",
                f"{subscriber.subscriber_name} renewed its contract for another year",
                _book_line(b), {"screen": "subscribers", "params": {}},
            )  # fmt: skip
        else:
            subscriber.is_active = False
            subscriber.save(update_fields=["is_active"])
            add(
                "CONTRACT_LOST", "CRITICAL",
                f"{subscriber.subscriber_name} did not renew its contract",
                "It no longer checks the bureau. " + _book_line(b),
                {"screen": "subscribers", "params": {}},
            )  # fmt: skip


def _book_line(b: Book) -> str:
    if b.behind_rate is None:
        return "It lent nothing with our reports this year."
    usual = f" (its usual rate is {b.usual_rate:.1%})" if b.usual_rate is not None else ""
    return f"Of the {b.lent} loans it made, {b.behind_rate:.1%} fell behind{usual}."
