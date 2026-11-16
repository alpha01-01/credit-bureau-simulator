"""Learning: missions, assistance and the Bureau Handbook (P2.11).

GET  /api/v1/games/<id>/missions/     the campaign: each mission, objectives, debriefs
POST /api/v1/games/<id>/missions/     {"action": "answer", "code": "M1", "value": "12"}
                                      {"action": "campaign", "on": false}
GET  /api/v1/games/<id>/assistance/   the toggles
POST /api/v1/games/<id>/assistance/   {"name": "assist_recommend", "on": true}
                                      {"name": "pause_all", "on": true}
GET  /api/v1/games/<id>/handbook/     every entry, with its citations
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.standards.handbook import DISCLAIMER, ENTRIES

from . import controls, missions
from .api import _error, _game
from .engine import ClockError
from .models import Game, Severity

ALL_SEVERITIES = [s.value for s in Severity]


@api_view(["GET", "POST"])
def missions_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    result: dict[str, Any] = {}
    if request.method == "POST":
        action = str(request.data.get("action", ""))
        try:
            if action == "answer":
                right = controls.answer_mission(
                    game, str(request.data.get("code", "")), str(request.data.get("value", ""))
                )
                result["last_answer"] = {"right": right}
            elif action == "campaign":
                controls.set_campaign(game, bool(request.data.get("on")))
            else:
                return _error(ValueError("action must be answer or campaign"))
        except ClockError as exc:
            return _error(exc)
        game.refresh_from_db()
    return Response({"campaign": game.campaign, "missions": missions.overview(game), **result})


def _assistance(game: Game) -> dict[str, Any]:
    return {
        "assist_accuracy": game.assist_accuracy,
        "assist_recommend": game.assist_recommend,
        "assist_extended_deadlines": game.assist_extended_deadlines,
        "pause_all": sorted(game.pause_severities) == sorted(ALL_SEVERITIES),
    }


@api_view(["GET", "POST"])
def assistance_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        name, on = str(request.data.get("name", "")), bool(request.data.get("on"))
        try:
            if name == "pause_all":
                game = controls.set_pause_rules(
                    game, ALL_SEVERITIES if on else ["CRITICAL"], game.pause_on_deadlines
                )
            else:
                game = controls.set_assistance(game, name, on)
        except ClockError as exc:
            return _error(exc)
    return Response(_assistance(game))


@api_view(["GET"])
def handbook_view(request: Request, game_id: int) -> Response:
    _game(request, game_id)
    return Response({"disclaimer": DISCLAIMER, "entries": [asdict(e) for e in ENTRIES]})
