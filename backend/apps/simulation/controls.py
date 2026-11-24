"""Time controls and the action log (roadmap S4).

Every player command is recorded with the clock position at which it was
given. Replaying a game's action log on a new game in the same world gives
the same result; that is the replay guarantee tested in S4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.bureau.quality.models import CleansingRule, RuleAction
from apps.bureau.quality.rules import POLICIES, RELAX_TO, RELAXABLE
from apps.bureau.submissions.feedback import send_report
from apps.bureau.submissions.mapping import MappingError, save_mapping
from apps.bureau.submissions.models import FeedbackReport, FileStatus, Submission, SubmissionFile
from apps.bureau.submissions.pipeline import process_submission
from apps.org.models import Employee
from apps.standards.rulebook import DATA_STANDARDS
from apps.workitems.models import WorkItem
from apps.workitems.work import resolve_by_player

from . import duties, hr, it, missions, providers, roles, sales, scorecards, solvency
from .checkpoints import checkpoint_now
from .clock import REAL_SECONDS_PER_TICK_AT_1X, TICKS_PER_HOUR
from .engine import ClockError, advance, calendar, end_of_day_tick, next_event_tick
from .feed import Feed
from .judgement import sync_work_items
from .models import (
    SPEEDS,
    Checkpoint,
    ConsentCheck,
    EventStatus,
    FundingRequest,
    Game,
    GameStatus,
    Incident,
    Notice,
    PlayerAction,
    Proposal,
    Sanction,
    ScoreModel,
    Severity,
)

# A real-time tick may come a little early (timers are not exact) but not much.
STEP_TOLERANCE = 0.8

ADVANCE_UNITS = ("hour", "day", "next_event")


def record(game: Game, action_type: str, payload: dict[str, Any] | None = None) -> PlayerAction:
    """Log a player command. A game that has ended takes no more commands (P2.10)."""
    if Game.objects.filter(pk=game.pk, status=GameStatus.ENDED).exists():
        raise ClockError("The game has ended")
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


def map_template(game: Game, reference: str, file_name: str, columns: list[str]) -> Game:
    """Map a rejected file's columns to the template, keep the mapping, and load the file."""
    stored = (
        SubmissionFile.objects.select_related("submission")
        .filter(
            submission__organization=game.organization,
            submission__submission_reference=reference,
            file_name=file_name,
        )
        .first()
    )
    if stored is None:
        raise ClockError(f"No file {file_name} in {reference}")
    if stored.file_status != FileStatus.REJECTED or stored.rejection_reason != "T001":
        raise ClockError("Only a file rejected for its columns (T001) can be mapped")
    cal = calendar(game)
    at = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    with transaction.atomic():
        try:
            save_mapping(stored, columns, "Player", at)
        except MappingError as exc:
            raise ClockError(str(exc)) from exc
        record(
            game, "MAP_TEMPLATE", {"submission": reference, "file": file_name, "columns": columns}
        )
        process_submission(stored.submission, at=at, files=[stored])
        sync_work_items(game, game.current_tick)
    return game


def add_cleansing_rule(
    game: Game, field: str, action: str, find: str, replace: str = "", provider: str = ""
) -> CleansingRule:
    """A cleansing rule of the bureau's own, applied to files processed from now on."""
    known = {
        f.name for edition in DATA_STANDARDS.editions for fields in edition.fields.values()
        for f in fields
    }  # fmt: skip
    if field not in known:
        raise ClockError(f"{field!r} is not a template field")
    if action not in RuleAction.values:
        raise ClockError(f"Action must be one of {', '.join(RuleAction.values)}")
    if not find or len(find) > 100 or len(replace) > 100:
        raise ClockError("Say what to find (up to 100 characters)")
    institution = None
    if provider:
        institution = game.organization.institutions.filter(institution_code=provider).first()
        if institution is None:
            raise ClockError(f"No provider {provider}")
    record(game, "ADD_CLEANSING_RULE", {"field": field, "action": action, "find": find,
                                        "replace": replace, "provider": provider})  # fmt: skip
    cal = calendar(game)
    count = CleansingRule.objects.filter(organization=game.organization).count()
    return CleansingRule.objects.create(
        organization=game.organization,
        code=f"U{count + 1:02d}",
        field=field,
        action=action,
        find=find,
        replace=replace,
        institution=institution,
        created_at=cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1),
    )


