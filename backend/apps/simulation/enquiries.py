"""Credit applications in the world become (or do not become) bureau enquiries (roadmap S6).

For every application to a lender that subscribes, the lender decides whether
to check the bureau (demand model). An enquiry is billed, and judged against
the world: should the bureau have found the applicant, did it, and was the
report about the right person? Each subscriber's view of the bureau moves
with its own experience, which drives its future demand.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from apps.bureau.core.models import Enquiry, IdentifierType
from apps.bureau.providers.models import Institution
from apps.bureau.reports.enquiries import enquire
from apps.commercial.models import Contract, Product, Subscriber
from apps.commercial.usage import active_contract, record_usage
from apps.standards.calendar import next_working_day
from apps.world.generation.rng import stream
from apps.world.models import Lender, Loan, LoanApplication

from .clock import DAY_START, TICK_MINUTES, TICKS_PER_DAY, Calendar
from .demand import REFERENCE_PRICE, p_enquire, update_perception
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


def schedule_applications(game: Game, cal: Calendar, tick: int, period: date, sequence: int) -> int:
    """Schedule this month's applications to subscribing lenders. Returns the next sequence."""
    codes = list(
        Subscriber.objects.filter(organization=game.organization, is_active=True)
        .order_by("subscriber_code")
        .values_list("subscriber_code", flat=True)
    )
    applications = LoanApplication.objects.filter(
        world=game.world, period=period, lender__code__in=codes
    ).order_by("lender__code", "seq")
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


def handle_application(game: Game, payload: dict[str, object], at: datetime) -> Enquiry | None:
    code = str(payload["lender"])
    period = date.fromisoformat(str(payload["period"]))
    seq = int(str(payload["seq"]))
    application = LoanApplication.objects.select_related("person", "business").get(
        world=game.world, lender__code=code, period=period, seq=seq
    )
    view = SubscriberView.objects.select_for_update().get(game=game, subscriber_code=code)
    subscriber = Subscriber.objects.get(organization=game.organization, subscriber_code=code)
    product = Product.objects.get(organization=game.organization, product_code=PRODUCT)
    price = active_contract(subscriber.pk, product, at.date()).unit_price

    view.opportunities += 1
    rng = stream(game.world.seed, f"enquire:{code}:{period:%Y%m}:{seq}")
    if rng.random() >= p_enquire(view.perceived_value, price):
        view.save()
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

    enquiry = enquire(
        game.organization,
        subscriber,
        PRODUCT,
        "NEW_CREDIT",
        f"CONSENT-{code}-{period:%Y%m}-{seq:05d}",
        id_type,
        id_value,
        name,
        at,
    )
    record_usage(enquiry)

    hit = enquiry.customer_id is not None
    correct = (
        (customer_borrower(game, enquiry.customer_id) == borrower) if enquiry.customer_id else None
    )
    outcome = "NO_HIT" if not hit else ("CORRECT_HIT" if correct else "WRONG_PERSON")
    EnquiryJudgement.objects.create(
        game=game,
        enquiry=enquiry,
        application=application,
        should_hit=_has_reported_credit(game, borrower, period),
        hit=hit,
        correct_person=correct,
        outcome=outcome,
    )
    view.enquiries += 1
    view.hits += int(hit)
    view.wrong_person += int(outcome == "WRONG_PERSON")
    view.perceived_value = round(update_perception(view.perceived_value, outcome), 6)
    view.save()
    return enquiry


def _has_reported_credit(game: Game, borrower: tuple[str, int], period: date) -> bool:
    """Does the applicant have a loan, before this month, with a lender reporting to the bureau?"""
    providers = list(
        Institution.objects.filter(organization=game.organization).values_list(
            "institution_code", flat=True
        )
    )
    loans = Loan.objects.filter(
        world=game.world, lender__code__in=providers, disbursement_date__lt=period.replace(day=1)
    )
    if borrower[0] == "person":
        return loans.filter(customer__person_id=borrower[1]).exists()
    return loans.filter(customer__business_id=borrower[1]).exists()
