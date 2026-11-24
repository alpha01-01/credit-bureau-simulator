"""The Finance department's screens (P3.8).

GET/POST /api/v1/games/<id>/finance/bills/    bills; approve, reject, the approval limit
GET/POST /api/v1/games/<id>/finance/bank/     ?period=; post or query a line, complete
GET/POST /api/v1/games/<id>/finance/budget/   ?month=; set a budget, mark it reviewed
GET/POST /api/v1/games/<id>/finance/close/    the checklist; close the month
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.finance import bank, budget
from apps.finance.models import BankStatement, BillStatus, LineStatus, MonthClose, SupplierBill

from . import controls, finance_dept, roles
from .api import _error, _game
from .clock import previous_month_end
from .engine import ClockError
from .models import Game

ERRORS = (ClockError, ValueError, TypeError, InvalidOperation)


def _today(game: Game) -> date:
    return controls.state(game).now.date()


@api_view(["GET", "POST"])
def bills_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        data, action = request.data, str(request.data.get("action", ""))
        try:
            if action == "approve":
                roles.require(game, "APPROVE_BILL")
                controls.approve_bill(game, int(data.get("number", 0)))
            elif action == "reject":
                roles.require(game, "REJECT_BILL")
                controls.reject_bill(game, int(data.get("number", 0)))
            elif action == "limit":
                roles.require(game, "SET_APPROVAL_LIMIT")
                controls.set_approval_limit(game, Decimal(str(data.get("amount"))))
            else:
                return _error(ValueError("action must be approve, reject or limit"))
        except ERRORS as exc:
            return _error(exc)
        game.organization.refresh_from_db()
    today = _today(game)
    bills = list(
        SupplierBill.objects.filter(organization=game.organization).order_by("-number")[:200]
    )
    earlier: dict[tuple[str, str], int] = {}
    for b in sorted(bills, key=lambda x: x.number):
        earlier.setdefault((b.supplier_code, b.reference), b.number)
    return Response(
        {
            "approval_limit": game.organization.bill_approval_limit,
            "late_charge_rate": "0.02",
            "bills": [
                {
                    "number": b.number,
                    "supplier": b.supplier_name,
                    "reference": b.reference,
                    "description": b.description,
                    "account": b.account_code,
                    "amount": b.amount,
                    "bill_date": b.bill_date,
                    "due_date": b.due_date,
                    "status": b.status,
                    "approved_by": b.approved_by or None,
                    "paid_on": b.paid_on,
                    "late_fee": b.late_fee,
                    "overdue": b.status in (BillStatus.RECEIVED, BillStatus.APPROVED)
                    and b.due_date < today,
                    # What the bureau can see: another bill under the same reference.
                    "same_reference_as": earlier[(b.supplier_code, b.reference)]
                    if earlier[(b.supplier_code, b.reference)] != b.number
                    else None,
                }
                for b in bills
            ],
        }
    )


def _line(line: Any) -> dict[str, Any]:
    return {
        "period": line.statement.period,
        "line": line.line_number,
        "value_date": line.value_date,
        "description": line.description,
        "reference": line.reference or None,
        "amount": line.amount,
        "status": line.status,
        "answer": line.answer or None,
        "awaiting_answer": line.status == LineStatus.QUERIED and not line.answer,
    }


@api_view(["GET", "POST"])
def bank_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    org = game.organization
    statements = list(BankStatement.objects.filter(organization=org).order_by("-period"))
    asked = request.query_params.get("period") or request.data.get("period")
    try:
        period = date.fromisoformat(str(asked)) if asked else None
    except ValueError as exc:
        return _error(exc)
    if request.method == "POST":
        data, action = request.data, str(request.data.get("action", ""))
        try:
            if period is None:
                raise ValueError("'period' is required")
            if action == "post":
                roles.require(game, "POST_STATEMENT_LINE")
                controls.post_statement_line(game, period, int(data.get("line", 0)))
            elif action == "query":
                roles.require(game, "QUERY_STATEMENT_LINE")
                controls.query_statement_line(game, period, int(data.get("line", 0)))
            elif action == "complete":
                roles.require(game, "COMPLETE_RECONCILIATION")
                controls.complete_reconciliation(game, period)
            else:
                return _error(ValueError("action must be post, query or complete"))
        except ERRORS as exc:
            return _error(exc)
        statements = list(BankStatement.objects.filter(organization=org).order_by("-period"))
    chosen = next((s for s in statements if s.period == period), None) if period else None
    chosen = chosen or (statements[0] if statements else None)
    body: dict[str, Any] = {
        "statements": [
            {
                "period": s.period,
                "closing_balance": s.closing_balance,
                "reconciled": s.reconciled_at is not None,
            }
            for s in statements
        ],
        "statement": None,
    }
    if chosen is not None:
        found = bank.summary(chosen)
        body["statement"] = {
            "period": chosen.period,
            "opening_balance": chosen.opening_balance,
            "closing_balance": chosen.closing_balance,
            "received_at": chosen.received_at,
            "reconciled_at": chosen.reconciled_at,
            "lines": [
                _line(x) for x in chosen.lines.select_related("statement").order_by("line_number")
            ],
            "ledger_balance": found["ledger_balance"],
            "difference": found["difference"],
            "uncleared": found["uncleared"],
            "unrecorded": [_line(x) for x in found["unrecorded"]],
            "explained_balance": found["explained_balance"],
            "reconciles": found["reconciles"],
            "open_items": found["open_items"],
        }
    return Response(body)


@api_view(["GET", "POST"])
def budget_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    today = _today(game)
    asked = request.query_params.get("month") or request.data.get("month")
    try:
        month = date.fromisoformat(str(asked)) if asked else today
    except ValueError as exc:
        return _error(exc)
    if request.method == "POST":
        data, action = request.data, str(request.data.get("action", ""))
        try:
            if action == "set":
                roles.require(game, "SET_BUDGET")
                controls.set_budget(
                    game, str(data.get("centre", "")), Decimal(str(data.get("amount"))),
                    month.replace(day=1),
                )  # fmt: skip
            elif action == "review":
                roles.require(game, "REVIEW_BUDGET")
                controls.review_budget(game, budget.month_bounds(month)[1])
            else:
                return _error(ValueError("action must be set or review"))
        except ERRORS as exc:
            return _error(exc)
    months: list[date] = []
    cursor = budget.month_bounds(today)[1]
    while cursor >= game.clock_start.replace(day=1) and len(months) < 12:
        months.append(cursor)
        cursor = previous_month_end(cursor)
    found = budget.report(game.organization, month)
    reviewed = MonthClose.objects.filter(
        organization=game.organization, period=found["month"], budget_reviewed_at__isnull=False
    ).exists()
    return Response(found | {"months": months, "reviewed": reviewed})


@api_view(["GET", "POST"])
def close_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        try:
            roles.require(game, "CLOSE_MONTH")
            controls.close_month(game, date.fromisoformat(str(request.data.get("period"))))
        except ERRORS as exc:
            return _error(exc)
        game.organization.refresh_from_db()
    period = finance_dept.next_to_close(game)
    today = _today(game)
    return Response(
        {
            "closed_through": game.organization.closed_through,
            "period": period,
            "ended": period < today,
            "checklist": finance_dept.checklist(game, period),
            "closed": list(
                MonthClose.objects.filter(organization=game.organization, closed_at__isnull=False)
                .order_by("-period")
                .values("period", "closed_at")
            ),
        }
    )
