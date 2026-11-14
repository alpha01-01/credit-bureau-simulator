"""Fast inserts of Django model objects with PostgreSQL COPY.

A drop-in for ``bulk_create`` on large batches: primary keys are reserved
from the table's sequence first (so objects get their ids, as bulk_create
gives them), field defaults and auto timestamps are applied as save() would,
foreign keys to objects saved earlier in the same batch are resolved, and
the rows are streamed with COPY instead of a large INSERT statement.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from django.db import connection
from django.db.models import JSONField, Model


def copy_insert[M: Model](objs: Sequence[M]) -> list[M]:
    """Insert ``objs`` (all of one model) and set their primary keys. Returns them."""
    items = list(objs)
    if not items:
        return items
    model = type(items[0])
    meta = model._meta
    table = meta.db_table
    pk_column = meta.pk.column
    fields = [f for f in meta.concrete_fields if not f.primary_key]

    with connection.cursor() as wrapper:
        cursor = wrapper.cursor
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence(%s, %s)) FROM generate_series(1, %s) ORDER BY 1",
            [table, pk_column, len(items)],
        )
        ids = [row[0] for row in cursor.fetchall()]
        columns = [pk_column, *(f.column for f in fields)]
        sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
        with cursor.copy(sql) as copy:
            for obj, pk in zip(items, ids, strict=True):
                obj._prepare_related_fields_for_save(operation_name="copy_insert")  # type: ignore[attr-defined]
                obj.pk = pk
                row: list[Any] = [pk]
                for f in fields:
                    value = f.pre_save(obj, add=True)
                    if isinstance(f, JSONField):
                        row.append(None if value is None else json.dumps(value, cls=f.encoder))
                    else:
                        row.append(f.get_db_prep_save(value, connection))
                copy.write_row(row)
    for obj in items:
        obj._state.adding = False
        obj._state.db = connection.alias
    return items
