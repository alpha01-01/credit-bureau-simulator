# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Month-end and on-demand checkpoints (Document 07, Section 12.3; P2.1).

A checkpoint marks a point in a game: the tick, how many player actions had
been taken, and the code that ran. The game is deterministic, so replaying
that many actions on a fresh game up to that tick reproduces the state; the
checkpoint's summary (row counts of everything the game owns and the main
money totals, worked out in the database) confirms that it did.

The full fingerprint hashes every row and is too slow to take every month on
an established bureau; tests use it alongside checkpoints where games are small.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from django.db import connection, models, transaction

from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.bureau.quality.models import TransformationLog
from apps.bureau.submissions.pipeline import PROCESSING_VERSION
from apps.commercial.models import UsageRecord
from apps.finance.models import JournalEntry, JournalLine
from apps.org.models import Organization

from .lifecycle import _ORDER, game_scope
from .models import (
    Checkpoint,
    CheckpointKind,
    Game,
    HistoryTemplate,
    PlayerAction,
)

SUMMARY_FORMAT = "1"
CODE_VERSION = f"{PROCESSING_VERSION}/c{SUMMARY_FORMAT}"

# What is counted: everything the game owns, apart from the game and organisation rows,
# the action log (a replay records its own) and checkpoints and templates themselves.
# Transformation logs have no game key and take seconds to count on an established
# bureau (so does reading every staging record's changes); they are left to the full
# fingerprint, which tests compare where games are small.
_SUMMARISED: tuple[tuple[type[models.Model], str], ...] = tuple(
    (model, condition)
    for model, condition in _ORDER
    if model
    not in (Game, Organization, HistoryTemplate, Checkpoint, PlayerAction, TransformationLog)
)


def _table(model: type[models.Model]) -> str:
    return model._meta.db_table


_TOTALS = {
    "ledger_debits": f"SELECT COALESCE(SUM(debit), 0) FROM {_table(JournalLine)} WHERE entry_id IN "
    f"(SELECT id FROM {_table(JournalEntry)} WHERE organization_id = %(org)s)",
    "ledger_credits": f"SELECT COALESCE(SUM(credit), 0) FROM {_table(JournalLine)} WHERE entry_id IN "
    f"(SELECT id FROM {_table(JournalEntry)} WHERE organization_id = %(org)s)",
    "balances_on_file": f"SELECT COALESCE(SUM(outstanding_balance), 0) "
    f"FROM {_table(AccountObservation)} WHERE is_current AND credit_account_id IN "
    f"(SELECT id FROM {_table(CreditAccount)} WHERE organization_id = %(org)s)",
    "usage_billed": f"SELECT COALESCE(SUM(quantity * unit_price), 0) FROM {_table(UsageRecord)} "
    "WHERE organization_id = %(org)s",
}


def summarise(game: Game) -> dict[str, Any]:
    """Row counts of everything the game owns, and its main money totals."""
    params = {"org": game.organization_id, "game": game.pk}
    counts: dict[str, int] = {}
    totals: dict[str, str] = {}
    with connection.cursor() as cursor, game_scope(cursor, params, records_view=True):
        for model, condition in _SUMMARISED:
            cursor.execute(f"SELECT count(*) FROM {_table(model)} WHERE {condition}", params)
            counts[_table(model)] = int(cursor.fetchone()[0])
        for name, sql in _TOTALS.items():
            cursor.execute(sql, params)
            totals[name] = str(cursor.fetchone()[0])
    return {"format": SUMMARY_FORMAT, "counts": counts, "totals": totals}


def digest(summary: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()


def take_checkpoint(game: Game, kind: str, at: datetime, label: str = "") -> Checkpoint:
    """Record a checkpoint at the game's current tick. Call inside the tick's transaction."""
    summary = summarise(game)
    return Checkpoint.objects.create(
        game=game,
        tick=game.current_tick,
        sim_time=at,
        kind=kind,
        label=label[:100],
        action_count=PlayerAction.objects.filter(game=game).count(),
        code_version=CODE_VERSION,
        summary=summary,
        digest=digest(summary),
    )


def checkpoint_now(game: Game, label: str, at: datetime) -> Checkpoint:
    """An on-demand checkpoint. It changes nothing in the game, so it is not an action."""
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        return take_checkpoint(locked, CheckpointKind.ON_DEMAND, at, label)
