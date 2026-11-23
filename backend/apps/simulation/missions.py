"""The learning campaign: missions M1-M6 and their debriefs (P2.11; Document 07, Section 11).

Missions sit on top of the normal simulation: no scripted data. Each has
objectives the bureau can see for itself (files processed, decisions taken, a
question about its own figures) and, once done, a debrief that reveals the slice
of hidden truth the mission was about. Missions run in order; the campaign is
optional (``Game.campaign``).

ASSUMPTION A-068: the objectives and targets below (3 triage decisions, 5 match
reviews, 20 enquiries; answers exact, or within one percentage point or one cedi).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.bureau.core.models import Enquiry, EnquiryOutcome
from apps.bureau.quality.models import CaseType, CleansingRule, Decision
from apps.bureau.submissions.models import FeedbackReport, ProcessingRun, Submission
from apps.finance.models import Invoice, JournalEntry
from apps.finance.statements import income_statement
from apps.workitems.models import ResolvedBy, WorkItem

from .models import EnquiryJudgement, Game, MissionState, Severity

TRIAGE_TARGET, REVIEW_TARGET, ENQUIRY_TARGET = 3, 5, 20


@dataclass
class Objective:
    text: str
    done: bool
    progress: str = ""


@dataclass
class Question:
    text: str
    answer: Decimal | None  # None while the question cannot be asked yet
    tolerance: Decimal = Decimal("0")
    unit: str = ""


@dataclass
class Check:
    objectives: list[Objective]
    question: Question | None = None
    figures: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Mission:
    code: str
    title: str
    concept: str
    handbook: tuple[str, ...]
    check: Callable[[Game], Check]
    debrief: Callable[[Game, Check], dict[str, Any]]


def _since(game: Game) -> datetime:
    return datetime.combine(game.clock_start, time(0), tzinfo=UTC)


def _runs(game: Game) -> Any:
    """Processing runs of files received during play, in the order they finished."""
    return (
        ProcessingRun.objects.filter(
            submission__organization=game.organization,
            submission__received_at__gte=_since(game),
            completed_at__isnull=False,
        )
        .select_related("submission__institution")
        .order_by("completed_at", "submission__submission_reference", "run_number")
    )


def _player_items(game: Game, item_type: str) -> Any:
    return WorkItem.objects.filter(
        organization=game.organization, item_type=item_type, resolved_by=ResolvedBy.PLAYER
    ).order_by("resolved_tick", "item_number")


def _count(done: int, target: int) -> str:
    return f"{min(done, target)} of {target}"


# --- M1 First file -------------------------------------------------------------------------


def _m1(game: Game) -> Check:
    received = Submission.objects.filter(
        organization=game.organization, received_at__gte=_since(game)
    ).exists()
    first = _runs(game).first()
    question = Question(
        f"How many records in {first.submission.submission_reference} "
        f"({first.submission.institution.institution_name}) could not be loaded? (Submissions)"
        if first
        else "How many records in the first file could not be loaded? (Asked once it is "
        "processed.)",
        Decimal(first.records_unloadable) if first else None,
        unit="records",
    )
    figures = {}
    if first:
        figures = {
            "reference": first.submission.submission_reference,
            "received": first.records_received,
            "accepted": first.records_accepted,
            "unloadable": first.records_unloadable,
            "duplicates": first.records_duplicated,
            "pending": first.records_pending,
        }
    return Check(
        [
            Objective("A provider's file arrives and is registered", received),
            Objective("The overnight batch validates and loads it", first is not None),
        ],
        question,
        figures,
    )


def _m1_debrief(game: Game, check: Check) -> dict[str, Any]:
    f = check.figures
    return {
        "headline": f"{f['reference']}: {f['accepted']} of {f['received']} records loaded.",
        "figures": [
            ["Records received", f["received"]],
            ["Loaded", f["accepted"]],
            ["Could not be loaded", f["unloadable"]],
            ["Sent twice (duplicates)", f["duplicates"]],
            ["Held for a decision", f["pending"]],
        ],
        "lessons": [
            "Every file is registered before it is read: who sent it, for which month, when.",
            "Validation checks the file against the template first, then every field. A "
            "record that fails a rule the bureau will not relax cannot be loaded, and what "
            "it says reaches no report until the provider sends it again.",
            "The processing summary must reconcile: received = loaded + unloadable + "
            "duplicates + held.",
        ],
    }


# --- M2 Dirty data -------------------------------------------------------------------------


def _m2(game: Game) -> Check:
    org = game.organization
    triaged = _player_items(game, CaseType.UNLOADABLE_TRIAGE).count()
    feedback = FeedbackReport.objects.filter(organization=org).exists()
    rule = CleansingRule.objects.filter(organization=org).exists() or bool(org.rule_overrides)
    return Check(
        [
            Objective(
                f"Decide {TRIAGE_TARGET} unloadable records yourself (Work queue; "
                "your team leaves them for you until you have)",
                triaged >= TRIAGE_TARGET,
                _count(triaged, TRIAGE_TARGET),
            ),
            Objective("Send a provider its feedback report (Submissions)", feedback),
            Objective("Add a cleansing rule, or relax a check (Rules)", rule),
        ]
    )


def _m2_debrief(game: Game, check: Check) -> dict[str, Any]:
    items = list(_player_items(game, CaseType.UNLOADABLE_TRIAGE)[:TRIAGE_TARGET])
    right = sum(bool(i.is_correct) for i in items)
    loaded_wrong = sum(
        1 for i in items if not i.is_correct and i.decision == Decision.CORRECT_AND_LOAD
    )
    return {
        "headline": f"{right} of your {len(items)} triage decisions were right.",
        "figures": [
            ["Your decisions", len(items)],
            ["Right", right],
            ["Loaded with a wrong correction", loaded_wrong],
            ["Sent back when the correction was right", len(items) - right - loaded_wrong],
        ],
        "lessons": [
            "A proposed correction is a guess about what the provider meant. Load it when "
            "the rest of the record makes it certain; otherwise send it back.",
            "A wrong correction is worse than a missing record: it puts a false fact on "
            "someone's report.",
            "Feedback reports and the provider's own fixes cure dirty data at the source; "
            "cleansing rules only treat the symptom you can name.",
        ],
    }


# --- M3 Is this the same person? -----------------------------------------------------------


def _m3(game: Game) -> Check:
    done = _player_items(game, CaseType.MATCH_REVIEW).count()
    return Check(
        [
            Objective(
                f"Decide {REVIEW_TARGET} match reviews yourself (Work queue)",
                done >= REVIEW_TARGET,
                _count(done, REVIEW_TARGET),
            )
        ]
    )


def _m3_debrief(game: Game, check: Check) -> dict[str, Any]:
    items = list(_player_items(game, CaseType.MATCH_REVIEW)[:REVIEW_TARGET])
    right = sum(bool(i.is_correct) for i in items)
    merges = sum(1 for i in items if not i.is_correct and i.decision == Decision.SAME_CUSTOMER)
    splits = sum(1 for i in items if not i.is_correct and i.decision == Decision.DIFFERENT_CUSTOMER)
    return {
        "headline": f"{right} of your {len(items)} match decisions were right.",
        "figures": [
            ["Your decisions", len(items)],
            ["Right", right],
            ["False merges (two people joined)", merges],
            ["False splits (one person divided)", splits],
        ],
        "lessons": [
            "A false merge puts someone else's debts on a person's report: a lender may "
            "refuse them, and they will dispute it.",
            "A false split hides part of a person's history: their report looks thinner or "
            "cleaner than it is.",
            "The thresholds in Matching policy trade one error for the other.",
        ],
    }


# --- M4 Month two --------------------------------------------------------------------------


def _m4(game: Game) -> Check:
    runs = list(_runs(game))
    periods = sorted({r.submission.reporting_period for r in runs})
    latest = runs[-1] if len(periods) >= 2 else None
    question = Question(
        f"In {latest.submission.submission_reference}, how many accounts were new to the bureau?"
        if latest
        else "How many accounts in a second month's file were new to the bureau? (Asked once "
        "it is processed.)",
        Decimal(latest.accounts_created) if latest else None,
        unit="accounts",
    )
    figures = {}
    if latest:
        figures = {
            "reference": latest.submission.submission_reference,
            "new_accounts": latest.accounts_created,
            "observations": latest.observations_created,
            "new_customers": latest.customers_created,
        }
    return Check(
        [
            Objective(
                "Files for a second reporting month are processed",
                len(periods) >= 2,
                _count(len(periods), 2) + " months",
            )
        ],
        question,
        figures,
    )


def _m4_debrief(game: Game, check: Check) -> dict[str, Any]:
    f = check.figures
    return {
        "headline": f"{f['reference']}: {f['observations']} monthly observations, "
        f"{f['new_accounts']} new accounts.",
        "figures": [
            ["Monthly observations recorded", f["observations"]],
            ["Accounts new to the bureau", f["new_accounts"]],
            ["Customers new to the bureau", f["new_customers"]],
        ],
        "lessons": [
            "Most of a month's file is the same accounts again: each month adds one more "
            "observation of balance, arrears and status to an account the bureau knows.",
            "That history is what a report shows: 12 months of days past due, not one.",
            "Every observation keeps its lineage: which file, which row, which run.",
        ],
    }


# --- M5 The first report -------------------------------------------------------------------


def _enquiries(game: Game) -> Any:
    return Enquiry.objects.filter(organization=game.organization, enquired_at__gte=_since(game))


def _today(game: Game) -> date:
    from .engine import calendar  # here: the engine imports this module

    cal = calendar(game)
    return (cal.tick_end(game.current_tick) if game.current_tick else cal.tick_start(1)).date()


def _m5(game: Game) -> Check:
    total = _enquiries(game).count()
    month = Enquiry.objects.filter(
        organization=game.organization, enquired_at__date__gte=_today(game).replace(day=1)
    )
    in_month = month.count()
    hits = month.filter(outcome=EnquiryOutcome.HIT).count()
    rate = (Decimal(hits) * 100 / in_month).quantize(Decimal("0.1")) if in_month else None
    return Check(
        [
            Objective(
                f"Lenders check the bureau {ENQUIRY_TARGET} times",
                total >= ENQUIRY_TARGET,
                _count(total, ENQUIRY_TARGET),
            )
        ],
        Question(
            "What is this month's hit rate, as a percentage? (Dashboard)",
            rate if total >= ENQUIRY_TARGET else None,
            tolerance=Decimal("1"),
            unit="%",
        ),
        {"enquiries": total},
    )


def _m5_debrief(game: Game, check: Check) -> dict[str, Any]:
    judged = EnquiryJudgement.objects.filter(game=game, enquiry__enquired_at__gte=_since(game))
    right = judged.filter(hit=True, correct_person=True).count()
    wrong = judged.filter(hit=True, correct_person=False).count()
    missed = judged.filter(hit=False, should_hit=True).count()
    nothing = judged.filter(hit=False, should_hit=False).count()
    return {
        "headline": f"Of {judged.count()} enquiries, {right} found the right person.",
        "figures": [
            ["Found the right person", right],
            ["Found the wrong person", wrong],
            ["Missed someone we hold (no hit)", missed],
            ["Rightly found nothing (no credit history)", nothing],
        ],
        "lessons": [
            "Every enquiry carries a permissible purpose and the applicant's consent; the "
            "bureau may not answer one without them.",
            "A hit rate counts only finding someone. Whether it was the right someone is "
            "the question the lender cares about, and only a dispute or a bad loan tells.",
            "A missed hit usually means a false split or an identifier the bureau does not hold.",
        ],
    }


# --- M6 Closing the month ------------------------------------------------------------------


def _first_invoice(game: Game) -> Invoice | None:
    return (
        Invoice.objects.filter(organization=game.organization, issue_date__gte=game.clock_start)
        .order_by("issue_date", "invoice_number")
        .first()
    )


def _month(invoice: Invoice) -> tuple[date, date]:
    start = invoice.period_start.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return start, end


def _m6(game: Game) -> Check:
    invoice = _first_invoice(game)
    question = Question(
        "What was the bureau's net profit (negative for a loss) for "
        f"{_month(invoice)[0]:%B %Y}, in GHS? (Finance)"
        if invoice
        else "What was the bureau's net profit for its first month? (Asked once it is invoiced.)",
        None,
        tolerance=Decimal("1"),
        unit="GHS",
    )
    figures: dict[str, Any] = {}
    if invoice:
        start, end = _month(invoice)
        statement = income_statement(game.organization, start, end)
        question.answer = statement["net_profit"]
        figures = {
            "month": start.isoformat(),
            "income": str(statement["total_income"]),
            "expenses": str(statement["total_expenses"]),
            "net": str(statement["net_profit"]),
        }
    return Check(
        [Objective("The month is closed: usage invoiced to subscribers", invoice is not None)],
        question,
        figures,
    )


def _m6_debrief(game: Game, check: Check) -> dict[str, Any]:
    f = check.figures
    entries = JournalEntry.objects.filter(organization=game.organization).count()
    return {
        "headline": f"{date.fromisoformat(f['month']):%B %Y}: income GHS {f['income']}, "
        f"expenses GHS {f['expenses']}, net GHS {f['net']}.",
        "figures": [
            ["Income", f"GHS {f['income']}"],
            ["Expenses", f"GHS {f['expenses']}"],
            ["Net profit", f"GHS {f['net']}"],
            ["Journal entries posted so far, every one balanced", entries],
        ],
        "lessons": [
            "Each report sold is usage; at the month end usage becomes an invoice, and the "
            "invoice a debit to receivables and a credit to revenue.",
            "Every business event posts a balanced entry; the statements are only sums of "
            "those entries.",
            "Revenue is earned when the report is delivered, not when the subscriber pays: "
            "profit and cash are different things.",
        ],
    }


MISSIONS: tuple[Mission, ...] = (
    Mission("M1", "First file", "Submission registration, template validation, the "
            "processing summary", ("submission", "validation", "processing-summary"),
            _m1, _m1_debrief),
    Mission("M2", "Dirty data", "Field validation, cleansing, the unloadable record, provider "
            "feedback", ("unloadable-record", "cleansing", "provider-feedback"),
            _m2, _m2_debrief),
    Mission("M3", "Is this the same person?", "Identity resolution, false merges versus false "
            "splits", ("identity-resolution", "false-merge", "false-split"), _m3, _m3_debrief),
    Mission("M4", "Month two", "Monthly observations versus new accounts; history and lineage",
            ("monthly-observation", "days-past-due", "lineage"), _m4, _m4_debrief),
    Mission("M5", "The first report", "Enquiries, consent and permissible purpose, hit rates",
            ("enquiry", "permissible-purpose", "consent", "hit-rate"), _m5, _m5_debrief),
    Mission("M6", "Closing the month", "Usage billing, invoices, double-entry posting, the P&L",
            ("usage-billing", "double-entry", "income-statement"), _m6, _m6_debrief),
)  # fmt: skip
BY_CODE = {m.code: m for m in MISSIONS}


class MissionError(Exception):
    pass


def _state(game: Game, code: str) -> MissionState:
    record, _ = MissionState.objects.get_or_create(game=game, code=code)
    return record


def current(game: Game) -> Mission | None:
    """The first mission not yet completed, if the campaign is on."""
    if not game.campaign:
        return None
    done = set(
        MissionState.objects.filter(game=game, completed_tick__isnull=False).values_list(
            "code", flat=True
        )
    )
    return next((m for m in MISSIONS if m.code not in done), None)


def held_for_player(game: Game) -> frozenset[str]:
    """Work item types the team leaves for the player while a mission asks for them.

    M2 asks the player to decide unloadable records; in a small world they are few,
    and the team would otherwise take them first (P3.0).
    """
    if not game.campaign:
        return frozenset()
    mission = current(game)
    if mission is None or mission.code != "M2":
        return frozenset()
    if _player_items(game, CaseType.UNLOADABLE_TRIAGE).count() >= TRIAGE_TARGET:
        return frozenset()
    return frozenset({CaseType.UNLOADABLE_TRIAGE})


def answered(record: MissionState) -> bool:
    return any(a["right"] for a in record.answers)


def _complete(check: Check, record: MissionState) -> bool:
    return all(o.done for o in check.objectives) and (check.question is None or answered(record))


def update(game: Game, tick: int, add: Any) -> None:
    """After a tick or an answer: has the current mission been completed?"""
    mission = current(game)
    if mission is None:
        return
    check = mission.check(game)
    record = _state(game, mission.code)
    if not _complete(check, record):
        return
    record.completed_tick = tick
    record.debrief = mission.debrief(game, check)
    record.save(update_fields=["completed_tick", "debrief"])
    following = current(game)
    add(
        "MISSION_COMPLETE", Severity.INFO,
        f"Mission {mission.code} complete: {mission.title}",
        record.debrief["headline"]
        + (f" Next: {following.code} {following.title}." if following else " Campaign done."),
        {"screen": "missions", "params": {"code": mission.code}},
    )  # fmt: skip


def parse(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").replace("GHS", "").replace("%", "").strip())
    except InvalidOperation as exc:
        raise MissionError(f"{value!r} is not a number") from exc


def answer(game: Game, code: str, value: str, tick: int) -> bool:
    """The player answers the current mission's question. True if right."""
    mission = current(game)
    if mission is None or mission.code != code:
        raise MissionError(f"{code} is not the current mission")
    question = mission.check(game).question
    if question is None or question.answer is None:
        raise MissionError("There is no question to answer yet")
    given = parse(value)
    right = abs(given - question.answer) <= question.tolerance
    record = _state(game, code)
    record.answers = [*record.answers, {"tick": tick, "value": str(given), "right": right}]
    record.save(update_fields=["answers"])
    return right


def overview(game: Game) -> list[dict[str, Any]]:
    """Every mission, with its objectives (for the current one) and debrief (when done)."""
    states = {s.code: s for s in MissionState.objects.filter(game=game)}
    now = current(game)
    rows = []
    for mission in MISSIONS:
        record = states.get(mission.code)
        done = record is not None and record.completed_tick is not None
        row: dict[str, Any] = {
            "code": mission.code,
            "title": mission.title,
            "concept": mission.concept,
            "handbook": list(mission.handbook),
            "status": "DONE"
            if done
            else "CURRENT"
            if now and now.code == mission.code
            else "LATER",
            "debrief": record.debrief if done and record else None,
        }
        if now and now.code == mission.code:
            check = mission.check(game)
            row["objectives"] = [o.__dict__ for o in check.objectives]
            q = check.question
            row["question"] = (
                {
                    "text": q.text,
                    "ready": q.answer is not None,
                    "unit": q.unit,
                    "answered": bool(record and answered(record)),
                    "attempts": len(record.answers) if record else 0,
                }
                if q
                else None
            )
        rows.append(row)
    return rows
