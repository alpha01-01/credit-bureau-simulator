# ruff: noqa: S608  (SQL is built from model table and column names only, never from input)
"""History templates: build an established bureau once per world, copy it into games (P2.1).

Pre-loading 12 months of history through the pipeline takes many minutes on a
default world. It is also deterministic: the same world and number of months
always give the same bureau, down to the former staff's mistakes. So the
history is built once, in a hidden template game, and each new game receives
a copy of everything the template holds:

* every row of the template's game and organisation (the tables that
  ``lifecycle.delete_game`` removes), with new ids allocated in the same
  relative order, so anything ordered by id behaves the same;
* foreign keys remapped through per-table id maps; references to the world
  (shared by all games) are kept; new unique UUIDs are drawn;
* the bureau's stored files, hard-linked into the new organisation's folder.

A copied game is the same game as one built directly; a test compares their
fingerprints (``fingerprint.py``), which ignore database ids.
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, models, transaction

from apps.bureau.submissions.models import SubmissionFile
from apps.bureau.submissions.pipeline import PROCESSING_VERSION
from apps.org.models import Organization
from apps.world.models import World

from .lifecycle import _ORDER
from .models import Game, HistoryTemplate

# Change when anything that shapes a pre-loaded history changes, so old templates are rebuilt.
TEMPLATE_FORMAT = "1"
CODE_VERSION = f"{PROCESSING_VERSION}/t{TEMPLATE_FORMAT}"

# Rows that are copied: everything a game owns, apart from the game and organisation
# rows themselves (the new game has its own) and the template's own marker.
_COPIED: tuple[tuple[type[models.Model], str], ...] = tuple(
    (model, condition)
    for model, condition in reversed(_ORDER)
    if model not in (Game, Organization, HistoryTemplate)
)
# Organisation fields that belong to the new bureau, not to the history.
_ORG_OWN = {"id", "public_id", "name", "organization_code", "created_at"}
_GAME_COPIED = ("clock_start", "current_tick", "status", "speed")


def ensure_template(
    world: World, months: int, progress: Callable[[str], None] | None = None
) -> HistoryTemplate:
    """The world's template for ``months`` of history, built now if there is none yet."""
    with transaction.atomic(), connection.cursor() as cursor:
        # One builder per world and history length; others wait, then copy.
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [world.pk, months])
        template = (
            HistoryTemplate.objects.filter(world=world, months=months)
            .select_related("game")
            .first()
        )
        if template is not None and template.code_version == CODE_VERSION:
            return template
        if template is not None:  # built by other code: rebuild
            from .lifecycle import delete_game

            delete_game(template.game)
        return _build(world, months, progress)


def _build(world: World, months: int, progress: Callable[[str], None] | None) -> HistoryTemplate:
    from .bridge import new_game, set_up_bureau
    from .history import preload_history

    start = time.perf_counter()
    if progress is not None:
        progress("Preparing this world's history for the first time (a few minutes)")
    game = new_game(world, owner=None, bureau_name="History template")
    set_up_bureau(game)
    preload_history(game, months, progress)
    return HistoryTemplate.objects.create(
        world=world, months=months, game=game, code_version=CODE_VERSION,
        build_seconds=round(time.perf_counter() - start, 1),
    )  # fmt: skip


def copy_bureau(source: Game, target: Game) -> None:
    """Copy everything ``source`` holds into ``target``, a new game with an empty bureau."""
    params: dict[str, Any] = {
        "org": source.organization_id,
        "game": source.pk,
        "target_org": target.organization_id,
        "target_game": target.pk,
        "source_folder": f"bureau/org_{source.organization_id}/",
        "target_folder": f"bureau/org_{target.organization_id}/",
    }
    copied = {model for model, _ in _COPIED}
    with transaction.atomic(), connection.cursor() as cursor:
        # A copy can always be made again: no need to wait for its log to reach the disk.
        cursor.execute("SET LOCAL synchronous_commit = off")
        maps = {
            model: _id_map(cursor, model, condition, params, n)
            for n, (model, condition) in enumerate(_COPIED)
        }
        for model, _ in _COPIED:
            _copy_rows(cursor, model, maps, copied, params)
        # Dropped now, not at commit: a caller's transaction may copy several games.
        cursor.execute(f"DROP TABLE {', '.join(maps.values())}")
        _copy_organization(source.organization_id, target.organization_id)
        for name in _GAME_COPIED:
            setattr(target, name, getattr(source, name))
        target.save(update_fields=list(_GAME_COPIED))
    _link_files(source.organization_id, target.organization_id)


