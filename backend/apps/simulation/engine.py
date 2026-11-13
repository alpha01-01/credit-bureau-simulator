"""The tick engine (Document 07, Section 5.3).

Each tick runs in one transaction and is idempotent: a tick that has a TickLog
row is never run again. Within a tick the order is fixed:

  1. start of month: schedule this month's provider file arrivals
  2. events due in this tick, in (due tick, sequence) order
  3. end of day: the overnight batch processes every received submission

All randomness comes from streams keyed by the world seed, so the same world
and the same action log reproduce the same game.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from django.db import transaction
from django.db.models import Max

from apps.bureau.submissions.models import Submission, SubmissionStatus
from apps.bureau.submissions.pipeline import process_submission
from apps.standards.calendar import next_working_day
from apps.workitems.work import has_work, work_tick
from apps.world.generation.advance import extend_world
from apps.world.generation.applications import ensure_applications
from apps.world.generation.rng import stream
from apps.world.models import Lender, ProviderSubmission
from apps.world.provider_files import generate_submission
from apps.world.provider_files import month_end as period_end

from .bridge import deliver
from .clock import DAY_START, TICK_MINUTES, TICKS_PER_DAY, Calendar, previous_month_end
from .enquiries import handle_application, schedule_applications
from .judgement import rng_for, sync_work_items
from .models import EventStatus, EventType, Game, ScheduledEvent, TickLog


class ClockError(Exception):
    """The clock cannot do what was asked (e.g. a tick out of order)."""


@lru_cache(maxsize=64)
def calendar_for(clock_start: object) -> Calendar:
    return Calendar(clock_start)  # type: ignore[arg-type]


def calendar(game: Game) -> Calendar:
    return calendar_for(game.clock_start)


# --- Running ticks ----------------------------------------------------------------


def advance(game: Game, ticks: int) -> Game:
    """Run the next ``ticks`` ticks.

    Busy ticks run one transaction each. A stretch of quiet ticks (no month
    start, no event due, nothing waiting for the overnight batch) has nothing
    to do but be logged, so it is logged in one transaction; the result is
    identical to running those ticks one by one.
    """
    if ticks < 0:
        raise ClockError("Cannot go back in time")
    target = game.current_tick + ticks
    while game.current_tick < target:
        quiet_until = min(next_busy_tick(game) - 1, target)
        if quiet_until > game.current_tick:
            _log_quiet_ticks(game.pk, game.current_tick + 1, quiet_until)
        else:
            run_tick(game.pk, game.current_tick + 1)
        game.refresh_from_db()
    return game


def next_busy_tick(game: Game) -> int:
    """The first tick after the current one that has work to do."""
    cal = calendar(game)
    current = game.current_tick
    candidates = [next_month_tick(cal, current)]
    if cal.is_first_tick_of_month(current + 1):
        candidates.append(current + 1)
    pending = (
        game.events.filter(status=EventStatus.PENDING)
        .order_by("due_tick")
        .values_list("due_tick", flat=True)
        .first()
    )
    if pending is not None:
        candidates.append(max(pending, current + 1))
    if Submission.objects.filter(
        organization_id=game.organization_id, submission_status=SubmissionStatus.RECEIVED
    ).exists():
        candidates.append(end_of_day_tick(current))
    if has_work(game.organization):
        candidates.append(current + 1)  # staff are working through the queue
    return min(candidates)


def _log_quiet_ticks(game_id: int, first: int, last: int) -> None:
    with transaction.atomic():
        game = Game.objects.select_for_update().get(pk=game_id)
        if game.current_tick != first - 1:
            raise ClockError(f"Tick {first} cannot run after tick {game.current_tick}")
        if TickLog.objects.filter(game=game, tick__gte=first, tick__lte=last).exists():
            raise ClockError(f"Ticks {first}-{last} have already run")
        cal = calendar(game)
        TickLog.objects.bulk_create(
            TickLog(game=game, tick=t, sim_time=cal.tick_start(t), events_processed=0)
            for t in range(first, last + 1)
        )
        game.current_tick = last
        game.save(update_fields=["current_tick"])


def run_tick(game_id: int, tick: int) -> bool:
    """Run one tick. Returns False if it had already run (idempotent)."""
    with transaction.atomic():
        game = (
            Game.objects.select_for_update().select_related("world", "organization").get(pk=game_id)
        )
        if TickLog.objects.filter(game=game, tick=tick).exists():
            return False
        if tick != game.current_tick + 1:
            raise ClockError(f"Tick {tick} cannot run after tick {game.current_tick}")
        cal = calendar(game)
        processed = 0

        if cal.is_first_tick_of_month(tick):
            _schedule_month(game, cal, tick)

        due = ScheduledEvent.objects.filter(
            game=game, status=EventStatus.PENDING, due_tick__lte=tick
        ).order_by("due_tick", "sequence")
        for event in due:
            _handle(game, event, cal.tick_start(tick))
            event.status = EventStatus.DONE
            event.processed_tick = tick
            event.save(update_fields=["status", "processed_tick"])
            processed += 1

        if has_work(game.organization):
            processed += work_tick(
                game.organization,
                tick,
                (tick - 1) // TICKS_PER_DAY,
                cal.tick_end(tick),
                rng_for(game),
            )

        if cal.is_last_tick_of_day(tick):
            processed += _overnight_batch(game, cal.tick_end(tick))

        # Review cases opened this tick (by the batch or by decisions) become work items.
        sync_work_items(game, tick)

        TickLog.objects.create(
            game=game, tick=tick, sim_time=cal.tick_start(tick), events_processed=processed
        )
        game.current_tick = tick
        game.save(update_fields=["current_tick"])
        return True


# --- Scheduling ---------------------------------------------------------------------


def _next_sequence(game: Game) -> int:
    return (game.events.aggregate(n=Max("sequence"))["n"] or 0) + 1


def _schedule_month(game: Game, cal: Calendar, tick: int) -> None:
    """At the start of a month: the world's month, last month's files, this month's applications.

    The world lives through the coming month now (its truth stays hidden until
    providers report it next month). The new month is a pure function of the
    seed, so whichever game gets here first stores it and every game sees the
    same month; the event is recorded by every game alike.
    """
    today = cal.tick_start(tick).date()
    period = previous_month_end(today)
    this_month = period_end(today.year, today.month)
    sequence = _next_sequence(game)
    world = game.world
    if this_month > date.fromisoformat(world.config["history_end"]):
        while world.history_end < this_month:
            extend_world(world.pk)
            world.refresh_from_db()
        ScheduledEvent.objects.create(
            game=game,
            event_type=EventType.WORLD_ADVANCED,
            due_tick=tick,
            sequence=sequence,
            payload={"period": this_month.isoformat()},
        )
        sequence += 1
        ensure_applications(world, this_month)
        sequence = schedule_applications(game, cal, tick, this_month, sequence)

    for institution in game.organization.institutions.filter(is_active=True).order_by(
        "institution_code"
    ):
        code = institution.institution_code
        lender = Lender.objects.get(world=world, code=code)
        world_sub = ProviderSubmission.objects.filter(lender=lender, period=period).first()
        if world_sub is None:
            world_sub = generate_submission(world, lender, period).submission
        if not world_sub.files.exists():
            continue
        slot = int(stream(world.seed, f"arrival-slot:{code}:{period:%Y%m}").integers(TICKS_PER_DAY))
        arrival_day = next_working_day(world_sub.arrival_date)
        arrival = datetime.combine(arrival_day, DAY_START, tzinfo=UTC) + timedelta(
            minutes=TICK_MINUTES * slot
        )
        ScheduledEvent.objects.create(
            game=game,
            event_type=EventType.PROVIDER_FILES_ARRIVE,
            due_tick=max(cal.tick_at(arrival), tick),
            sequence=sequence,
            payload={"lender": code, "period": period.isoformat(), "arrival": arrival.isoformat()},
        )
        sequence += 1


def _handle(game: Game, event: ScheduledEvent, at: datetime) -> None:
    if event.event_type == EventType.CREDIT_APPLICATION:
        handle_application(game, event.payload, at)
        return
    if event.event_type == EventType.PROVIDER_FILES_ARRIVE:
        world_sub = ProviderSubmission.objects.get(
            lender__world=game.world,
            lender__code=event.payload["lender"],
            period=event.payload["period"],
        )
        deliver(game, world_sub, datetime.fromisoformat(event.payload["arrival"]))
    # WORLD_ADVANCED is a record only: the work was done when it was scheduled.


def _overnight_batch(game: Game, at: datetime) -> int:
    """Process every submission received and not yet processed."""
    waiting = Submission.objects.filter(
        organization=game.organization, submission_status=SubmissionStatus.RECEIVED
    ).order_by("received_at", "submission_reference")
    count = 0
    for submission in waiting:
        process_submission(submission, at=at)
        count += 1
    return count


# --- Looking ahead ------------------------------------------------------------------


def next_event_tick(game: Game) -> int:
    """The next tick at which something happens, for "skip to next event"."""
    cal = calendar(game)
    current = game.current_tick
    candidates = []
    pending = (
        game.events.filter(status=EventStatus.PENDING, due_tick__gt=current)
        .order_by("due_tick")
        .values_list("due_tick", flat=True)
        .first()
    )
    if pending is not None:
        candidates.append(pending)
    end_of_today = (current // TICKS_PER_DAY + 1) * TICKS_PER_DAY
    if Submission.objects.filter(
        organization=game.organization, submission_status=SubmissionStatus.RECEIVED
    ).exists():
        candidates.append(end_of_today)
    if cal.is_first_tick_of_month(current + 1):
        candidates.append(current + 1)  # month-start scheduling is an event too
    candidates.append(next_month_tick(cal, current))
    return min(candidates)


def next_month_tick(cal: Calendar, current: int) -> int:
    """First tick of the next calendar month after tick ``current``."""
    day_index = current // TICKS_PER_DAY  # the day the next tick falls on
    month = cal.day(day_index).month
    while cal.day(day_index).month == month:
        day_index += 1
    return cal.first_tick_of_day(day_index)


def end_of_day_tick(current: int) -> int:
    """Last tick of the day the next tick falls on."""
    return (current // TICKS_PER_DAY + 1) * TICKS_PER_DAY
