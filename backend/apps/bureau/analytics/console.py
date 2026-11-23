"""The SQL console (P3.4; Document 09): read-only SQL over one game's own data.

A query runs in a transaction that is always rolled back:

1. the game's organisation is recorded for this database session (``console_session``);
2. the session takes the console role (``simb_console``), which may read only the views
   of the ``console`` schema, and those views show only that organisation's rows;
3. the transaction is read-only, statements stop after ``TIMEOUT_SECONDS``, and at most
   ``MAX_ROWS`` rows come back.

So the console never sees the world, another game, the app's own tables or the answer
key, and never writes. Checks on the text (one SELECT, nothing that changes the role)
are a second line of defence, not the first.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from django.db import connection, transaction

ROLE = "simb_console"
SCHEMA = "console"
TIMEOUT_SECONDS = 5
MAX_ROWS = 500
MAX_LENGTH = 5_000
_FIRST_WORD = re.compile(r"^\s*(\w+)", re.IGNORECASE)
_FORBIDDEN = re.compile(r"\bset_config\b|\b(set|reset)\s+(session\s+)?(role|authorization)\b", re.I)


class ConsoleError(Exception):
    """The query was refused or failed; the message says why, for the player."""


@dataclass(frozen=True)
class ConsoleResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    milliseconds: int


def available() -> bool:
    """Whether the console role exists and the app may take it (README: "The SQL console")."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s) "
            "AND pg_has_role(current_user, %s, 'MEMBER')",
            [ROLE, ROLE],
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def catalogue() -> list[dict[str, Any]]:
    """The tables the console offers, with their columns, for the player's reference."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
            [SCHEMA],
        )
        tables: dict[str, list[dict[str, str]]] = {}
        for table, column, kind in cursor.fetchall():
            tables.setdefault(table, []).append({"name": column, "type": kind})
    return [{"table": t, "columns": c} for t, c in tables.items()]


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _check(sql: str) -> str:
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise ConsoleError("Write a query first.")
    if len(text) > MAX_LENGTH:
        raise ConsoleError(f"Queries are limited to {MAX_LENGTH:,} characters.")
    if ";" in text:
        raise ConsoleError("One statement at a time, please.")
    first = _FIRST_WORD.match(text)
    if not first or first.group(1).upper() not in ("SELECT", "WITH"):
        raise ConsoleError("The console only reads: start with SELECT or WITH.")
    if _FORBIDDEN.search(text):
        raise ConsoleError("The console cannot change its role or settings.")
    return text


def run(organization_id: int, sql: str) -> ConsoleResult:
    """Run one read-only query over the organisation's own data."""
    text = _check(sql)
    if not available():
        raise ConsoleError(
            "The SQL console is not set up on this server: a database administrator must "
            "create the console role once (see the README, 'The SQL console')."
        )
    started = time.perf_counter()
    try:
        with transaction.atomic():
            connection.ensure_connection()
            raw = connection.connection.cursor()
            raw.execute(
                "INSERT INTO console_session (pid, organization_id) VALUES (pg_backend_pid(), %s) "
                "ON CONFLICT (pid) DO UPDATE SET organization_id = EXCLUDED.organization_id",
                [organization_id],
            )
            raw.execute(f"SET LOCAL statement_timeout = '{TIMEOUT_SECONDS}s'")
            raw.execute("SET LOCAL transaction_read_only = on")
            raw.execute(f"SET LOCAL search_path = {SCHEMA}")
            raw.execute(f"SET LOCAL ROLE {ROLE}")
            # Extended protocol (prepare=True): a single statement, never several.
            raw.execute(text, prepare=True)
            if raw.description is None:
                raise ConsoleError("That statement returned no rows.")
            columns = [d.name for d in raw.description]
            fetched = raw.fetchmany(MAX_ROWS + 1)
            transaction.set_rollback(True)
    except ConsoleError:
        raise
    except psycopg.errors.QueryCanceled as exc:
        raise ConsoleError(
            f"The query was stopped after {TIMEOUT_SECONDS} seconds. Narrow it down: filter "
            "by date or lender, or aggregate."
        ) from exc
    except psycopg.errors.InsufficientPrivilege as exc:
        raise ConsoleError(
            "The console can read only its own tables (customers, accounts, observations, "
            "enquiries, ...): see the list beside the query box."
        ) from exc
    except psycopg.errors.ReadOnlySqlTransaction as exc:
        raise ConsoleError("The console only reads; it cannot change anything.") from exc
    except psycopg.Error as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise ConsoleError(message) from exc
    except Exception as exc:  # a database error raised through Django's wrapper
        cause = exc.__cause__ if isinstance(exc.__cause__, psycopg.Error) else None
        if cause is None:
            raise
        raise ConsoleError(str(cause).strip().splitlines()[0]) from exc
    return ConsoleResult(
        columns=columns,
        rows=[[_plain(v) for v in row] for row in fetched[:MAX_ROWS]],
        truncated=len(fetched) > MAX_ROWS,
        milliseconds=round((time.perf_counter() - started) * 1000),
    )