def _table(model: type[models.Model]) -> str:
    return model._meta.db_table


def _id_map(
    cursor: Any, model: type[models.Model], condition: str, params: dict[str, Any], n: int
) -> str:
    """A temporary table pairing each source row's id with a new id, in the same order."""
    table, pk = _table(model), model._meta.pk.column
    name = f"clone_map_{n}"
    cursor.execute(f"CREATE TEMP TABLE {name} (old bigint PRIMARY KEY, new bigint NOT NULL)")
    # New ids are drawn in the order of the old ones (the subquery's order), so the
    # copy keeps the template's relative order.
    cursor.execute(
        f"INSERT INTO {name} (old, new) "
        f"SELECT {pk}, nextval(pg_get_serial_sequence(%(map_table)s, %(map_pk)s)) "
        f"FROM (SELECT {pk} FROM {table} WHERE {condition} ORDER BY {pk}) ordered",
        params | {"map_table": table, "map_pk": pk},
    )
    cursor.execute(f"ANALYZE {name}")
    return name


def _copy_rows(
    cursor: Any,
    model: type[models.Model],
    maps: dict[type[models.Model], str],
    copied: set[type[models.Model]],
    params: dict[str, Any],
) -> None:
    table = _table(model)
    columns, values, joins = (
        [],
        [],
        [f"JOIN {maps[model]} self ON self.old = t.{model._meta.pk.column}"],
    )
    for n, field in enumerate(model._meta.concrete_fields):
        columns.append(field.column)
        if field.primary_key:
            values.append("self.new")
        elif field.is_relation and field.related_model is not None:
            related = field.related_model
            if isinstance(related, str):  # unresolved lazy reference: never once apps load
                raise TypeError(f"{model.__name__}.{field.name} points to {related}")
            if related is Organization:
                values.append("%(target_org)s")
            elif related is Game:
                values.append("%(target_game)s")
            elif related in copied:
                alias = f"m{n}"
                joins.append(f"LEFT JOIN {maps[related]} {alias} ON {alias}.old = t.{field.column}")
                values.append(f"{alias}.new")
            else:  # the world, or a user: shared, kept as it is
                values.append(f"t.{field.column}")
        elif isinstance(field, models.UUIDField) and field.unique:
            values.append("gen_random_uuid()")
        elif model is SubmissionFile and field.name == "storage_path":
            values.append(f"replace(t.{field.column}, %(source_folder)s, %(target_folder)s)")
        else:
            values.append(f"t.{field.column}")
    cursor.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"SELECT {', '.join(values)} FROM {table} t {' '.join(joins)}",
        params,
    )


def _copy_organization(source_pk: int, target_pk: int) -> None:
    """The bureau's own settings and counters (its next customer number, ...)."""
    source = Organization.objects.get(pk=source_pk)
    target = Organization.objects.get(pk=target_pk)
    names = [f.name for f in Organization._meta.concrete_fields if f.name not in _ORG_OWN]
    for name in names:
        setattr(target, name, getattr(source, name))
    target.save(update_fields=names)


def _link_files(source_org: int, target_org: int) -> None:
    """Hard-link the bureau's stored files into the new organisation's folder (copy if needed)."""
    root = Path(settings.STORAGE_ROOT) / "bureau"
    source, target = root / f"org_{source_org}", root / f"org_{target_org}"
    if not source.exists():
        return
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, destination)
        except OSError:
            shutil.copy2(path, destination)
