"""The managed departments: HR, Sales and IT (P2.9).

GET  /api/v1/games/<id>/staff/   the team, this month's candidates, pay and training
POST /api/v1/games/<id>/staff/   {"action": "hire", "candidate": 2}
                                 {"action": "train", "employee": "E0001", "work_type": "DISPUTE"}
                                 {"action": "salary", "employee": "E0001", "salary": "7000"}
GET  /api/v1/games/<id>/sales/   lenders we could sign, and our proposals
POST /api/v1/games/<id>/sales/   {"lender": "SWC", "price": "18.00"}
GET  /api/v1/games/<id>/it/      capacity, files waiting, outages
POST /api/v1/games/<id>/it/      {"action": "respond", "response": "VENDOR" | "BACKUP"}
                                 {"action": "capacity", "level": "STANDARD" | "HIGH"}
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.commercial.models import Contract, Subscriber
from apps.finance.events import IT_CAPACITY_COST
from apps.org.models import Employee

from . import controls, hr, it, roles, sales
from .api import _error, _game
from .clock import TICKS_PER_HOUR
from .demand import REFERENCE_PRICE
from .engine import ClockError
from .models import Game, Incident, Proposal
from .reputation import reputation


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{value!r} is not an amount") from exc


@api_view(["GET", "POST"])
def staff(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        data, action = request.data, str(request.data.get("action", ""))
        try:
            if action == "hire":
                roles.require(game, "HIRE")
                controls.hire_candidate(game, int(data.get("candidate", 0)))
            elif action == "train":
                roles.require(game, "TRAIN_EMPLOYEE")
                controls.train_employee(
                    game, str(data.get("employee", "")), str(data.get("work_type", ""))
                )
            elif action == "salary":
                roles.require(game, "SET_SALARY")
                controls.set_salary(game, str(data.get("employee", "")), _money(data.get("salary")))
            else:
                return _error(ValueError("action must be hire, train or salary"))
        except (ClockError, ValueError) as exc:
            return _error(exc)
    tick = game.current_tick
    team = [
        {
            "number": e.employee_number,
            "name": f"{e.first_name} {e.last_name}",
            "job_title": e.job_title,
            "skills": e.skills,
            "morale": e.morale,
            "salary": str(e.monthly_salary),
            "market_salary": str(hr.market_salary(e.job_title)),
            "hired_on": e.hired_on,
            "active": e.is_active,
            "away": e.away_until_tick > tick,
        }
        for e in Employee.objects.filter(organization=game.organization).order_by("employee_number")
    ]
    candidates = [
        {
            "number": c.number,
            "name": f"{c.first_name} {c.last_name}",
            "job_title": c.job_title,
            "skills": c.skills,
            "asking_salary": str(c.asking_salary),
            "hired": c.hired,
        }
        for c in hr.candidates_for(game, controls.this_month(game))
    ]
    return Response(
        {
            "team": team,
            "candidates": candidates,
            "month": controls.this_month(game),
            "training_cost": str(hr.TRAINING_COST),
            "training_types": [str(t) for t in hr.WORK_TYPES],
        }
    )


def _proposal(p: Proposal) -> dict[str, Any]:
    return {
        "number": p.number,
        "lender": p.lender_code,
        "price": str(p.unit_price),
        "sent_at": p.sent_at,
        "status": p.status,
        "answered_at": p.answered_at,
    }


@api_view(["GET", "POST"])
def sales_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        roles.require(game, "SEND_PROPOSAL")
        try:
            controls.send_proposal(
                game, str(request.data.get("lender", "")), _money(request.data.get("price"))
            )
        except (ClockError, ValueError) as exc:
            return _error(exc)
    _, at = controls._now(game)
    pending = set(
        Proposal.objects.filter(game=game, status="PENDING").values_list("lender_code", flat=True)
    )
    subscribers = []
    for s in Subscriber.objects.filter(organization=game.organization).order_by("subscriber_code"):
        contract = Contract.objects.filter(subscriber=s).order_by("-start_date").first()
        subscribers.append(
            {
                "code": s.subscriber_code,
                "name": s.subscriber_name,
                "active": s.is_active,
                "since": s.since,
                "price": str(contract.unit_price) if contract else None,
            }
        )
    return Response(
        {
            "reputation": reputation(game, at)["subscribers"],
            "list_price": str(REFERENCE_PRICE),
            "answer_days": sales.ANSWER_DAYS,
            "subscribers": subscribers,
            "prospects": [
                {
                    "code": lender.code,
                    "name": lender.name,
                    "type": lender.lender_type,
                    "waiting": lender.code in pending,
                }
                for lender in sales.prospects(game)
            ],
            "proposals": [
                _proposal(p) for p in Proposal.objects.filter(game=game).order_by("-number")
            ],
        }
    )


def _incident(game: Game, i: Incident) -> dict[str, Any]:
    return {
        "number": i.number,
        "kind": i.kind,
        "detail": i.detail,
        "started_tick": i.started_tick,
        "ends_tick": i.ends_tick,
        "hours": (i.ends_tick - i.started_tick + 1) / TICKS_PER_HOUR,
        "response": i.response,
        "active": i.started_tick <= game.current_tick + 1 <= i.ends_tick,
    }


@api_view(["GET", "POST"])
def it_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        action = str(request.data.get("action", ""))
        try:
            if action == "respond":
                roles.require(game, "RESPOND_TO_OUTAGE")
                controls.respond_to_outage(game, str(request.data.get("response", "")))
            elif action == "capacity":
                roles.require(game, "SET_IT_CAPACITY")
                controls.set_it_capacity(game, str(request.data.get("level", "")))
            else:
                return _error(ValueError("action must be respond or capacity"))
        except ClockError as exc:
            return _error(exc)
        game.organization.refresh_from_db()
    incidents = [_incident(game, i) for i in Incident.objects.filter(game=game).order_by("-number")]
    return Response(
        {
            "capacity": game.organization.it_capacity,
            "levels": [
                {"level": level, "files_per_night": n, "monthly_cost": str(IT_CAPACITY_COST[level])}
                for level, n in it.CAPACITY.items()
            ],
            "files_waiting": it.waiting(game),
            "down": any(i["active"] for i in incidents),
            "vendor_cost": str(it.VENDOR_COST),
            "incidents": incidents,
        }
    )
