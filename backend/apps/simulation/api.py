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