def set_cleansing_rule_active(game: Game, code: str, active: bool) -> CleansingRule:
    rule = CleansingRule.objects.filter(organization=game.organization, code=code).first()
    if rule is None:
        raise ClockError(f"No rule {code}")
    record(game, "SET_CLEANSING_RULE_ACTIVE", {"code": code, "active": bool(active)})
    rule.is_active = bool(active)
    rule.save(update_fields=["is_active"])
    return rule


def set_rule_override(game: Game, code: str, setting: str) -> Game:
    """Relax a validation rule to a warning (load as sent), or restore it (ERROR)."""
    if code not in RELAXABLE:
        raise ClockError(f"{code} cannot be relaxed; these can: {', '.join(RELAXABLE)}")
    if setting not in (*RELAX_TO, "ERROR"):
        raise ClockError("Setting must be ERROR or WARNING")
    record(game, "SET_RULE_OVERRIDE", {"code": code, "setting": setting})
    organization = game.organization
    overrides = dict(organization.rule_overrides)
    if setting == "ERROR":
        overrides.pop(code, None)
    else:
        overrides[code] = setting
    organization.rule_overrides = overrides
    organization.save(update_fields=["rule_overrides"])
    return game


def send_feedback(game: Game, reference: str) -> FeedbackReport:
    """Send a provider the feedback report on one of its submissions."""
    submission = Submission.objects.filter(
        organization=game.organization, submission_reference=reference
    ).first()
    if submission is None:
        raise ClockError(f"No submission {reference}")
    record(game, "SEND_FEEDBACK", {"submission": reference})
    cal = calendar(game)
    at = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    return send_report(submission, at)


def _provider(game: Game, code: str) -> str:
    if not game.organization.institutions.filter(institution_code=code).exists():
        raise ClockError(f"No provider {code}")
    return code


def train_provider(game: Game, code: str) -> Game:
    """Pay for a data-quality training session for a provider's staff (P2.6)."""
    _provider(game, code)
    cal = calendar(game)
    at = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    with transaction.atomic():
        try:
            providers.train(game, code, at.date(), at)
        except providers.RelationshipError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "TRAIN_PROVIDER", {"provider": code})
    return game


def penalise_provider(game: Game, code: str) -> Game:
    """Impose an SLA penalty on a provider for late or poor data (P2.6)."""
    _provider(game, code)
    with transaction.atomic():
        providers.penalise(game, code)
        record(game, "PENALISE_PROVIDER", {"provider": code})
    return game


TOOLING_LEVELS = {
    "BASIC": "Identifiers only",
    "STANDARD": "Fuzzy matching on name and date of birth",
    "ADVANCED": "Fuzzy matching with phone numbers",
}


def set_matching_thresholds(game: Game, auto_link: float, review: float) -> Game:
    """The similarity at which records are linked without review, and held for review."""
    if not 0.5 <= review <= auto_link <= 1.0:
        raise ClockError("Thresholds must satisfy 0.50 <= review <= auto-link <= 1.00")
    auto_link, review = round(auto_link, 2), round(review, 2)
    record(game, "SET_MATCHING_THRESHOLDS", {"auto_link": auto_link, "review": review})
    organization = game.organization
    organization.match_auto_link, organization.match_review = auto_link, review
    organization.save(update_fields=["match_auto_link", "match_review"])
    return game


def set_matching_tooling(game: Game, level: str) -> Game:
    """Buy (or drop) matching software; billed from the next month."""
    if level not in TOOLING_LEVELS:
        raise ClockError(f"Tooling must be one of {', '.join(TOOLING_LEVELS)}")
    record(game, "SET_MATCHING_TOOLING", {"level": level})
    organization = game.organization
    organization.matching_tooling = level
    organization.save(update_fields=["matching_tooling"])
    return game


# --- Departments (P2.9) ---------------------------------------------------------------


def _now(game: Game) -> tuple[int, datetime]:
    """The clock position a player action happens at: between the last tick and the next."""
    cal = calendar(game)
    at = cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)
    return game.current_tick, at


