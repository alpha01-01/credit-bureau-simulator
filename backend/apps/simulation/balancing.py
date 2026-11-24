"""Headless runs of scripted strategies, for balancing (P2.12; Document 08).

A strategy is a set of player decisions taken at the start and then at each
month start; the run then measures where the bureau stands. The same strategies
are run across seeds; ``outcomes`` is the yardstick every comparison uses.

    manage.py balance --size small --seeds 81 82 83 --months 6

Strategies (Document 08, P2.12):

* ``strict_quality``: reject on any field failure, fuzzy matching with a wide
  review band, a senior hire, training and feedback for every provider.
* ``fast_coverage``: reject only on core fields, every relaxable check relaxed,
  matching that links readily, no extra staff, no provider work.
* ``cheap_staffing``: the starting policies, pay cut to the bottom of each band,
  no tooling, no training.

All three sell the same way: a proposal to the two largest lenders that do not
subscribe, at the list price, in the first month. Differences in outcomes come
from how they run the data.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.bureau.quality.models import Dispute
from apps.bureau.quality.rules import CORE, RELAXABLE, STANDARD
from apps.bureau.submissions.models import Submission
from apps.commercial.models import Subscriber, UsageRecord
from apps.finance.events import balance
from apps.finance.ledger import BANK
from apps.finance.statements import income_statement
from apps.org.models import Employee
from apps.world.models import World

from . import controls, hr, lending
from .bridge import start_game
from .engine import ClockError
from .health import health
from .models import (
    BoardReview,
    EnquiryJudgement,
    Game,
    GameStatus,
    LendingDecision,
    RegulatorFinding,
)
from .sales import prospects

Strategy = Callable[[Game, int], Game]  # (game, month number from 0) -> game


def _sell(game: Game) -> Game:
    """A proposal at list price to the two largest lenders that do not subscribe.

    Size is the lender's loans disbursed before play began: the same in every game,
    however far the world has been lived through since.
    """
    from apps.world.models import Loan

    sizes = {
        lender.code: Loan.objects.filter(
            lender=lender, disbursement_date__lt=game.clock_start
        ).count()
        for lender in prospects(game)
    }
    for code in sorted(sizes, key=lambda c: (-sizes[c], c))[:2]:
        controls.send_proposal(game, code, Decimal("15.00"))
    return game


def strict_quality(game: Game, month: int) -> Game:
    if month == 0:
        game = controls.set_rejection_policy(game, STANDARD)
        game = controls.set_matching_tooling(game, "ADVANCED")
        game = controls.set_matching_thresholds(game, 0.97, 0.75)
        senior = next(
            c
            for c in hr.candidates_for(game, controls.this_month(game))
            if c.job_title == "Senior Data Officer"
        )
        controls.hire_candidate(game, senior.number)
        game = _sell(game)
    for code in game.organization.institutions.filter(is_active=True).values_list(
        "institution_code", flat=True
    ):
        with contextlib.suppress(ClockError):
            game = controls.train_provider(game, code)
    _feedback(game)
    return game


def fast_coverage(game: Game, month: int) -> Game:
    if month == 0:
        game = controls.set_rejection_policy(game, CORE)
        for code in RELAXABLE:
            game = controls.set_rule_override(game, code, "WARNING")
        game = controls.set_matching_tooling(game, "STANDARD")
        game = controls.set_matching_thresholds(game, 0.80, 0.78)
        game = _sell(game)
    return game


def cheap_staffing(game: Game, month: int) -> Game:
    if month == 0:
        for person in Employee.objects.filter(organization=game.organization).order_by(
            "employee_number"
        ):
            low = hr.ROLES.get(person.job_title, hr.ROLES["Data Officer"])[1][0]
            controls.set_salary(game, person.employee_number, Decimal(low))
        game = _sell(game)
    return game


STRATEGIES: dict[str, Strategy] = {
    "strict_quality": strict_quality,
    "fast_coverage": fast_coverage,
    "cheap_staffing": cheap_staffing,
}


def _feedback(game: Game) -> None:
    """Send every provider the feedback report for its processed submissions."""
    for sub in (
        Submission.objects.filter(
            organization=game.organization, runs__isnull=False, feedback_reports__isnull=True
        )
        .distinct()
        .order_by("submission_reference")
    ):
        with contextlib.suppress(ClockError):
            controls.send_feedback(game, sub.submission_reference)


@dataclass
class Run:
    strategy: str
    seed: int
    months: int
    outcomes: dict[str, Any]


def play(world: World, strategy: str, months: int) -> Game:
    game = controls.set_pause_rules(start_game(world), [], deadlines=False)
    for month in range(months):
        game = STRATEGIES[strategy](game, month)
        current = controls.state(game).now.month
        while controls.state(game).now.month == current and game.status != GameStatus.ENDED:
            game = controls.advance_by(game, "next_event")
        if game.status == GameStatus.ENDED:
            break
    return game


def _share(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def outcomes(game: Game) -> dict[str, Any]:
    """Where the bureau stands: money, data, customers, compliance, people."""
    org = game.organization
    now = controls.state(game).now
    start = game.clock_start
    last_month_end = now.date().replace(day=1) - timedelta(days=1)
    statement = income_statement(org, start, last_month_end)
    review = game.reviews.order_by("-period").first()
    truth = review.figures["assets"]["truth"] if review else {}
    visible = review.figures["assets"]["visible"] if review else {}
    judged = EnquiryJudgement.objects.filter(game=game)
    hits = judged.filter(hit=True).count()
    decided = LendingDecision.objects.filter(game=game)
    summary = health(game, now)
    reviews = list(BoardReview.objects.filter(game=game).order_by("period"))
    return {
        "ended": game.ended_reason or None,
        "months": round(game.current_tick / (36 * 21.7), 1),
        # Money
        "revenue": float(statement["total_income"]),
        "expenses": float(statement["total_expenses"]),
        "net_profit": float(statement["net_profit"]),
        "bank": float(balance(org, BANK, now.date())),
        "reports_sold": UsageRecord.objects.filter(
            organization=org, product__product_code="CONSUMER_REPORT"
        ).aggregate(n=Sum("quantity"))["n"]
        or 0,
        # Data
        "accuracy_true": (truth.get("accuracy") or {}).get("share"),
        "false_merge_rate": (truth.get("identity") or {}).get("merge_rate"),
        "false_split_rate": (truth.get("identity") or {}).get("split_rate"),
        "coverage": (visible.get("coverage") or {}).get("share"),
        "freshness_days": visible.get("freshness_days"),
        # Customers
        "enquiries": judged.count(),
        "hit_rate": _share(hits, judged.count()),
        "wrong_person_rate": _share(judged.filter(outcome="WRONG_PERSON").count(), hits),
        "subscribers": Subscriber.objects.filter(organization=org, is_active=True).count(),
        "loans_fell_behind": _fell_behind(game, last_month_end),
        "checked_share": _share(decided.filter(checked=True).count(), decided.count()),
        # Compliance
        "disputes": Dispute.objects.filter(organization=org).count(),
        "findings": RegulatorFinding.objects.filter(game=game).count(),
        # People
        "staff": Employee.objects.filter(organization=org, is_active=True).count(),
        "morale": summary["parts"]["team"]["average_morale"],
        # The board's view
        "health": summary["overall"],
        "health_parts": {k: v["score"] for k, v in summary["parts"].items()},
        "board": [round(r.confidence, 1) for r in reviews],
    }


def _fell_behind(game: Game, as_of: date) -> float | None:
    """Of the loans the subscribers made while checking us, the share that fell behind."""
    lent = behind = 0
    for book in lending.books(game, as_of):
        lent += book.lent
        behind += book.fell_behind
    return _share(behind, lent)


def run(world: World, strategy: str, months: int) -> Run:
    game = play(world, strategy, months)
    return Run(strategy, world.seed, months, outcomes(game))
