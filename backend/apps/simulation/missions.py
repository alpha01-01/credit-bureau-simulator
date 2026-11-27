"""The learning campaign: missions and their debriefs (P2.11, P3.14; Document 07, Section 11).

Missions sit on top of the normal simulation: no scripted data. Each has
objectives the bureau can see for itself (files processed, decisions taken, a
question about its own figures) and, once done, a debrief that reveals the slice
of hidden truth the mission was about. The campaign is optional (``Game.campaign``).

Two tracks (P3.14): the campaign M1-M8 runs in order; the workspace missions W1-W5,
one for each department's workspace, are open together and done in any order.
M7 is the one mission that arranges its situation: if no dispute has come by the
time it begins, a subject of one of the bureau's own reports files one (A-085).

ASSUMPTION A-068: the objectives and targets below (3 triage decisions, 5 match
reviews, 20 enquiries; answers exact, or within one percentage point or one cedi).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.bureau.analytics.portfolio import portfolio
from apps.bureau.core.models import CreditAccount, Enquiry, EnquiryOutcome
from apps.bureau.quality.models import CaseType, CleansingRule, CorrectionRecord, Decision, Dispute
from apps.bureau.submissions.models import FeedbackReport, ProcessingRun, Submission
from apps.finance.events import MATCHING_TOOLING_COST
from apps.finance.models import Invoice, JournalEntry, SupplierBill
from apps.finance.statements import income_statement
from apps.org.models import Employee
from apps.workitems.models import ItemStatus, ResolvedBy, WorkItem

from . import compliance
from .clock import TICKS_PER_DAY
from .models import (
    ConsentCheck,
    EnquiryJudgement,
    EventStatus,
    EventType,
    Game,
    LenderResearch,
    MissionState,
    Proposal,
    ScoreModel,
    Severity,
)

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
    # For an answer too costly to work out every tick: worked out when the player answers.
    compute: Callable[[], Decimal | None] | None = None

    @property
    def ready(self) -> bool:
        return self.answer is not None or self.compute is not None

    def expected(self) -> Decimal | None:
        return self.answer if self.answer is not None or self.compute is None else self.compute()


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
    track: str = "CAMPAIGN"  # or WORKSPACE: open together, in any order (P3.14)
    role: str = ""  # whose workspace it is


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


# --- M7 The dispute (P3.14) ----------------------------------------------------------------


def _began(game: Game, code: str) -> int:
    """The tick a campaign mission became current: when the one before it was completed."""
    index = next(n for n, m in enumerate(CAMPAIGN) if m.code == code)
    if index == 0:
        return 0
    before = MissionState.objects.filter(game=game, code=CAMPAIGN[index - 1].code).first()
    return before.completed_tick or 0 if before else 0


def _at(game: Game, tick: int) -> datetime:
    from .engine import calendar  # here: the engine imports this module

    return calendar(game).tick_end(tick) if tick else _since(game)


def _disputes_since(game: Game, tick: int) -> Any:
    return Dispute.objects.filter(
        organization=game.organization, received_at__gte=_at(game, tick)
    ).order_by("dispute_number")


def _player_disputes(game: Game, tick: int) -> Any:
    return (
        _player_items(game, CaseType.DISPUTE)
        .filter(resolved_tick__gte=tick)
        .select_related("case__dispute")
    )


def arrange_dispute(game: Game, tick: int) -> None:
    """M7 needs a dispute. If none has come since it began, one of the bureau's own
    report subjects files one (Document 07, Section 11.1: missions choose the events
    that produce the situation they teach). Arranged once; replay arranges the same."""
    began = _began(game, "M7")
    if _disputes_since(game, began).exists():
        return
    if game.events.filter(event_type=EventType.DISPUTE_FILED, status=EventStatus.PENDING).exists():
        return
    if game.events.filter(event_type=EventType.DISPUTE_FILED, payload__mission="M7").exists():
        return
    compliance.mission_dispute(game, tick)


def _m7(game: Game) -> Check:
    began = _began(game, "M7")
    received = _disputes_since(game, began).first()
    decided = _player_disputes(game, began).first()
    dispute = decided.case.dispute if decided is not None else None
    in_time = (
        dispute is not None
        and dispute.resolved_at is not None
        and dispute.resolved_at.date() <= dispute.due_date
    )
    return Check(
        [
            Objective(
                "A subject disputes their credit report (Disputes)"
                + (f": dispute {received.dispute_number}, due by {received.due_date:%d %B}"
                   if received else ""),
                received is not None,
            ),
            Objective(
                "Decide a dispute yourself, as Head of Compliance (Work queue; your team "
                "leaves disputes for you until you have)",
                decided is not None,
            ),
            Objective("Settle it within its statutory deadline", in_time),
        ],
        Question(
            "How many working days does the bureau have to settle a dispute? (Disputes)",
            Decimal(compliance.STATUTORY_WORKING_DAYS),
            unit="working days",
        ),
        {"item": decided.item_number if decided else None},
    )  # fmt: skip


def _m7_debrief(game: Game, check: Check) -> dict[str, Any]:
    item = WorkItem.objects.select_related("case__dispute").get(
        organization=game.organization, item_number=check.figures["item"]
    )
    dispute = item.case.dispute
    if dispute is None or dispute.resolved_at is None:
        raise MissionError(f"Work item {item.item_number} settled no dispute")
    corrected = CorrectionRecord.objects.filter(dispute=dispute).count()
    upheld = item.decision == Decision.UPHOLD_DISPUTE
    return {
        "headline": f"Dispute {dispute.dispute_number}: you "
        f"{'upheld' if upheld else 'rejected'} it, and you were "
        f"{'right' if item.is_correct else 'wrong'}.",
        "figures": [
            ["Received", f"{dispute.received_at:%d %B}"],
            ["Due by", f"{dispute.due_date:%d %B}"],
            ["Settled", f"{dispute.resolved_at:%d %B}"],
            ["Accounts disputed", len(dispute.accounts)],
            ["Accounts corrected", corrected],
            ["The truth", item.correct_basis],
        ],
        "lessons": [
            "A subject has the right to see their report and to dispute what is wrong in it. "
            "While the dispute is open the accounts are flagged on every report.",
            "Upholding corrects the record by a new record that supersedes the old: who "
            "changed what, why and on whose authority stays visible. Nothing is deleted.",
            "The regulator counts every dispute left past its deadline; findings climb a "
            "ladder from a concern letter to the loss of the licence.",
        ],
    }


# --- M8 Hire or automate? ------------------------------------------------------------------


def _actions(game: Game, kinds: tuple[str, ...], since: int = 0) -> Any:
    return game.actions.filter(action_type__in=kinds, tick__gte=since).order_by("sequence")


def _m8(game: Game) -> Check:
    began = _began(game, "M8")
    choice = _actions(game, ("HIRE", "SET_MATCHING_TOOLING"), began).first()
    after = None
    if choice is not None:
        at = _at(game, choice.tick)
        before = (
            _runs(game)
            .filter(completed_at__lte=at)
            .order_by("-submission__reporting_period")
            .values_list("submission__reporting_period", flat=True)
            .first()
        )
        later = _runs(game).filter(completed_at__gt=at)
        if before is not None:
            later = later.filter(submission__reporting_period__gt=before)
        after = later.first()
    return Check(
        [
            Objective(
                "Hire someone (Staff) or buy better matching tooling (Work queue, Matching policy): "
                "both are the chief executive's decisions",
                choice is not None,
            ),
            Objective("A new month's files are processed after your decision", after is not None),
        ],
        Question(
            "What would a year of the most capable matching tooling cost, in GHS? "
            "(Work queue, Matching policy)",
            MATCHING_TOOLING_COST["ADVANCED"] * 12,
            unit="GHS",
        ),
        {"choice": choice.sequence if choice else None},
    )  # fmt: skip


def _decided(game: Game, start: int, end: int | None) -> tuple[int, int]:
    """Items the team decided between two ticks, and how many rightly."""
    items = WorkItem.objects.filter(
        organization=game.organization, resolved_by=ResolvedBy.EMPLOYEE, resolved_tick__gte=start
    )
    if end is not None:
        items = items.filter(resolved_tick__lt=end)
    return items.count(), items.filter(is_correct=True).count()


def _share(right: int, total: int) -> str:
    return f"{right} of {total} right ({right * 100 // total}%)" if total else "none"


def _m8_debrief(game: Game, check: Check) -> dict[str, Any]:
    choice = game.actions.get(sequence=check.figures["choice"])
    span = 20 * TICKS_PER_DAY
    before = _decided(game, max(choice.tick - span, 0), choice.tick)
    after = _decided(game, choice.tick, None)
    if choice.action_type == "HIRE":
        hired = (
            Employee.objects.filter(organization=game.organization)
            .order_by("-hired_on", "-employee_number")
            .first()
        )
        what = f"Hired {hired.first_name} {hired.last_name}" if hired else "Hired"
        cost = f"GHS {hired.monthly_salary} a month in salary" if hired else "a salary"
    else:
        level = str(choice.payload["level"])
        what = f"Matching tooling set to {level.lower()}"
        cost = f"GHS {MATCHING_TOOLING_COST[level]} a month"
    waiting = WorkItem.objects.filter(
        organization=game.organization, status__in=(ItemStatus.OPEN, ItemStatus.IN_PROGRESS)
    ).count()
    return {
        "headline": f"{what}: {cost}.",
        "figures": [
            ["Team decisions in the 20 days before", _share(before[1], before[0])],
            ["Team decisions since", _share(after[1], after[0])],
            ["Work items waiting now", waiting],
            ["What it costs", cost],
        ],
        "lessons": [
            "Capacity is how much work gets done; skill is how much of it is right. A "
            "junior hire adds capacity but makes more wrong decisions than a senior one.",
            "Better matching tooling links more records automatically and sends fewer to "
            "review, but its mistakes are made silently and at scale.",
            "Quality has a price either way: salaries rise every year and tooling is a "
            "fixed monthly cost. Compare each with the cost of a wrong report: disputes, "
            "findings and lost subscribers.",
        ],
    }  # fmt: skip


# --- Workspace missions (P3.14): one per department workspace, in any order ----------------


def _w1(game: Game) -> Check:
    switched = _actions(game, ("SWITCH_ROLE",)).filter(payload__role="DATA_ANALYTICS").exists()
    held = CreditAccount.objects.filter(organization=game.organization).exists()

    def oldest_vintage() -> Decimal | None:
        vintages = portfolio(game.organization_id, None)["vintages"]
        if not vintages:
            return None
        return (Decimal(str(vintages[0]["default_rate_so_far"])) * 100).quantize(Decimal("0.1"))

    return Check(
        [Objective("Work as the Head of Data Analytics (Role)", switched)],
        Question(
            "What share of the oldest vintage's accounts has defaulted so far, as a "
            "percentage? (Analytics, Vintages)"
            if held
            else "What share of the oldest vintage's accounts has defaulted so far? (Asked "
            "once the bureau holds accounts.)",
            None,
            tolerance=Decimal("0.1"),
            unit="%",
            compute=oldest_vintage if held else None,
        ),
    )


def _w1_debrief(game: Game, check: Check) -> dict[str, Any]:
    vintages = portfolio(game.organization_id, None)["vintages"]
    first, last = vintages[0], vintages[-1]
    return {
        "headline": f"The {first['quarter']} vintage: {first['defaulted']} of "
        f"{first['accounts']} accounts defaulted so far.",
        "figures": [
            [f"{v['quarter']}: defaulted so far", f"{v['default_rate_so_far'] * 100:.1f}%"]
            for v in vintages
        ],
        "lessons": [
            "A vintage is the loans disbursed in one quarter, followed as they age. Young "
            f"vintages ({last['quarter']}) look good only because their loans have not had "
            "time to go bad.",
            "Compare vintages at the same age, or once they are mature (12 months here): "
            "that is what the default rate column shows.",
            "The bureau sees only what lenders report: a lender that reports late or "
            "stops reporting makes its portfolio look better than it is.",
        ],
    }


TERM_NAMES = {"SHORT": "short term", "MID": "mid term", "LONG": "long term",
              "ALL": "all loans", "COMPOSITE": "composite"}  # fmt: skip


def _w2(game: Game) -> Check:
    first = ScoreModel.objects.filter(game=game).order_by("number").first()
    gini = (first.results.get("holdout") or {}).get("gini") if first else None
    return Check(
        [Objective("Build a scorecard (Scorecards, as Head of Data Analytics)", first is not None)],
        Question(
            f"What is scorecard {first.number}'s Gini on its holdout sample? (Scorecards)"
            if first
            else "What is your first scorecard's Gini on its holdout sample? (Asked once it "
            "is built.)",
            Decimal(str(gini)).quantize(Decimal("0.001")) if gini is not None else None,
            tolerance=Decimal("0.001"),
        ),
        {"model": first.number if first else None},
    )


def _w2_debrief(game: Game, check: Check) -> dict[str, Any]:
    model = ScoreModel.objects.get(game=game, number=check.figures["model"])
    holdout = model.results.get("holdout") or {}
    return {
        "headline": f"Scorecard {model.number} ({TERM_NAMES.get(model.term, model.term)}) "
        "ranks borrowers "
        f"with a Gini of {holdout.get('gini', 0):.3f} on customers it never saw.",
        "figures": [
            ["Characteristics", len(model.features)],
            ["Holdout customers", holdout.get("customers", "—")],
            ["Of whom went bad", holdout.get("bads", "—")],
            ["AUC", f"{holdout.get('auc', 0):.3f}"],
            ["Gini (2 x AUC - 1)", f"{holdout.get('gini', 0):.3f}"],
        ],
        "lessons": [
            "A scorecard is judged on a holdout: customers it was not fitted on. A good fit "
            "on the development sample alone proves little.",
            "Gini measures ranking, not accuracy: whether the bad borrowers score lower "
            "than the good ones. Lenders set the cut-offs.",
            "A restricted attribute such as gender may not be used, however predictive. "
            "Compliance raises a finding if one is deployed.",
        ],
    }


def _w3(game: Game) -> Check:
    first = ConsentCheck.objects.filter(game=game).order_by("number").first()
    answered = first is not None and first.reviewed  # read by Compliance (P4.0)
    return Check(
        [
            Objective(
                "Ask a subscriber for the consent behind a sample of its enquiries "
                "(Compliance, as Head of Compliance)",
                first is not None,
            ),
            Objective(
                "The subscriber sends its forms, and Compliance reads them",
                answered,
            ),
        ],
        Question(
            f"For how many enquiries in consent check {first.number} could "
            f"{first.subscriber_code} not show consent? (Compliance)"
            if first
            else "For how many sampled enquiries could the subscriber not show consent? "
            "(Asked once it answers.)",
            Decimal(len(first.missing)) if answered and first else None,
            unit="enquiries",
        ),
        {"check": first.number if first else None},
    )


def _w3_debrief(game: Game, check: Check) -> dict[str, Any]:
    sample = ConsentCheck.objects.get(game=game, number=check.figures["check"])
    truly = EnquiryJudgement.objects.filter(
        game=game, enquiry__enquiry_reference__in=sample.sample, grounds_held=False
    ).count()
    return {
        "headline": f"{sample.subscriber_code} could not show consent for "
        f"{len(sample.missing)} of {len(sample.sample)} sampled enquiries.",
        "figures": [
            ["Enquiries sampled", len(sample.sample)],
            ["Consent not shown", len(sample.missing)],
            ["Truly made without consent or purpose", truly],
        ],
        "lessons": [
            "The bureau answers an enquiry on the subscriber's word that it holds consent "
            "and a permitted purpose; sampling is how it checks that word.",
            "A larger sample finds more, and costs the subscriber more goodwill.",
            "A subscriber that cannot show consent may be warned, suspended or reported: "
            "the bureau is answerable for who sees the data it holds.",
        ],
    }


def _w4(game: Game) -> Check:
    decided = _actions(game, ("APPROVE_BILL", "REJECT_BILL")).exists()
    reconciled = _actions(game, ("COMPLETE_RECONCILIATION",)).exists()
    return Check(
        [
            Objective(
                "Approve or reject a supplier's bill yourself (Finance, Bills, as Head of Finance)",
                decided,
            ),
            Objective("Reconcile a bank statement (Finance, Bank)", reconciled),
        ]
    )


def _w4_debrief(game: Game, check: Check) -> dict[str, Any]:
    bills = SupplierBill.objects.filter(organization=game.organization)
    late = bills.filter(late_fee__gt=0).count()
    return {
        "headline": f"{bills.count()} bills received so far; {late} paid late.",
        "figures": [
            ["Bills received", bills.count()],
            ["Paid late, with a charge", late],
            ["Bank statements reconciled", _actions(game, ("COMPLETE_RECONCILIATION",)).count()],
        ],
        "lessons": [
            "A bill is an expense when it is received, not when it is paid: payables sit "
            "on the balance sheet until the money goes.",
            "Reconciling matches every line of the bank's statement to an entry in the "
            "books. A line with no entry is either a missing posting or a query for the bank.",
            "Bills left unapproved cost late charges and, for hosting, the suspension of "
            "the bureau's systems.",
        ],
    }


def _w5(game: Game) -> Check:
    today = _today(game)
    research = (
        LenderResearch.objects.filter(game=game, ready_on__lte=today)
        .order_by("ready_on", "id")
        .first()
    )
    proposed = Proposal.objects.filter(game=game).exists()
    return Check(
        [
            Objective("Research a lender (Sales, as Head of Sales)", research is not None),
            Objective("Send a lender a proposal (Sales)", proposed),
        ],
        Question(
            f"About how many applications a month does {research.lender_code} take, by your "
            "research? (Sales)"
            if research
            else "About how many applications a month does the lender take? (Asked once the "
            "research is in.)",
            Decimal(str(research.findings["volume"])) if research else None,
            unit="applications",
        ),
        {"lender": research.lender_code if research else None},
    )  # fmt: skip


def _w5_debrief(game: Game, check: Check) -> dict[str, Any]:
    proposals = Proposal.objects.filter(game=game)
    sent = proposals.count()
    return {
        "headline": f"{sent} proposal{'' if sent == 1 else 's'} sent; "
        f"{proposals.filter(status='ACCEPTED').count()} accepted so far.",
        "figures": [
            ["Lenders researched", LenderResearch.objects.filter(game=game).count()],
            ["Proposals sent", proposals.count()],
            ["Accepted", proposals.filter(status="ACCEPTED").count()],
        ],
        "lessons": [
            "Research first: a lender's volume and what it values (price, service, "
            "coverage) decide which terms it will sign.",
            "A lower price wins subscribers but every report sold earns less; a monthly "
            "minimum smooths revenue, a discount rewards volume.",
            "A subscriber stays while the reports are worth what it pays: hit rate, "
            "accuracy and disputes answered on time are what it sees.",
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
    Mission("M7", "The dispute", "Consumer rights, correction workflows, regulator deadlines",
            ("dispute", "subject-rights", "correction", "regulator-ladder"), _m7, _m7_debrief,
            role="COMPLIANCE"),
    Mission("M8", "Hire or automate?", "Capacity, skill, tooling and the cost of quality",
            ("capacity-and-skill", "matching-tooling", "cost-of-quality"), _m8, _m8_debrief,
            role="CEO"),
    Mission("W1", "Reading the portfolio", "Vintages, the default definition, reporting lags",
            ("vintage", "default-definition", "roll-rate"), _w1, _w1_debrief,
            "WORKSPACE", "DATA_ANALYTICS"),
    Mission("W2", "A first scorecard", "Characteristics, the holdout, Gini and fairness",
            ("scorecard", "gini", "restricted-attribute"), _w2, _w2_debrief,
            "WORKSPACE", "DATA_ANALYTICS"),
    Mission("W3", "Checking consent", "Consent sampling and the subscriber's duty",
            ("consent", "consent-sampling", "sanction"), _w3, _w3_debrief,
            "WORKSPACE", "COMPLIANCE"),
    Mission("W4", "Paying the bills", "Supplier bills, approval, bank reconciliation",
            ("supplier-bill", "bank-reconciliation", "month-close"), _w4, _w4_debrief,
            "WORKSPACE", "FINANCE"),
    Mission("W5", "Winning a subscriber", "Lender research, proposals and pricing",
            ("lender-research", "proposal", "pricing"), _w5, _w5_debrief,
            "WORKSPACE", "SALES"),
)  # fmt: skip
BY_CODE = {m.code: m for m in MISSIONS}
CAMPAIGN = tuple(m for m in MISSIONS if m.track == "CAMPAIGN")
WORKSPACE = tuple(m for m in MISSIONS if m.track == "WORKSPACE")


class MissionError(Exception):
    pass


def _state(game: Game, code: str) -> MissionState:
    record, _ = MissionState.objects.get_or_create(game=game, code=code)
    return record


def _done(game: Game) -> set[str]:
    return set(
        MissionState.objects.filter(game=game, completed_tick__isnull=False).values_list(
            "code", flat=True
        )
    )


def current(game: Game) -> Mission | None:
    """The first campaign mission not yet completed, if the campaign is on."""
    if not game.campaign:
        return None
    done = _done(game)
    return next((m for m in CAMPAIGN if m.code not in done), None)


def open_missions(game: Game) -> list[Mission]:
    """Every mission the player may work on now: the campaign's current one and each
    workspace mission not yet done."""
    if not game.campaign:
        return []
    done = _done(game)
    now = next((m for m in CAMPAIGN if m.code not in done), None)
    return [*([now] if now else []), *(m for m in WORKSPACE if m.code not in done)]


def held_for_player(game: Game) -> frozenset[str]:
    """Work item types the team leaves for the player while a mission asks for them.

    M2 asks the player to decide unloadable records; in a small world they are few,
    and the team would otherwise take them first (P3.0). M7 asks for a dispute.
    """
    if not game.campaign:
        return frozenset()
    mission = current(game)
    if mission is None:
        return frozenset()
    if mission.code == "M2":
        if _player_items(game, CaseType.UNLOADABLE_TRIAGE).count() >= TRIAGE_TARGET:
            return frozenset()
        return frozenset({CaseType.UNLOADABLE_TRIAGE})
    if mission.code == "M7" and not _player_disputes(game, _began(game, "M7")).exists():
        return frozenset({CaseType.DISPUTE})
    return frozenset()


def answered(record: MissionState) -> bool:
    return any(a["right"] for a in record.answers)


def _complete(check: Check, record: MissionState) -> bool:
    return all(o.done for o in check.objectives) and (check.question is None or answered(record))


# Missions whose check always asks a question: none is complete until it is answered
# right, so ``update`` need not check their objectives every tick until then (P4.0).
ASKS = frozenset({"M1", "M4", "M5", "M6", "M7", "M8", "W1", "W2", "W3", "W5"})


def update(game: Game, tick: int, add: Any) -> None:
    """After a tick or an answer: has an open mission been completed?"""
    missions = open_missions(game)
    if not missions:
        return
    states = {r.code: r for r in MissionState.objects.filter(game=game)}
    for mission in missions:
        if mission.code == "M7":
            arrange_dispute(game, tick)
        record = states.get(mission.code) or _state(game, mission.code)
        if mission.code in ASKS and not answered(record):
            continue  # it cannot be complete yet
        check = mission.check(game)
        if not _complete(check, record):
            continue
        record.completed_tick = tick
        record.debrief = mission.debrief(game, check)
        record.save(update_fields=["completed_tick", "debrief"])
        following = current(game) if mission.track == "CAMPAIGN" else None
        after = (
            (f" Next: {following.code} {following.title}." if following else " Campaign done.")
            if mission.track == "CAMPAIGN"
            else ""
        )
        add(
            "MISSION_COMPLETE", Severity.INFO,
            f"Mission {mission.code} complete: {mission.title}",
            record.debrief["headline"] + after,
            {"screen": "missions", "params": {"code": mission.code}},
        )  # fmt: skip


def parse(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").replace("GHS", "").replace("%", "").strip())
    except InvalidOperation as exc:
        raise MissionError(f"{value!r} is not a number") from exc


def answer(game: Game, code: str, value: str, tick: int) -> bool:
    """The player answers an open mission's question. True if right."""
    mission = next((m for m in open_missions(game) if m.code == code), None)
    if mission is None:
        raise MissionError(f"{code} is not a mission open now")
    question = mission.check(game).question
    expected = question.expected() if question is not None else None
    if question is None or expected is None:
        raise MissionError("There is no question to answer yet")
    given = parse(value)
    right = abs(given - expected) <= question.tolerance
    record = _state(game, code)
    record.answers = [*record.answers, {"tick": tick, "value": str(given), "right": right}]
    record.save(update_fields=["answers"])
    return right


def overview(game: Game) -> list[dict[str, Any]]:
    """Every mission, with its objectives (for the open ones) and debrief (when done)."""
    states = {s.code: s for s in MissionState.objects.filter(game=game)}
    now = {m.code for m in open_missions(game)}
    rows = []
    for mission in MISSIONS:
        record = states.get(mission.code)
        done = record is not None and record.completed_tick is not None
        row: dict[str, Any] = {
            "code": mission.code,
            "title": mission.title,
            "concept": mission.concept,
            "track": mission.track,
            "role": mission.role,
            "handbook": list(mission.handbook),
            "status": "DONE" if done else "CURRENT" if mission.code in now else "LATER",
            "debrief": record.debrief if done and record else None,
        }
        if mission.code in now:
            check = mission.check(game)
            row["objectives"] = [o.__dict__ for o in check.objectives]
            q = check.question
            row["question"] = (
                {
                    "text": q.text,
                    "ready": q.ready,
                    "unit": q.unit,
                    "answered": bool(record and answered(record)),
                    "attempts": len(record.answers) if record else 0,
                }
                if q
                else None
            )
        rows.append(row)
    return rows
