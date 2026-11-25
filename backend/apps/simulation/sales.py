"""Sales: winning lenders that do not subscribe yet (P2.9, P3.9; Document 07, Section 6.7).

ASSUMPTION A-063 (until reference R8 gives real pricing, sales cycles and win rates):

* The bureau may send a proposal to any lender in the market that does not subscribe.
  One proposal per lender at a time, and not again within 90 days of a refusal.
* The lender answers three working days later. It accepts with chance
  (subscriber reputation / 100) x fit^2, kept within 5%-95%: a bureau known for
  finding the right people, on terms that suit the lender, wins.

ASSUMPTION A-079 (P3.9, the negotiation):

* Each lender has needs of its own, hidden until Sales researches it: what it values
  most (price, service or flexibility), its monthly volume, and how much it would pay
  (90%-110% of the list price).
* Research takes two working days. A meeting, once the research is in, takes two more:
  the lender says what it would pay, and for 60 days its answers lean our way (x1.15).
* A proposal sets the price, the term (12 or 24 months), the service level (premium
  gives a credit for a month of long downtime), a monthly minimum and a volume
  discount. Fit = what the lender would pay x how the terms suit it / the price it
  would actually pay per report at its volume. Premium is worth 15% more to a lender
  that values service; a 24-month term or a minimum is worth 15% / 10% less to one
  that values flexibility, and a 24-month term 5% more to one that values price.
* A lender that declines a price it finds too high (fit 0.8-1) names the price it
  would sign at. Sales may accept that within ten working days.
* An accepted proposal starts the new subscriber's onboarding (``onboarding``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

from apps.bureau.providers.models import Institution
from apps.commercial.models import Contract, Product, ServiceLevel, Subscriber
from apps.world.generation.rng import stream
from apps.world.models import Lender, Loan, LoanApplication
from apps.world.provider_files import month_end as period_end

from .clock import DAY_START, TICKS_PER_DAY
from .compliance import add_working_days
from .demand import REFERENCE_PRICE
from .models import (
    EventType,
    Game,
    LenderResearch,
    Onboarding,
    Proposal,
    ScheduledEvent,
    SubscriberView,
)
from .reputation import reputation

ANSWER_DAYS = 3
COOL_OFF_DAYS = 90
MIN_P, MAX_P = 0.05, 0.95
PRODUCT = "CONSUMER_REPORT"
RESEARCH_DAYS = MEETING_DAYS = 2  # working days
MEETING_BONUS, MEETING_LASTS_DAYS = 1.15, 60
APPETITE = (0.9, 1.1)
PRIORITIES = ("PRICE", "SERVICE", "FLEXIBILITY")
PRIORITY_WORDS = {
    "PRICE": "the price above all; a longer term is welcome if it keeps the price down",
    "SERVICE": "reliable service; it would pay more for a premium service level",
    "FLEXIBILITY": "flexibility; it dislikes long terms and monthly minimums",
}
COUNTER_FROM, COUNTER_DAYS = 0.8, 10
TERMS_MONTHS = (12, 24)
MAX_DISCOUNT = Decimal("0.30")


class SalesError(Exception):
    pass


@dataclass(frozen=True)
class Terms:
    """What a proposal offers. The defaults are the standard price list's."""

    price: Decimal
    term_months: int = 12
    service_level: str = ServiceLevel.STANDARD
    monthly_minimum: Decimal = Decimal("0")
    discount_threshold: int | None = None
    discount_rate: Decimal = Decimal("0")

    def check(self) -> Terms:
        if self.price <= 0:
            raise SalesError("The price must be more than zero")
        if self.term_months not in TERMS_MONTHS:
            raise SalesError("The term is 12 or 24 months")
        if self.service_level not in ServiceLevel.values:
            raise SalesError("The service level is STANDARD or PREMIUM")
        if self.monthly_minimum < 0:
            raise SalesError("The monthly minimum cannot be negative")
        if not Decimal("0") <= self.discount_rate <= MAX_DISCOUNT:
            raise SalesError(f"The volume discount is between 0 and {MAX_DISCOUNT:.0%}")
        if self.discount_rate and (self.discount_threshold is None or self.discount_threshold < 0):
            raise SalesError("A volume discount needs the number of reports it starts above")
        return replace(
            self,
            price=self.price.quantize(Decimal("0.01")),
            monthly_minimum=self.monthly_minimum.quantize(Decimal("0.01")),
            discount_rate=self.discount_rate.quantize(Decimal("0.0001")),
            discount_threshold=self.discount_threshold if self.discount_rate else None,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "price": str(self.price),
            "term_months": self.term_months,
            "service_level": self.service_level,
            "monthly_minimum": str(self.monthly_minimum),
            "discount_threshold": self.discount_threshold,
            "discount_rate": str(self.discount_rate),
        }

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> Terms:
        threshold = p.get("discount_threshold")
        return cls(
            price=Decimal(str(p["price"])),
            term_months=int(p.get("term_months", 12)),
            service_level=str(p.get("service_level", ServiceLevel.STANDARD)),
            monthly_minimum=Decimal(str(p.get("monthly_minimum", "0"))),
            discount_threshold=None if threshold is None or threshold == "" else int(threshold),
            discount_rate=Decimal(str(p.get("discount_rate", "0"))),
        )

    @classmethod
    def of(cls, proposal: Proposal) -> Terms:
        return cls(
            proposal.unit_price, proposal.term_months, proposal.service_level,
            proposal.monthly_minimum, proposal.discount_threshold, proposal.discount_rate,
        )  # fmt: skip


