# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Data assets: what the bureau's data is worth (P2.3; Document 07, Section 6.2).

| Asset              | Definition                                                       |
| ------------------ | ---------------------------------------------------------------- |
| Coverage           | Share of the world's active borrowers with an account on file     |
| Depth              | Months of history held per account                                |
| Freshness          | Days since the latest report, per open account (median)           |
| Accuracy           | Share of accounts whose latest balance and arrears match the truth |
| Identity integrity | False merges (two people as one) and false splits (one as two)    |

The player sees coverage, depth and freshness. Accuracy and identity integrity
are estimated by a monthly sampling audit (ASSUMPTION A-046): a real bureau never
knows its true error rate, only what it finds when it checks a sample with the
providers. The true values appear in the Data Quality Review.

Only the simulation may read the world; these functions are its window.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django.db import connection, models

from apps.bureau.core.models import (
    AccountObservation,
    CreditAccount,
    Customer,
    ProviderCustomerLink,
)
from apps.bureau.providers.models import Institution
from apps.bureau.submissions.models import Submission
from apps.standards.submission_template import OPEN_STATUS_ON_FILE
from apps.world.generation.persist import loan_month_partition
from apps.world.generation.rng import stream
from apps.world.models import Lender as WorldLender
from apps.world.models import LenderCustomer, Loan

from .clock import previous_month_end
from .models import Game

AUDIT_SAMPLE = 100  # accounts, and customers, checked with the providers each month
BALANCE_TOLERANCE = 1  # whole cedis: providers report whole amounts

Borrower = tuple[str, int]


def _t(model: type[models.Model]) -> str:
    return model._meta.db_table


# Each bureau account and the true borrower of the loan it describes.
_ACCOUNTS = f"""
SELECT ca.id, ca.customer_id, i.institution_code, ca.facility_account_number,
       lc.person_id, lc.business_id, l.id
FROM {_t(CreditAccount)} ca
JOIN {_t(Institution)} i ON i.id = ca.institution_id
JOIN {_t(WorldLender)} wl ON wl.world_id = %(world)s AND wl.code = i.institution_code
JOIN {_t(Loan)} l ON l.lender_id = wl.id AND l.account_number = ca.facility_account_number
JOIN {_t(LenderCustomer)} lc ON lc.id = l.customer_id
WHERE ca.organization_id = %(org)s
"""

# Each provider customer number the bureau has linked, and whose it really is.
_LINKS = f"""
SELECT pl.customer_id, i.institution_code, pl.provider_customer_number,
       lc.person_id, lc.business_id
FROM {_t(ProviderCustomerLink)} pl
JOIN {_t(Institution)} i ON i.id = pl.institution_id
JOIN {_t(WorldLender)} wl ON wl.world_id = %(world)s AND wl.code = i.institution_code
JOIN {_t(LenderCustomer)} lc ON lc.lender_id = wl.id AND lc.customer_number = pl.provider_customer_number
WHERE pl.organization_id = %(org)s
"""


def _borrower(person: int | None, business: int | None) -> Borrower:
    return ("person", person) if person is not None else ("business", int(business or 0))


@dataclass(frozen=True)
class AccountTruth:
    account_id: int
    customer_id: int
    provider: str
    account_number: str
    borrower: Borrower
    loan_id: int


def account_truth(game: Game) -> list[AccountTruth]:
    with connection.cursor() as cursor:
        cursor.execute(_ACCOUNTS, {"world": game.world_id, "org": game.organization_id})
        return [
            AccountTruth(a, c, code, number, _borrower(p, b), loan)
            for a, c, code, number, p, b, loan in cursor.fetchall()
        ]


@dataclass
class Identity:
    """Who each bureau customer really is, from the provider links."""

    borrowers_of: dict[int, set[Borrower]]  # bureau customer -> true borrowers
    customers_of: dict[Borrower, set[int]]  # true borrower -> bureau customers

    @property
    def merged(self) -> list[int]:
        """Bureau customers that are really two or more people (false merges)."""
        return sorted(c for c, b in self.borrowers_of.items() if len(b) > 1)

    @property
    def split(self) -> list[Borrower]:
        """People the bureau holds as two or more customers (false splits)."""
        return sorted(b for b, c in self.customers_of.items() if len(c) > 1)


def identity(game: Game) -> Identity:
    borrowers_of: dict[int, set[Borrower]] = defaultdict(set)
    customers_of: dict[Borrower, set[int]] = defaultdict(set)
    with connection.cursor() as cursor:
        cursor.execute(_LINKS, {"world": game.world_id, "org": game.organization_id})
        for customer, _code, _number, person, business in cursor.fetchall():
            who = _borrower(person, business)
            borrowers_of[customer].add(who)
            customers_of[who].add(customer)
    return Identity(dict(borrowers_of), dict(customers_of))


