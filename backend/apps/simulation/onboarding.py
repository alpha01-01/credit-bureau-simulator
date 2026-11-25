"""A new subscriber's way through the company (P3.9; PRD, Section 16).

Sales signs the lender; Compliance checks it; IT connects it; Finance sets up its
billing; Support answers its first questions. Each step is its department's work and
waits for the step before it, so a step left undone holds up every step after it.

ASSUMPTION A-079 (the hand-offs; working days):

* Compliance's staff check the subscriber in 3 days: its licence and permissible
  purpose, and a sample of 40 of its consent forms. Two or more missing is a concern
  the staff cannot settle: the check waits for the Head of Compliance, who approves,
  approves under a warning (the P3.7 sanction, which makes the lender more careful)
  or refuses the subscriber.
* IT (managed) needs 5 days of work, on days the systems are up, and connects one
  subscriber at a time (two on high capacity). Once connected, the subscriber's
  applications reach the bureau.
* Finance's staff set up billing on standard terms in 2 days. Terms off the price
  list (a minimum, a discount, premium service, a 24-month term) wait for the Head of
  Finance. Until billing is set up, the subscriber's usage is not invoiced.
* Support (managed until P3.10) needs 2 days, on days the systems are up.
* A lender not connected within 30 working days of signing walks away.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import F, Max, Sum

from apps.commercial.models import Subscriber, UsageRecord
from apps.world.generation.rng import stream
from apps.world.models import Lender

from . import duties, it
from .compliance import add_working_days
from .models import Game, Onboarding, OnboardingStep, Proposal

STEPS = (  # department, code, what is done, working days
    ("SALES", "HANDOVER", "Sign the contract and hand the subscriber over", 0),
    ("COMPLIANCE", "SUBSCRIBER_CHECK",
     "Check the subscriber: licence, permissible purpose, consent forms", 3),
    ("IT", "CONNECTION", "Connect the subscriber to the bureau's systems", 5),
    ("FINANCE", "BILLING", "Set up billing on the contract's terms", 2),
    ("SUPPORT", "WELCOME", "Answer the subscriber's first questions and train its staff", 2),
)  # fmt: skip
TITLES = {code: title for _, code, title, _ in STEPS}
DAYS = {code: days for _, code, _, days in STEPS}
PATIENCE_WORKING_DAYS = 30
CONSENT_SAMPLE, CONCERN_MISSING = 40, 2
CONNECTIONS_AT_ONCE = {"STANDARD": 1, "HIGH": 2}
APPROVE, WARN, REFUSE = "APPROVE", "APPROVE_WITH_WARNING", "REFUSE"
DONE, READY, ESCALATED, WAITING, CANCELLED = "DONE", "READY", "ESCALATED", "WAITING", "CANCELLED"


class OnboardingError(Exception):
    pass


def _drill(onboarding: Onboarding) -> dict[str, Any]:
    return {"screen": "onboarding", "params": {"number": str(onboarding.number)}}


def start(game: Game, proposal: Proposal, price: Decimal, at: datetime, add: Any) -> Onboarding:
    """The lender has signed: the onboarding begins, with Compliance's check."""
    today = at.date()
    number = (Onboarding.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1
    onboarding = Onboarding.objects.create(
        game=game,
        number=number,
        lender_code=proposal.lender_code,
        proposal=proposal,
        unit_price=price,
        signed_on=today,
        give_up_on=add_working_days(today, PATIENCE_WORKING_DAYS),
    )
    OnboardingStep.objects.bulk_create(
        OnboardingStep(onboarding=onboarding, position=n, department=dept, code=code)
        for n, (dept, code, _, _) in enumerate(STEPS, 1)
    )
    handover = onboarding.steps.get(code="HANDOVER")
    _done(handover, today, None, "Sales", f"Signed at GHS {price} a report")
    _ready(game, onboarding, today, add)
    return onboarding


def current(onboarding: Onboarding) -> OnboardingStep | None:
    """The step the onboarding is waiting on."""
    return onboarding.steps.exclude(status__in=[DONE, CANCELLED]).order_by("position").first()


def _done(step: OnboardingStep, on: date, tick: int | None, by: str, outcome: str) -> None:
    step.status, step.done_on, step.done_tick = DONE, on, tick
    step.done_by, step.outcome, step.held = by, outcome[:300], ""
    step.save()


def _ready(game: Game, onboarding: Onboarding, on: date, add: Any) -> None:
    """Hand the onboarding to the next department."""
    step = current(onboarding)
    if step is None:
        onboarding.status, onboarding.ended_on = "COMPLETE", on
        onboarding.save(update_fields=["status", "ended_on"])
        add(
            "ONBOARDING_COMPLETE", "INFO", f"{onboarding.lender_code} is fully onboarded",
            "Every department has done its part.", _drill(onboarding),
        )  # fmt: skip
        return
    step.status, step.ready_on = READY, on
    step.due_on = add_working_days(on, DAYS[step.code])
    if step.code == "SUBSCRIBER_CHECK":
        rate = duties.improper_rate(game, onboarding.lender_code)
        rng = stream(game.world.seed, f"onboarding-check:{onboarding.lender_code}:{on}")
        missing = int(rng.binomial(CONSENT_SAMPLE, rate))
        step.evidence = {
            "licensed": True,
            "purpose": "Credit decisions on its own applicants",
            "sample": CONSENT_SAMPLE,
            "missing": missing,
            "concern": missing >= CONCERN_MISSING,
        }
        if missing >= CONCERN_MISSING:
            step.status = ESCALATED
            step.held = (
                f"{missing} of {CONSENT_SAMPLE} consent forms missing: the staff will not "
                "approve it. The Head of Compliance decides."
            )
            add(
                "ONBOARDING_CHECK", "WARNING",
                f"Compliance must decide on {onboarding.lender_code}",
                step.held, _drill(onboarding),
            )  # fmt: skip
    elif step.code == "BILLING":
        terms = onboarding.proposal
        standard = (
            terms.term_months == 12
            and terms.service_level == "STANDARD"
            and not terms.monthly_minimum
            and not terms.discount_rate
        )
        step.evidence = {"standard": standard}
        if not standard:
            step.status = ESCALATED
            step.held = (
                "Terms off the price list: the Head of Finance checks them against the "
                "contract before billing is set up."
            )
            add(
                "ONBOARDING_BILLING", "WARNING",
                f"Finance must set up {onboarding.lender_code}'s billing",
                step.held, _drill(onboarding),
            )  # fmt: skip
    step.save()


# --- Each morning --------------------------------------------------------------------------


def morning(game: Game, day: date, tick: int, at: datetime, add: Any) -> None:
    """Staff do the steps that are theirs; the lender may lose patience."""
    onboardings = list(
        Onboarding.objects.filter(game=game, status="IN_PROGRESS").order_by("number")
    )
    if not onboardings:
        return
    from .startup import systems_ready

    down = it.systems_down(game, tick)
    slots = CONNECTIONS_AT_ONCE.get(game.organization.it_capacity, 1)
    connecting = 0
    for onboarding in onboardings:
        step = current(onboarding)
        if step is None:
            continue
        if step.position <= 3 and day > onboarding.give_up_on:
            _withdraw(onboarding, day, add)
            continue
        if step.status == ESCALATED or step.ready_on is None or step.ready_on >= day:
            continue  # waiting for a head of department, or handed over only today
        if step.code in ("CONNECTION", "WELCOME"):
            if step.code == "CONNECTION":
                if connecting >= slots:
                    step.held = "Queued: IT connects one subscriber at a time on this capacity"
                    step.save(update_fields=["held"])
                    continue
                connecting += 1
            if step.code == "CONNECTION" and not systems_ready(game, day):
                step.held = "The bureau's systems are not set up yet"
                step.save(update_fields=["held"])
                continue
            if step.code == "WELCOME" and game.organization.support_staff == 0:
                step.held = "There are no contact-centre agents to welcome it"
                step.save(update_fields=["held"])
                continue
            if down:
                step.held = "The systems are down"
                step.save(update_fields=["held"])
                continue
            step.progress += 1
            step.held = ""
            step.due_on = add_working_days(day, DAYS[step.code] - step.progress)
            step.save(update_fields=["progress", "held", "due_on"])
            if step.progress < DAYS[step.code]:
                continue
            if step.code == "CONNECTION":
                _done(step, day, tick, "IT", "Connected; its applications now reach the bureau")
                _go_live(game, onboarding, day, add)
            else:
                _done(step, day, tick, "Support", "Questions answered; its staff trained")
            _ready(game, onboarding, day, add)
        elif step.due_on is not None and step.due_on <= day:
            if step.code == "SUBSCRIBER_CHECK":
                _done(step, day, tick, "Compliance staff", "Approved: no concerns found")
            else:  # BILLING on standard terms
                _set_up(onboarding, step, day, tick, "Finance staff")
            _ready(game, onboarding, day, add)


def _go_live(game: Game, onboarding: Onboarding, day: date, add: Any) -> None:
    from . import sales

    lender = Lender.objects.get(world=game.world, code=onboarding.lender_code)
    sales.sign(
        game, lender, onboarding.unit_price, day,
        sales.Terms.of(onboarding.proposal), billing_ready=False,
    )  # fmt: skip
    onboarding.live_on = day
    onboarding.save(update_fields=["live_on"])
    add(
        "SUBSCRIBER_LIVE", "INFO", f"{lender.name} is connected",
        "Its applications reach us from today. Finance sets up its billing next.",
        _drill(onboarding),
    )  # fmt: skip


def _set_up(onboarding: Onboarding, step: OnboardingStep, day: date, tick: int, by: str) -> None:
    Subscriber.objects.filter(
        organization=onboarding.game.organization, subscriber_code=onboarding.lender_code
    ).update(billing_ready=True)
    _done(step, day, tick, by, "Billing set up on the contract's terms")


def _withdraw(onboarding: Onboarding, day: date, add: Any) -> None:
    onboarding.status, onboarding.ended_on = "WITHDRAWN", day
    onboarding.save(update_fields=["status", "ended_on"])
    step = current(onboarding)
    onboarding.steps.exclude(status=DONE).update(status=CANCELLED)
    add(
        "ONBOARDING_WITHDRAWN", "WARNING",
        f"{onboarding.lender_code} has walked away",
        f"Signed on {onboarding.signed_on:%d %B}, it was still not connected after "
        f"{PATIENCE_WORKING_DAYS} working days"
        + (f": held up at {step.department.lower()}." if step else "."),
        _drill(onboarding),
    )  # fmt: skip


# --- The heads' decisions ------------------------------------------------------------------


def _waiting_on(game: Game, number: int, code: str) -> tuple[Onboarding, OnboardingStep]:
    onboarding = Onboarding.objects.filter(game=game, number=number).first()
    if onboarding is None:
        raise OnboardingError(f"There is no onboarding {number}")
    step = current(onboarding)
    if onboarding.status != "IN_PROGRESS" or step is None or step.code != code:
        where = step.department.lower() if step else onboarding.status.lower()
        raise OnboardingError(f"Onboarding {number} is not at this step (it is at {where})")
    return onboarding, step


def decide_check(
    game: Game, number: int, decision: str, tick: int, at: datetime, add: Any
) -> Onboarding:
    """The Head of Compliance approves, approves under a warning, or refuses."""
    if decision not in (APPROVE, WARN, REFUSE):
        raise OnboardingError(f"The decision is {APPROVE}, {WARN} or {REFUSE}")
    onboarding, step = _waiting_on(game, number, "SUBSCRIBER_CHECK")
    today = at.date()
    if decision == REFUSE:
        _done(step, today, tick, "Head of Compliance", "Refused")
        onboarding.status, onboarding.ended_on = "REFUSED", today
        onboarding.save(update_fields=["status", "ended_on"])
        onboarding.steps.exclude(status=DONE).update(status=CANCELLED)
        return onboarding
    if decision == WARN:
        duties.sanction(game, onboarding.lender_code, duties.WARNING, tick)
    _done(
        step, today, tick, "Head of Compliance",
        "Approved under a warning" if decision == WARN else "Approved",
    )  # fmt: skip
    _ready(game, onboarding, today, add)
    return onboarding


def set_up_billing(game: Game, number: int, tick: int, at: datetime, add: Any) -> Onboarding:
    """The Head of Finance has checked the terms: billing starts."""
    onboarding, step = _waiting_on(game, number, "BILLING")
    _set_up(onboarding, step, at.date(), tick, "Head of Finance")
    _ready(game, onboarding, at.date(), add)
    return onboarding


def unbilled(game: Game, code: str) -> Decimal:
    """Usage the subscriber has had that waits for its billing to be set up."""
    total = UsageRecord.objects.filter(
        organization=game.organization,
        subscriber__subscriber_code=code,
        subscriber__billing_ready=False,
        invoiced=False,
    ).aggregate(s=Sum(F("unit_price") * F("quantity")))["s"]
    return total or Decimal("0")
