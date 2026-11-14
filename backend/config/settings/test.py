"""Settings for the automated test suite."""

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast, tests only

# Prepare established games in the request, not a background thread.
SIMB_SETUP_IN_BACKGROUND = False
