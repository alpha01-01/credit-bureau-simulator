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
from typing import Any

from django.db import transaction
from django.db.models import Max

from apps.bureau.core.models import (
    AccountObservation,
    CreditAccount,
    Customer,
    CustomerContact,
    CustomerIdentifier,
    ProviderCustomerLink,
)
from apps.bureau.quality.models import TransformationLog, ValidationIssue
from apps.bureau.submissions.models import StagingRecord, Submission, SubmissionStatus
from apps.bureau.submissions.pipeline import process_submission
from apps.finance.events import run_payroll
from apps.standards.calendar import next_working_day
from apps.workitems.models import WorkItem
from apps.workitems.work import has_work, work_tick
from apps.world.generation.advance import extend_world
from apps.world.generation.applications import ensure_applications
from apps.world.generation.persist import analyze
from apps.world.generation.rng import stream
from apps.world.models import Lender, ProviderSubmission
from apps.world.provider_files import month_end as period_end

from . import (
    board,
    bookkeeping,
    compliance,
    hr,
    it,
    lending,
    missions,
    providers,
    sales,
    solvency,
)
from .bridge import deliver
from .checkpoints import take_checkpoint
from .clock import DAY_START, TICK_MINUTES, TICKS_PER_DAY, Calendar, previous_month_end
from .enquiries import handle_application, schedule_applications
from .feed import Feed, money
from .judgement import rng_for, sync_work_items
from .models import (
    CheckpointKind,
    EventStatus,
    EventType,
    Game,
    GameStatus,
    Incident,
    Notice,
    ScheduledEvent,
    Severity,
    TickLog,
)
from .review import build_review

# The bureau tables a month of files fills, and the month-end summaries read.
MONTH_END_TABLES = (
    AccountObservation, CreditAccount, Customer, CustomerContact, CustomerIdentifier,
    ProviderCustomerLink, StagingRecord, TransformationLog, ValidationIssue, WorkItem,
)  # fmt: skip


class ClockError(Exception):
    """The clock cannot do what was asked (e.g. a tick out of order)."""


@lru_cache(maxsize=64)
def calendar_for(clock_start: object) -> Calendar:
    return Calendar(clock_start)  # type: ignore[arg-type]


def calendar(game: Game) -> Calendar:
    return calendar_for(game.clock_start)


# --- Running ticks ----------------------------------------------------------------


def advance(game: Game, ticks: int, *, stop_on_pause: bool = False) -> Game:
    """Run the next ``ticks`` ticks.

    Busy ticks run one transaction each. A stretch of quiet ticks (no month
    start, no event due, nothing waiting for the overnight batch) has nothing
    to do but be logged, so it is logged in one transaction; the result is
    identical to running those ticks one by one.

    With ``stop_on_pause``, a tick whose notices match the auto-pause rules ends
    the advance there (the player asked to be stopped for such things).
    """
    if ticks < 0:
        raise ClockError("Cannot go back in time")
    target = game.current_tick + ticks
    while game.current_tick < target:
        quiet_until = min(next_busy_tick(game) - 1, target)
        if quiet_until > game.current_tick:
            _log_quiet_ticks(game.pk, game.current_tick + 1, quiet_until)
            game.refresh_from_db()
            continue
        tick = game.current_tick + 1
        run_tick(game.pk, tick)
        game.refresh_from_db()
        if game.status == GameStatus.ENDED:
            break  # a hard failure: the clock stops for good
        if stop_on_pause and Notice.objects.filter(game=game, tick=tick, paused=True).exists():
            break
    return game


