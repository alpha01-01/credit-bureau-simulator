"""Analytics screens (P3.4): portfolio analytics, and (below) the SQL console.

GET /api/v1/games/<id>/analytics/        ?as_of=YYYY-MM-DD (default: latest month on file)
"""

from __future__ import annotations

from datetime import date

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.analytics import console
from apps.bureau.analytics.portfolio import portfolio

from . import roles
from .api import _error, _game


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
