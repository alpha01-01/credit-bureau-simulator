"""Customer Support and Product Development, managed by the chief executive (P3.10).

GET/POST /api/v1/games/<id>/support/    tickets, response, satisfaction; {"agents": 3}
GET/POST /api/v1/games/<id>/products/   the development menu; {"code": "CREDIT_SCORE"}
GET      /api/v1/games/<id>/batches/    batch files (P3.11); ?reference= for one file
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.reports.batch import BATCH_ENQUIRY, result_file
from apps.bureau.reports.models import BatchFile

from . import controls, products, roles, support
from .api import _error, _game
from .engine import ClockError
from .finance_dept import AGENT_MONTHLY
from .models import ProductDevelopment, SupportTicket

DAYS_SHOWN = 30


@api_view(["GET", "POST"])
def support_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        try:
            roles.require(game, "SET_SUPPORT_STAFF")
            controls.set_support_staff(game, int(request.data.get("agents", -1)))
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
        game.organization.refresh_from_db()
    now = controls.state(game).now
    today = now.date()
    since = today - timedelta(days=DAYS_SHOWN)
    recent = SupportTicket.objects.filter(game=game, opened_on__gt=since)
    by_day: dict[str, Counter[str]] = {}
    for opened, topic in recent.values_list("opened_on", "topic"):
        by_day.setdefault(opened.isoformat(), Counter())[topic] += 1
    answered = [
        (o, a, d)
        for o, a, d in recent.values_list("opened_on", "answered_on", "due_on")
        if a is not None
    ]
    staff = game.organization.support_staff
    tickets = SupportTicket.objects.filter(game=game).order_by("-number")[:50]
    return Response(
        {
            "agents": staff,
            "per_agent": support.TICKETS_PER_AGENT,
            "capacity": staff * support.TICKETS_PER_AGENT,
            "agent_monthly": AGENT_MONTHLY,
            "range": support.STAFF_RANGE,
            "response_days": support.RESPONSE_WORKING_DAYS,
            "waiting": SupportTicket.objects.filter(game=game, answered_on__isnull=True).count(),
            "satisfaction": support.satisfaction(game, now),
            "topics": support.TOPICS,
            "days": [{"day": d, "topics": dict(c)} for d, c in sorted(by_day.items())],
            "answered_30d": len(answered),
            "on_time_30d": sum(1 for _, a, d in answered if a <= d),
            "average_days_30d": (
                sum((a - o).days for o, a, _ in answered) / len(answered) if answered else None
            ),
            "tickets": [
                {
                    "number": t.number,
                    "source": t.source,
                    "subscriber": t.subscriber_code or None,
                    "topic": t.topic,
                    "opened_on": t.opened_on,
                    "due_on": t.due_on,
                    "answered_on": t.answered_on,
                }
                for t in tickets
            ],
        }
    )


def _offering(game: Any, o: products.Offering, today: Any) -> dict[str, Any]:
    project = ProductDevelopment.objects.filter(game=game, code=o.code).first()
    status = "AVAILABLE"
    if project is not None and project.launched_on is not None:
        status = "LAUNCHED"
    elif project is not None and project.started_on is not None:
        status = "IN_DEVELOPMENT"
    return {
        "code": o.code,
        "name": o.name,
        "does": o.does,
        "cost": o.cost,
        "working_days": o.working_days,
        "status": status,
        "started_on": project.started_on if project else None,
        "ready_on": project.ready_on if project else None,
        "launched_on": project.launched_on if project else None,
    }


@api_view(["GET", "POST"])
def products_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        try:
            roles.require(game, "DEVELOP_PRODUCT")
            controls.develop_product(game, str(request.data.get("code", "")))
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
    today = controls.state(game).now.date()
    return Response({"products": [_offering(game, o, today) for o in products.MENU.values()]})


@api_view(["GET"])
def batches_view(request: Request, game_id: int) -> Response:
    """Batch files subscribers sent (P3.11); ?reference= for one file's records and result."""
    game = _game(request, game_id)
    files = BatchFile.objects.filter(organization=game.organization).select_related("subscriber")
    body: dict[str, Any] = {
        "launched": products.launched(game, BATCH_ENQUIRY),
        "price": products.SOLD[BATCH_ENQUIRY][1],
        "batches": [
            {
                "reference": b.reference,
                "subscriber": b.subscriber.subscriber_code,
                "name": b.subscriber.subscriber_name,
                "received_at": b.received_at,
                "records": b.records,
                "hits": b.hits,
            }
            for b in files.order_by("-received_at", "reference")[:100]
        ],
        "batch": None,
    }
    if reference := request.query_params.get("reference"):
        chosen = files.filter(reference=reference).first()
        if chosen is not None:
            body["batch"] = {
                "reference": chosen.reference,
                "rows": [
                    {
                        "row": r.row_number,
                        "identifier": r.identifier_value,
                        "name": r.subject_name,
                        "outcome": r.enquiry.outcome,
                        "report": r.enquiry.enquiry_reference,
                        "accounts": r.enquiry.accounts_reported,
                    }
                    for r in chosen.rows.select_related("enquiry").order_by("row_number")
                ],
                "result_file": result_file(chosen),
            }
    return Response(body)
