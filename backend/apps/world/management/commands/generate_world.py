"""Generate a synthetic world: python manage.py generate_world --seed 42 --scale default"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.world.generation import build_world
from apps.world.generation.config import SCALES
from apps.world.generation.persist import write_world


class Command(BaseCommand):
    help = "Generate a synthetic world (people, lenders, loans and their history) and store it."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--seed", type=int, required=True)
        parser.add_argument("--scale", choices=sorted(SCALES), default="default")
        parser.add_argument(
            "--history-end", type=date.fromisoformat, default=None, help="YYYY-MM-DD"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Simulate and report without saving"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        started = time.monotonic()
        world = build_world(options["seed"], options["scale"], options["history_end"])
        simulated = time.monotonic()
        self.stdout.write(f"Simulated in {simulated - started:.1f}s")
        for line in world.stats.as_lines():
            self.stdout.write("  " + line)
        if options["dry_run"]:
            return
        with transaction.atomic():
            world_id = write_world(
                world.config,
                world.people,
                world.businesses,
                world.branches,
                world.result,
                world.stats,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved world {world_id} in {time.monotonic() - simulated:.1f}s "
                f"({len(world.result.snapshots):,} loan-months)"
            )
        )
