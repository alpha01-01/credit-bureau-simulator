"""Performance on a full-size game with every system on (P3.15; Document 09).

    python manage.py perf --months 2 --out ../docs/balancing/perf-full.json

A default-size world (40,000 people, mobile loans, the standard economy) with an
established bureau and 12 months of history, the campaign on. The player develops the
score product and deploys careful scorecards, keeps up compliance's duties, and sells
as ``steady`` does; every other system runs as in play. Each month of play is timed,
then every screen's API is called three times as the game's owner and the slowest
call kept. The game and its user are deleted afterwards unless ``--keep``.
"""

from __future__ import annotations

import contextlib
import json
import statistics
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.test import Client

from apps.accounts.models import User
from apps.simulation import balancing, controls, scenarios
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError
from apps.simulation.lifecycle import delete_game
from apps.simulation.models import GameStatus

SCREENS = (
    "", "dashboard/", "briefing/", "submissions/", "customers/", "accounts/", "ledger/",
    "invoices/", "clock/", "feed/", "data-assets/", "reviews/", "work-items/", "employees/",
    "rejection-policy/", "matching-policy/", "rules/", "providers/", "disputes/", "market/",
    "staff/", "sales/", "onboarding/", "support/", "products/", "batches/", "economy/",
    "startup/", "it/", "health/", "missions/", "assistance/", "role/", "office/",
    "analytics/", "scorecards/", "compliance/", "handbook/", "enquiries/", "finance/",
    "finance/bills/", "finance/bank/", "finance/budget/", "finance/close/",
)  # fmt: skip


class Command(BaseCommand):
    help = "Time a full-size game with every system on, and every screen's API."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--seed", type=int, default=44)
        parser.add_argument("--months", type=int, default=2)
        parser.add_argument("--out", default="perf-full.json")
        parser.add_argument("--keep", action="store_true", help="Keep the game")

    def say(self, line: str) -> None:
        self.stdout.write(line)
        self.stdout.flush()

    def handle(self, *args: Any, **options: Any) -> None:
        result: dict[str, object] = {"seed": options["seed"], "size": "default"}

        started = time.perf_counter()
        world = scenarios.find_world(
            options["seed"], "default", "STANDARD"
        ) or scenarios.make_world(options["seed"], "default", "STANDARD")
        result["world"] = world.pk
        result["world_seconds"] = round(time.perf_counter() - started)
        self.say(f"world {world.pk} in {result['world_seconds']}s")

        user, _ = User.objects.get_or_create(username="perf-check")
        started = time.perf_counter()
        game = controls.set_pause_rules(
            start_game(world, owner=user, history_months=12), [], deadlines=False
        )
        result["game"] = game.pk
        result["setup_seconds"] = round(time.perf_counter() - started)
        self.say(f"game {game.pk} ready in {result['setup_seconds']}s")

        months = []
        try:
            for month in range(options["months"]):
                started = time.perf_counter()
                game = balancing.score_careful(game, month)
                last = controls.state(game).now.date().replace(day=1) - timedelta(days=1)
                for code in game.organization.subscribers.filter(is_active=True).values_list(
                    "subscriber_code", flat=True
                ):
                    with contextlib.suppress(ClockError):
                        controls.sample_consent(game, code, last, 25)
                current, steps = controls.state(game).now.month, 0
                while controls.state(game).now.month == current and game.status != GameStatus.ENDED:
                    game = controls.advance_by(game, "next_event")
                    balancing._tend(game, "compliance_diligent")
                    steps += 1
                seconds = round(time.perf_counter() - started, 1)
                months.append({"month": month, "seconds": seconds, "steps": steps})
                self.say(f"month {month}: {seconds}s in {steps} steps")
            result["months"] = months
            result["outcomes"] = balancing.outcomes(game)

            client = Client(HTTP_HOST="localhost")
            client.force_login(user)
            timings = {}
            for screen in SCREENS:
                path = f"/api/v1/games/{game.pk}/{screen}"
                calls = []
                for _ in range(3):
                    t = time.perf_counter()
                    response = client.get(path)
                    calls.append(time.perf_counter() - t)
                timings[screen or "game"] = {
                    "status": response.status_code,
                    "slowest_ms": round(max(calls) * 1000),
                    "median_ms": round(statistics.median(calls) * 1000),
                }
                self.say(
                    f"{screen or 'game':22} {response.status_code} {max(calls) * 1000:6.0f} ms"
                )
            result["screens"] = timings
        finally:
            Path(options["out"]).write_text(
                json.dumps(result, indent=1, default=str), encoding="utf-8"
            )
            if not options["keep"]:
                delete_game(game)
                user.delete()
