"""Take or list a game's checkpoints (Document 07, Section 12.3).

python manage.py checkpoint --game 2                     # list them
python manage.py checkpoint --game 2 --take "before fix" # take one now
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.simulation import controls
from apps.simulation.models import Game


class Command(BaseCommand):
    help = "List a game's checkpoints, or take one now."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--game", type=int, required=True)
        parser.add_argument("--take", metavar="LABEL", help="take a checkpoint with this label")

    def handle(self, *args: Any, **options: Any) -> None:
        game = Game.objects.filter(pk=options["game"]).first()
        if game is None:
            raise CommandError(f"No game with id {options['game']}")
        if options["take"] is not None:
            taken = controls.checkpoint(game, options["take"])
            self.stdout.write(f"Checkpoint {taken.pk} at tick {taken.tick}: {taken.digest[:12]}")
            return
        for cp in game.checkpoints.order_by("tick", "pk"):
            self.stdout.write(
                f"{cp.pk:>6}  tick {cp.tick:>6}  {cp.sim_time:%Y-%m-%d}  {cp.kind:<9}  "
                f"actions {cp.action_count:>4}  {cp.digest[:12]}  {cp.label}"
            )
