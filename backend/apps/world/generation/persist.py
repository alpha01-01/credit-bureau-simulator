"""Write a generated world to PostgreSQL.

Large tables are written with COPY, which is orders of magnitude faster than
row-by-row inserts. Primary keys are reserved from each table's sequence first
so foreign keys can be filled in before the rows are sent.

Only loans that are live at some point inside the stored history window are
written; loans that ended during burn-in never become visible to anyone.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from django.conf import settings
from django.db import connection, transaction

from .config import PRODUCTS, WorldConfig
from .engine import PERSON, PRODUCT_CODES, STATUS_NAMES, SimulationResult
from .population import EMPLOYMENT_CODES, REGION_CODES, SECTOR_CODES, Branch, Businesses, People
from .stats import WorldStats


def _money(values: np.ndarray) -> list[str]:
    """Integer pesewas -> exact decimal strings."""
    return [f"{v // 100}.{v % 100:02d}" for v in values.astype(np.int64).tolist()]


def _scramble(seq: int, modulus: int, multiplier: int, offset: int) -> int:
    """Bijective, deterministic scrambling of a sequence number (multiplier coprime to modulus)."""
    return (seq * multiplier + offset) % modulus


def customer_number(prefix: str, seq: int) -> str:
    return f"{prefix}{_scramble(seq, 10**8, 7919, 104729):08d}"


def account_number(prefix: str, seq: int) -> str:
    width = 14 - len(prefix)
    return f"{prefix}{_scramble(seq, 10**width, 1_000_003, 7_777):0{width}d}"


def _reserve_ids(cursor: Any, table: str, count: int) -> list[int]:
    if count == 0:
        return []
    cursor.execute(
        "SELECT nextval(pg_get_serial_sequence(%s, 'id')) AS id FROM generate_series(1, %s) ORDER BY 1",
        [table, count],
    )
    return [row[0] for row in cursor.fetchall()]


def copy_rows(
    cursor: Any, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    with cursor.copy(sql) as copy:
        for row in rows:
            copy.write_row(row)


def _copy_columns(
    cursor: Any, table: str, columns: Sequence[str], data: Sequence[Sequence[str]]
) -> None:
    """Fast COPY for large tables whose values are already strings without tabs,
    newlines or backslashes (numbers, dates, codes). Sends text in chunks."""
    sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    total = len(data[0])
    chunk = 250_000
    with cursor.copy(sql) as copy:
        for start in range(0, total, chunk):
            rows = zip(*(col[start : start + chunk] for col in data), strict=True)
            text = "\n".join(map("\t".join, rows)) + "\n"
            copy.write(text.encode("ascii"))


def _month_end(month: np.datetime64) -> date:
    value: date = (
        (month + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    ).tolist()
    return value


def write_world(
    config: WorldConfig,
    people: People,
    businesses: Businesses,
    branches: list[Branch],
    result: SimulationResult,
    stats: WorldStats,
) -> int:
    """Persist everything and return the new world's id. Call inside a transaction."""
    from apps.world.models import World

    months = result.months
    period_ends = [_month_end(m) for m in months]
    world = World.objects.create(
        seed=config.seed,
        scale=config.scale.name,
        generator_version=_generator_version(),
        history_start=period_ends[result.history_start],
        history_end=period_ends[-1],
        config=_config_snapshot(config),
        stats=asdict(stats),
    )
    world_id = world.pk

    with connection.cursor() as cursor:
        cursor = cursor.cursor  # the underlying psycopg cursor, for COPY

        # Economy
        copy_rows(
            cursor,
            "world_economymonth",
            ("world_id", "period", "stress_index"),
            (
                (world_id, period_ends[t], float(result.stress[t]))
                for t in range(result.history_start, len(months))
            ),
        )

        # Lenders and branches
        lender_ids = _reserve_ids(cursor, "world_lender", len(config.lenders))
        copy_rows(
            cursor,
            "world_lender",
            ("id", "world_id", "seq_no", "code", "name", "lender_type", "founded", "profile"),
            (
                (
                    lender_ids[i],
                    world_id,
                    i + 1,
                    lp.code,
                    lp.name,
                    lp.lender_type,
                    lp.founded,
                    _json(asdict(lp)),
                )
                for i, lp in enumerate(config.lenders)
            ),
        )
        branch_ids = _reserve_ids(cursor, "world_branch", len(branches))
        copy_rows(
            cursor,
            "world_branch",
            ("id", "lender_id", "code", "name", "region", "town"),
            (
                (
                    branch_ids[i],
                    lender_ids[b.lender],
                    b.code,
                    b.name,
                    REGION_CODES[b.region],
                    b.town,
                )
                for i, b in enumerate(branches)
            ),
        )

        # People
        person_ids = _reserve_ids(cursor, "world_person", people.n)
        incomes = _money(people.income)
        births = people.birth_date.tolist()
        copy_rows(
            cursor,
            "world_person",
            (
                "id", "world_id", "seq_no", "ghana_card", "first_name", "middle_name", "last_name", "gender",
                "date_of_birth", "phone_primary", "phone_secondary", "region", "town", "name_group",
                "employment_type", "sector", "monthly_income", "risk_z", "income_stability",
            ),
            (
                (
                    person_ids[i], world_id, i + 1, people.ghana_card[i], people.first_name[i],
                    people.middle_name[i] or "", people.last_name[i], people.gender[i], births[i],
                    people.phone_primary[i], people.phone_secondary[i] or "", REGION_CODES[people.region[i]],
                    people.town[i], people.name_group[i], EMPLOYMENT_CODES[people.employment[i]],
                    SECTOR_CODES[people.sector[i]], incomes[i], float(people.risk_z[i]),
                    float(people.stability[i]),
                )
                for i in range(people.n)
            ),
        )  # fmt: skip

        # Businesses
        business_ids = _reserve_ids(cursor, "world_business", businesses.n)
        revenues = _money(businesses.revenue)
        copy_rows(
            cursor,
            "world_business",
            (
                "id", "world_id", "seq_no", "owner_id", "registered_name", "trading_name",
                "registration_number", "tin", "sector", "region", "town", "size_band",
                "registration_date", "monthly_revenue", "health_z",
            ),
            (
                (
                    business_ids[i], world_id, i + 1, person_ids[businesses.owner[i]],
                    businesses.registered_name[i], businesses.trading_name[i] or "",
                    businesses.registration_number[i], businesses.tin[i],
                    SECTOR_CODES[businesses.sector[i]], REGION_CODES[businesses.region[i]],
                    businesses.town[i], businesses.size_band[i], businesses.registration_date[i],
                    revenues[i], float(businesses.health_z[i]),
                )
                for i in range(businesses.n)
            ),
        )  # fmt: skip

        # Loans visible in the history window, and the customers behind them.
        book = result.book
        visible = (book["terminal_month"] < 0) | (book["terminal_month"] >= result.history_start)
        loan_idx = np.flatnonzero(visible)
        used_customers = np.unique(book["customer"][loan_idx])
        customer_ids_list = _reserve_ids(cursor, "world_lendercustomer", len(used_customers))
        customer_id = dict(zip(used_customers.tolist(), customer_ids_list, strict=True))
        copy_rows(
            cursor,
            "world_lendercustomer",
            ("id", "world_id", "lender_id", "person_id", "business_id", "customer_number"),
            (
                (
                    customer_id[c],
                    world_id,
                    lender_ids[result.customers[c][0]],
                    person_ids[result.customers[c][2]]
                    if result.customers[c][1] == PERSON
                    else None,
                    business_ids[result.customers[c][2]]
                    if result.customers[c][1] != PERSON
                    else None,
                    customer_number(
                        config.lenders[result.customers[c][0]].customer_prefix,
                        result.customer_seq[c],
                    ),
                )
                for c in used_customers.tolist()
            ),
        )

        loan_ids_list = _reserve_ids(cursor, "world_loan", len(loan_idx))
        loan_id = np.full(book.n, -1, dtype=np.int64)
        loan_id[loan_idx] = loan_ids_list

        lender = book["lender"][loan_idx]
        product = book["product"][loan_idx]
        term = book["term"][loan_idx]
        first_due_month = book["first_due"][loan_idx].astype("datetime64[M]")
        due_day = book["due_day"][loan_idx]
        first_due_dates = (first_due_month.astype("datetime64[D]") + (due_day - 1)).tolist()
        maturity_dates = (
            (first_due_month + (term - 1)).astype("datetime64[D]") + (due_day - 1)
        ).tolist()
        disbursed = book["disbursed"][loan_idx].tolist()
        principal = _money(book["principal"][loan_idx])
        installment = _money(book["installment"][loan_idx])
        annual_rate = [f"{r:.4f}" for r in book["annual_rate"][loan_idx].tolist()]
        status = book["status"][loan_idx]
        terminal = book["terminal_month"][loan_idx]
        first_90 = book["first_90_month"][loan_idx]
        customers = book["customer"][loan_idx]
        branch = book["branch"][loan_idx]
        lender_seq = book["lender_seq"][loan_idx]
        copy_rows(
            cursor,
            "world_loan",
            (
                "id", "world_id", "seq_no", "lender_id", "branch_id", "customer_id", "account_number",
                "product", "facility_type", "currency", "principal", "annual_rate", "term_months",
                "installment", "disbursement_date", "first_due_date", "maturity_date", "status",
                "terminal_period", "first_default_period",
            ),
            (
                (
                    loan_ids_list[j], world_id, j + 1, lender_ids[lender[j]], branch_ids[branch[j]],
                    customer_id[int(customers[j])],
                    account_number(config.lenders[lender[j]].account_prefix, int(lender_seq[j])),
                    PRODUCT_CODES[product[j]], PRODUCTS[PRODUCT_CODES[product[j]]].facility_type, "GHS",
                    principal[j], annual_rate[j], int(term[j]), installment[j], disbursed[j],
                    first_due_dates[j], maturity_dates[j], STATUS_NAMES[int(status[j])],
                    period_ends[terminal[j]] if terminal[j] >= 0 else None,
                    period_ends[first_90[j]] if first_90[j] >= 0 else None,
                )
                for j in range(len(loan_idx))
            ),
        )  # fmt: skip

        # Month-end history
        snaps = result.snapshots
        s_loan = snaps.column("loan")
        s_month = snaps.column("month")
        s_ids = loan_id[s_loan]
        s_lender = book["lender"][s_loan]
        cols = {
            "due": snaps.column("k_due").tolist(),
            "paid_n": snaps.column("k_paid").tolist(),
            "outstanding": _money(snaps.column("outstanding")),
            "principal": _money(snaps.column("principal_balance")),
            "arrears": _money(snaps.column("arrears")),
            "dpd": snaps.column("dpd").tolist(),
            "paid": _money(snaps.column("paid")),
            "status": snaps.column("status").tolist(),
        }
        period_text = [d.isoformat() for d in period_ends]
        status_text = {code: name for code, name in STATUS_NAMES.items()}
        n_rows = len(s_loan)
        partition = loan_month_partition(world_id)
        cursor.execute(
            f"CREATE TABLE {partition} (LIKE world_loanmonth INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
        )
        _copy_columns(
            cursor,
            partition,
            (
                "world_id", "lender_id", "loan_id", "period", "installments_due", "installments_paid",
                "outstanding_balance", "principal_balance", "arrears_amount", "days_past_due",
                "amount_paid", "status",
            ),
            (
                [str(world_id)] * n_rows,
                list(map(str, np.array(lender_ids, dtype=np.int64)[s_lender].tolist())),
                list(map(str, s_ids.tolist())),
                [period_text[m] for m in s_month.tolist()],
                list(map(str, cols["due"])),
                list(map(str, cols["paid_n"])),
                cols["outstanding"],
                cols["principal"],
                cols["arrears"],
                list(map(str, cols["dpd"])),
                cols["paid"],
                [status_text[c] for c in cols["status"]],
            ),
        )  # fmt: skip
        # Index once after loading, then attach. The CHECK lets ATTACH skip its validation scan.
        cursor.execute(
            f"CREATE UNIQUE INDEX {partition}_loan_period ON {partition} (loan_id, period)"
        )
        cursor.execute(f"CREATE INDEX {partition}_lender_period ON {partition} (lender_id, period)")
        cursor.execute(
            f"ALTER TABLE {partition} ADD CONSTRAINT {partition}_world CHECK (world_id = {world_id})"
        )
        cursor.execute(
            f"ALTER TABLE world_loanmonth ATTACH PARTITION {partition} FOR VALUES IN ({world_id})"
        )
        cursor.execute(f"ANALYZE {partition}")

    return world_id