def this_month(game: Game) -> date:
    """The month of the next tick: the month the player is in."""
    return calendar(game).tick_start(game.current_tick + 1).date().replace(day=1)


def _employee(game: Game, number: str) -> Employee:
    try:
        return Employee.objects.get(organization=game.organization, employee_number=number)
    except Employee.DoesNotExist as exc:
        raise ClockError(f"No employee {number}") from exc


def hire_candidate(game: Game, number: int) -> Employee:
    candidate = next((c for c in hr.candidates_for(game, this_month(game)) if c.number == number),
                     None)  # fmt: skip
    if candidate is None:
        raise ClockError(f"No candidate {number} this month")
    _, at = _now(game)
    with transaction.atomic():
        try:
            employee = hr.hire(game, candidate, at.date())
        except hr.HRError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "HIRE", {"candidate": number})
    return employee


def train_employee(game: Game, number: str, work_type: str) -> Employee:
    employee = _employee(game, number)
    tick, at = _now(game)
    with transaction.atomic():
        try:
            hr.train(employee, work_type, tick, at.date(), at)
        except hr.HRError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "TRAIN_EMPLOYEE", {"employee": number, "work_type": work_type})
    return employee


def set_salary(game: Game, number: str, salary: Decimal) -> Employee:
    employee = _employee(game, number)
    with transaction.atomic():
        try:
            hr.set_salary(employee, salary)
        except hr.HRError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "SET_SALARY", {"employee": number, "salary": str(employee.monthly_salary)})
    return employee


def send_proposal(game: Game, lender: str, price: Decimal) -> Proposal:
    tick, at = _now(game)
    with transaction.atomic():
        try:
            # The answer is scheduled from the next tick: the one the player is waiting for.
            proposal = sales.propose(game, lender, price, tick + 1, at)
        except sales.SalesError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "SEND_PROPOSAL", {"lender": lender, "price": str(proposal.unit_price)})
    return proposal


def respond_to_outage(game: Game, response: str) -> Incident:
    tick, at = _now(game)
    with transaction.atomic():
        try:
            incident = it.respond(game, response, tick, at.date(), at)
        except it.ITError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "RESPOND_TO_OUTAGE", {"response": response})
    return incident


def set_it_capacity(game: Game, level: str) -> Game:
    """Buy (or drop) overnight processing capacity; billed from the next month."""
    with transaction.atomic():
        try:
            it.set_capacity(game, level)
        except it.ITError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "SET_IT_CAPACITY", {"level": level})
    return game


# --- Learning (P2.11) -----------------------------------------------------------------


def answer_mission(game: Game, code: str, value: str) -> bool:
    """Answer the current mission's question; a right answer may complete the mission."""
    tick, at = _now(game)
    with transaction.atomic():
        try:
            right = missions.answer(game, code, value, tick)
        except missions.MissionError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "ANSWER_MISSION", {"code": code, "value": value})
        feed = Feed(game, tick, at)
        missions.update(game, tick, feed.add)
        feed.save()
    return right


def switch_role(game: Game, role: str) -> Game:
    """Work as the chief executive or a department head (P3.1). The new role's actions wait
    for the changeover (``roles.CHANGEOVER_TICKS``)."""
    if role not in roles.ROLES:
        raise ClockError(f"There is no role {role!r}")
    if role == game.role:
        raise ClockError(f"You are already working as the {roles.ROLES[role].title}")
    with transaction.atomic():
        record(game, "SWITCH_ROLE", {"role": role})
        game.role = role
        game.role_ready_tick = game.current_tick + roles.CHANGEOVER_TICKS
        game.save(update_fields=["role", "role_ready_tick"])
    return game


def build_scorecard(
    game: Game, term: str, observation: date, window: int, features: list[str]
) -> ScoreModel:
    """Build a term scorecard in the workbench (P3.5)."""
    with transaction.atomic():
        try:
            model = scorecards.build(
                game, term, observation, window, list(features), game.current_tick
            )
        except scorecards.ScorecardError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "BUILD_SCORECARD", {
            "term": term, "observation": observation.isoformat(), "window": window,
            "features": list(features),
        })  # fmt: skip
    return model


