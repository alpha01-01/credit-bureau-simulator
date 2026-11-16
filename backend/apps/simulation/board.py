"""Quarterly board reviews and the board's confidence (P2.10; Document 07, Section 10.2).

ASSUMPTION A-066: every game is in the Established mode, so it has a board. At the
first tick of January, April, July and October the board reviews the quarter just
ended (if the game played all of it). Its confidence is the bureau's overall
health (A-067). From 65 it is confident; from 55 concerned; below 55 it has no
confidence, and a second such review in a row removes the managing director: the
game ends. (Measured on a small world: a careful bureau scores about 80; one that
lets in no data and underpays its staff 52 and then 46.)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .failure import PATHS, REMOVED_BY_BOARD, end_game
from .health import health
from .models import BoardReview, Game, Severity

CONFIDENT_FROM, CONCERNED_FROM = 65.0, 55.0

QUARTER_MONTHS = (1, 4, 7, 10)
NAMES = {
    "financial": "finances",
    "data_quality": "data quality",
    "reputation": "reputation",
    "compliance": "compliance",
    "team": "the team",
}


def _quarter_start(today: date) -> date:
    month = today.month - 3
    year = today.year
    if month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def quarterly_review(
    game: Game, today: date, at: datetime, tick: int, add: Any
) -> BoardReview | None:
    if today.month not in QUARTER_MONTHS:
        return None
    start = _quarter_start(today)
    if game.clock_start > start:
        return None  # the management has not had a full quarter yet
    period = date(today.year, today.month, 1) - timedelta(days=1)  # the quarter's last day
    if BoardReview.objects.filter(game=game, period=period).exists():
        return None
    summary = health(game, at)
    confidence = summary["overall"]
    parts = {name: part["score"] for name, part in summary["parts"].items()}
    weakest = sorted(
        (name for name, score in parts.items() if score is not None and score < CONFIDENT_FROM),
        key=lambda name: parts[name] or 0.0,
    )
    previous = BoardReview.objects.filter(game=game).order_by("-period").first()
    if confidence >= CONFIDENT_FROM:
        verdict = "CONFIDENT"
    elif confidence >= CONCERNED_FROM:
        verdict = "CONCERNED"
    else:
        verdict = "NO_CONFIDENCE"
    removed = (
        verdict == "NO_CONFIDENCE"
        and previous is not None
        and (previous.verdict == "NO_CONFIDENCE")
    )
    worry = (
        "The board is worried about " + ", ".join(NAMES[n] for n in weakest[:3]) + "."
        if weakest
        else "Every part of the bureau is in good health."
    )
    review = BoardReview.objects.create(
        game=game, period=period, tick=tick, confidence=confidence, parts=parts,
        verdict="REMOVED" if removed else verdict, detail=worry,
    )  # fmt: skip
    drill = {"screen": "health", "params": {}}
    quarter = f"Q{(period.month - 1) // 3 + 1} {period.year}"
    if removed:
        end_game(
            game, REMOVED_BY_BOARD, tick,
            f"Confidence {confidence:.0f} at the {quarter} review, after no confidence at the "
            f"last one. {worry}",
            add,
        )  # fmt: skip
    elif verdict == "NO_CONFIDENCE":
        add(
            "BOARD_NO_CONFIDENCE", Severity.CRITICAL,
            f"The board has no confidence in the management ({confidence:.0f})",
            f"{quarter} review. {worry} If the next review is below {CONCERNED_FROM:.0f} too, you will be "
            f"removed. {PATHS[REMOVED_BY_BOARD]['path_back']}",
            drill,
        )  # fmt: skip
    elif verdict == "CONCERNED":
        add(
            "BOARD_CONCERNED", Severity.WARNING,
            f"The board is concerned ({confidence:.0f})",
            f"{quarter} review. {worry} Below {CONCERNED_FROM:.0f} it loses confidence.",
            drill,
        )  # fmt: skip
    else:
        add(
            "BOARD_CONFIDENT", Severity.INFO,
            f"The board is confident in the management ({confidence:.0f})",
            f"{quarter} review. {worry}",
            drill,
        )  # fmt: skip
    return review
