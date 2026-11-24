"""Taking on a subscriber, department by department (P3.9).

GET  /api/v1/games/<id>/onboarding/   every onboarding with its steps
POST /api/v1/games/<id>/onboarding/   {"action": "decide", "number": 1, "decision": "APPROVE"}
                                      {"action": "billing", "number": 1}
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.standards.calendar import is_working_day
from apps.world.models import Lender

from . import controls, onboarding, roles
from .api import _error, _game
from .engine import ClockError
from .models import Onboarding, OnboardingStep


def _working_days(start: date, end: date) -> int:
    """Working days after ``start`` up to and including ``end``."""
    days, day = 0, start
    while day < end:
        day = date.fromordinal(day.toordinal() + 1)
        days += is_working_day(day)
    return days


def _step(step: OnboardingStep, before: OnboardingStep | None, today: date) -> dict[str, Any]:
    waiting_for = None
    if step.status == onboarding.WAITING and before is not None:
        waiting_for = before.department
    return {
        "position": step.position,
        "department": step.department,
        "code": step.code,
        "title": onboarding.TITLES[step.code],
        "status": step.status,
        "ready_on": step.ready_on,
        "due_on": step.due_on,
        "progress": step.progress,
        "days": onboarding.DAYS[step.code],
        "held": step.held or None,
        "waiting_for": waiting_for,
        "waited": _working_days(step.ready_on, today)
        if step.ready_on and step.status in (onboarding.READY, onboarding.ESCALATED)
        else None,
        "done_on": step.done_on,
        "done_by": step.done_by or None,
        "outcome": step.outcome or None,
        "evidence": step.evidence,
    }


@api_view(["GET", "POST"])
def onboarding_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        data, action = request.data, str(request.data.get("action", ""))
        try:
            number = int(data.get("number", 0))
            if action == "decide":
                roles.require(game, "DECIDE_SUBSCRIBER_CHECK")
                controls.decide_subscriber_check(game, number, str(data.get("decision", "")))
            elif action == "billing":
                roles.require(game, "SET_UP_BILLING")
                controls.set_up_billing(game, number)
            else:
                return _error(ValueError("action must be decide or billing"))
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
    today = controls.state(game).now.date()
    names = dict(Lender.objects.filter(world=game.world).values_list("code", "name"))
    found = []
    for o in Onboarding.objects.filter(game=game).select_related("proposal").order_by("-number"):
        steps = list(o.steps.order_by("position"))
        at = onboarding.current(o) if o.status == "IN_PROGRESS" else None
        p = o.proposal
        found.append(
            {
                "number": o.number,
                "lender": o.lender_code,
                "name": names.get(o.lender_code, o.lender_code),
                "status": o.status,
                "signed_on": o.signed_on,
                "give_up_on": o.give_up_on,
                "live_on": o.live_on,
                "ended_on": o.ended_on,
                "at": at.department if at else None,
                "terms": {
                    "price": str(o.unit_price),
                    "term_months": p.term_months,
                    "service_level": p.service_level,
                    "monthly_minimum": str(p.monthly_minimum),
                    "discount_threshold": p.discount_threshold,
                    "discount_rate": str(p.discount_rate),
                },
                "unbilled": str(onboarding.unbilled(game, o.lender_code)),
                "steps": [
                    _step(s, steps[n - 1] if n else None, today) for n, s in enumerate(steps)
                ],
            }
        )
    return Response(
        {
            "patience_days": onboarding.PATIENCE_WORKING_DAYS,
            "decisions": [onboarding.APPROVE, onboarding.WARN, onboarding.REFUSE],
            "onboardings": found,
        }
    )
