"""Start a game: a bureau in a world, established with pre-loaded history.

python manage.py start_game --world 1
python manage.py start_game --world 1 --history-months 0   # a bureau with no past
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.bureau.core.models import AccountObservation, CreditAccount, Customer
from apps.simulation.bridge import start_game
from apps.simulation.history import DEFAULT_HISTORY_MONTHS
from apps.workitems.models import ResolvedBy, WorkItem
from apps.world.models import World


class Command(BaseCommand):
    help = "Start a game in a world, with the bureau's history pre-loaded."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--world", type=int, required=True)
        parser.add_argument("--history-months", type=int, default=DEFAULT_HISTORY_MONTHS)

    def handle(self, *args: Any, **options: Any) -> None:
        world = World.objects.filter(pk=options["world"]).first()
        if world is None:
            raise CommandError(f"No world with id {options['world']}")
        started = time.perf_counter()
        game = start_game(world, history_months=options["history_months"])
        org = game.organization
        past = WorkItem.objects.filter(organization=org, resolved_by=ResolvedBy.HISTORIC)
        self.stdout.write(
            f"Game {game.pk} ready in {time.perf_counter() - started:.0f}s: "
            f"{Customer.objects.filter(organization=org).count():,} customers, "
            f"{CreditAccount.objects.filter(organization=org).count():,} accounts, "
            f"{AccountObservation.objects.filter(credit_account__organization=org).count():,} "
            f"observations; {past.count():,} past review cases "
            f"({past.filter(is_correct=False).count():,} decided wrongly by former staff)"
        )
