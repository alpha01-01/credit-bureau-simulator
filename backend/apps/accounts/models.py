"""User accounts.

A user is someone who can sign in. It is deliberately separate from an
employee (apps.org), which is a person employed by a simulated bureau.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model, created before the first migration so it can evolve."""

    class Meta:
        db_table = "accounts_user"
