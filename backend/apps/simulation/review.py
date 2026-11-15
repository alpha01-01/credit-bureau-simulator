# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""The monthly Data Quality Review: the first debrief (P2.3; Document 07, Section 11.2).

At the end of each month the game reveals a slice of the hidden truth:

* match decisions: how many were right, which were false merges (two people
  made one) and false splits (one person made two);
* triage decisions: genuine records sent back to the provider, and wrong
  corrections loaded;
* records not loaded (unloadable, or discarded as duplicates), by the rule that
  stopped them, and how many were genuine (everything but rows a provider sent twice);
* the data assets: what the player saw and estimated, beside the truth;
* the consequence chains of the month: wrong reports and the decisions behind them.

The review is kept as it was at the month's end. Every figure keeps the natural
keys of its records, so it drills down to them (and survives copying a game).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from django.db import connection, models

from apps.bureau.quality.models import CaseType, Decision, ValidationIssue
from apps.bureau.quality.models import Severity as IssueSeverity
from apps.bureau.quality.rules import RULES
from apps.bureau.submissions.models import (
    ProcessingRun,
    RecordStatus,
    StagingRecord,
    Submission,
    SubmissionFile,
)
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.models import FileDefect

from . import assets
from .clock import Calendar
from .models import Consequence, DataQualityReview, Delivery, Game

REVIEW_FORMAT = "2"  # 2: matching (P2.4)
DESCRIPTIONS = {"DUPLICATE": "Discarded as a repeat of another row in the same submission"}


def _t(model: type[models.Model]) -> str:
    return model._meta.db_table


def month_ticks(cal: Calendar, period: date) -> tuple[int, int]:
    """The first and last tick of the month ending on ``period``."""
    first = cal.first_tick_of_day(cal.index_of(period.replace(day=1)))
    after = cal.first_tick_of_day(cal.index_of(period + timedelta(days=1)))
    return first, after - 1


def build_review(game: Game, cal: Calendar, period: date, tick: int) -> DataQualityReview:
    """Review the month ending on ``period`` (called at its last tick)."""
    first, _last = month_ticks(cal, period)
    refs: dict[str, list[Any]] = {}
    figures: dict[str, Any] = {"format": REVIEW_FORMAT, "period": period.isoformat()}
    figures["match"], figures["triage"] = _decisions(game, first, tick, refs)
    figures["rejected"] = _rejected(game, period, refs)
    today = cal.tick_end(tick).date()
    visible, truth = assets.month_end_assets(game, today)
    figures["assets"] = {"visible": visible, "truth": truth}
    org = game.organization
    figures["matching"] = {
        "tooling": org.matching_tooling,
        "auto_link": org.match_auto_link,
        "review": org.match_review,
        "methods": assets.link_audit(
            game,
            datetime.combine(period.replace(day=1), time(0), tzinfo=UTC),
            datetime.combine(period + timedelta(days=1), time(0), tzinfo=UTC),
        ),
    }
    figures["consequences"] = _consequences(game, first, tick, refs)
    review, _ = DataQualityReview.objects.update_or_create(
        game=game, period=period, defaults={"tick": tick, "figures": figures, "refs": refs}
    )
    return review


# --- Decisions ---------------------------------------------------------------------------


