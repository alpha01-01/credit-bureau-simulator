"""Run one reporting month end to end: provider files -> delivery -> bureau pipeline.

    python manage.py process_month --world 1 --period 2026-11
    python manage.py process_month --game 1 --period 2026-12 --lender HZF

Creates a game (a bureau) for the world on first use. Provider files are
generated if they do not exist yet.
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.bureau.quality.models import ValidationIssue
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.simulation.models import Delivery, Game
from apps.world.models import Lender, ProviderSubmission, World
from apps.world.provider_files import generate_submission, month_end
from apps.world.provider_files.profiles import REPORTING_PROVIDERS


class Command(BaseCommand):
    help = "Deliver a month's provider files to the bureau and process them."

    def add_arguments(self, parser: CommandParser) -> None:
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--world", type=int, help="World id (uses or creates its game)")
        target.add_argument("--game", type=int, help="Game id")
        parser.add_argument("--period", required=True, help="Reporting month, YYYY-MM")
        parser.add_argument("--lender", action="append", help="Provider code (repeatable)")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            year, month = (int(p) for p in options["period"].split("-"))
            period = month_end(year, month)
        except ValueError as exc:
            raise CommandError("Period must look like 2026-12") from exc

        if options["game"]:
            game = Game.objects.select_related("world").filter(pk=options["game"]).first()
            if game is None:
                raise CommandError(f"No game with id {options['game']}")
        else:
            world = World.objects.filter(pk=options["world"]).first()
            if world is None:
                raise CommandError(f"No world with id {options['world']}")
            game = Game.objects.filter(world=world).order_by("pk").first() or start_game(world)
            self.stdout.write(f"Game {game.pk}: {game.organization.name}")
        world = game.world

        for code in options["lender"] or REPORTING_PROVIDERS:
            lender = Lender.objects.get(world=world, code=code)
            world_sub = ProviderSubmission.objects.filter(lender=lender, period=period).first()
            if world_sub is None:
                world_sub = generate_submission(world, lender, period).submission
            if Delivery.objects.filter(game=game, world_submission=world_sub).exists():
                self.stdout.write(f"{code} {period:%Y-%m}: already delivered, skipped")
                continue

            started = time.perf_counter()
            submission = deliver(game, world_sub)
            run = process_submission(submission)
            late = " LATE" if submission.is_late else ""
            self.stdout.write(
                f"{code} {period:%Y-%m}{late}  received {run.records_received:,}  "
                f"accepted {run.records_accepted:,}  unloadable {run.records_unloadable:,}  "
                f"duplicate {run.records_duplicated:,}  | new customers {run.customers_created:,}  "
                f"new accounts {run.accounts_created:,}  ({time.perf_counter() - started:.1f}s)"
            )
            for f in submission.files.filter(file_status="REJECTED"):
                self.stdout.write(f"    file {f.file_name} REJECTED ({f.rejection_reason})")
            errors = (
                ValidationIssue.objects.filter(run=run)
                .values_list("rule_code", flat=True)
                .order_by("rule_code")
            )
            counts: dict[str, int] = {}
            for code_ in errors:
                counts[code_] = counts.get(code_, 0) + 1
            if counts:
                self.stdout.write(
                    "    issues: " + ", ".join(f"{k} {v:,}" for k, v in counts.items())
                )
