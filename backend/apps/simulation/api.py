"""Clock API (roadmap S4).

    GET  /api/v1/games/<id>/clock/            state
    POST /api/v1/games/<id>/clock/pause/
    POST /api/v1/games/<id>/clock/resume/
    POST /api/v1/games/<id>/clock/speed/      {"speed": 1|2|4|8}
    POST /api/v1/games/<id>/clock/advance/    {"unit": "hour"|"day"|"next_event", "count": 1}
    POST /api/v1/games/<id>/clock/step/       one real-time tick, if one is due (P2.2)
    POST /api/v1/games/<id>/clock/pause-rules/  {"severities": [...], "deadlines": true}
    GET  /api/v1/games/<id>/feed/             notices, newest first (?severity=, ?before=)

Players may only see and drive their own games.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.core.models import AccountObservation, Enquiry
from apps.bureau.quality.models import ALLOWED_DECISIONS
from apps.bureau.quality.rules import POLICIES
from apps.bureau.submissions.models import StagingRecord
from apps.bureau.submissions.review import ReviewError
from apps.finance import statements
from apps.finance.events import MATCHING_TOOLING_COST
from apps.org.models import Employee
from apps.workitems.models import WorkItem
from apps.workitems.work import WorkError

from . import assets, controls
from .engine import ClockError
from .models import DataQualityReview, Game


def _game(request: Request, game_id: int) -> Game:
    return get_object_or_404(
        Game.objects.select_related("world", "organization"), pk=game_id, owner=request.user
    )


def _ok(game: Game) -> Response:
    return Response(controls.state(game).as_dict())


def _error(exc: Exception) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def clock_state(request: Request, game_id: int) -> Response:
    return _ok(_game(request, game_id))


@api_view(["POST"])
def clock_pause(request: Request, game_id: int) -> Response:
    return _ok(controls.pause(_game(request, game_id)))


@api_view(["POST"])
def clock_resume(request: Request, game_id: int) -> Response:
    return _ok(controls.resume(_game(request, game_id)))


@api_view(["POST"])
def clock_speed(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    try:
        return _ok(controls.set_speed(game, int(_field(request, "speed"))))
    except (ClockError, ValueError, TypeError) as exc:
        return _error(exc)


@api_view(["POST"])
def clock_advance(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    try:
        unit = str(_field(request, "unit"))
        count = int(request.data.get("count", 1))
        return _ok(controls.advance_by(game, unit, count))
    except (ClockError, ValueError, TypeError) as exc:
        return _error(exc)


@api_view(["POST"])
def clock_step(request: Request, game_id: int) -> Response:
    return _ok(controls.step(_game(request, game_id)))


@api_view(["POST"])
def clock_pause_rules(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    severities = request.data.get("severities", [])
    if not isinstance(severities, list):
        return _error(ValueError("severities must be a list"))
    try:
        return _ok(
            controls.set_pause_rules(
                game, [str(s) for s in severities], bool(request.data.get("deadlines", True))
            )
        )
    except ClockError as exc:
        return _error(exc)


FEED_PAGE = 100


@api_view(["GET"])
def feed(request: Request, game_id: int) -> Response:
    """The event feed, newest first, a page at a time."""
    game = _game(request, game_id)
    notices = game.notices.order_by("-pk")
    if severity := request.query_params.get("severity"):
        notices = notices.filter(severity=severity)
    if before := request.query_params.get("before"):
        if not before.isdigit():
            return _error(ValueError("before must be a notice id"))
        notices = notices.filter(pk__lt=int(before))
    page = list(notices[: FEED_PAGE + 1])
    return Response(
        {
            "notices": [controls.notice_dict(n) for n in page[:FEED_PAGE]],
            "more": len(page) > FEED_PAGE,
        }
    )


@api_view(["GET", "POST"])
def matching_policy(request: Request, game_id: int) -> Response:
    """Customer matching (P2.4): the tooling bought and the thresholds set."""
    game = _game(request, game_id)
    if request.method == "POST":
        try:
            if "tooling" in request.data:
                controls.set_matching_tooling(game, str(request.data["tooling"]))
            if "auto_link" in request.data or "review" in request.data:
                org = game.organization
                controls.set_matching_thresholds(
                    game,
                    float(request.data.get("auto_link", org.match_auto_link)),
                    float(request.data.get("review", org.match_review)),
                )
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
    org = game.organization
    return Response(
        {
            "tooling": org.matching_tooling,
            "auto_link": org.match_auto_link,
            "review": org.match_review,
            "options": [
                {
                    "level": level,
                    "description": label,
                    "monthly_cost": str(MATCHING_TOOLING_COST[level]),
                }
                for level, label in controls.TOOLING_LEVELS.items()
            ],
        }
    )


@api_view(["GET", "POST"])
def rejection_policy(request: Request, game_id: int) -> Response:
    """The bureau's record rejection policy (D18): read it, or change it."""
    game = _game(request, game_id)
    if request.method == "POST":
        try:
            controls.set_rejection_policy(game, str(_field(request, "policy")))
        except (ClockError, ValueError) as exc:
            return _error(exc)
    return Response(
        {
            "policy": game.organization.rejection_policy,
            "options": [{"code": k, "description": v} for k, v in POLICIES.items()],
        }
    )