def _decisions(
    game: Game, first: int, last: int, refs: dict[str, list[Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    items = WorkItem.objects.filter(
        organization=game.organization,
        status=ItemStatus.DONE,
        resolved_tick__gte=first,
        resolved_tick__lte=last,
    ).order_by("item_number")
    groups: dict[str, list[int]] = defaultdict(list)
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "right": 0})
    for item in items.values("item_number", "item_type", "decision", "correct_decision",
                             "is_correct", "resolved_by"):  # fmt: skip
        kind = "match" if item["item_type"] == CaseType.MATCH_REVIEW else "triage"
        groups[f"{kind}.all"].append(item["item_number"])
        tally = by[f"{kind}.{item['resolved_by']}"]
        tally["total"] += 1
        if item["is_correct"]:
            groups[f"{kind}.right"].append(item["item_number"])
            tally["right"] += 1
            continue
        groups[f"{kind}.{_mistake(item['decision'], item['correct_decision'])}"].append(
            item["item_number"]
        )
    refs.update(groups)

    def n(key: str) -> int:
        return len(groups.get(key, []))

    def resolvers(kind: str) -> dict[str, dict[str, int]]:
        return {k.split(".", 1)[1]: v for k, v in by.items() if k.startswith(f"{kind}.")}

    match = {
        "total": n("match.all"),
        "right": n("match.right"),
        "false_merges": n("match.false_merge"),
        "false_splits": n("match.false_split"),
        "other_wrong": n("match.other_wrong"),
        "by": resolvers("match"),
    }
    triage = {
        "total": n("triage.all"),
        "right": n("triage.right"),
        "genuine_returned": n("triage.genuine_returned"),
        "wrongly_loaded": n("triage.wrongly_loaded"),
        "other_wrong": n("triage.other_wrong"),
        "by": resolvers("triage"),
    }
    return match, triage


def _mistake(decision: str, correct: str) -> str:
    if decision == Decision.SAME_CUSTOMER and correct == Decision.DIFFERENT_CUSTOMER:
        return "false_merge"
    if decision == Decision.DIFFERENT_CUSTOMER and correct == Decision.SAME_CUSTOMER:
        return "false_split"
    if decision == Decision.RETURN_TO_PROVIDER and correct == Decision.CORRECT_AND_LOAD:
        return "genuine_returned"
    if decision == Decision.CORRECT_AND_LOAD and correct == Decision.RETURN_TO_PROVIDER:
        return "wrongly_loaded"
    return "other_wrong"


# --- Records left unloadable ------------------------------------------------------------

_UNLOADABLE = f"""
SELECT s.submission_reference, f.file_name, sr.source_row_number,
       CASE WHEN sr.record_status = %(duplicate)s THEN 'DUPLICATE' ELSE
       (SELECT min(vi.rule_code) FROM {_t(ValidationIssue)} vi
         WHERE vi.record_id = sr.id AND vi.severity = %(error)s) END AS rule,
       EXISTS (SELECT 1 FROM {_t(FileDefect)} d
                WHERE d.file_id = dl.world_file_id AND d.row_number = sr.source_row_number
                  AND d.defect_type = 'DUPLICATE_ROW') AS repeated
FROM {_t(StagingRecord)} sr
JOIN {_t(ProcessingRun)} r ON r.id = sr.run_id
JOIN {_t(Submission)} s ON s.id = r.submission_id
JOIN {_t(SubmissionFile)} f ON f.id = sr.file_id
JOIN {_t(Delivery)} dl ON dl.game_id = %(game)s AND dl.bureau_file_id = f.id
WHERE s.organization_id = %(org)s AND sr.record_status IN (%(status)s, %(duplicate)s)
  AND r.completed_at >= %(start)s AND r.completed_at < %(end)s
ORDER BY s.submission_reference, f.file_name, sr.source_row_number
"""


def _rejected(game: Game, period: date, refs: dict[str, list[Any]]) -> dict[str, Any]:
    """Records from this month's runs that were not loaded, by the rule that stopped them.

    Unloadable records and those discarded as duplicates. A record is genuine unless
    the provider really did send its row twice.
    """
    params: dict[str, Any] = {
        "game": game.pk,
        "org": game.organization_id,
        "status": RecordStatus.UNLOADABLE,
        "duplicate": RecordStatus.DUPLICATE,
        "error": IssueSeverity.ERROR,
        "start": datetime.combine(period.replace(day=1), time(0), tzinfo=UTC),
        "end": datetime.combine(period + timedelta(days=1), time(0), tzinfo=UTC),
    }
    rules: dict[str, dict[str, int]] = defaultdict(lambda: {"records": 0, "genuine": 0})
    with connection.cursor() as cursor:
        cursor.execute(_UNLOADABLE, params)
        for reference, file_name, row, rule, repeated in cursor.fetchall():
            code = rule or "OTHER"
            rules[code]["records"] += 1
            rules[code]["genuine"] += int(not repeated)
            key = f"rejected.{code}.{'repeated' if repeated else 'genuine'}"
            refs.setdefault(key, []).append([reference, file_name, row])
    listed = [
        {
            "rule": code,
            "description": DESCRIPTIONS.get(code) or RULES.get(code, "No single rule recorded"),
            "records": t["records"],
            "genuine": t["genuine"],
        }
        for code, t in sorted(rules.items(), key=lambda kv: (-kv[1]["records"], kv[0]))
    ]
    return {
        "total": sum(r["records"] for r in listed),
        "genuine": sum(r["genuine"] for r in listed),
        "rules": listed,
    }


# --- Consequences ------------------------------------------------------------------------


def _consequences(game: Game, first: int, last: int, refs: dict[str, list[Any]]) -> dict[str, Any]:
    rows = (
        Consequence.objects.filter(game=game, tick__gte=first, tick__lte=last)
        .select_related("enquiry", "work_item")
        .order_by("tick", "pk")
    )
    chains = [
        {
            "at": c.sim_time.isoformat(),
            "effect": c.effect,
            "enquiry": c.enquiry.enquiry_reference,
            "subscriber": c.subscriber_code,
            "accounts": c.accounts,
            "cause": c.cause,
            "work_item": c.work_item.item_number if c.work_item else None,
            "provider": c.provider,
            "provider_customer": c.provider_customer,
            "detail": c.detail,
        }
        for c in rows
    ]
    refs["consequences"] = [[c["enquiry"], c["provider"], c["provider_customer"]] for c in chains]
    return {
        "mixed_reports": len({c["enquiry"] for c in chains if c["effect"] == "MIXED_REPORT"}),
        "incomplete_reports": len(
            {c["enquiry"] for c in chains if c["effect"] == "INCOMPLETE_REPORT"}
        ),
        "from_decisions": sum(c["cause"] == "DECISION" for c in chains),
        "automatic": sum(c["cause"] == "AUTOMATIC" for c in chains),
        "chains": chains,
    }
