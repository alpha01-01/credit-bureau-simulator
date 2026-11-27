"""The Compliance screen (P3.7).

GET  /api/v1/games/<id>/compliance/   the rules and their citations, the returns, consent
     checks, sanctions, retention, access, and the findings (the bureau's and the regulator's).
POST /api/v1/games/<id>/compliance/   {"action": ...}:
     "sample"    {"subscriber", "month" (a month-end), "size"}
     "sanction"  {"subscriber", "kind": "WARNING" | "SUSPENSION"}
     "retention" {"years"}
     "access_review"
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.quality.models import RegulatoryReturn
from apps.commercial.models import Subscriber
from apps.org.models import Employee
from apps.standards.compliance_rules import LEGAL_RETENTION_YEARS, RULES
from apps.workitems.models import WorkItem
from apps.world.provider_files import month_end as period_end

from . import compliance, controls, duties, roles
from .api import _error, _game
from .clock import previous_month_end
from .engine import ClockError
from .models import Game


@api_view(["GET", "POST"])
def compliance_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        data = request.data
        action = str(data.get("action", ""))
        try:
            if action == "sample":
                roles.require(game, "SAMPLE_CONSENT")
                controls.sample_consent(
                    game, str(data.get("subscriber", "")),
                    date.fromisoformat(str(data.get("month"))), int(data.get("size", 0)),
                )  # fmt: skip
            elif action == "sanction":
                roles.require(game, "SANCTION_SUBSCRIBER")
                controls.sanction_subscriber(
                    game, str(data.get("subscriber", "")), str(data.get("kind", ""))
                )
            elif action == "retention":
                roles.require(game, "SET_RETENTION")
                controls.set_retention(game, int(data.get("years", 0)))
            elif action == "access_review":
                roles.require(game, "ACCESS_REVIEW")
                controls.review_access(game)
            else:
                return _error(
                    ValueError("action must be sample, sanction, retention or access_review")
                )
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
        game.refresh_from_db()
        game.organization.refresh_from_db()
    return Response(overview(game))


def overview(game: Game) -> dict[str, Any]:
    state = controls.state(game)
    today, tick = state.now.date(), state.tick
    org = game.organization
    items = dict(
        WorkItem.objects.filter(organization=org, case__regulatory_return__isnull=False)
        .values_list("case__regulatory_return__period", "item_number")
    )  # fmt: skip
    subscribers = list(Subscriber.objects.filter(organization=org).order_by("subscriber_code"))
    months = [period_end(today.year, today.month)]  # this month's enquiries so far, and before
    while len(months) < 4:
        months.append(previous_month_end(months[-1]))
    return {
        "today": today,
        "rules": [
            {
                "code": r.code,
                "title": r.title,
                "rule": r.rule,
                "citation": r.citation,
                "status": r.status,
            }
            for r in RULES.values()
        ],
        "returns": [
            {
                "period": r.period,
                "due_date": r.due_date,
                "filed_at": r.filed_at,
                "filed_by": r.filed_by or None,
                "figures": r.figures,
                "late": (r.filed_at is None and r.due_date < today)
                or (r.filed_at is not None and r.filed_at.date() > r.due_date),
                "work_item": items.get(r.period),
            }
            for r in RegulatoryReturn.objects.filter(organization=org).order_by("-period")[:12]
        ],
        "subscribers": [
            {
                "code": s.subscriber_code,
                "name": s.subscriber_name,
                "suspended": duties.subscriber_suspended(game, s.subscriber_code, tick),
                "sanctions": game.sanctions.filter(subscriber_code=s.subscriber_code).count(),
            }
            for s in subscribers
        ],
        "sample_months": months,
        "sample_sizes": list(duties.SAMPLE_SIZES),
        "consent_checks": [
            {
                "number": c.number,
                "subscriber": c.subscriber_code,
                "month": c.month,
                "size": len(c.sample),
                "answered": c.answered,
                "reviewed": c.reviewed,
                "review_days_left": c.review_days_left,
                # The bureau knows which forms are missing once Compliance has read them.
                "missing": c.missing if c.reviewed else [],
                "answer_tick": c.answer_tick,
            }
            for c in game.consent_checks.order_by("-number")[:30]
        ],
        "sanctions": [
            {
                "number": s.number,
                "subscriber": s.subscriber_code,
                "kind": s.kind,
                "tick": s.tick,
                "until_tick": s.until_tick,
                "active": s.until_tick is not None and s.until_tick >= tick,
            }
            for s in game.sanctions.order_by("-number")
        ],
        "retention": {
            "years": org.retention_years,
            "legal_years": LEGAL_RETENTION_YEARS,
            "choices": list(duties.RETENTION_CHOICES),
        },
        "officer": {  # Compliance's working day (P4.0)
            "busy_today": org.compliance_busy_on == today,
            "busy_with": org.compliance_busy_with or None,
            "forms_per_day": duties.FORMS_PER_DAY,
            "days_queued": sum(
                c.review_days_left
                for c in game.consent_checks.filter(answered=True, reviewed=False)
            )
            + int(org.access_review_requested),
        },
        "access": {
            "review_requested": org.access_review_requested,
            "staff": Employee.objects.filter(organization=org, has_system_access=True).count(),
            "leavers_with_access": [
                f"{e.first_name} {e.last_name} ({e.job_title})"
                for e in duties.leavers_with_access(game)
            ],
        },
        "findings": [
            {
                "number": f.number,
                "kind": f.kind,
                "reference": f.reference,
                "detail": f.detail,
                "remedy": f.remedy or None,
                "raised_at": f.raised_at,
                "due_date": f.due_date,
                "resolved": f.resolved_tick is not None,
                "escalated": f.escalated,
            }
            for f in game.compliance_findings.order_by("-number")[:50]
        ],
        "regulator": {
            "level": compliance.standing(game).level,
            "standing": compliance.LEVEL_NAMES[compliance.standing(game).level],
            "findings": [
                {
                    "kind": f.kind,
                    "reference": f.reference,
                    "raised_at": f.raised_at,
                    "detail": f.detail,
                }
                for f in game.findings.order_by("-raised_at")[:30]
            ],
        },
    }
