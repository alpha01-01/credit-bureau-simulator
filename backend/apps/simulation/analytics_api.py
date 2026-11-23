"""Analytics screens (P3.4): portfolio analytics, and (below) the SQL console.

GET /api/v1/games/<id>/analytics/        ?as_of=YYYY-MM-DD (default: latest month on file)
"""

from __future__ import annotations

from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.analytics import console
from apps.bureau.analytics.portfolio import portfolio

from . import controls, roles, scorecards
from .api import _error, _game
from .engine import ClockError
from .models import ScoreModel


@api_view(["GET"])
def analytics_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    as_of = request.query_params.get("as_of")
    try:
        day = date.fromisoformat(as_of) if as_of else None
    except ValueError as exc:
        return _error(exc)
    return Response(portfolio(game.organization_id, day))


@api_view(["GET", "POST"])
def console_view(request: Request, game_id: int) -> Response:
    """The SQL console (P3.4).

    GET  the tables it offers, and whether it is set up.
    POST {"sql": "SELECT ..."}: run one read-only query over this game's own data.
    """
    game = _game(request, game_id)
    if request.method == "GET":
        return Response({"available": console.available(), "tables": console.catalogue(),
                         "max_rows": console.MAX_ROWS, "timeout_seconds": console.TIMEOUT_SECONDS})  # fmt: skip
    if "console" not in roles.ROLES[game.role].screens:
        raise roles.RoleError(
            f"The SQL console is the Head of Data Analytics's (and the Chief Executive's). "
            f"You are working as the {roles.ROLES[game.role].title}; switch role to use it."
        )
    try:
        result = console.run(game.organization_id, str(request.data.get("sql", "")))
    except console.ConsoleError as exc:
        return _error(exc)
    return Response(
        {
            "columns": result.columns,
            "rows": result.rows,
            "truncated": result.truncated,
            "milliseconds": result.milliseconds,
        }
    )


@api_view(["GET", "POST"])
def scorecards_view(request: Request, game_id: int) -> Response:
    """The scorecard workbench (P3.5).

    GET  the options (terms, features, windows and observation dates), the models built,
         and Compliance's findings.
    POST {"action": "build", "term", "observation", "window", "features"},
         {"action": "composite", "observation", "window"} or {"action": "deploy", "number"}.
    """
    game = _game(request, game_id)
    if request.method == "POST":
        data = request.data
        action = str(data.get("action", ""))
        try:
            if action == "build":
                roles.require(game, "BUILD_SCORECARD")
                model = controls.build_scorecard(
                    game, str(data.get("term", "")), date.fromisoformat(str(data.get("observation"))),
                    int(data.get("window", 12)), [str(f) for f in data.get("features", [])],
                )  # fmt: skip
            elif action == "composite":
                roles.require(game, "BUILD_COMPOSITE")
                model = controls.build_composite(
                    game,
                    date.fromisoformat(str(data.get("observation"))),
                    int(data.get("window", 12)),
                )
            elif action == "deploy":
                roles.require(game, "DEPLOY_SCORECARD")
                model = controls.deploy_scorecard(game, int(data.get("number", 0)))
            else:
                return _error(ValueError("action must be build, composite or deploy"))
        except (ClockError, ValueError, TypeError) as exc:
            return _error(exc)
        return Response(scorecards.summary(model))
    return Response(
        {
            "options": scorecards.options(game),
            "models": [scorecards.summary(m) for m in game.score_models.order_by("-number")],
            "findings": list(
                game.compliance_findings.order_by("-number").values(
                    "number", "kind", "reference", "detail", "raised_at", "resolved_tick"
                )
            ),
        }
    )


@api_view(["GET"])
def scorecard_detail(request: Request, game_id: int, number: int) -> Response:
    """One model: its characteristics, validation, fairness, truth and monitoring."""
    game = _game(request, game_id)
    model = get_object_or_404(ScoreModel, game=game, number=number)
    return Response(
        {
            **scorecards.summary(model),
            "results": model.results,
            "monitoring": scorecards.monitor(game, model),
        }
    )