# --- The market ---------------------------------------------------------------------------


def prospects(game: Game) -> list[Lender]:
    """Lenders in the market that do not subscribe now, nor are being taken on."""
    busy = set(
        Subscriber.objects.filter(organization=game.organization, is_active=True).values_list(
            "subscriber_code", flat=True
        )
    ) | set(
        Onboarding.objects.filter(game=game, status="IN_PROGRESS").values_list(
            "lender_code", flat=True
        )
    )
    return [
        lender
        for lender in Lender.objects.filter(world=game.world).order_by("seq_no")
        if lender.code not in busy
    ]


def needs(game: Game, code: str) -> dict[str, Any]:
    """The lender's hidden needs: what it values most and how much it would pay."""
    rng = stream(game.world.seed, f"lender-needs:{code}")
    priority = PRIORITIES[int(rng.integers(len(PRIORITIES)))]
    appetite = round(float(rng.uniform(*APPETITE)), 4)
    return {"priority": priority, "appetite": appetite}


def monthly_volume(game: Game, code: str) -> int:
    """Its loans a month in the year before play: about how many reports it would buy."""
    since = game.clock_start - timedelta(days=365)
    loans = Loan.objects.filter(
        lender__world=game.world,
        lender__code=code,
        disbursement_date__gte=since,
        disbursement_date__lt=game.clock_start,
    ).count()
    return max(1, round(loans / 12))


def _worth(priority: str, terms: Terms) -> float:
    """How the terms suit a lender that values ``priority`` (1 = indifferent)."""
    worth = 1.0
    if priority == "SERVICE" and terms.service_level == ServiceLevel.PREMIUM:
        worth *= 1.15
    if priority == "FLEXIBILITY":
        worth *= 0.85 if terms.term_months > 12 else 1.0
        worth *= 0.9 if terms.monthly_minimum > 0 else 1.0
    if priority == "PRICE" and terms.term_months > 12:
        worth *= 1.05
    return worth


def effective_price(terms: Terms, volume: int) -> Decimal:
    """What a report would cost the lender at its volume: discount and minimum included."""
    bill = terms.price * volume
    if terms.discount_rate and terms.discount_threshold is not None:
        bill -= terms.price * terms.discount_rate * max(0, volume - terms.discount_threshold)
    bill = max(bill, terms.monthly_minimum)
    return bill / max(volume, 1)


def fit(game: Game, code: str, terms: Terms, volume: int | None = None) -> float:
    """Above 1, the terms are better than the lender needs; below, worse."""
    wants = needs(game, code)
    paid = effective_price(terms, volume if volume is not None else monthly_volume(game, code))
    if paid <= 0:
        return 2.0
    appetite = float(wants["appetite"])
    return float(REFERENCE_PRICE) * appetite * _worth(str(wants["priority"]), terms) / float(paid)


def p_accept(subscriber_score: float, terms_fit: float, met: bool = False) -> float:
    bonus = MEETING_BONUS if met else 1.0
    return max(MIN_P, min(MAX_P, subscriber_score / 100 * terms_fit**2 * bonus))


# --- Research and meetings ----------------------------------------------------------------


def _lender(game: Game, code: str) -> Lender:
    lender = Lender.objects.filter(world=game.world, code=code).first()
    if lender is None:
        raise SalesError(f"There is no lender {code}")
    return lender


def research(game: Game, code: str, tick: int, today: date) -> LenderResearch:
    """Sales looks into a lender's needs; the findings come in two working days later."""
    lender = _lender(game, code)
    if LenderResearch.objects.filter(game=game, lender_code=code).exists():
        raise SalesError(f"{lender.name} has been researched already")
    wants = needs(game, code)
    volume = monthly_volume(game, code)
    rounded = max(10, round(volume / 10) * 10)
    return LenderResearch.objects.create(
        game=game,
        lender_code=code,
        requested_tick=tick,
        ready_on=add_working_days(today, RESEARCH_DAYS),
        findings={
            "volume": rounded,
            "priority": wants["priority"],
            "values": PRIORITY_WORDS[wants["priority"]],
            "type": lender.lender_type,
        },
    )


