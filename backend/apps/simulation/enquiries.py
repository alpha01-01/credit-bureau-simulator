"""Credit applications in the world become (or do not become) bureau enquiries (roadmap S6).

For every application to a lender that subscribes, the lender decides whether
to check the bureau (demand model). An enquiry is billed, and judged against
the world: should the bureau have found the applicant, did it, and was the
report about the right person? Each subscriber's view of the bureau moves
with its own experience, which drives its future demand.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any

from django.db.models import Q

from apps.bureau.core.models import Enquiry, IdentifierType
from apps.bureau.providers.models import Institution
from apps.bureau.reports.enquiries import BUSINESS_REPORT, enquire
from apps.commercial.models import Contract, Product, Subscriber, UsageRecord
from apps.commercial.usage import active_contract, record_usage
from apps.standards.calendar import next_working_day
from apps.world.generation.rng import stream
from apps.world.models import Lender, Loan, LoanApplication

from . import compliance, duties, it, lending, products, scoreproduct
from .clock import DAY_START, TICK_MINUTES, TICKS_PER_DAY, Calendar
from .consequences import trace
from .demand import REFERENCE_PRICE, p_enquire, update_perception
from .feed import AT_RISK, RECOVERED, Feed
from .judgement import customer_borrower
from .models import EnquiryJudgement, EventType, Game, ScheduledEvent, SubscriberView

PRODUCT = "CONSUMER_REPORT"
# Providers that also subscribe at the start of the Established scenario (Document 07, 7.4).
STARTING_SUBSCRIBERS = ("ATB", "MRB", "UNS")


def set_up_commercial(game: Game, since: date) -> None:
    product = Product.objects.create(
        organization=game.organization,
        product_code=PRODUCT,
        product_name="Consumer credit report",
        list_price=REFERENCE_PRICE,
    )
    for code in STARTING_SUBSCRIBERS:
        lender = Lender.objects.get(world=game.world, code=code)
        subscriber = Subscriber.objects.create(
            organization=game.organization,
            subscriber_code=code,
            subscriber_name=lender.name,
            institution=Institution.objects.filter(
                organization=game.organization, institution_code=code
            ).first(),
            since=since,
        )
        Contract.objects.create(
            subscriber=subscriber, product=product, unit_price=product.list_price, start_date=since
        )
        SubscriberView.objects.create(game=game, subscriber_code=code)


def schedule_applications(
    game: Game,
    cal: Calendar,
    tick: int,
    period: date,
    sequence: int,
    codes: list[str] | None = None,
    since: date | None = None,
) -> int:
    """Schedule this month's applications to subscribing lenders. Returns the next sequence.

    ``codes`` and ``since`` limit it to some lenders' applications made on or after a day
    (a lender that signs up during the month, P2.9).
    """
    if codes is None:
        codes = list(
            Subscriber.objects.filter(organization=game.organization, is_active=True)
            .order_by("subscriber_code")
            .values_list("subscriber_code", flat=True)
        )
    applications = LoanApplication.objects.filter(
        world=game.world, period=period, lender__code__in=codes
    ).order_by("lender__code", "seq")
    if since is not None:
        applications = applications.filter(application_date__gte=since)
    events = []
    for application in applications.select_related("lender"):
        code = application.lender.code
        key = f"{code}:{period:%Y%m}:{application.seq}"
        slot = int(stream(game.world.seed, f"application-slot:{key}").integers(TICKS_PER_DAY))
        moment = datetime.combine(
            next_working_day(application.application_date), DAY_START, tzinfo=UTC
        ) + timedelta(minutes=TICK_MINUTES * slot)
        events.append(
            ScheduledEvent(
                game=game,
                event_type=EventType.CREDIT_APPLICATION,
                due_tick=max(cal.tick_at(moment), tick),
                sequence=sequence,
                payload={"lender": code, "period": period.isoformat(), "seq": application.seq},
            )
        )
        sequence += 1
    ScheduledEvent.objects.bulk_create(events, batch_size=2000)
    return sequence


VIEWS, APPLICATIONS, WRITES = "subscriber-views", "applications", "tick-writes"


def prefetch_applications(
    game: Game, payloads: list[dict[str, object]], memo: dict[Any, Any]
) -> None:
    """Load the tick's applications in one query (P4.0: a query each was most of a month)."""
    keys = {
        (str(p["lender"]), date.fromisoformat(str(p["period"])), int(str(p["seq"])))
        for p in payloads
    }
    if not keys:
        return
    match = Q()
    for code, period, seq in keys:
        match |= Q(lender__code=code, period=period, seq=seq)
    found = memo.setdefault(APPLICATIONS, {})
    for application in (
        LoanApplication.objects.filter(world=game.world)
        .filter(match)
        .select_related("lender", "person", "business")
    ):
        found[(application.lender.code, application.period, application.seq)] = application