def loan_month_partition(world_id: int) -> str:
    return f"world_loanmonth_w{int(world_id)}"


def delete_world(world_id: int) -> None:
    """Delete a world and everything in it. Call inside a transaction.

    Uses set-based SQL: the ORM's cascade would load millions of rows into memory.
    """
    partition = loan_month_partition(world_id)
    with connection.cursor() as cursor:
        # Provider submissions first: they reference loans.
        cursor.execute(
            "DELETE FROM world_filedefect WHERE submission_id IN "
            "(SELECT id FROM world_providersubmission WHERE world_id = %s)",
            [world_id],
        )
        cursor.execute(
            "DELETE FROM world_providerfilerow WHERE file_id IN (SELECT f.id FROM world_providerfile f "
            "JOIN world_providersubmission s ON s.id = f.submission_id WHERE s.world_id = %s)",
            [world_id],
        )
        cursor.execute(
            "DELETE FROM world_providerfile WHERE submission_id IN "
            "(SELECT id FROM world_providersubmission WHERE world_id = %s)",
            [world_id],
        )
        cursor.execute("DELETE FROM world_providersubmission WHERE world_id = %s", [world_id])
        cursor.execute(f"DROP TABLE IF EXISTS {partition}")
        for table, column in (
            ("world_loanapplication", "world_id"),
            ("world_loan", "world_id"),
            ("world_lendercustomer", "world_id"),
            ("world_business", "world_id"),
            ("world_person", "world_id"),
        ):
            cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", [world_id])  # noqa: S608
        cursor.execute(
            "DELETE FROM world_branch WHERE lender_id IN (SELECT id FROM world_lender WHERE world_id = %s)",
            [world_id],
        )
        for table in ("world_lender", "world_economymonth", "world_world"):
            column = "id" if table == "world_world" else "world_id"
            cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", [world_id])  # noqa: S608

    # The world's provider files on disk go too, once the deletion is committed.
    files = Path(settings.STORAGE_ROOT) / "provider_files" / f"world_{int(world_id)}"
    transaction.on_commit(lambda: shutil.rmtree(files, ignore_errors=True))


def _generator_version() -> str:
    from .config import GENERATOR_VERSION

    return GENERATOR_VERSION


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str, sort_keys=True)


def _config_snapshot(config: WorldConfig) -> dict[str, Any]:
    return {
        "seed": config.seed,
        "scale": asdict(config.scale),
        "history_end": config.history_end.isoformat(),
        "behaviour": asdict(config.behaviour),
        "economy": asdict(config.economy),
        "lenders": [lp.code for lp in config.lenders],
    }
