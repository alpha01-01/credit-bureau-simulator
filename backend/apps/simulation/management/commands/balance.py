"""Play scripted strategies headlessly across seeds and record their outcomes (P2.12).

python manage.py balance --size small --seeds 81 82 83 --months 6
python manage.py balance --size default --seeds 7 --months 6 --strategies strict_quality fast_coverage
python manage.py balance --size small --seeds 81 --months 6 --history 6 --strategies score_careful score_careless
python manage.py balance --size small --seeds 81 --months 6 --scenario STARTUP --difficulty BEGINNER EXPERT

Each run is played in a world of the seed and size with the economy its difficulty
(or a Sandbox's ``--sandbox`` settings) asks for, and mobile loans, as a new game in the app
would be (P3.15); it is built unless one exists. Results
go to ``--out`` as JSON lines (one run per line) and are printed as a table.
Games are deleted afterwards unless ``--keep``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.simulation import balancing, scenarios
from apps.simulation.lifecycle import delete_game
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

COLUMNS = (
    "revenue", "net_profit", "bank", "reports_sold", "report_price", "scores_sold", "score_auc",
    "hit_rate", "wrong_person_rate", "accuracy_true", "false_merge_rate", "coverage",
    "disputes", "findings", "improper_enquiry_rate", "subscribers", "health", "ended",
)  # fmt: skip


def world_for(seed: int, size: str, economy: str = "STILL") -> World:
    """A current world of this seed, size and economy (with mobile loans), built if need be."""
    found = scenarios.find_world(seed, size, economy)
    return found if found is not None else scenarios.make_world(seed, size, economy)


def legacy_world(seed: int, size: str) -> World:
    """The first stored world of this seed and size, whatever its economy (P2.12's runs)."""
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
        parser.add_argument(
            "--scenario", default="ESTABLISHED", choices=["ESTABLISHED", "STARTUP", "SANDBOX"]
        )
        parser.add_argument(
            "--difficulty", nargs="+", default=["INTERMEDIATE"],
            choices=["BEGINNER", "INTERMEDIATE", "EXPERT"],
        )  # fmt: skip
        parser.add_argument("--history", type=int, default=0, help="Months of past files")
        parser.add_argument(
            "--sandbox",
            type=json.loads,
            default=None,
            help='A Sandbox\'s settings, as JSON: {"provider_quality": 2}',
        )
        parser.add_argument(
            "--legacy-worlds",
            action="store_true",
            help="Play in the first stored world of each seed (P2.12)",
        )
        parser.add_argument("--out", default="balance-runs.jsonl")
        parser.add_argument("--keep", action="store_true", help="Keep the games")

    def handle(self, *args: Any, **options: Any) -> None:
        out = Path(options["out"])
        rows = []
        for seed in options["seeds"]:
            for difficulty, name in [
                (d, n) for d in options["difficulty"] for n in options["strategies"]
            ]:
                params = scenarios.resolve(options["scenario"], difficulty, options["sandbox"])
                started = time.perf_counter()
                world = (
                    legacy_world(seed, options["size"])
                    if options["legacy_worlds"]
                    else world_for(seed, options["size"], params.economy)
                )
                game = balancing.play(
                    world, name, options["months"], difficulty, options["scenario"],
                    options["history"], options["sandbox"],
                )  # fmt: skip
                result = balancing.outcomes(game)
                row = {"size": options["size"], "seed": seed, "world": world.pk, "strategy": name,
                       "months": options["months"], "history": options["history"],
                       "settings": options["sandbox"],
                       "seconds": round(time.perf_counter() - started), **result}  # fmt: skip
                rows.append(row)
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, default=str) + "\n")
                self.stdout.write(
                    f"  {name} ({difficulty}, world {world.pk}): "
                    f"{time.perf_counter() - started:.0f}s "
                    + " ".join(f"{c}={row.get(c)}" for c in COLUMNS)
                )
                self.stdout.flush()
                if not options["keep"]:
                    delete_game(game)
        self.stdout.write(f"{len(rows)} runs written to {out}")