def _field(request: Request, name: str) -> Any:
    if name not in request.data:
        raise ValueError(f"'{name}' is required")
    return request.data[name]


# --- Work queue -----------------------------------------------------------------------
#
#   GET  /api/v1/games/<id>/work-items/?status=OPEN
#   GET  /api/v1/games/<id>/work-items/<number>/
#   POST /api/v1/games/<id>/work-items/<number>/resolve/   {"decision": "..."}
#   GET  /api/v1/games/<id>/employees/
#
# The answer key (correct decision, whether a decision was right) is never sent:
# the player learns it from consequences and the debrief.


def _item_summary(item: WorkItem) -> dict[str, Any]:
    return {
        "number": item.item_number,
        "type": item.item_type,
        "status": item.status,
        "difficulty": item.difficulty,
        "created_tick": item.created_tick,
        "assignee": item.assignee.employee_number if item.assignee else None,
        "decision": item.decision or None,
        "resolved_by": item.resolved_by or None,
        "resolved_tick": item.resolved_tick,
    }


@api_view(["GET"])
def work_items(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    items = WorkItem.objects.filter(organization=game.organization).select_related("assignee")
    status_filter = request.query_params.get("status")
    if status_filter:
        items = items.filter(status=status_filter)
    # Waiting work oldest first (as it is worked); finished work newest first.
    order = "-item_number" if status_filter == "DONE" else "item_number"
    return Response([_item_summary(i) for i in items.order_by(order)[:500]])


@api_view(["GET"])
def work_item(request: Request, game_id: int, number: int) -> Response:
    game = _game(request, game_id)
    item = get_object_or_404(
        WorkItem.objects.select_related(
            "case__record__file__submission__institution", "case__candidate_customer", "assignee"
        ),
        organization=game.organization,
        item_number=number,
    )
    case = item.case
    candidate = None
    if case.candidate_customer is not None:
        customer = case.candidate_customer
        profile = getattr(customer, "individual", None)
        business = getattr(customer, "business", None)
        candidate = {
            "reference": customer.customer_reference,
            "name": (
                f"{profile.first_name} {profile.last_name}"
                if profile
                else (business.registered_name if business else None)
            ),
            "date_of_birth": profile.date_of_birth.isoformat()
            if profile and profile.date_of_birth
            else None,
            "registration_date": business.registration_date.isoformat()
            if business and business.registration_date
            else None,
        }
    institution = case.record.file.submission.institution
    return Response(
        _item_summary(item)
        | {
            "provider": {
                "code": institution.institution_code,
                "name": institution.institution_name,
            },
            "on_file": _on_file(institution.pk, case.record.cleansed.get("FacilityAccNum", "")),
            "record": case.record.cleansed,
            "candidate": candidate,
            "score": case.score,
            "evidence": case.evidence,
            "proposal": case.proposal,
            "allowed_decisions": list(ALLOWED_DECISIONS[case.case_type]),
            "explanation": item.explanation or None,
        }
    )


def _on_file(institution_id: int, account_number: str) -> dict[str, Any] | None:
    """The bureau's latest position for the account, so a reviewer can compare."""
    latest = (
        AccountObservation.objects.filter(
            credit_account__institution_id=institution_id,
            credit_account__facility_account_number=account_number,
            is_current=True,
        )
        .select_related("credit_account")
        .order_by("-reporting_date")
        .first()
    )
    if latest is None:
        return None
    return {
        "reporting_date": latest.reporting_date.isoformat(),
        "status": latest.facility_status,
        "balance": str(latest.outstanding_balance),
        "arrears": str(latest.arrears_amount),
        "days_past_due": latest.days_past_due,
        "disbursement_date": latest.credit_account.disbursement_date.isoformat()
        if latest.credit_account.disbursement_date
        else None,
    }


@api_view(["POST"])
def resolve_work_item(request: Request, game_id: int, number: int) -> Response:
    game = _game(request, game_id)
    try:
        item = controls.resolve_item(game, number, str(_field(request, "decision")))
    except (ClockError, WorkError, ReviewError, ValueError) as exc:
        return _error(exc)
    return Response(_item_summary(item))


@api_view(["GET"])
def employees(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    return Response(
        [
            {
                "number": e.employee_number,
                "name": f"{e.first_name} {e.last_name}",
                "job_title": e.job_title,
                "skills": e.skills,
                "experience": e.experience,
                "morale": e.morale,
                "done_today": e.done_today,
            }
            for e in Employee.objects.filter(organization=game.organization).order_by(
                "employee_number"
            )
        ]
    )


# --- Enquiries --------------------------------------------------------------------------
#
#   GET /api/v1/games/<id>/enquiries/            latest enquiries
#   GET /api/v1/games/<id>/enquiries/<reference>/  the report as delivered


@api_view(["GET"])
def enquiries(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    query = Enquiry.objects.filter(organization=game.organization)
    if start := request.query_params.get("start"):
        query = query.filter(enquired_at__date__gte=start)
    if outcome := request.query_params.get("outcome"):
        query = query.filter(outcome=outcome)
    rows = query.select_related("subscriber", "customer").order_by(
        "-enquired_at", "-enquiry_reference"
    )[:500]
    return Response(
        [
            {
                "reference": e.enquiry_reference,
                "subscriber": e.subscriber.subscriber_code,
                "purpose": e.purpose,
                "enquired_at": e.enquired_at.isoformat(),
                "outcome": e.outcome,
                "customer": e.customer.customer_reference if e.customer else None,
                "accounts_reported": e.accounts_reported,
            }
            for e in rows
        ]
    )


@api_view(["GET"])
def enquiry_report(request: Request, game_id: int, reference: str) -> Response:
    game = _game(request, game_id)
    enquiry = get_object_or_404(
        Enquiry, organization=game.organization, enquiry_reference=reference
    )
    return Response({"reference": enquiry.enquiry_reference, "report": enquiry.report})


# --- Finance ----------------------------------------------------------------------------
#
#   GET /api/v1/games/<id>/finance/   statements at the current game date:
#       trial balance, month-to-date and year-to-date income statements,
#       balance sheet and cash position, all derived from posted entries.


@api_view(["GET"])
def finance(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    today = controls.state(game).now.date()
    org = game.organization
    return Response(
        {
            "as_of": today,
            "trial_balance": statements.trial_balance(org, today),
            "income_month_to_date": statements.income_statement(org, today.replace(day=1), today),
            "income_year_to_date": statements.income_statement(
                org, today.replace(month=1, day=1), today
            ),
            "balance_sheet": statements.balance_sheet(org, today),
            "cash": statements.cash_position(org, today),
        }
    )


# --- Data assets and the Data Quality Review (P2.3) --------------------------------------
#
#   GET /api/v1/games/<id>/data-assets/                 what the player sees and estimates
#   GET /api/v1/games/<id>/reviews/                     the monthly reviews, newest first
#   GET /api/v1/games/<id>/reviews/<YYYY-MM>/           one review: the truth revealed
#   GET /api/v1/games/<id>/reviews/<YYYY-MM>/drill/?key=match.false_merge
#                                                       the records behind one figure


@api_view(["GET"])
def data_assets(request: Request, game_id: int) -> Response:
    """The latest month-end figures; before the first month ends, worked out now."""
    game = _game(request, game_id)
    latest = game.reviews.order_by("-period").first()
    if latest is not None:
        return Response({"source": "month_end", **latest.figures["assets"]["visible"]})
    today = controls.state(game).now.date()
    return Response({"source": "now", **assets.visible_assets(game, today)})


@api_view(["GET"])
def reviews(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    return Response(
        [
            {
                "period": f"{r.period:%Y-%m}",
                "match": r.figures["match"],
                "rejected": {k: r.figures["rejected"][k] for k in ("total", "genuine")},
                "consequences": r.figures["consequences"]["mixed_reports"]
                + r.figures["consequences"]["incomplete_reports"],
            }
            for r in game.reviews.order_by("-period")
        ]
    )


def _review(game: Game, period: str) -> DataQualityReview:
    try:
        month = datetime.strptime(period, "%Y-%m").date()
    except ValueError as exc:
        raise Http404("No such month") from exc
    return get_object_or_404(
        DataQualityReview, game=game, period__year=month.year, period__month=month.month
    )


@api_view(["GET"])
def review(request: Request, game_id: int, period: str) -> Response:
    game = _game(request, game_id)
    found = _review(game, period)
    return Response(
        {
            "period": f"{found.period:%Y-%m}",
            "figures": found.figures,
            "drill": sorted(k for k, v in found.refs.items() if v),
        }
    )


@api_view(["GET"])
def review_drill(request: Request, game_id: int, period: str) -> Response:
    """The records behind one figure of a review."""
    game = _game(request, game_id)
    found = _review(game, period)
    key = request.query_params.get("key", "")
    if key not in found.refs:
        return _error(ValueError(f"No figure {key!r} in this review"))
    refs = found.refs[key]
    if key.startswith(("match.", "triage.")):
        return Response({"key": key, "kind": "work_items", "rows": _item_rows(game, refs)})
    if key.startswith("rejected."):
        return Response({"key": key, "kind": "records", "rows": _record_rows(game, refs)})
    chains = found.figures["consequences"]["chains"]
    return Response({"key": key, "kind": "consequences", "rows": chains})


def _item_rows(game: Game, numbers: list[int]) -> list[dict[str, Any]]:
    items = (
        WorkItem.objects.filter(organization=game.organization, item_number__in=numbers)
        .select_related("case__record__run__submission", "assignee")
        .order_by("item_number")
    )
    return [
        {
            "item": i.item_number,
            "type": i.item_type,
            "decision": i.decision,
            "correct_decision": i.correct_decision,
            "correct": i.is_correct,
            "resolved_by": i.resolved_by,
            "employee": f"{i.assignee.first_name} {i.assignee.last_name}" if i.assignee else None,
            "why_right": i.correct_basis,
            "submission": i.case.record.run.submission.submission_reference,
            "row": i.case.record.source_row_number,
        }
        for i in items
    ]


def _record_rows(game: Game, refs: list[list[Any]]) -> list[dict[str, Any]]:
    wanted = {(r[0], r[1], int(r[2])) for r in refs}
    records = StagingRecord.objects.filter(
        run__submission__organization=game.organization,
        run__submission__submission_reference__in={r[0] for r in wanted},
        source_row_number__in={r[2] for r in wanted},
    ).select_related("run__submission", "file")
    rows = []
    for record in records:
        key = (record.run.submission.submission_reference, record.file.file_name,
               record.source_row_number)  # fmt: skip
        if key not in wanted:
            continue
        issues = record.issues.filter(severity="ERROR").order_by("rule_code")
        values = record.cleansed
        rows.append(
            {
                "submission": key[0],
                "file": key[1],
                "row": key[2],
                "name": " ".join(
                    v
                    for v in (
                        values.get("FirstName"),
                        values.get("Surname"),
                        values.get("BusinessName"),
                    )
                    if v
                ),
                "errors": [
                    {"rule": i.rule_code, "field": i.field, "value": i.value} for i in issues
                ],
            }
        )
    return sorted(rows, key=lambda r: (r["submission"], r["file"], r["row"]))