# Every provider link: how it was made, when its file arrived, and whose it really is.
_LINK_AUDIT = f"""
SELECT pl.id, pl.customer_id, pl.method, s.received_at, lc.person_id, lc.business_id
FROM {_t(ProviderCustomerLink)} pl
JOIN {_t(Submission)} s ON s.id = pl.source_submission_id
JOIN {_t(Institution)} i ON i.id = pl.institution_id
JOIN {_t(WorldLender)} wl ON wl.world_id = %(world)s AND wl.code = i.institution_code
JOIN {_t(LenderCustomer)} lc ON lc.lender_id = wl.id AND lc.customer_number = pl.provider_customer_number
WHERE pl.organization_id = %(org)s
ORDER BY pl.id
"""


def link_audit(game: Game, start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """How the bureau linked its provider customers, and how often each way was wrong.

    A link is a **wrong merge** when it puts someone other than the customer's first
    linked person on the customer; a link that made a new customer is a **false
    split** when its person was already held as another customer. ``this_month``
    counts links from files received between ``start`` and ``end``.
    """
    with connection.cursor() as cursor:
        cursor.execute(_LINK_AUDIT, {"world": game.world_id, "org": game.organization_id})
        rows = cursor.fetchall()
    first_of: dict[int, Borrower] = {}  # customer -> the person its first link names
    held_as: dict[Borrower, int] = {}  # person -> the customer first linked to them
    out: dict[str, dict[str, int]] = defaultdict(
        lambda: {"links": 0, "this_month": 0, "wrong_merges": 0, "false_splits": 0,
                 "wrong_this_month": 0}
    )  # fmt: skip
    for _link, customer, method, received, person, business in rows:
        who = _borrower(person, business)
        tally = out[method or "BEFORE_P2_4"]
        recent = start <= received < end
        tally["links"] += 1
        tally["this_month"] += recent
        wrong = False
        if customer not in first_of:
            first_of[customer] = who
            if who in held_as and held_as[who] != customer:
                tally["false_splits"] += 1
                wrong = True
        elif first_of[customer] != who:
            tally["wrong_merges"] += 1
            wrong = True
        held_as.setdefault(who, customer)
        tally["wrong_this_month"] += recent and wrong
    return dict(out)


def active_borrowers(game: Game, period: date) -> set[Borrower]:
    """Everyone with a loan open at the end of ``period``, with any lender."""
    sql = (
        f"SELECT DISTINCT lc.person_id, lc.business_id FROM {loan_month_partition(game.world_id)} m "
        f"JOIN {_t(Loan)} l ON l.id = m.loan_id JOIN {_t(LenderCustomer)} lc ON lc.id = l.customer_id "
        "WHERE m.period = %(period)s AND m.status = 'ACTIVE'"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, {"period": period})
        return {_borrower(p, b) for p, b in cursor.fetchall()}


def latest_facts(
    game: Game, accounts: list[AccountTruth] | None = None
) -> list[tuple[int, Any, int, Any, Any]]:
    """Each account's latest report beside the truth for the same month.

    Rows: (account id, balance on file, days past due on file, true balance, true days
    past due); the truth is None where the world has no month for it. Done in steps,
    joined here: one query over the bureau's reports, one over the world's months.
    ``accounts`` limits it to some accounts (an audit sample); by default, all.
    """
    if accounts is None:
        accounts = account_truth(game)
    loan_of = {a.account_id: a.loan_id for a in accounts}
    sql = f"""
    SELECT DISTINCT ON (o.credit_account_id) o.credit_account_id, o.reporting_date,
           o.outstanding_balance, o.days_past_due
    FROM {_t(AccountObservation)} o
    WHERE o.is_current AND o.credit_account_id = ANY(%(accounts)s)
    ORDER BY o.credit_account_id, o.reporting_date DESC
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, {"accounts": list(loan_of)})
        latest = cursor.fetchall()
        wanted = {(loan_of[a], reported) for a, reported, _, _ in latest}
        cursor.execute(
            f"SELECT loan_id, period, outstanding_balance, days_past_due "
            f"FROM {loan_month_partition(game.world_id)} "
            "WHERE loan_id = ANY(%(loans)s) AND period = ANY(%(periods)s)",
            {
                "loans": sorted({loan for loan, _ in wanted}),
                "periods": sorted({period for _, period in wanted}),
            },
        )
        truth = {(loan, period): (bal, dpd) for loan, period, bal, dpd in cursor.fetchall()}
    rows = []
    for account, reported, balance, dpd in latest:
        true_balance, true_dpd = truth.get((loan_of[account], reported), (None, None))
        rows.append((account, balance, dpd, true_balance, true_dpd))
    return rows


def fact_is_right(row: tuple[int, Any, int, Any, Any]) -> bool:
    _, balance, dpd, true_balance, true_dpd = row
    if true_balance is None:
        return False
    return bool(abs(balance - round(true_balance)) <= BALANCE_TOLERANCE and dpd == true_dpd)


# --- What the bureau can see -----------------------------------------------------------


def depth_and_freshness(game: Game, today: date) -> dict[str, Any]:
    """Months of history per account, and days since each open account's latest report."""
    sql = f"""
    SELECT count(*), avg(n), percentile_disc(0.5) WITHIN GROUP (ORDER BY age)
           FILTER (WHERE is_open),
           count(*) FILTER (WHERE is_open)
    FROM (
        SELECT count(*) AS n, %(today)s - max(o.reporting_date) AS age,
               bool_or(ca.account_status = ANY(%(open)s)) AS is_open
        FROM {_t(AccountObservation)} o
        JOIN {_t(CreditAccount)} ca ON ca.id = o.credit_account_id
        WHERE ca.organization_id = %(org)s AND o.is_current
        GROUP BY o.credit_account_id
    ) per_account
    """
    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            {"org": game.organization_id, "today": today, "open": sorted(OPEN_STATUS_ON_FILE)},
        )
        accounts, depth, freshness, open_accounts = cursor.fetchone()
    return {
        "accounts": accounts,
        "depth_months": round(float(depth), 1) if depth is not None else None,
        "freshness_days": freshness,
        "open_accounts": open_accounts,
    }


