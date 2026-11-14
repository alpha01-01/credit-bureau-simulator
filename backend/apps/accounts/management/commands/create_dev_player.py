"""Create (or reset) the local development player from .env.

    python manage.py create_dev_player

Reads SIMB_DEV_PLAYER_USERNAME and SIMB_DEV_PLAYER_PASSWORD. For local
development only; refuses to run with DEBUG off.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create or reset the local development player account from .env."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("Development accounts are for DEBUG environments only")
        username = os.environ.get("SIMB_DEV_PLAYER_USERNAME", "")
        password = os.environ.get("SIMB_DEV_PLAYER_PASSWORD", "")
        if not username or not password:
            raise CommandError("Set SIMB_DEV_PLAYER_USERNAME and SIMB_DEV_PLAYER_PASSWORD in .env")
        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.save()
        self.stdout.write(f"{'Created' if created else 'Reset'} development player {username!r}")