def meet(game: Game, code: str, tick: int, today: date) -> LenderResearch:
    """A meeting with the lender, once the research is in: it says what it would pay."""
    lender = _lender(game, code)
    found = LenderResearch.objects.filter(game=game, lender_code=code).first()
    if found is None or found.ready_on > today:
        raise SalesError(f"Research {lender.name} first: a meeting needs to know its needs")
    if found.meeting_on is not None and found.meeting_on >= today:
        raise SalesError(f"A meeting with {lender.name} is already arranged")
    wants = needs(game, code)
    # Rounded down to the half cedi, as a buyer would put it.
    stated = (REFERENCE_PRICE * Decimal(str(wants["appetite"])) * 2).to_integral_value(
        rounding=ROUND_DOWN
    ) / 2
    stated = stated.quantize(Decimal("0.01"))
    found.meeting_requested_tick = tick
    found.meeting_on = add_working_days(today, MEETING_DAYS)
    found.meeting_reported = False
    found.meeting_notes = {
        "price": str(stated),
        "said": f"{lender.name} would sign on standard terms at about GHS {stated} a report, "
        f"and cares most about {PRIORITY_WORDS[wants['priority']]}.",
    }
    found.save()
    return found


def met_recently(game: Game, code: str, on: date) -> bool:
    found = LenderResearch.objects.filter(game=game, lender_code=code).first()
    return bool(
        found
        and found.meeting_on is not None
        and found.meeting_on <= on < found.meeting_on + timedelta(days=MEETING_LASTS_DAYS)
    )


def morning(game: Game, day: date, add: Any) -> None:
    """Research and meetings that came in today."""
    for found in LenderResearch.objects.filter(game=game, reported=False, ready_on__lte=day):
        found.reported = True
        found.save(update_fields=["reported"])
        add(
            "LENDER_RESEARCHED", "INFO", f"Research on {found.lender_code} is in",
            f"About {found.findings['volume']} applications a month; it values "
            f"{found.findings['values']}.",
            {"screen": "sales", "params": {}},
        )  # fmt: skip
    for found in LenderResearch.objects.filter(
        game=game, meeting_reported=False, meeting_on__lte=day
    ):
        found.meeting_reported = True
        found.save(update_fields=["meeting_reported"])
        add(
            "LENDER_MET", "INFO", f"We met {found.lender_code}", found.meeting_notes["said"],
            {"screen": "sales", "params": {}},
        )  # fmt: skip


# --- Proposals ----------------------------------------------------------------------------


