"""The clock worker: advances running games in real time (Document 07, Section 5.1).

    python manage.py run_clock

At 1x one tick (15 game minutes) takes 5 real seconds, so a game hour takes
20 seconds and a working day 3 minutes. Paused games are left alone.
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.simulation.clock import REAL_SECONDS_PER_TICK_AT_1X
from apps.simulation.controls import step
from apps.simulation.models import Game, GameStatus


class Command(BaseCommand):
    help = "Advance running games in real time."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--game", type=int, help="Only this game")
        parser.add_argument("--max-ticks", type=int, help="Stop after this many ticks (testing)")

    def handle(self, *args: Any, **options: Any) -> None:
        due: dict[int, float] = {}
        ticks = 0
        while options["max_ticks"] is None or ticks < options["max_ticks"]:
            games = Game.objects.filter(status=GameStatus.RUNNING, setup_status="READY")
            if options["game"]:
                games = games.filter(pk=options["game"])
            now = time.monotonic()
            for game in games:
                if due.get(game.pk, 0.0) > now:
                    continue
                step(game)
                ticks += 1
                due[game.pk] = now + REAL_SECONDS_PER_TICK_AT_1X / game.speed
            time.sleep(0.2)
