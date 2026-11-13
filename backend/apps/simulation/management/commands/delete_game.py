"""Delete a game and its bureau, or a world together with all its games.

python manage.py delete_game --game 2
python manage.py delete_game --world 1
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.simulation.lifecycle import delete_game, delete_world_with_games
from apps.simulation.models import Game
from apps.world.models import World


class Command(BaseCommand):
    help = "Delete a game (and its bureau data), or a world with all its games."

    def add_arguments(self, parser: CommandParser) -> None:
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--game", type=int)
        target.add_argument("--world", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        if options["game"]:
            game = Game.objects.filter(pk=options["game"]).first()
            if game is None:
                raise CommandError(f"No game with id {options['game']}")
            delete_game(game)
            self.stdout.write(f"Deleted game {options['game']}")
        else:
            if not World.objects.filter(pk=options["world"]).exists():
                raise CommandError(f"No world with id {options['world']}")
            delete_world_with_games(options["world"])
            self.stdout.write(f"Deleted world {options['world']} and its games")
