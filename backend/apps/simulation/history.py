"""Pre-loading an established bureau's history (Established scenario).

A new game's bureau has been operating for years. Its database is built the
honest way: the providers' files for the last months of history are put
through the same pipeline, in order, and the review cases they raise are
settled by the team that worked there before the player arrived, with
realistic accuracy (ASSUMPTION A-029). The bureau therefore starts with a
believable past, including a few of its predecessors' mistakes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from apps.bureau.submissions.pipeline import process_submission
from apps.bureau.submissions.review import apply_decision
from apps.workitems.models import ItemStatus, ResolvedBy, WorkItem
from apps.workitems.resolution import judge
from apps.workitems.work import explain
from apps.world.generation.rng import stream
from apps.world.models import Lender, ProviderSubmission
from apps.world.provider_files import generate_submission, month_end

from .bridge import deliver
from .judgement import sync_work_items
from .models import Game

# Skill and morale of the team that settled past review cases (ASSUMPTION A-029).
FORMER_TEAM_SKILL = 0.75
FORMER_TEAM_MORALE = 0.7
DEFAULT_HISTORY_MONTHS = 12


def history_periods(game: Game, months: int) -> list[date]:
    """The months to pre-load: those whose files would have arrived before play began.

    The last generated month is not included: its files arrive in the first
    month of play.
    """
    generated_end = date.fromisoformat(game.world.config["history_end"])
    periods: list[date] = []
    current = generated_end.replace(day=1) - timedelta(days=1)  # the month before
    while len(periods) < months and current >= game.world.history_start:
        periods.append(current)
        current = current.replace(day=1) - timedelta(days=1)
    return sorted(periods)


def preload_history(
    game: Game,
    months: int = DEFAULT_HISTORY_MONTHS,
    progress: Callable[[str], None] | None = None,
) -> int:
    """Load the last ``months`` months of provider files into the bureau. Returns runs made."""
    runs = 0
    periods = history_periods(game, months)
    for n, period in enumerate(periods, start=1):
        if progress is not None:
            progress(f"Loading history: {period:%B %Y} ({n} of {len(periods)})")
        for institution in game.organization.institutions.filter(is_active=True).order_by(
            "institution_code"
        ):
            lender = Lender.objects.get(world=game.world, code=institution.institution_code)
            world_sub = ProviderSubmission.objects.filter(lender=lender, period=period).first()
            if world_sub is None:
                world_sub = generate_submission(game.world, lender, period).submission
            if not world_sub.files.exists():
                continue
            submission = deliver(game, world_sub)
            at = datetime.combine(world_sub.arrival_date, time(17, 0), tzinfo=UTC)
            process_submission(submission, at=at)
            runs += 1
            _settle_cases(game, at)
    return runs


def _settle_cases(game: Game, at: datetime) -> None:
    """The former team works the queue until it is empty (decisions can open new cases)."""
    while (
        sync_work_items(game, 0)
        or WorkItem.objects.filter(organization=game.organization, status=ItemStatus.OPEN).exists()
    ):
        for item in WorkItem.objects.filter(
            organization=game.organization, status=ItemStatus.OPEN
        ).order_by("item_number"):
            rng = stream(game.world.seed, f"history-item:{item.item_number}")
            result = judge(
                item.item_type,
                item.correct_decision,
                item.difficulty,
                FORMER_TEAM_SKILL,
                FORMER_TEAM_MORALE,
                0.0,
                rng,
            )
            case = apply_decision(item.case, result.decision, "Former staff", at)
            item.status = ItemStatus.DONE
            item.resolved_tick = 0
            item.resolved_by = ResolvedBy.HISTORIC
            item.decision = result.decision
            item.is_correct = result.decision == item.correct_decision
            item.confidence = result.confidence
            item.minutes_remaining = 0.0
            item.explanation = explain(case, result)
            item.save()


__all__ = ["DEFAULT_HISTORY_MONTHS", "history_periods", "month_end", "preload_history"]
