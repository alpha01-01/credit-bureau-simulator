"""The second floor: the executive floor, as the office draws it (P4.6; Document 10).

The boardroom fills for a board review; Risk and Compliance shows its open findings and
the consent samples in progress; the chief executive works at their desk; the notice
board gives the current mission, the month's targets and the regulator's open actions
(Document 05, Section 5.3). All of it is worked out from what the game holds, at the
tick under way: nothing is stored and nothing is random.

ASSUMPTION A-095 (the board, the chief executive, Compliance and the notice board):

* **The board** is five: a chair and four non-executive directors. They come in for
  each quarterly review (A-066), for its two hours from 08:00 (A-091), and sit with the
  chief executive and Data Operations' most senior person, who presents. They are not
  on the payroll. Between reviews the boardroom gives the last review's verdict.
* **The chief executive** is the player: drawn at their desk in the CEO's office (a
  Startup founder's office) from 08:00 to 17:00, and in the boardroom during a review.
* **Risk and Compliance** shows the one compliance officer of A-088 (or its real staff,
  when it has some), at work on what the officer's day went to; the open findings lie on
  the desk as paper, so a new one shows on the next refresh.
* **The notice board**, in Executive Management: the campaign's current mission and its
  objectives; this month's budget, revenue to reach and costs to keep within, against
  the actuals so far (P3.8: a game starts with cost budgets; revenue has a target once
  the player sets one); and what the regulator
  expects: the bureau's standing on its ladder and the next step, the regulator's
  findings in the last six months, the monthly return while it is unfiled, disputes
  open against their statutory deadlines, and findings already reported to it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from apps.bureau.quality.models import Dispute, DisputeStatus, RegulatoryReturn
from apps.finance import budget

from . import building, compliance, missions, places
from .models import (
    BoardReview,
    ComplianceFinding,
    ConsentCheck,
    Game,
    RegulatorFinding,
    RegulatorStanding,
)

DIRECTORS = (
    "Board chair",
    "Non-executive director",
    "Non-executive director",
    "Non-executive director",
    "Non-executive director",
)
QUARTER_MONTHS = (1, 4, 7, 10)
FINDING_WORDS = {
    "CONSENT_MISSING": "enquiries without consent on file",
    "ACCESS_REVIEW_DUE": "the quarterly access review due",
    "RESTRICTED_ATTRIBUTE_IN_SCORECARD": "a scorecard using a restricted attribute",
}
VERDICTS = {
    "CONFIDENT": "confident",
    "CONCERNED": "concerned",
    "NO_CONFIDENCE": "no confidence",
    "REMOVED": "removed the management",
}


def _day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _quarter(period: date) -> str:
    return f"Q{(period.month - 1) // 3 + 1} {period.year}"


# --- The board ----------------------------------------------------------------------------


def in_session(game: Game) -> BoardReview | None:
    """The board review being held now, if one is (its two hours from its tick)."""
    if places.after_hours(game):
        return None
    tick = game.current_tick + 1
    if places.slot(tick) >= places.BOARD_TICKS:
        return None
    return (
        BoardReview.objects.filter(game=game, tick__gt=tick - places.BOARD_TICKS, tick__lte=tick)
        .order_by("-tick")
        .first()
    )


def board(game: Game, today: date) -> dict[str, Any]:
    """The boardroom's state: in session, the last review, and when the next is due."""
    last = BoardReview.objects.filter(game=game).order_by("-period").first()
    month = next(
        (m for m in QUARTER_MONTHS if m > today.month), QUARTER_MONTHS[0]
    )  # the next quarter's first month
    year = today.year + (month <= today.month)
    return {
        "in_session": in_session(game) is not None,
        "last": None
        if last is None
        else {
            "period": last.period,
            "quarter": _quarter(last.period),
            "confidence": round(last.confidence),
            "verdict": last.verdict,
            "words": VERDICTS.get(last.verdict, last.verdict.lower()),
            "detail": last.detail,
        },
        "next_on": date(year, month, 1),
    }


def directors(game: Game) -> list[dict[str, Any]]:
    """The board, in the boardroom while a review is held."""
    review = in_session(game)
    found = building.room_for_place(game, places.BOARDROOM)
    if review is None or found is None:
        return []
    doing = f"at the board review of {_quarter(review.period)}"
    return [
        {
            "number": f"BOARD-{n}",
            "name": f"Director {n - 1}" if n > 1 else "The chair",
            "job_title": title,
            "visitor": True,
            "desk": None,
            "room": found[1].code,
            "place": places.BOARDROOM,
            "activity": places.BOARD,
            "doing": doing,
            "item": None,
            "morale": None,
            "screen": "health#board",
        }
        for n, title in enumerate(DIRECTORS, start=1)
    ]


