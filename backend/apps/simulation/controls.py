"""Time controls and the action log (roadmap S4).

Every player command is recorded with the clock position at which it was
given. Replaying a game's action log on a new game in the same world gives
the same result; that is the replay guarantee tested in S4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.bureau.quality.rules import POLICIES
from apps.workitems.models import WorkItem
from apps.workitems.work import resolve_by_player

from .checkpoints import checkpoint_now
from .clock import REAL_SECONDS_PER_TICK_AT_1X, TICKS_PER_HOUR
from .engine import ClockError, advance, calendar, end_of_day_tick, next_event_tick
from .judgement import sync_work_items
from .models import (
    SPEEDS,
    Checkpoint,
    EventStatus,
    Game,
    GameStatus,
    Notice,
    PlayerAction,
    Severity,
)

# A real-time tick may come a little early (timers are not exact) but not much.
STEP_TOLERANCE = 0.8

ADVANCE_UNITS = ("hour", "day", "next_event")


def record(game: Game, action_type: str, payload: dict[str, Any] | None = None) -> PlayerAction:
    with transaction.atomic():
        sequence = (game.actions.aggregate(n=Max("sequence"))["n"] or 0) + 1
        return PlayerAction.objects.create(
            game=game,
            sequence=sequence,
            tick=game.current_tick,
            action_type=action_type,
            payload=payload or {},
        )


def pause(game: Game) -> Game:
    record(game, "PAUSE")
    game.status = GameStatus.PAUSED
    game.save(update_fields=["status"])
    return game


def _ready(game: Game) -> None:
    if game.setup_status != "READY":
        raise ClockError("The game is still being prepared")


def resume(game: Game) -> Game:
    _ready(game)
    record(game, "RESUME")
    game.status = GameStatus.RUNNING
    game.save(update_fields=["status"])
    return game


def set_speed(game: Game, speed: int) -> Game:
    if speed not in SPEEDS:
        raise ClockError(f"Speed must be one of {', '.join(f'{s}x' for s in SPEEDS)}")
    record(game, "SET_SPEED", {"speed": speed})
    game.speed = speed
    game.save(update_fields=["speed"])
    return game


def advance_by(game: Game, unit: str, count: int = 1) -> Game:
    """Advance the clock: hours, to the end of the day (repeated), or to the next event."""
    _ready(game)
    if unit not in ADVANCE_UNITS:
        raise ClockError(f"Unit must be one of {', '.join(ADVANCE_UNITS)}")
    if not 1 <= count <= 31:
        raise ClockError("Count must be between 1 and 31")
    record(game, "ADVANCE", {"unit": unit, "count": count})
    for _ in range(count):
        if unit == "hour":
            target = game.current_tick + TICKS_PER_HOUR
        elif unit == "day":
            target = end_of_day_tick(game.current_tick)
        else:
            target = next_event_tick(game)
        game = advance(game, target - game.current_tick, stop_on_pause=True)
        if stopped_by(game) is not None:  # something the player asked to be stopped for
            break
    return game


def stopped_by(game: Game) -> Notice | None:
    """The notice that paused the clock at the current tick, if one did."""
    return (
        Notice.objects.filter(game=game, tick=game.current_tick, paused=True).order_by("pk").first()
    )


def set_pause_rules(game: Game, severities: list[str], deadlines: bool) -> Game:
    """Which notices stop the clock (Document 07, Section 5.2)."""
    unknown = set(severities) - set(Severity.values)
    if unknown:
        raise ClockError(f"Unknown severity: {', '.join(sorted(unknown))}")
    chosen = [s for s in Severity.values if s in severities]  # a stable order
    record(game, "SET_PAUSE_RULES", {"severities": chosen, "deadlines": bool(deadlines)})
    game.pause_severities = chosen
    game.pause_on_deadlines = bool(deadlines)
    game.save(update_fields=["pause_severities", "pause_on_deadlines"])
    return game


def resolve_item(game: Game, item_number: int, decision: str) -> WorkItem:
    """The player decides a work item, at the current game time."""
    item = WorkItem.objects.filter(organization=game.organization, item_number=item_number).first()
    if item is None:
        raise ClockError(f"No work item {item_number}")
    record(game, "RESOLVE_ITEM", {"item": item_number, "decision": decision})
    cal = calendar(game)
    at = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    try:
        return resolve_by_player(item, decision, game.current_tick, at)
    finally:
        sync_work_items(game, game.current_tick)


def set_rejection_policy(game: Game, policy: str) -> Game:
    """How strictly incoming records are rejected; applies to files processed from now on."""
    if policy not in POLICIES:
        raise ClockError(f"Policy must be one of {', '.join(POLICIES)}")
    record(game, "SET_REJECTION_POLICY", {"policy": policy})
    organization = game.organization
    organization.rejection_policy = policy
    organization.save(update_fields=["rejection_policy"])
    return game


def step(game: Game) -> Game:
    """One tick of a running clock, in real time. Not an action: speed is.

    Driven by the browser (or the clock worker) every few seconds. A tick due
    sooner than the speed allows is not run, so two open tabs, or a tab and the
    worker, do not make the clock run faster.
    """
    with transaction.atomic():
        game = Game.objects.select_for_update().get(pk=game.pk)
        if game.status != GameStatus.RUNNING or game.setup_status != "READY":
            return game
        now = timezone.now()
        interval = timedelta(seconds=REAL_SECONDS_PER_TICK_AT_1X / game.speed)
        if game.last_step_at is not None and now - game.last_step_at < interval * STEP_TOLERANCE:
            return game
        game.last_step_at = now
        game.save(update_fields=["last_step_at"])
    return advance(game, 1, stop_on_pause=True)


def replay(source: Game, target: Game) -> Game:
    """Apply ``source``'s action log to ``target`` (a fresh game in the same world)."""
    if target.world_id != source.world_id:
        raise ClockError("Replay needs a game in the same world")
    for action in source.actions.order_by("sequence"):
        if target.current_tick < action.tick:
            target = advance(target, action.tick - target.current_tick)
        target = _apply(target, action)
    if target.current_tick < source.current_tick:  # ticks run by the clock worker
        target = advance(target, source.current_tick - target.current_tick)
    return target


