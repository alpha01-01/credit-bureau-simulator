"""Sales: proposals to lenders that do not subscribe yet (P2.9; Document 07, Section 6.7).

ASSUMPTION A-063 (until reference R8 gives real pricing, sales cycles and win rates):

* The bureau may send a proposal, at a price per report it chooses, to any lender
  in the market that does not subscribe. One proposal per lender at a time, and
  not again within 90 days of a refusal.
* The lender answers three working days later. It accepts with chance
  (subscriber reputation / 100) x (list price / offered price)^2, kept within
  5%-95%: a bureau known for finding the right people, at a fair price, wins.
* A lender that accepts subscribes from the next working day on a one-year
  contract at the offered price; its applications from that day are checked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.bureau.providers.models import Institution
from apps.commercial.models import Contract, Product, Subscriber
from apps.standards.calendar import next_working_day
from apps.world.generation.rng import stream
from apps.world.models import Lender, LoanApplication
from apps.world.provider_files import month_end as period_end

from .clock import DAY_START, TICKS_PER_DAY
from .demand import REFERENCE_PRICE
from .models import EventType, Game, Proposal, ScheduledEvent, SubscriberView
from .reputation import reputation

ANSWER_DAYS = 3
COOL_OFF_DAYS = 90
MIN_P, MAX_P = 0.05, 0.95
PRODUCT = "CONSUMER_REPORT"


class SalesError(Exception):
    pass


def prospects(game: Game) -> list[Lender]:
    """Lenders in the market that do not subscribe now."""
    subscribing = set(
        Subscriber.objects.filter(organization=game.organization, is_active=True).values_list(
            "subscriber_code", flat=True
        )
    )
    return [
        lender
        for lender in Lender.objects.filter(world=game.world).order_by("seq_no")
        if lender.code not in subscribing
    ]


def p_accept(subscriber_score: float, price: Decimal) -> float:
    ratio = float(REFERENCE_PRICE / price) if price > 0 else 1.0
    return max(MIN_P, min(MAX_P, subscriber_score / 100 * ratio**2))


def propose(game: Game, lender_code: str, price: Decimal, tick: int, at: datetime) -> Proposal:
    if price <= 0:
        raise SalesError("The price must be more than zero")
    if lender_code not in {lender.code for lender in prospects(game)}:
        raise SalesError(f"{lender_code} is not a lender we could sign")
    proposals = Proposal.objects.filter(game=game, lender_code=lender_code)
    if proposals.filter(status="PENDING").exists():
        raise SalesError(f"A proposal to {lender_code} is waiting for an answer")
    refused = proposals.filter(status="DECLINED").order_by("-answered_at").first()
    if refused and refused.answered_at and at - refused.answered_at < timedelta(COOL_OFF_DAYS):
        raise SalesError(f"{lender_code} refused within the last {COOL_OFF_DAYS} days")
    number = (Proposal.objects.filter(game=game).count()) + 1
    proposal = Proposal.objects.create(
        game=game,
        number=number,
        lender_code=lender_code,
        unit_price=price.quantize(Decimal("0.01")),
        sent_at=at,
    )
    from .engine import _next_sequence

    # The answer comes at the same time of day, three working days on.
    ScheduledEvent.objects.create(
        game=game,
        event_type=EventType.PROPOSAL_ANSWERED,
        due_tick=tick + ANSWER_DAYS * TICKS_PER_DAY,
        sequence=_next_sequence(game),
        payload={"proposal": number},
    )
    return proposal


def answer(game: Game, payload: dict[str, Any], at: datetime, add: Any) -> Proposal:
    proposal = Proposal.objects.get(game=game, number=int(payload["proposal"]))
    lender = Lender.objects.get(world=game.world, code=proposal.lender_code)
    score = float(reputation(game, at)["subscribers"]["score"])
    rng = stream(game.world.seed, f"proposal:{proposal.lender_code}:{proposal.number}")
    accepted = rng.random() < p_accept(score, proposal.unit_price)
    proposal.status = "ACCEPTED" if accepted else "DECLINED"
    proposal.answered_at = at
    proposal.save(update_fields=["status", "answered_at"])
    if accepted:
        start = next_working_day(at.date() + timedelta(days=1))
        sign(game, lender, proposal.unit_price, start)
        add(
            "PROPOSAL_ACCEPTED", "INFO",
            f"{lender.name} has signed up at GHS {proposal.unit_price} a report",
            f"It subscribes from {start:%d %B}; its applications reach us from next month.",
            {"screen": "sales", "params": {}},
        )  # fmt: skip
    else:
        add(
            "PROPOSAL_DECLINED", "WARNING",
            f"{lender.name} declined our proposal",
            f"Price offered GHS {proposal.unit_price}; our subscriber reputation was {score:.0f}.",
            {"screen": "sales", "params": {}},
        )  # fmt: skip
    return proposal


def sign(game: Game, lender: Lender, price: Decimal, start: date) -> Subscriber:
    """Make the lender a subscriber from ``start``; its applications from then are checked."""
    product = Product.objects.get(organization=game.organization, product_code=PRODUCT)
    subscriber, _ = Subscriber.objects.update_or_create(
        organization=game.organization,
        subscriber_code=lender.code,
        defaults={
            "subscriber_name": lender.name,
            "since": start,
            "is_active": True,
            "institution": Institution.objects.filter(
                organization=game.organization, institution_code=lender.code
            ).first(),
        },
    )
    Contract.objects.create(
        subscriber=subscriber, product=product, unit_price=price, start_date=start
    )
    SubscriberView.objects.get_or_create(game=game, subscriber_code=lender.code)
    # The rest of this month's applications (later months are scheduled with the others).
    from .engine import _next_sequence, calendar
    from .enquiries import schedule_applications

    period = period_end(start.year, start.month)
    if LoanApplication.objects.filter(world=game.world, period=period).exists():
        cal = calendar(game)
        schedule_applications(
            game, cal, cal.tick_at(datetime.combine(start, DAY_START, tzinfo=UTC)), period,
            _next_sequence(game), codes=[lender.code], since=start,
        )  # fmt: skip
    return subscriber