# --- Risk and Compliance ------------------------------------------------------------------


def compliance_state(game: Game, today: date) -> dict[str, Any]:
    """Compliance's open findings, its consent samples in progress, and its day."""
    org = game.organization
    findings = [
        {
            "number": f.number,
            "kind": f.kind,
            "words": FINDING_WORDS.get(f.kind, f.kind.replace("_", " ").lower()),
            "due": f.due_date,
            "escalated": f.escalated,
        }
        for f in ComplianceFinding.objects.filter(game=game, resolved_tick__isnull=True).order_by(
            "number"
        )
    ]
    samples = []
    for c in ConsentCheck.objects.filter(game=game, reviewed=False).order_by("number"):
        if not c.answered:
            state = f"waiting for the forms (asked about {len(c.sample)} enquiries)"
        else:
            state = f"reading the forms: {c.review_days_left} working day(s) left"
        samples.append({"number": c.number, "subscriber": c.subscriber_code, "state": state})
    busy = org.compliance_busy_with if org.compliance_busy_on == today else ""
    return {"open": len(findings), "findings": findings, "samples": samples, "today": busy}


# --- The notice board ---------------------------------------------------------------------


def _mission(game: Game) -> dict[str, Any] | None:
    found = missions.current(game)
    if found is None:
        return None
    check = found.check(game)
    return {
        "code": found.code,
        "title": found.title,
        "objectives": [
            {"text": o.text, "done": o.done, "progress": o.progress} for o in check.objectives
        ],
    }


def _targets(game: Game, today: date) -> list[str]:
    """This month's budget, where the player has set one, against the actuals so far."""
    found = budget.report(game.organization, today)
    lines = []
    for row in found["rows"]:
        if row["budget"] is None:
            continue
        if row["income"]:
            lines.append(f"Revenue: GHS {row['actual']:,.0f} of GHS {row['budget']:,.0f} to reach")
    costs = [r for r in found["rows"] if not r["income"] and r["budget"] is not None]
    if costs:
        spent = sum((r["actual"] for r in costs), Decimal("0"))
        allowed = sum((r["budget"] for r in costs), Decimal("0"))
        lines.append(f"Costs: GHS {spent:,.0f} of GHS {allowed:,.0f} budgeted, so far")
    return lines


def _regulator(game: Game, today: date) -> list[str]:
    """What the regulator expects of the bureau now."""
    lines = []
    record = RegulatorStanding.objects.filter(game=game).first()
    level = record.level if record is not None else 0
    if level:
        why = next((text for _, lvl, text in compliance.LADDER if lvl == level), "")
        lines.append(f"Standing: {compliance.LEVEL_NAMES[level]}. {why}.")
        if level in compliance.NEXT_STEP:
            lines.append(compliance.NEXT_STEP[level])
    since = today - timedelta(days=compliance.FINDINGS_WINDOW_DAYS)
    recent = RegulatorFinding.objects.filter(game=game, raised_at__date__gte=since).count()
    if recent:
        lines.append(f"{recent} regulator finding(s) in the last six months")
    for r in RegulatoryReturn.objects.filter(
        organization=game.organization, filed_at__isnull=True
    ).order_by("period"):
        late = " (late)" if r.due_date < today else ""
        lines.append(f"Monthly return for {r.period:%B %Y}: due {_day(r.due_date)}{late}")
    disputes = Dispute.objects.filter(organization=game.organization, status=DisputeStatus.OPEN)
    first = disputes.order_by("due_date").first()
    if first is not None:
        lines.append(
            f"{disputes.count()} dispute(s) open; the first must be settled by "
            f"{_day(first.due_date)}"
        )
    reported = ComplianceFinding.objects.filter(
        game=game, resolved_tick__isnull=True, escalated=True
    ).count()
    if reported:
        lines.append(f"{reported} compliance finding(s) reported to the regulator, still open")
    return lines


def notices(game: Game, today: date) -> dict[str, Any]:
    """The notice board: the current mission, the month's targets, the regulator."""
    return {
        "mission": _mission(game),
        "campaign": game.campaign,
        "targets": _targets(game, today),
        "regulator": _regulator(game, today),
    }


def ceo_place(game: Game) -> tuple[str, str, str] | None:
    """Where the chief executive is: (place, activity, words), or None after hours."""
    if places.after_hours(game):
        return None
    review = in_session(game)
    if review is not None:
        return places.BOARDROOM, places.BOARD, f"at the board review of {_quarter(review.period)}"
    return places.DESK, places.WORKING, "at their desk: the company at a glance"
