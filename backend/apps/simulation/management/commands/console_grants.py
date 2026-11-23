"""Let the console role read the console's views (P3.4).

The migration grants this if the role exists already; run this after a database
administrator creates the role (README, "The SQL console").
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.bureau.analytics.console import ROLE, SCHEMA, available


class Command(BaseCommand):
    help = "Grant the console role read access to the console schema's views."

    def handle(self, *args: Any, **options: Any) -> None:
        if not available():
            raise CommandError(
                f"The role {ROLE} does not exist, or this database user is not a member of it."
            )
        with connection.cursor() as cursor:
            cursor.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}")
            cursor.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} TO {ROLE}")
        self.stdout.write(f"{ROLE} may now read the {SCHEMA} views.")