def build_composite(game: Game, observation: date, window: int) -> ScoreModel:
    """Combine the deployed term scorecards into a composite score (P3.5)."""
    with transaction.atomic():
        try:
            model = scorecards.build_composite(game, observation, window, game.current_tick)
        except scorecards.ScorecardError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "BUILD_COMPOSITE", {"observation": observation.isoformat(), "window": window})
    return model


def deploy_scorecard(game: Game, number: int) -> ScoreModel:
    """Put a scorecard into use (P3.5)."""
    tick, at = _now(game)
    with transaction.atomic():
        try:
            model = scorecards.deploy(game, number, tick, at)
        except scorecards.ScorecardError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "DEPLOY_SCORECARD", {"number": number})
    return model


def retire_scorecard(game: Game, number: int) -> ScoreModel:
    """Take a scorecard out of use (P3.7), e.g. to settle a fairness finding."""
    tick, _ = _now(game)
    with transaction.atomic():
        try:
            model = scorecards.retire(game, number, tick)
        except scorecards.ScorecardError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "RETIRE_SCORECARD", {"number": number})
    return model


# --- Compliance's duties (P3.7) ---------------------------------------------------------


def sample_consent(game: Game, subscriber: str, month: date, size: int) -> ConsentCheck:
    """Ask a subscriber for the consent forms behind a sample of a month's enquiries."""
    tick, _ = _now(game)
    with transaction.atomic():
        try:
            check = duties.sample_consent(game, subscriber, month, size, tick)
        except duties.DutyError as exc:
            raise ClockError(str(exc)) from exc
        record(
            game, "SAMPLE_CONSENT",
            {"subscriber": subscriber, "month": month.isoformat(), "size": size},
        )  # fmt: skip
    return check


def sanction_subscriber(game: Game, subscriber: str, kind: str) -> Sanction:
    """Warn a subscriber, or suspend its enquiries for a month."""
    tick, _ = _now(game)
    with transaction.atomic():
        try:
            made = duties.sanction(game, subscriber, kind, tick)
        except duties.DutyError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "SANCTION_SUBSCRIBER", {"subscriber": subscriber, "kind": kind})
    return made


def set_retention(game: Game, years: int) -> Game:
    """How long reports keep closed accounts; the law allows 5 years at most."""
    with transaction.atomic():
        try:
            duties.set_retention(game, years)
        except duties.DutyError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "SET_RETENTION", {"years": years})
    return game


def review_access(game: Game) -> int:
    """The quarter's access review: leavers lose their access. Returns how many did."""
    tick, _ = _now(game)
    with transaction.atomic():
        removed = duties.review_access(game, tick)
        record(game, "ACCESS_REVIEW")
    return removed


def set_campaign(game: Game, on: bool) -> Game:
    with transaction.atomic():
        record(game, "SET_CAMPAIGN", {"on": on})
        game.campaign = on
        game.save(update_fields=["campaign"])
    return game


ASSISTANCE = ("assist_accuracy", "assist_recommend", "assist_extended_deadlines")


def set_assistance(game: Game, name: str, on: bool) -> Game:
    """Turn one assistance toggle on or off (Document 07, Section 12.2)."""
    if name not in ASSISTANCE:
        raise ClockError(f"Assistance must be one of {', '.join(ASSISTANCE)}")
    with transaction.atomic():
        record(game, "SET_ASSISTANCE", {"name": name, "on": on})
        setattr(game, name, on)
        game.save(update_fields=[name])
    return game


