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

P3.15 widens the runs to the levers Phase 3 added. Each pair changes one lever on
top of ``steady`` (the starting policies, the same sale), so a difference within a
pair comes from that lever alone:

* score quality: ``score_careful`` (a scorecard per term on its recommended features,
  then the composite) against ``score_careless`` (one long-term scorecard on a single
  weak feature); both develop the score product first, and need history on file;
* compliance effort: ``compliance_diligent`` (a consent sample from every subscriber
  each month, a warning for every one found short and the access review as soon as
  each is due, the legal retention) against ``compliance_lax`` (retention beyond the law, nothing
  else);
* pricing: ``price_high`` and ``price_low`` (the sale at 130% and 75% of list).

Scenario and difficulty are arguments of ``play``: any strategy runs in an
established bureau, a startup (``_found`` builds it first) or a sandbox, at any
difficulty.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum

from apps.bureau.analytics import scoredata as sd
from apps.bureau.quality.models import Dispute
from apps.bureau.quality.rules import CORE, RELAXABLE, STANDARD
from apps.bureau.submissions.models import Submission
from apps.commercial.models import Contract, Subscriber, UsageRecord
from apps.finance.events import balance
from apps.finance.ledger import BANK
from apps.finance.models import BillStatus, SupplierBill
from apps.finance.statements import income_statement
from apps.org.models import Employee
from apps.world.models import World

from . import controls, hr, lending, scenarios, startup
from .bridge import start_game
from .engine import ClockError
from .health import health
from .models import (
    BoardReview,
    ComplianceFinding,
    ConsentCheck,
    EnquiryJudgement,
    Game,
    GameStatus,
    LendingDecision,
    OnboardingStep,
    Proposal,
    RegulatorFinding,
)
from .sales import prospects
from .scorecards import WINDOWS, observation_dates
from .scoreproduct import SCORE, scoring_model

Strategy = Callable[[Game, int], Game]  # (game, month number from 0) -> game


LIST_PRICE = Decimal("15.00")
# Per game: a sale the strategy decided on but could not make yet (a startup has no
# report on sale at first), retried after each step for as long as the run lasts.
_PENDING: dict[int, Decimal] = {}


def _sell(game: Game, price: Decimal = LIST_PRICE) -> Game:
    """A proposal at ``price`` to the two largest lenders that do not subscribe.

    Size is the lender's loans disbursed before play began: the same in every game,
    however far the world has been lived through since. Until there is a report to
    sell, the sale waits.
    """
    from apps.world.models import Loan

    sizes = {
        lender.code: Loan.objects.filter(
            lender=lender, disbursement_date__lt=game.clock_start
        ).count()
        for lender in prospects(game)
    }
    try:
        for code in sorted(sizes, key=lambda c: (-sizes[c], c))[:2]:
            controls.send_proposal(game, code, price)
    except ClockError:
        _PENDING[game.pk] = price
    else:
        _PENDING.pop(game.pk, None)
    return game


def strict_quality(game: Game, month: int) -> Game:
    if month == 0:
        game = controls.set_rejection_policy(game, STANDARD)
        game = controls.set_matching_tooling(game, "ADVANCED")
        game = controls.set_matching_thresholds(game, 0.97, 0.75)
        for senior in hr.candidates_for(game, controls.this_month(game)):
            if senior.job_title == "Senior Data Officer":
                with contextlib.suppress(ClockError):  # a startup's founder hired them already
                    controls.hire_candidate(game, senior.number)
                break
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


def steady(game: Game, month: int) -> Game:
    """The starting policies and the standard sale: the base each lever is set against."""
    return _sell(game) if month == 0 else game


def _dates(game: Game) -> list[tuple[int, date]]:
    """Every (window, observation date) the data allows: longest window, latest date first."""
    return [
        (window, date.fromisoformat(day))
        for window in sorted(WINDOWS, reverse=True)
        for day in reversed(observation_dates(game, window))
    ]


def _build(game: Game, term: str, features: list[str]) -> tuple[int, date] | None:
    """Build and deploy a scorecard on the first window and date with enough data."""
    for window, observation in _dates(game):
        try:
            model = controls.build_scorecard(game, term, observation, window, features)
        except ClockError:
            continue  # too little data there: an earlier date, or a shorter window
        controls.deploy_scorecard(game, model.number)
        return window, observation
    return None