def save_views(memo: dict[Any, Any]) -> None:
    """Save what the tick's applications wrote (P4.0: once a tick): the usage billed and
    the judgements, which nothing reads until the tick's events are done, and the
    subscribers' views they changed."""
    writes: dict[type, list[Any]] = memo.pop(WRITES, {})
    for model in (UsageRecord, EnquiryJudgement):
        if writes.get(model):
            model.objects.bulk_create(writes[model], batch_size=1000)
    views = memo.pop(VIEWS, {})
    if views:
        SubscriberView.objects.bulk_update(
            [views[code] for code in sorted(views)],
            ["perceived_value", "opportunities", "enquiries", "hits", "wrong_person", "at_risk"],
        )


def handle_application(
    game: Game,
    payload: dict[str, object],
    at: datetime,
    memo: dict[object, Any] | None = None,
    feed: Feed | None = None,
) -> Enquiry | None:
    """One loan application: the lender may check the bureau, and judges what it gets back.

    ``memo`` holds lookups shared by the applications of one tick, which cannot change
    while the tick runs, and the subscribers' views, which the caller saves with
    ``save_views`` once the tick's applications are done. Without a ``memo``, the view
    is saved here.
    """
    if memo is None:
        memo = {}
        try:
            return handle_application(game, payload, at, memo, feed)
        finally:
            save_views(memo)
    code = str(payload["lender"])
    period = date.fromisoformat(str(payload["period"]))
    seq = int(str(payload["seq"]))
    application = memo.get(APPLICATIONS, {}).get((code, period, seq))
    if application is None:
        application = LoanApplication.objects.select_related("person", "business").get(
            world=game.world, lender__code=code, period=period, seq=seq
        )
    views = memo.setdefault(VIEWS, {})
    if code not in views:
        views[code] = SubscriberView.objects.select_for_update().get(
            game=game, subscriber_code=code
        )
    view = views[code]
    key = ("subscriber", code, at.date())
    if key not in memo:
        subscriber = Subscriber.objects.get(organization=game.organization, subscriber_code=code)
        product = Product.objects.get(organization=game.organization, product_code=PRODUCT)
        memo[key] = (subscriber, product, active_contract(subscriber.pk, product, at.date()))
    subscriber, product, contract = memo[key]
    price = contract.unit_price
    if application.business is not None:  # the business report, once developed (P3.11)
        business = ("business-report", code, at.date())
        if business not in memo:
            memo[business] = None
            if products.launched(game, BUSINESS_REPORT):
                item = products.sale_item(game, BUSINESS_REPORT)
                memo[business] = (item, scoreproduct.contract(subscriber, item, at.date()))
        if memo[business] is not None:
            product, contract = memo[business]
            # Lenders weigh its price against its list price, as they do the report's.
            price = contract.unit_price * REFERENCE_PRICE / product.list_price

    view.opportunities += 1
    tick = feed.tick if feed else game.current_tick
    blocked = ("subscriber-suspended", code, tick)
    if blocked not in memo:
        memo[blocked] = duties.subscriber_suspended(game, code, tick)
    if ("bureau-suspended", tick) not in memo:
        memo[("bureau-suspended", tick)] = compliance.suspended(game)
    if memo[("bureau-suspended", tick)] or it.systems_down(game, tick, memo) or memo[blocked]:
        # A suspended bureau may not serve enquiries (P2.7); nor can one whose systems
        # are down (P2.9); nor a subscriber the bureau has suspended (P3.7). The lender
        # lends without a report.
        lending.decide(game, application, code, None, tick)
        return None
    rng = stream(game.world.seed, f"enquire:{code}:{period:%Y%m}:{seq}")
    if rng.random() >= p_enquire(view.perceived_value, price):
        lending.decide(game, application, code, None, tick)  # lent without checking
        return None

    if application.person is not None:
        id_type, id_value = IdentifierType.GHANA_CARD, application.person.ghana_card
        name = f"{application.person.first_name} {application.person.last_name}"
        borrower = ("person", application.person.pk)
    else:
        assert application.business is not None  # noqa: S101 - an application has one applicant
        id_type = IdentifierType.BUSINESS_REGISTRATION
        id_value = application.business.registration_number
        name = application.business.registered_name
        borrower = ("business", application.business.pk)

    with_score = product.product_code == PRODUCT and scoreproduct.buys_score(
        game, view, code, period, seq
    )
    enquiry = enquire(
        game.organization,
        subscriber,
        product.product_code,
        "NEW_CREDIT",
        f"CONSENT-{code}-{period:%Y%m}-{seq:05d}",
        id_type,
        id_value,
        name,
        at,
        include_score=with_score,
        memo=memo,
    )
    writes = memo.setdefault(WRITES, {})
    writes.setdefault(UsageRecord, []).append(record_usage(enquiry, product, contract, save=False))
    if with_score and (enquiry.report.get("score") or {}).get("score") is not None:
        # The score is billed only when one is delivered (P3.6).
        item = scoreproduct.product(game, scoreproduct.SCORE)
        terms = scoreproduct.contract(subscriber, item, at.date())
        writes[UsageRecord].append(UsageRecord(
            organization=game.organization, subscriber=subscriber, contract=terms, enquiry=enquiry,
            product=item, quantity=1, unit_price=terms.unit_price, usage_at=at,
        ))  # fmt: skip

    hit = enquiry.customer_id is not None
    correct = (
        (customer_borrower(game, enquiry.customer_id) == borrower) if enquiry.customer_id else None
    )
    outcome = "NO_HIT" if not hit else ("CORRECT_HIT" if correct else "WRONG_PERSON")
    writes.setdefault(EnquiryJudgement, []).append(
        EnquiryJudgement(
            game=game,
            enquiry=enquiry,
            application=application,
            should_hit=_has_reported_credit(game, borrower, period, memo),
            hit=hit,
            correct_person=correct,
            outcome=outcome,
            grounds_held=duties.grounds_held(game, code, period, seq, memo),
        )
    )
    duties.retention_breach(game, enquiry, at, feed.add if feed is not None else duties.quietly)
    view.enquiries += 1
    view.hits += int(hit)
    view.wrong_person += int(outcome == "WRONG_PERSON")
    view.perceived_value = round(update_perception(view.perceived_value, outcome), 6)
    lending.decide(game, application, code, enquiry.report, tick)  # acts on the report (P2.8)
    if hit:
        chains = trace(game, enquiry, borrower, code, tick, at)
        compliance.maybe_dispute(game, enquiry, name, chains, tick)
    if feed is not None:
        if outcome == "WRONG_PERSON":
            feed.wrong_person(subscriber.subscriber_name, enquiry.enquiry_reference)
        if not view.at_risk and view.perceived_value < AT_RISK:
            view.at_risk = True
            feed.subscriber_mood(subscriber.subscriber_name, at_risk=True)
        elif view.at_risk and view.perceived_value > RECOVERED:
            view.at_risk = False
            feed.subscriber_mood(subscriber.subscriber_name, at_risk=False)
    return enquiry


def _has_reported_credit(
    game: Game, borrower: tuple[str, int], period: date, memo: dict[object, Any]
) -> bool:
    """Does the applicant have a loan, before this month, with a lender reporting to the bureau?"""
    if "providers" not in memo:
        memo["providers"] = tuple(
            Institution.objects.filter(organization=game.organization)
            .order_by("institution_code")
            .values_list("institution_code", flat=True)
        )
    providers = memo["providers"]
    people, businesses = _reported_borrowers(game.world_id, providers, period.replace(day=1))
    return borrower[1] in (people if borrower[0] == "person" else businesses)


# The answer is the same for every application in a month, so it is worked out once (P2.1).
@lru_cache(maxsize=8)
def _reported_borrowers(
    world_id: int, providers: tuple[str, ...], before: date
) -> tuple[frozenset[int], frozenset[int]]:
    loans = Loan.objects.filter(
        world_id=world_id, lender__code__in=providers, disbursement_date__lt=before
    ).values_list("customer__person_id", "customer__business_id")
    people: set[int] = set()
    businesses: set[int] = set()
    for person, business in loans.iterator(chunk_size=20_000):
        if person is not None:
            people.add(person)
        else:
            businesses.add(business)
    return frozenset(people), frozenset(businesses)