def replay_to(checkpoint: Checkpoint, target: Game) -> Game:
    """Bring ``target`` (a fresh game like the checkpoint's) to the checkpoint's point.

    The actions taken before the checkpoint are applied at their ticks. Advances are
    not applied as actions: the clock is moved to each action's tick instead, and to
    the checkpoint's tick at the end, so a long advance that ran past the checkpoint
    stops there.
    """
    source = checkpoint.game
    if target.world_id != source.world_id:
        raise ClockError("Replay needs a game in the same world")
    if target.current_tick > checkpoint.tick:
        raise ClockError("The game is already past the checkpoint")
    actions = source.actions.order_by("sequence")[: checkpoint.action_count]
    for action in actions:
        if target.current_tick < action.tick:
            target = advance(target, action.tick - target.current_tick)
        if action.action_type != "ADVANCE":
            target = _apply(target, action)
    if target.current_tick < checkpoint.tick:
        target = advance(target, checkpoint.tick - target.current_tick)
    return target


def checkpoint(game: Game, label: str = "") -> Checkpoint:
    """Take an on-demand checkpoint at the current tick."""
    return checkpoint_now(game, label, state(game).now)


def _apply(target: Game, action: PlayerAction) -> Game:
    match action.action_type:
        case "PAUSE":
            target = pause(target)
        case "RESUME":
            target = resume(target)
        case "SET_SPEED":
            target = set_speed(target, int(action.payload["speed"]))
        case "ADVANCE":
            target = advance_by(target, action.payload["unit"], int(action.payload["count"]))
        case "SET_REJECTION_POLICY":
            target = set_rejection_policy(target, str(action.payload["policy"]))
        case "RESOLVE_ITEM":
            resolve_item(target, int(action.payload["item"]), str(action.payload["decision"]))
        case "SET_PAUSE_RULES":
            target = set_pause_rules(
                target, list(action.payload["severities"]), bool(action.payload["deadlines"])
            )
        case other:
            raise ClockError(f"Unknown action {other}")
    return target


@dataclass(frozen=True)
class ClockState:
    game_id: int
    tick: int
    now: datetime
    status: str
    speed: int
    next_event_tick: int
    next_event_at: datetime
    pending_events: int
    reporting_data_through: str
    pause_severities: list[str]
    pause_on_deadlines: bool
    stopped_by: dict[str, Any] | None
    latest_notice: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "game": self.game_id,
            "tick": self.tick,
            "now": self.now.isoformat(),
            "date": self.now.date().isoformat(),
            "weekday": self.now.strftime("%A"),
            "time": self.now.strftime("%H:%M"),
            "status": self.status,
            "speed": self.speed,
            "next_event": {"tick": self.next_event_tick, "at": self.next_event_at.isoformat()},
            "pending_events": self.pending_events,
            "reporting_data_through": self.reporting_data_through,
            "pause_rules": {
                "severities": self.pause_severities,
                "deadlines": self.pause_on_deadlines,
            },
            "stopped_by": self.stopped_by,
            "latest_notice": self.latest_notice,
        }


def state(game: Game) -> ClockState:
    cal = calendar(game)
    now = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    upcoming = next_event_tick(game)
    return ClockState(
        game_id=game.pk,
        tick=game.current_tick,
        now=now,
        status=game.status,
        speed=game.speed,
        next_event_tick=upcoming,
        next_event_at=cal.tick_start(upcoming),
        pending_events=game.events.filter(status=EventStatus.PENDING).count(),
        reporting_data_through=game.world.history_end.isoformat(),
        pause_severities=list(game.pause_severities),
        pause_on_deadlines=game.pause_on_deadlines,
        stopped_by=notice_dict(stop) if (stop := _paused_now(game)) else None,
        latest_notice=game.notices.order_by("-pk").values_list("pk", flat=True).first(),
    )


def _paused_now(game: Game) -> Notice | None:
    """While the game is paused, the notice that paused it at this tick, if any."""
    return stopped_by(game) if game.status == GameStatus.PAUSED else None


def notice_dict(notice: Notice) -> dict[str, Any]:
    return {
        "id": notice.pk,
        "tick": notice.tick,
        "at": notice.sim_time.isoformat(),
        "kind": notice.kind,
        "severity": notice.severity,
        "title": notice.title,
        "detail": notice.detail,
        "drill": notice.drill or None,
        "deadline": notice.is_deadline,
        "paused": notice.paused,
    }