def _score(game: Game, month: int, careful: bool) -> Game:
    """Develop the score product, then build and deploy scorecards once the data allows.

    Careful: a scorecard per term on its recommended features, then the composite.
    Careless: one long-term scorecard on a single weak feature.
    """
    if month == 0:
        game = _sell(game)
        with contextlib.suppress(ClockError):
            controls.develop_product(game, SCORE)
    if scoring_model(game) is not None:
        return game
    if not careful:
        _build(game, sd.LONG, ["facilities_ever"])
        return game
    built = [
        _build(game, term, [f for f, (_, ts) in sd.FEATURES.items() if term in ts])
        for term in sd.TERMS
    ]
    for window, observation in [b for b in built if b is not None][:1]:
        with contextlib.suppress(ClockError):
            model = controls.build_composite(game, observation, window)
            controls.deploy_scorecard(game, model.number)
    return game


def score_careful(game: Game, month: int) -> Game:
    return _score(game, month, careful=True)


def score_careless(game: Game, month: int) -> Game:
    return _score(game, month, careful=False)


def compliance_diligent(game: Game, month: int) -> Game:
    """Each month a consent sample from every subscriber; the findings dealt with as they
    come (``_compliance_duties``, after every step)."""
    if month == 0:
        game = _sell(game)
        game = controls.set_retention(game, 5)
    last_month = controls.state(game).now.date().replace(day=1) - timedelta(days=1)
    for code in (
        Subscriber.objects.filter(organization=game.organization, is_active=True)
        .order_by("subscriber_code")
        .values_list("subscriber_code", flat=True)
    ):
        with contextlib.suppress(ClockError):
            controls.sample_consent(game, code, last_month, 50)
    _compliance_duties(game)
    return game


def _compliance_duties(game: Game) -> None:
    """A warning for each subscriber found short; the access review once it is due."""
    open_findings = ComplianceFinding.objects.filter(game=game, resolved_tick__isnull=True)
    for code in sorted(
        {r.split("-CHECK-")[0] for r in open_findings.filter(kind="CONSENT_MISSING")
         .values_list("reference", flat=True)}
    ):  # fmt: skip
        with contextlib.suppress(ClockError):
            controls.sanction_subscriber(game, code, "WARNING")
    if open_findings.filter(kind="ACCESS_REVIEW_DUE").exists():
        controls.review_access(game)


def compliance_lax(game: Game, month: int) -> Game:
    if month == 0:
        game = _sell(game)
        game = controls.set_retention(game, 7)
    return game


def price_high(game: Game, month: int) -> Game:
    return _sell(game, LIST_PRICE * Decimal("1.30")) if month == 0 else game


def price_low(game: Game, month: int) -> Game:
    return _sell(game, LIST_PRICE * Decimal("0.75")) if month == 0 else game


# What a strategy's heads of department do after every step, beyond ``_tend``.
DUTIES: dict[str, Callable[[Game], None]] = {"compliance_diligent": _compliance_duties}

