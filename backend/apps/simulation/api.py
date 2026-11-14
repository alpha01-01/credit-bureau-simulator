"""Clock API (roadmap S4).

    GET  /api/v1/games/<id>/clock/            state
    POST /api/v1/games/<id>/clock/pause/
    POST /api/v1/games/<id>/clock/resume/
    POST /api/v1/games/<id>/clock/speed/      {"speed": 1|2|4|8}
    POST /api/v1/games/<id>/clock/advance/    {"unit": "hour"|"day"|"next_event", "count": 1}

Players may only see and drive their own games.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.core.models import Enquiry
from apps.bureau.quality.models import ALLOWED_DECISIONS
from apps.bureau.submissions.review import ReviewError
from apps.finance import statements
from apps.org.models import Employee
from apps.workitems.models import WorkItem
from apps.workitems.work import WorkError

from . import controls
from .engine import ClockError
from .models import Game


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
        WorkItem.objects.select_related("case__record", "case__candidate_customer", "assignee"),
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
    return Response(
        _item_summary(item)
        | {
            "record": case.record.cleansed,
            "candidate": candidate,
            "score": case.score,
            "evidence": case.evidence,
            "proposal": case.proposal,
            "allowed_decisions": list(ALLOWED_DECISIONS[case.case_type]),
            "explanation": item.explanation or None,
        }
    )


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