def request_funding(game: Game, amount: Decimal) -> FundingRequest:
    """Ask the shareholders for new capital (P2.10). Their answer is immediate."""
    _, at = _now(game)
    with transaction.atomic():
        try:
            request = solvency.request_funding(game, amount, at)
        except solvency.FundingError as exc:
            raise ClockError(str(exc)) from exc
        record(game, "REQUEST_FUNDING", {"amount": str(request.amount)})
    return request


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
        case "SET_MATCHING_THRESHOLDS":
            target = set_matching_thresholds(
                target, float(action.payload["auto_link"]), float(action.payload["review"])
            )
        case "SET_MATCHING_TOOLING":
            target = set_matching_tooling(target, str(action.payload["level"]))
        case "MAP_TEMPLATE":
            target = map_template(
                target,
                str(action.payload["submission"]),
                str(action.payload["file"]),
                [str(c) for c in action.payload["columns"]],
            )
        case "ADD_CLEANSING_RULE":
            p = action.payload
            add_cleansing_rule(
                target, str(p["field"]), str(p["action"]), str(p["find"]), str(p["replace"]),
                str(p["provider"]),
            )  # fmt: skip
        case "SET_CLEANSING_RULE_ACTIVE":
            set_cleansing_rule_active(
                target, str(action.payload["code"]), bool(action.payload["active"])
            )
        case "SET_RULE_OVERRIDE":
            target = set_rule_override(
                target, str(action.payload["code"]), str(action.payload["setting"])
            )
        case "SEND_FEEDBACK":
            send_feedback(target, str(action.payload["submission"]))
        case "TRAIN_PROVIDER":
            target = train_provider(target, str(action.payload["provider"]))
        case "PENALISE_PROVIDER":
            target = penalise_provider(target, str(action.payload["provider"]))
        case "SET_PAUSE_RULES":
            target = set_pause_rules(
                target, list(action.payload["severities"]), bool(action.payload["deadlines"])
            )
        case "HIRE":
            hire_candidate(target, int(action.payload["candidate"]))
        case "TRAIN_EMPLOYEE":
            p = action.payload
            train_employee(target, str(p["employee"]), str(p["work_type"]))
        case "SET_SALARY":
            set_salary(target, str(action.payload["employee"]), Decimal(action.payload["salary"]))
        case "SEND_PROPOSAL":
            send_proposal(target, str(action.payload["lender"]), Decimal(action.payload["price"]))
        case "RESPOND_TO_OUTAGE":
            respond_to_outage(target, str(action.payload["response"]))
        case "SET_IT_CAPACITY":
            target = set_it_capacity(target, str(action.payload["level"]))
        case "ANSWER_MISSION":
            answer_mission(target, str(action.payload["code"]), str(action.payload["value"]))
        case "SET_CAMPAIGN":
            target = set_campaign(target, bool(action.payload["on"]))
        case "BUILD_SCORECARD":
            p = action.payload
            build_scorecard(
                target, str(p["term"]), date.fromisoformat(p["observation"]), int(p["window"]),
                [str(f) for f in p["features"]],
            )  # fmt: skip
        case "BUILD_COMPOSITE":
            p = action.payload
            build_composite(target, date.fromisoformat(p["observation"]), int(p["window"]))
        case "DEPLOY_SCORECARD":
            deploy_scorecard(target, int(action.payload["number"]))
        case "RETIRE_SCORECARD":
            retire_scorecard(target, int(action.payload["number"]))
        case "SAMPLE_CONSENT":
            p = action.payload
            sample_consent(
                target, str(p["subscriber"]), date.fromisoformat(p["month"]), int(p["size"])
            )
        case "SANCTION_SUBSCRIBER":
            sanction_subscriber(
                target, str(action.payload["subscriber"]), str(action.payload["kind"])
            )
        case "SET_RETENTION":
            target = set_retention(target, int(action.payload["years"]))
        case "ACCESS_REVIEW":
            review_access(target)
        case "SWITCH_ROLE":
            target = switch_role(target, str(action.payload["role"]))
        case "SET_ASSISTANCE":
            target = set_assistance(target, str(action.payload["name"]), bool(action.payload["on"]))
        case "REQUEST_FUNDING":
            request_funding(target, Decimal(action.payload["amount"]))
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
    ended_reason: str = ""
    role: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "game": self.game_id,
            "tick": self.tick,
            "now": self.now.isoformat(),
            "date": self.now.date().isoformat(),
            "weekday": self.now.strftime("%A"),
            "time": self.now.strftime("%H:%M"),
            "status": self.status,
            "ended_reason": self.ended_reason,
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
            "role": self.role,
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
        ended_reason=game.ended_reason,
        role=roles.as_dict(
            game, cal.tick_end(game.role_ready_tick) if game.role_ready_tick else None
        ),
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