def next_busy_tick(game: Game) -> int:
    """The first tick after the current one that has work to do."""
    cal = calendar(game)
    current = game.current_tick
    candidates = [next_month_tick(cal, current)]
    # Each working day starts with a look round (overdue data and invoices, cash, deadlines).
    candidates.append(((current - 1) // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 1)
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
    ending = (
        Incident.objects.filter(game=game, ends_tick__gte=current)
        .order_by("ends_tick")
        .values_list("ends_tick", flat=True)
        .first()
    )
    if ending is not None:
        candidates.append(ending + 1)  # systems back
    candidates.append(end_of_month_tick(cal, current))  # payroll
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
        if game.status == GameStatus.ENDED:
            raise ClockError("The game has ended")
        cal = calendar(game)
        processed = 0
        feed = Feed(game, tick, cal.tick_start(tick))

        if cal.is_first_tick_of_month(tick):
            _schedule_month(game, cal, tick, feed)
        it.restored(game, tick, feed.add)
        if (tick - 1) % TICKS_PER_DAY == 0:
            feed.morning(cal.tick_start(tick).date())
            it.morning(game, tick, cal.tick_start(tick).date(), feed.add)
            solvency.morning(
                game, cal.tick_start(tick).date(), cal.tick_start(tick), tick, feed.add
            )

        due = ScheduledEvent.objects.filter(
            game=game, status=EventStatus.PENDING, due_tick__lte=tick
        ).order_by("due_tick", "sequence")
        handled = []
        memo: dict[object, Any] = {}  # lookups that cannot change within a tick
        for event in due:
            _handle(game, event, cal.tick_start(tick), memo, feed)
            event.status = EventStatus.DONE
            event.processed_tick = tick
            handled.append(event)
        ScheduledEvent.objects.bulk_update(handled, ["status", "processed_tick"], batch_size=1000)
        processed += len(handled)

        if has_work(game.organization):
            processed += work_tick(
                game.organization,
                tick,
                (tick - 1) // TICKS_PER_DAY,
                cal.tick_end(tick),
                rng_for(game),
            )

        if cal.is_last_tick_of_day(tick):
            processed += _overnight_batch(game, tick, cal.tick_end(tick), feed)

        if cal.is_last_tick_of_month(tick):
            payday = cal.tick_start(tick).date()
            gross = run_payroll(game.organization, payday, cal.tick_end(tick))
            if gross:
                feed.money_out(
                    "PAYROLL_PAID", f"Salaries paid for {payday:%B}", f"Gross pay {money(gross)}."
                )
            processed += 1

        # Review cases opened this tick (by the batch or by decisions) become work items.
        sync_work_items(game, tick)

        if cal.is_last_tick_of_month(tick):
            # A month's files have been loaded since the planner last looked: refresh its
            # statistics (a sample; it sees this transaction's rows) before the month-end
            # summaries, which otherwise can take minutes over a plan for empty tables.
            analyze(*MONTH_END_TABLES)
            today = cal.tick_start(tick).date()
            period = period_end(today.year, today.month)
            build_review(game, cal, period, tick)
            feed.add(
                "REVIEW_READY",
                Severity.INFO,
                f"The Data Quality Review for {period:%B} is ready",
                "How many decisions were right, which records were wrongly rejected, and the "
                "true state of the data.",
                {"screen": "review", "params": {"period": f"{period:%Y-%m}"}},
            )

        if game.campaign and game.status != GameStatus.ENDED:
            missions.update(game, tick, feed.add)

        feed.save()
        TickLog.objects.create(
            game=game, tick=tick, sim_time=cal.tick_start(tick), events_processed=processed
        )
        game.current_tick = tick
        game.save(update_fields=["current_tick"])
        if cal.is_last_tick_of_month(tick):
            take_checkpoint(game, CheckpointKind.MONTH_END, cal.tick_end(tick))
        return True


# --- Scheduling ---------------------------------------------------------------------


def _next_sequence(game: Game) -> int:
    return (game.events.aggregate(n=Max("sequence"))["n"] or 0) + 1


def _schedule_month(game: Game, cal: Calendar, tick: int, feed: Feed) -> None:
    """At the start of a month: the world's month, last month's files, this month's applications.

    The world lives through the coming month now (its truth stays hidden until
    providers report it next month). The new month is a pure function of the
    seed, so whichever game gets here first stores it and every game sees the
    same month; the event is recorded by every game alike.
    """
    today = cal.tick_start(tick).date()
    period = previous_month_end(today)
    this_month = period_end(today.year, today.month)
    # Contracts whose year has ended are renewed or lost first: a lender that has left
    # gets no applications checked this month (P2.8).
    lending.renewals(game, today, cal.tick_start(tick), feed.add)
    solvency.month_start(game, today, cal.tick_start(tick), feed.add)
    board.quarterly_review(game, today, cal.tick_start(tick), tick, feed.add)
    hr.month_update(game, today, feed.add)
    hr.candidates_for(game, today.replace(day=1))
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

    sequence = bookkeeping.month_start(game, cal, tick, sequence, feed)

    for institution in game.organization.institutions.filter(is_active=True).order_by(
        "institution_code"
    ):
        code = institution.institution_code
        lender = Lender.objects.get(world=world, code=code)
        # The provider answers for last month: better files, or slower ones (P2.6).
        relation = providers.month_update(game, code, period, cal.tick_start(tick))
        world_sub = providers.submission_for(game, lender, period, relation.quality)
        if not world_sub.files.exists():
            continue
        slot = int(stream(world.seed, f"arrival-slot:{code}:{period:%Y%m}").integers(TICKS_PER_DAY))
        arrival_day = next_working_day(providers.arrival(world_sub, relation.goodwill))
        arrival = datetime.combine(arrival_day, DAY_START, tzinfo=UTC) + timedelta(
            minutes=TICK_MINUTES * slot
        )
        ScheduledEvent.objects.create(
            game=game,
            event_type=EventType.PROVIDER_FILES_ARRIVE,
            due_tick=max(cal.tick_at(arrival), tick),
            sequence=sequence,
            payload={
                "lender": code,
                "period": period.isoformat(),
                "arrival": arrival.isoformat(),
                "variant": world_sub.variant,
            },
        )
        sequence += 1


def _handle(
    game: Game, event: ScheduledEvent, at: datetime, memo: dict[object, Any], feed: Feed
) -> None:
    if event.event_type == EventType.CREDIT_APPLICATION:
        handle_application(game, event.payload, at, memo, feed)
        return
    if event.event_type in bookkeeping.FINANCE_EVENTS:
        bookkeeping.handle(game, event, at, feed)
        return
    if event.event_type == EventType.PROPOSAL_ANSWERED:
        sales.answer(game, event.payload, at, feed.add)
        return
    if event.event_type == EventType.DISPUTE_FILED:
        dispute = compliance.file_dispute(game, event.payload, at)
        if dispute is not None:
            feed.add(
                "DISPUTE_RECEIVED",
                Severity.WARNING,
                f"Dispute {dispute.dispute_number} from {dispute.subject_name}",
                f"{dispute.claim} Due by {dispute.due_date:%d %B}.",
                {"screen": "disputes", "params": {}},
            )
        return
    if event.event_type == EventType.PROVIDER_FILES_ARRIVE:
        world_sub = ProviderSubmission.objects.get(
            lender__world=game.world,
            lender__code=event.payload["lender"],
            period=event.payload["period"],
            variant=event.payload.get("variant", ""),
        )
        submission = deliver(game, world_sub, datetime.fromisoformat(event.payload["arrival"]))
        feed.files_arrived(submission)
    # WORLD_ADVANCED is a record only: the work was done when it was scheduled.


def _overnight_batch(game: Game, tick: int, at: datetime, feed: Feed) -> int:
    """Process the submissions received and not yet processed, as many as capacity allows."""
    waiting = Submission.objects.filter(
        organization=game.organization, submission_status=SubmissionStatus.RECEIVED
    ).order_by("received_at", "submission_reference")
    if not waiting.exists():
        return 0
    if it.systems_down(game, tick):
        feed.add(
            "BATCH_SKIPPED", Severity.WARNING, "The overnight batch could not run",
            f"Systems are down. {waiting.count()} files wait.", {"screen": "it", "params": {}},
        )  # fmt: skip
        return 0
    capacity = it.CAPACITY[game.organization.it_capacity]
    count = 0
    for submission in waiting.select_related("institution")[:capacity]:
        feed.run_finished(process_submission(submission, at=at))
        count += 1
    left = waiting.count()
    if left:
        feed.add(
            "BATCH_BACKLOG", Severity.WARNING,
            f"{left} files wait for tomorrow night's batch",
            f"Tonight's capacity was {capacity} files. More capacity costs money; files that "
            "wait reach reports later.", {"screen": "it", "params": {}},
        )  # fmt: skip
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


def end_of_month_tick(cal: Calendar, current: int) -> int:
    """Last tick of the month in which the next tick falls (payday)."""
    return next_month_tick(cal, current) - 1


def end_of_day_tick(current: int) -> int:
    """Last tick of the day the next tick falls on."""
    return (current // TICKS_PER_DAY + 1) * TICKS_PER_DAY
