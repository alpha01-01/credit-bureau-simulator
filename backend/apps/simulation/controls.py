"""Time controls and the action log (roadmap S4).

Every player command is recorded with the clock position at which it was
given. Replaying a game's action log on a new game in the same world gives
the same result; that is the replay guarantee tested in S4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Max

from apps.bureau.quality.rules import POLICIES
from apps.workitems.models import WorkItem
from apps.workitems.work import resolve_by_player

from .clock import TICKS_PER_HOUR
from .engine import ClockError, advance, calendar, end_of_day_tick, next_event_tick
from .judgement import sync_work_items
from .models import SPEEDS, EventStatus, Game, GameStatus, PlayerAction

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
        game = advance(game, target - game.current_tick)
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
    """One tick of a running clock (used by the clock worker). Not an action: speed is."""
    return advance(game, 1)


def replay(source: Game, target: Game) -> Game:
    """Apply ``source``'s action log to ``target`` (a fresh game in the same world)."""
    if target.world_id != source.world_id:
        raise ClockError("Replay needs a game in the same world")
    for action in source.actions.order_by("sequence"):
        if target.current_tick < action.tick:
            target = advance(target, action.tick - target.current_tick)
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
            case other:
                raise ClockError(f"Unknown action {other}")
    if target.current_tick < source.current_tick:  # ticks run by the clock worker
        target = advance(target, source.current_tick - target.current_tick)
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
    )
