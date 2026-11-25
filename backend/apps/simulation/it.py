"""IT: overnight processing capacity, outages and how the bureau responds (P2.9; Section 6.7).

ASSUMPTION A-064 (until reference R14 gives real operating and platform costs):

* The overnight batch processes at most 2 submissions a night on standard
  capacity, 5 on high capacity (GHS 12,000 a month more). The rest wait for the
  next night, so their data reaches reports later.
* Each working morning, an outage starts with chance 1.5% (standard) or 0.75%
  (high), doubled when files were left waiting the night before. Unanswered,
  it lasts two working days.
* While systems are down, lenders cannot check the bureau (they lend without a
  report) and the overnight batch does not run.
* The player may respond once: VENDOR (emergency support, GHS 15,000; systems
  back within two working hours) or BACKUP (restore from backup, free; back within
  one working day).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from apps.bureau.submissions.models import Submission, SubmissionStatus
from apps.finance.events import incident_vendor
from apps.world.generation.rng import stream

from .clock import TICKS_PER_DAY, TICKS_PER_HOUR
from .models import Game, Incident

CAPACITY = {"STANDARD": 2, "HIGH": 5}
DAILY_OUTAGE_CHANCE = {"STANDARD": 0.015, "HIGH": 0.0075}
UNANSWERED_TICKS = 2 * TICKS_PER_DAY
VENDOR_COST = Decimal("15000.00")
RESPONSE_TICKS = {"VENDOR": 2 * TICKS_PER_HOUR, "BACKUP": TICKS_PER_DAY}


class ITError(Exception):
    pass


def active_incident(game: Game, tick: int) -> Incident | None:
    """The outage under way during ``tick``, if any."""
    return (
        Incident.objects.filter(game=game, started_tick__lte=tick, ends_tick__gte=tick)
        .order_by("number")
        .first()
    )


def systems_down(game: Game, tick: int, memo: dict[object, Any] | None = None) -> bool:
    if memo is None:
        return active_incident(game, tick) is not None
    key = ("down", tick)
    if key not in memo:
        memo[key] = active_incident(game, tick) is not None
    return bool(memo[key])


def downtime_hours(game: Game, first_tick: int, last_tick: int) -> float:
    """Hours of working time the systems were down between two ticks (P3.9: service credits)."""
    ticks = 0
    for start, end in Incident.objects.filter(
        game=game, started_tick__lte=last_tick, ends_tick__gte=first_tick
    ).values_list("started_tick", "ends_tick"):
        ticks += min(end, last_tick) - max(start, first_tick) + 1
    return ticks / TICKS_PER_HOUR


def waiting(game: Game) -> int:
    return Submission.objects.filter(
        organization=game.organization, submission_status=SubmissionStatus.RECEIVED
    ).count()


def start_outage(game: Game, tick: int, detail: str, add: Any) -> Incident:
    number = Incident.objects.filter(game=game).count() + 1
    incident = Incident.objects.create(
        game=game,
        number=number,
        started_tick=tick,
        ends_tick=tick + UNANSWERED_TICKS - 1,
        detail=detail,
    )
    add(
        "OUTAGE", "CRITICAL",
        "Systems are down: lenders cannot check the bureau",
        f"{detail} Unanswered, it lasts two working days. Call the vendor or restore "
        "from backup.",
        {"screen": "it", "params": {}},
    )  # fmt: skip
    return incident


def morning(game: Game, tick: int, day: date, add: Any) -> None:
    """At the start of a working day: does something break?"""
    from .startup import systems_ready

    if not systems_ready(game, day) or active_incident(game, tick) is not None:
        return  # a startup's systems are not running yet (P3.13)
    chance = DAILY_OUTAGE_CHANCE[game.organization.it_capacity]
    backlog = waiting(game) > 0  # files left from last night
    if backlog:
        chance *= 2
    rng = stream(game.world.seed, f"outage:{game.organization.it_capacity}:{day:%Y%m%d}")
    if rng.random() < chance:
        cause = "The database server failed overnight." if not backlog else (
            "The database server failed under the load of last night's backlog."
        )  # fmt: skip
        start_outage(game, tick, cause, add)


def respond(game: Game, response: str, tick: int, on: date, at: datetime) -> Incident:
    if response not in RESPONSE_TICKS:
        raise ITError(f"{response} is not a response (VENDOR or BACKUP)")
    # The player acts between ticks: the outage under way is the one covering the next tick.
    incident = active_incident(game, tick + 1)
    if incident is None:
        raise ITError("Systems are running: there is nothing to respond to")
    if incident.kind == "SUPPLIER_HOLD":  # P3.8: only paying the hosting company helps
        raise ITError("The hosting company has suspended service: pay its bill (Finance)")
    if incident.response:
        raise ITError(f"Already responding ({incident.response.lower()})")
    if response == "VENDOR":
        incident_vendor(game.organization, VENDOR_COST, on, at)
    incident.response = response
    incident.ends_tick = min(incident.ends_tick, tick + RESPONSE_TICKS[response])
    incident.save(update_fields=["response", "ends_tick"])
    return incident


def restored(game: Game, tick: int, add: Any) -> None:
    """Report systems back when an outage ended with the previous tick."""
    for incident in Incident.objects.filter(game=game, ends_tick=tick - 1).order_by("number"):
        hours = (incident.ends_tick - incident.started_tick + 1) / TICKS_PER_HOUR
        how = {"VENDOR": " with the vendor's help", "BACKUP": " from backup"}.get(
            incident.response, ""
        )
        add(
            "OUTAGE_OVER", "INFO",
            f"Systems are back{how}",
            f"Down for {hours:.0f} working hours. Files that waited are processed tonight.",
            {"screen": "it", "params": {}},
        )  # fmt: skip


def set_capacity(game: Game, level: str) -> None:
    if not game.organization.has_systems:
        raise ITError("The bureau has no systems yet: set them up first")
    if level not in CAPACITY:
        raise ITError(f"{level} is not a capacity level")
    org = game.organization
    org.it_capacity = level
    org.save(update_fields=["it_capacity"])