def coverage(game: Game, period: date, accounts: list[AccountTruth]) -> dict[str, Any]:
    active = active_borrowers(game, period)
    held = {a.borrower for a in accounts}
    covered = len(active & held)
    return {
        "period": period.isoformat(),
        "active_borrowers": len(active),
        "covered": covered,
        "share": round(covered / len(active), 4) if active else None,
    }


def _estimate(hits: int, n: int) -> dict[str, Any]:
    """A sample share with its 95% margin of error."""
    if not n:
        return {"share": None, "margin": None, "sample": 0}
    p = hits / n
    margin = 1.96 * math.sqrt(max(p * (1 - p), 1 / n) / n)
    return {"share": round(p, 4), "margin": round(margin, 4), "sample": n}


def audit(
    game: Game,
    period: date,
    accounts: list[AccountTruth],
    who: Identity,
    facts: list[tuple[int, Any, int, Any, Any]] | None = None,
) -> dict[str, Any]:
    """The monthly sampling audit: accuracy and identity integrity, as the bureau estimates them.

    A sample of accounts is checked with the providers (are the balance and arrears
    right?) and a sample of customers (are their accounts all one person's?). The
    samples are drawn from the seed and the month, in the bureau's own order.
    """
    rng = stream(game.world.seed, f"audit:{period:%Y%m}")
    chosen = _sample(rng, sorted(accounts, key=lambda a: (a.provider, a.account_number)))
    if facts is None:
        checked = latest_facts(game, chosen)
    else:
        ids = {a.account_id for a in chosen}
        checked = [f for f in facts if f[0] in ids]
    customers = sorted(
        Customer.objects.filter(organization=game.organization).values_list(
            "customer_reference", "id"
        )
    )
    picked = _sample(rng, customers)
    merged = set(who.merged)
    return {
        "accuracy": _estimate(sum(fact_is_right(f) for f in checked), len(checked)),
        "one_person": _estimate(sum(c not in merged for _, c in picked), len(picked)),
    }


def _sample(rng: Any, rows: list[Any]) -> list[Any]:
    if len(rows) <= AUDIT_SAMPLE:
        return rows
    return [rows[int(i)] for i in sorted(rng.choice(len(rows), AUDIT_SAMPLE, replace=False))]


def visible_assets(game: Game, today: date) -> dict[str, Any]:
    """What the player sees: coverage, depth and freshness, and the audit's estimates."""
    return month_end_assets(game, today, with_truth=False)[0]


def month_end_assets(
    game: Game, today: date, *, with_truth: bool = True
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The visible figures and, for the review, the truth behind them; worked out together."""
    period = previous_month_end(today)
    accounts = account_truth(game)
    who = identity(game)
    facts = latest_facts(game, accounts) if with_truth else None
    visible = {
        "as_of": today.isoformat(),
        "coverage": coverage(game, period, accounts),
        **depth_and_freshness(game, today),
        "audit": audit(game, period, accounts, who, facts),
    }
    if facts is None:
        return visible, None
    right = sum(fact_is_right(f) for f in facts)
    customers, people = len(who.borrowers_of), len(who.customers_of)
    truth = {
        "accuracy": {
            "accounts": len(facts),
            "right": right,
            "share": round(right / len(facts), 4) if facts else None,
        },
        "identity": {
            "customers": customers,
            "false_merges": len(who.merged),
            "merge_rate": round(len(who.merged) / customers, 4) if customers else None,
            "people": people,
            "false_splits": len(who.split),
            "split_rate": round(len(who.split) / people, 4) if people else None,
        },
    }
    return visible, truth
