"""Play scripted strategies headlessly across seeds and record their outcomes (P2.12).

python manage.py balance --size small --seeds 81 82 83 --months 6
python manage.py balance --size default --seeds 7 --months 6 --strategies strict_quality fast_coverage

A world is built for each seed unless one of that size and seed exists. Results
go to ``--out`` as JSON lines (one run per line) and are printed as a table.
Games are deleted afterwards unless ``--keep``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.simulation import balancing
from apps.simulation.lifecycle import delete_game
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

COLUMNS = (
    "revenue", "net_profit", "reports_sold", "hit_rate", "wrong_person_rate", "accuracy_true",
    "false_merge_rate", "coverage", "disputes", "findings", "subscribers", "health",
)  # fmt: skip


def world_for(seed: int, size: str) -> World:
    for world in World.objects.filter(seed=seed).order_by("pk"):
        if world.config.get("scale", {}).get("name") == size:
            return world
    g = build_world(seed, size)
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


class Command(BaseCommand):
    help = "Run scripted strategies across seeds and record the outcomes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--size", default="small")
        parser.add_argument("--seeds", type=int, nargs="+", default=[81])
        parser.add_argument("--months", type=int, default=6)
        parser.add_argument(
            "--strategies",
            nargs="+",
            default=list(balancing.STRATEGIES),
            choices=balancing.STRATEGIES,
        )
        parser.add_argument("--out", default="balance-runs.jsonl")
        parser.add_argument("--keep", action="store_true", help="Keep the games")

    def handle(self, *args: Any, **options: Any) -> None:
        out = Path(options["out"])
        rows = []
        for seed in options["seeds"]:
            started = time.perf_counter()
            world = world_for(seed, options["size"])
            self.stdout.write(
                f"World {world.pk} (seed {seed}) in {time.perf_counter() - started:.0f}s"
            )
            for name in options["strategies"]:
                started = time.perf_counter()
                game = balancing.play(world, name, options["months"])
                result = balancing.outcomes(game)
                row = {"size": options["size"], "seed": seed, "strategy": name,
                       "months": options["months"], **result}  # fmt: skip
                rows.append(row)
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, default=str) + "\n")
                self.stdout.write(
                    f"  {name}: {time.perf_counter() - started:.0f}s "
                    + " ".join(f"{c}={row.get(c)}" for c in COLUMNS)
                )
                if not options["keep"]:
                    delete_game(game)
        self.stdout.write(f"{len(rows)} runs written to {out}")