STRATEGIES: dict[str, Strategy] = {
    "strict_quality": strict_quality,
    "fast_coverage": fast_coverage,
    "cheap_staffing": cheap_staffing,
    "steady": steady,
    "score_careful": score_careful,
    "score_careless": score_careless,
    "compliance_diligent": compliance_diligent,
    "compliance_lax": compliance_lax,
    "price_high": price_high,
    "price_low": price_low,
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


def _onboard(game: Game) -> None:
    """Sales takes a lender's counter-offer; the heads of Compliance and Finance settle
    what their staff pass up (P3.9)."""
    for number in Proposal.objects.filter(game=game, status="COUNTERED").values_list(
        "number", flat=True
    ):
        with contextlib.suppress(ClockError):
            controls.accept_counter(game, number)
    for step in OnboardingStep.objects.filter(
        onboarding__game=game, onboarding__status="IN_PROGRESS", status="ESCALATED"
    ).select_related("onboarding"):
        if step.code == "SUBSCRIBER_CHECK":
            controls.decide_subscriber_check(game, step.onboarding.number, "APPROVE_WITH_WARNING")
        elif step.code == "BILLING":
            controls.set_up_billing(game, step.onboarding.number)


def _found(game: Game) -> Game:
    """A founder's first hour (P3.13): office, IT, the report, agents, then the team."""
    controls.rent_office(game, "SMALL")
    controls.set_up_it(game, "STANDARD")
    controls.develop_product(game, "CONSUMER_REPORT")
    controls.set_support_staff(game, 1)
    _approve_bills(game)
    game = controls.advance_by(game, "hour")  # the month starts: this month's candidates
    for candidate in hr.candidates_for(game, controls.this_month(game)):
        controls.hire_candidate(game, candidate.number)
    return game


def _approve_bills(game: Game) -> None:
    """The Head of Finance approves every bill left waiting for them."""
    for number in SupplierBill.objects.filter(
        organization=game.organization, status=BillStatus.RECEIVED
    ).values_list("number", flat=True):
        with contextlib.suppress(ClockError):
            controls.approve_bill(game, number)


def _tend(game: Game, strategy: str) -> None:
    """What the heads of department do between the strategy's monthly decisions."""
    _onboard(game)
    if strategy in DUTIES:
        DUTIES[strategy](game)
    if game.scenario == scenarios.STARTUP:
        _approve_bills(game)
        if startup.systems_ready(game, controls.state(game).now.date()):
            for lender in startup.provider_prospects(game):
                with contextlib.suppress(ClockError):
                    controls.onboard_provider(game, lender.code)
    if game.pk in _PENDING:
        _sell(game, _PENDING[game.pk])


def play(
    world: World,
    strategy: str,
    months: int,
    difficulty: str = "INTERMEDIATE",
    scenario: str = "ESTABLISHED",
    history_months: int = 0,
    settings: dict[str, Any] | None = None,
) -> Game:
    game = controls.set_pause_rules(
        start_game(world, difficulty=difficulty, scenario=scenario,
                   history_months=history_months, settings=settings),
        [], deadlines=False,
    )  # fmt: skip
    if scenario == scenarios.STARTUP:
        game = _found(game)
    try:
        for month in range(months):
            game = STRATEGIES[strategy](game, month)
            current = controls.state(game).now.month
            while controls.state(game).now.month == current and game.status != GameStatus.ENDED:
                game = controls.advance_by(game, "next_event")
                _tend(game, strategy)
            if game.status == GameStatus.ENDED:
                break
    finally:
        _PENDING.pop(game.pk, None)
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
    model = scoring_model(game)
    contracts = Contract.objects.filter(
        subscriber__organization=org, product__product_code="CONSUMER_REPORT"
    )
    return {
        "scenario": game.scenario,
        "difficulty": game.difficulty,
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
        "report_price": (
            round(sum(float(c.unit_price) for c in contracts) / len(contracts), 2)
            if contracts
            else None
        ),
        # The score (P3.5, P3.6)
        "score_auc": (model.results.get("truth") or {}).get("auc_against_truth") if model else None,
        "scores_sold": UsageRecord.objects.filter(
            organization=org, product__product_code=SCORE
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
        "findings_by_kind": _by_kind(RegulatorFinding.objects.filter(game=game)),
        "compliance_findings": _by_kind(ComplianceFinding.objects.filter(game=game)),
        "consent_checks": ConsentCheck.objects.filter(game=game).count(),
        "improper_enquiry_rate": _share(judged.filter(grounds_held=False).count(), judged.count()),
        # People
        "staff": Employee.objects.filter(organization=org, is_active=True).count(),
        "morale": summary["parts"]["team"]["average_morale"],
        # The board's view
        "health": summary["overall"],
        "health_parts": {k: v["score"] for k, v in summary["parts"].items()},
        "board": [round(r.confidence, 1) for r in reviews],
    }


def _by_kind(rows: Any) -> dict[str, int]:
    return {k: n for k, n in rows.values_list("kind").annotate(n=Count("pk")).order_by("kind")}


def _fell_behind(game: Game, as_of: date) -> float | None:
    """Of the loans the subscribers made while checking us, the share that fell behind."""
    lent = behind = 0
    for book in lending.books(game, as_of):
        lent += book.lent
        behind += book.fell_behind
    return _share(behind, lent)


def run(world: World, strategy: str, months: int, difficulty: str = "INTERMEDIATE",
        scenario: str = "ESTABLISHED", history_months: int = 0) -> Run:  # fmt: skip
    game = play(world, strategy, months, difficulty, scenario, history_months)
    return Run(strategy, world.seed, months, outcomes(game))
