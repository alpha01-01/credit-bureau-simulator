"""Hard failures and the paths to them (P2.10; Document 07, Section 10.2).

Three things end a game: insolvency, a revoked licence and, in the Established
mode, removal by the board. Each is reached only through warnings in order, and
at every step the player is told what comes next and how to turn back.
"""

from __future__ import annotations

from typing import Any

from .models import Game, GameStatus, Severity

INSOLVENT, LICENCE_REVOKED, REMOVED_BY_BOARD = "INSOLVENT", "LICENCE_REVOKED", "REMOVED_BY_BOARD"

# For each failure: the steps of its warning path, and how to get back.
PATHS: dict[str, dict[str, Any]] = {
    INSOLVENT: {
        "name": "Insolvency",
        "steps": [
            ("LOW", "Cash below one month's costs"),
            ("OVERDRAFT", "The overdraft facility in use"),
            ("CREDITORS", "Creditors' notice: back within the overdraft limit by the deadline"),
            ("INSOLVENT", "Insolvency"),
        ],
        "path_back": (
            "Bring cash in and costs down: chase unpaid invoices, sign new subscribers, "
            "drop extra IT capacity or matching software, hold back pay rises, or ask the "
            "shareholders for capital (they agree only while the board has confidence)."
        ),
    },
    LICENCE_REVOKED: {
        "name": "Licence revoked",
        "steps": [
            ("1", "Concern letter"),
            ("2", "Formal directive"),
            ("3", "Financial penalty"),
            ("4", "Licence suspended"),
            ("5", "Licence revoked"),
        ],
        "path_back": (
            "Settle every dispute within the statutory period. Findings fall away after six "
            "months, and the regulator steps back down as they do; no new findings is the "
            "only way back."
        ),
    },
    REMOVED_BY_BOARD: {
        "name": "Removed by the board",
        "steps": [
            ("CONCERNED", "A quarterly review below 65: the board is concerned"),
            ("NO_CONFIDENCE", "A review below 55: no confidence; one more and you are removed"),
            ("REMOVED", "Removed by the board"),
        ],
        "path_back": (
            "The board's confidence is the bureau's health: lift the weakest dimension "
            "before the next quarterly review (see Bureau Health)."
        ),
    },
}

ENDINGS = {
    INSOLVENT: "The bureau is insolvent",
    LICENCE_REVOKED: "The regulator has revoked the bureau's licence",
    REMOVED_BY_BOARD: "The board has removed you as managing director",
}


def ended(game: Game) -> bool:
    return game.status == GameStatus.ENDED


def end_game(game: Game, reason: str, tick: int, detail: str, add: Any) -> None:
    """A hard failure: the clock stops for good; the game can still be looked at."""
    game.status = GameStatus.ENDED
    game.ended_tick = tick
    game.ended_reason = reason
    game.save(update_fields=["status", "ended_tick", "ended_reason"])
    add("GAME_OVER", Severity.CRITICAL, ENDINGS[reason], detail, {"screen": "health", "params": {}})
