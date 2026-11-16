"""Bureau Health and the paths to failure (P2.10).

GET  /api/v1/games/<id>/health/   the five dimensions, board reviews, the three
                                  hard failures with where the bureau stands on each
POST /api/v1/games/<id>/health/   {"action": "funding", "amount": "500000"}
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from . import controls, solvency
from .api import _error, _game
from .engine import ClockError
from .failure import ENDINGS, INSOLVENT, LICENCE_REVOKED, PATHS, REMOVED_BY_BOARD
from .health import health
from .models import BoardReview, FundingRequest, Game, RegulatorStanding


def _path(key: str, current: str | None, extra: str = "") -> dict[str, Any]:
    """A failure's warning path, with the steps already reached."""
    spec = PATHS[key]
    codes = [code for code, _ in spec["steps"]]
    reached = codes.index(current) if current in codes else -1
    return {
        "key": key,
        "name": spec["name"],
        "steps": [
            {"code": code, "label": label, "reached": i <= reached}
            for i, (code, label) in enumerate(spec["steps"])
        ],
        "current": spec["steps"][reached][1] if reached >= 0 else None,
        "next": spec["steps"][reached + 1][1] if reached + 1 < len(codes) else None,
        "detail": extra,
        "path_back": spec["path_back"],
    }


def failure_paths(game: Game) -> list[dict[str, Any]]:
    record = getattr(game, "solvency", None)
    stage = record.stage if record else "OK"
    deadline = record.creditors_deadline if record else None
    level = RegulatorStanding.objects.filter(game=game).values_list("level", flat=True).first() or 0
    reviews = list(BoardReview.objects.filter(game=game).order_by("-period")[:2])
    verdict = reviews[0].verdict if reviews else None
    return [
        _path(
            INSOLVENT,
            stage,
            f"Creditors' deadline {deadline:%d %B %Y}."
            if stage == "CREDITORS" and deadline
            else "",
        ),
        _path(LICENCE_REVOKED, str(level) if level else None),
        _path(
            REMOVED_BY_BOARD,
            verdict if verdict in ("CONCERNED", "NO_CONFIDENCE", "REMOVED") else None,
            f"Last review: confidence {reviews[0].confidence:.0f}." if reviews else "",
        ),
    ]


@api_view(["GET", "POST"])
def health_view(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    if request.method == "POST":
        if str(request.data.get("action", "")) != "funding":
            return _error(ValueError("action must be funding"))
        try:
            controls.request_funding(game, Decimal(str(request.data.get("amount"))))
        except (ClockError, InvalidOperation) as exc:
            return _error(exc)
        game.refresh_from_db()
    _, at = controls._now(game)
    return Response(
        {
            **health(game, at),
            "ended": {"reason": game.ended_reason, "title": ENDINGS[game.ended_reason]}
            if game.ended_reason
            else None,
            "failures": failure_paths(game),
            "board_reviews": [
                {
                    "period": r.period,
                    "confidence": r.confidence,
                    "verdict": r.verdict,
                    "detail": r.detail,
                    "parts": r.parts,
                }
                for r in BoardReview.objects.filter(game=game).order_by("-period")
            ],
            "funding": {
                "max": str(solvency.MAX_FUNDING),
                "needs_confidence": solvency.FUNDING_CONFIDENCE,
                "requests": [
                    {
                        "number": f.number,
                        "requested_at": f.requested_at,
                        "amount": str(f.amount),
                        "granted": f.granted,
                        "reason": f.reason,
                    }
                    for f in FundingRequest.objects.filter(game=game).order_by("-number")
                ],
            },
        }
    )
