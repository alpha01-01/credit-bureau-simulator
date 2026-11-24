"""Customer Support, a managed department (P3.10; Document 09).

Subscribers and data subjects raise tickets. The volume follows what goes wrong: the
systems being down, reports about the wrong person or missing someone, and disputes.
The contact centre's agents answer the oldest tickets first; the chief executive sets
how many agents there are. Subscribers judge the bureau partly on how quickly they
are answered (``satisfaction``, part of the subscriber reputation).

ASSUMPTION A-080 (until real contact-centre figures):

* Each working morning brings the tickets raised the working day before, each source
  a Poisson count with mean: 0.3 a day for each active subscriber (questions); 0.5 for
  each subscriber for each hour the systems were down; 0.5 for each report about the
  wrong person and 0.1 for each that missed someone on file; 0.8 for each dispute
  received (from the data subject).
* An agent answers 15 tickets a working day, oldest first; a ticket answered by the
  next working day is on time. Agents are contracted from a contact centre at GHS
  4,500 a month each (billed monthly); the bureau starts with two.
* Satisfaction is the share of subscribers' tickets in the last three months answered
  on time, counting those still open past their time as late.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.db.models import Max

from apps.bureau.quality.models import Dispute
from apps.commercial.models import Subscriber
from apps.standards.calendar import is_working_day
from apps.world.generation.rng import stream

from . import it
from .clock import TICKS_PER_DAY, Calendar
from .compliance import add_working_days
from .models import EnquiryJudgement, Game, SupportTicket

QUESTIONS_PER_SUBSCRIBER = 0.3
OUTAGE_PER_SUBSCRIBER_HOUR = 0.5
PER_WRONG_PERSON, PER_MISSED, PER_DISPUTE = 0.5, 0.1, 0.8
TICKETS_PER_AGENT = 15
RESPONSE_WORKING_DAYS = 1
STAFF_RANGE = (0, 20)
RECENT_DAYS = 91
TOPICS = {
    "QUESTION": "A question about reports or the service",
    "OUTAGE": "The bureau cannot be reached",
    "WRONG_PERSON": "A report about the wrong person",
    "MISSED": "No report for someone with credit on file",
    "DISPUTE": "A data subject asking about a dispute",
}


class SupportError(Exception):
    pass


def previous_working_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day


def arrivals(game: Game, day: date, cal: Calendar) -> dict[str, float]:
    """The expected tickets from each source for the working day before ``day``."""
    before = previous_working_day(day)
    if before < game.clock_start:
        return {}
    first = cal.first_tick_of_day(cal.index_of(before))
    down = it.downtime_hours(game, first, first + TICKS_PER_DAY - 1)
    subscribers = Subscriber.objects.filter(organization=game.organization, is_active=True).count()
    judged = EnquiryJudgement.objects.filter(game=game, enquiry__enquired_at__date=before)
    wrong = judged.filter(outcome="WRONG_PERSON").count()
    missed = judged.filter(outcome="NO_HIT", should_hit=True).count()
    disputes = Dispute.objects.filter(
        organization=game.organization, received_at__date=before
    ).count()
    return {
        "QUESTION": QUESTIONS_PER_SUBSCRIBER * subscribers,
        "OUTAGE": OUTAGE_PER_SUBSCRIBER_HOUR * subscribers * down,
        "WRONG_PERSON": PER_WRONG_PERSON * wrong,
        "MISSED": PER_MISSED * missed,
        "DISPUTE": PER_DISPUTE * disputes,
    }


def morning(game: Game, day: date, tick: int, cal: Calendar, add: Any) -> int:
    """Answer what the agents can, oldest first; then the day's new tickets arrive."""
    capacity = game.organization.support_staff * TICKETS_PER_AGENT
    waiting = list(
        SupportTicket.objects.filter(game=game, answered_on__isnull=True)
        .order_by("number")
        .values_list("pk", flat=True)[:capacity]
    )
    SupportTicket.objects.filter(pk__in=waiting).update(answered_on=day, answered_tick=tick)

    expected = arrivals(game, day, cal)
    if not any(expected.values()):
        return 0
    rng = stream(game.world.seed, f"support:{day:%Y%m%d}")
    codes = sorted(
        Subscriber.objects.filter(organization=game.organization, is_active=True).values_list(
            "subscriber_code", flat=True
        )
    )
    number = SupportTicket.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0
    due = add_working_days(day, RESPONSE_WORKING_DAYS)
    tickets = []
    for topic in TOPICS:
        for _ in range(int(rng.poisson(expected.get(topic, 0.0)))):
            number += 1
            subject = topic == "DISPUTE"
            tickets.append(
                SupportTicket(
                    game=game,
                    number=number,
                    source="SUBJECT" if subject else "SUBSCRIBER",
                    subscriber_code="" if subject or not codes else codes[
                        int(rng.integers(len(codes)))
                    ],
                    topic=topic,
                    opened_on=day,
                    opened_tick=tick,
                    due_on=due,
                )
            )  # fmt: skip
    SupportTicket.objects.bulk_create(tickets)
    backlog = SupportTicket.objects.filter(game=game, answered_on__isnull=True).count()
    if backlog > capacity:
        add(
            "SUPPORT_BACKLOG", "WARNING", f"Support is falling behind: {backlog} tickets waiting",
            f"The agents answer {capacity} a day; {len(tickets)} came in today.",
            {"screen": "support", "params": {}},
        )  # fmt: skip
    return len(tickets)


def set_staff(game: Game, agents: int) -> None:
    low, high = STAFF_RANGE
    if not low <= agents <= high:
        raise SupportError(f"Support has between {low} and {high} agents")
    game.organization.support_staff = agents
    game.organization.save(update_fields=["support_staff"])


def satisfaction(game: Game, at: datetime) -> dict[str, Any]:
    """How promptly subscribers have been answered over the last three months."""
    today = at.date()
    since = today - timedelta(days=RECENT_DAYS)
    tickets = SupportTicket.objects.filter(game=game, source="SUBSCRIBER", opened_on__gte=since)
    answered = tickets.filter(answered_on__isnull=False)
    on_time = sum(
        1 for a, d in answered.values_list("answered_on", "due_on") if a is not None and a <= d
    )
    overdue = tickets.filter(answered_on__isnull=True, due_on__lt=today).count()
    judged = answered.count() + overdue
    return {
        "score": on_time / judged if judged else None,
        "tickets": tickets.count(),
        "on_time": on_time,
        "late": judged - on_time,
    }