def propose(game: Game, lender_code: str, terms: Terms, tick: int, at: datetime) -> Proposal:
    terms = terms.check()
    if not Product.objects.filter(organization=game.organization, product_code=PRODUCT).exists():
        raise SalesError("There is no report to sell yet: develop the consumer credit report first")
    if lender_code not in {lender.code for lender in prospects(game)}:
        raise SalesError(f"{lender_code} is not a lender we could sign")
    proposals = Proposal.objects.filter(game=game, lender_code=lender_code)
    if proposals.filter(status="PENDING").exists():
        raise SalesError(f"A proposal to {lender_code} is waiting for an answer")
    refused = proposals.filter(status="DECLINED").order_by("-answered_at").first()
    if refused and refused.answered_at and at - refused.answered_at < timedelta(COOL_OFF_DAYS):
        raise SalesError(f"{lender_code} refused within the last {COOL_OFF_DAYS} days")
    left = (
        Onboarding.objects.filter(game=game, lender_code=lender_code, ended_on__isnull=False)
        .exclude(status="COMPLETE")
        .order_by("-ended_on")
        .first()
    )
    if left and left.ended_on and at.date() - left.ended_on < timedelta(COOL_OFF_DAYS):
        raise SalesError(f"{lender_code} walked away within the last {COOL_OFF_DAYS} days")
    proposals.filter(status="COUNTERED").update(status="LAPSED")  # a new offer replaces it
    number = (Proposal.objects.filter(game=game).count()) + 1
    proposal = Proposal.objects.create(
        game=game,
        number=number,
        lender_code=lender_code,
        unit_price=terms.price,
        sent_at=at,
        term_months=terms.term_months,
        service_level=terms.service_level,
        monthly_minimum=terms.monthly_minimum,
        discount_threshold=terms.discount_threshold,
        discount_rate=terms.discount_rate,
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
    from . import onboarding

    proposal = Proposal.objects.get(game=game, number=int(payload["proposal"]))
    lender = Lender.objects.get(world=game.world, code=proposal.lender_code)
    score = float(reputation(game, at)["subscribers"]["score"])
    terms = Terms.of(proposal)
    terms_fit = fit(game, lender.code, terms)
    met = met_recently(game, lender.code, at.date())
    rng = stream(game.world.seed, f"proposal:{proposal.lender_code}:{proposal.number}")
    accepted = rng.random() < p_accept(score, terms_fit, met)
    proposal.answered_at = at
    if accepted:
        proposal.status = "ACCEPTED"
        proposal.save(update_fields=["status", "answered_at"])
        onboarding.start(game, proposal, proposal.unit_price, at, add)
        add(
            "PROPOSAL_ACCEPTED", "INFO",
            f"{lender.name} has signed up at GHS {proposal.unit_price} a report",
            "Its onboarding begins: Compliance checks it, IT connects it, Finance sets up "
            "its billing and Support welcomes it.",
            {"screen": "onboarding", "params": {}},
        )  # fmt: skip
    elif COUNTER_FROM <= terms_fit < 1:
        proposal.status = "COUNTERED"
        proposal.counter_price = (proposal.unit_price * Decimal(str(terms_fit))).quantize(
            Decimal("0.10"), rounding=ROUND_DOWN
        )
        proposal.save(update_fields=["status", "answered_at", "counter_price"])
        add(
            "PROPOSAL_COUNTERED", "WARNING",
            f"{lender.name} would sign at GHS {proposal.counter_price} a report",
            f"It found GHS {proposal.unit_price} too high on these terms. Accept within "
            f"{COUNTER_DAYS} working days, or send a new proposal.",
            {"screen": "sales", "params": {}},
        )  # fmt: skip
    else:
        proposal.status = "DECLINED"
        proposal.save(update_fields=["status", "answered_at"])
        add(
            "PROPOSAL_DECLINED", "WARNING",
            f"{lender.name} declined our proposal",
            f"Price offered GHS {proposal.unit_price}; our subscriber reputation was {score:.0f}.",
            {"screen": "sales", "params": {}},
        )  # fmt: skip
    return proposal


def accept_counter(game: Game, number: int, at: datetime, add: Any) -> Proposal:
    """Take the lender at its word: it signs at the price it named."""
    from . import onboarding

    proposal = Proposal.objects.filter(game=game, number=number).first()
    if proposal is None or proposal.status != "COUNTERED" or proposal.counter_price is None:
        raise SalesError(f"Proposal {number} has no counter-offer to accept")
    answered = proposal.answered_at.date() if proposal.answered_at else at.date()
    if at.date() > add_working_days(answered, COUNTER_DAYS):
        raise SalesError(f"The counter-offer lapsed after {COUNTER_DAYS} working days")
    if proposal.lender_code not in {lender.code for lender in prospects(game)}:
        raise SalesError(f"{proposal.lender_code} is no longer a lender we could sign")
    proposal.status = "ACCEPTED"
    proposal.save(update_fields=["status"])
    onboarding.start(game, proposal, proposal.counter_price, at, add)
    return proposal


# --- Going live ---------------------------------------------------------------------------


def sign(
    game: Game,
    lender: Lender,
    price: Decimal,
    start: date,
    terms: Terms | None = None,
    billing_ready: bool = True,
) -> Subscriber:
    """Make the lender a subscriber from ``start``; its applications from then are checked."""
    terms = terms or Terms(price)
    product = Product.objects.get(organization=game.organization, product_code=PRODUCT)
    subscriber, _ = Subscriber.objects.update_or_create(
        organization=game.organization,
        subscriber_code=lender.code,
        defaults={
            "subscriber_name": lender.name,
            "since": start,
            "is_active": True,
            "billing_ready": billing_ready,
            "institution": Institution.objects.filter(
                organization=game.organization, institution_code=lender.code
            ).first(),
        },
    )
    year, month = divmod(start.month - 1 + terms.term_months, 12)
    end = start.replace(year=start.year + year, month=month + 1, day=1) + timedelta(
        days=start.day - 2
    )  # the day before the same date, ``term_months`` on
    Contract.objects.create(
        subscriber=subscriber,
        product=product,
        unit_price=price,
        start_date=start,
        end_date=end,
        term_months=terms.term_months,
        service_level=terms.service_level,
        monthly_minimum=terms.monthly_minimum,
        discount_threshold=terms.discount_threshold,
        discount_rate=terms.discount_rate,
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
