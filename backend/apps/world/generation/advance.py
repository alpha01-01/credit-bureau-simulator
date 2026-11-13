"""Advancing a stored world by one month during play.

The world is regenerated from its seed with one more simulated month
(``extra_months``). Generation is prefix-stable: everything up to the current
end is identical, so only the new month is written: its economy, its loan
history rows, the loans and lender customers that appear for the first time,
and the loans whose status changed.

Every game playing in the same world sees the same new month, because it is
a pure function of the seed.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

import numpy as np
from django.db import connection, transaction

from apps.world.models import (
    Branch,
    EconomyMonth,
    Lender,
    LenderCustomer,
    Loan,
    Person,
    World,
)
from apps.world.models import Business as BusinessRow

from . import GeneratedWorld, build_world
from .config import GENERATOR_VERSION, PRODUCTS
from .engine import PERSON, PRODUCT_CODES, STATUS_NAMES
from .persist import (
    _copy_columns,
    _money,
    _month_end,
    _reserve_ids,
    account_number,
    copy_rows,
    customer_number,
    loan_month_partition,
)


class WorldAdvanceError(Exception):
    pass


def _months_between(start: date, end: date) -> int:
    return (end.year * 12 + end.month) - (start.year * 12 + start.month)


def extend_world(world_id: int) -> date:
    """Simulate and store the month after the world's current end. Returns its month-end."""
    with transaction.atomic():
        world = World.objects.select_for_update().get(pk=world_id)
        if world.generator_version != GENERATOR_VERSION:
            raise WorldAdvanceError(
                f"World {world_id} was made by generator {world.generator_version}; "
                f"this code is {GENERATOR_VERSION} and cannot extend it exactly"
            )
        anchor = date.fromisoformat(world.config["history_end"])
        extra = _months_between(anchor, world.history_end) + 1
        generated = build_world(world.seed, world.scale, anchor, extra_months=extra)
        result = generated.result
        t = len(result.months) - 1
        period = _month_end(result.months[t])
        if _months_between(world.history_end, period) != 1:
            raise WorldAdvanceError(f"Expected the month after {world.history_end}, got {period}")

        with connection.cursor() as wrapper:
            cursor = wrapper.cursor
            _write_month(cursor, world, generated, t, period)

        EconomyMonth.objects.create(
            world=world, period=period, stress_index=float(result.stress[t])
        )
        world.history_end = period
        world.stats = asdict(generated.stats)
        world.save(update_fields=["history_end", "stats"])
        return period


def _write_month(
    cursor: Any, world: World, generated: GeneratedWorld, t: int, period: date
) -> None:
    result, config = generated.result, generated.config
    book = result.book
    snaps = result.snapshots
    in_month = snaps.column("month") == t
    s_loan = snaps.column("loan")[in_month]

    lender_ids = dict(Lender.objects.filter(world=world).values_list("code", "id"))
    lender_id = [lender_ids[lp.code] for lp in config.lenders]

    # Loans already stored, by (lender, account number).
    stored = {
        (lender, number): (pk, status)
        for pk, lender, number, status in Loan.objects.filter(world=world).values_list(
            "id", "lender_id", "account_number", "status"
        )
    }

    def account(i: int) -> tuple[int, str]:
        l_idx = int(book["lender"][i])
        return lender_id[l_idx], account_number(
            config.lenders[l_idx].account_prefix, int(book["lender_seq"][i])
        )

    new_loans = [int(i) for i in s_loan.tolist() if account(int(i)) not in stored]

    # Lender customers that appear for the first time.
    known_customers = {
        (lender, number): pk
        for pk, lender, number in LenderCustomer.objects.filter(world=world).values_list(
            "id", "lender_id", "customer_number"
        )
    }

    def customer_key(c: int) -> tuple[int, str]:
        l_idx = result.customers[c][0]
        return lender_id[l_idx], customer_number(
            config.lenders[l_idx].customer_prefix, result.customer_seq[c]
        )

    needed = {int(book["customer"][i]) for i in new_loans}
    missing = sorted(c for c in needed if customer_key(c) not in known_customers)
    if missing:
        people = dict(Person.objects.filter(world=world).values_list("seq_no", "id"))
        businesses = dict(BusinessRow.objects.filter(world=world).values_list("seq_no", "id"))
        ids = _reserve_ids(cursor, "world_lendercustomer", len(missing))
        customer_rows: list[tuple[Any, ...]] = []
        for pk, c in zip(ids, missing, strict=True):
            l_id, number = customer_key(c)
            _, kind, borrower = result.customers[c]
            customer_rows.append(
                (
                    pk, world.pk, l_id,
                    people[borrower + 1] if kind == PERSON else None,
                    businesses[borrower + 1] if kind != PERSON else None,
                    number,
                )
            )  # fmt: skip
            known_customers[(l_id, number)] = pk
        copy_rows(
            cursor,
            "world_lendercustomer",
            ("id", "world_id", "lender_id", "person_id", "business_id", "customer_number"),
            customer_rows,
        )

    # New loans.
    period_text = period.isoformat()
    loan_ids: dict[int, int] = {}
    if new_loans:
        branch_ids = {
            (lender, code): pk
            for pk, lender, code in Branch.objects.filter(lender__world=world).values_list(
                "id", "lender_id", "code"
            )
        }
        next_seq = (
            Loan.objects.filter(world=world)
            .order_by("-seq_no")
            .values_list("seq_no", flat=True)
            .first()
            or 0
        ) + 1
        ids = _reserve_ids(cursor, "world_loan", len(new_loans))
        loan_rows: list[tuple[Any, ...]] = []
        for n, (pk, i) in enumerate(zip(ids, new_loans, strict=True)):
            l_id, number = account(i)
            branch = generated.branches[int(book["branch"][i])]
            product = PRODUCT_CODES[int(book["product"][i])]
            term = int(book["term"][i])
            first_due = np.datetime64(int(book["first_due"][i]), "M")
            due_day = int(book["due_day"][i])
            day_offset = np.timedelta64(due_day - 1, "D")
            first_due_date = (first_due.astype("datetime64[D]") + day_offset).tolist()
            maturity = (
                (first_due + np.timedelta64(term - 1, "M")).astype("datetime64[D]") + day_offset
            ).tolist()
            status = int(book["status"][i])
            loan_rows.append(
                (
                    pk, world.pk, next_seq + n, l_id, branch_ids[(l_id, branch.code)],
                    known_customers[customer_key(int(book["customer"][i]))], number, product,
                    PRODUCTS[product].facility_type, "GHS",
                    _money(book["principal"][i : i + 1])[0],
                    f"{float(book['annual_rate'][i]):.4f}", term,
                    _money(book["installment"][i : i + 1])[0], book["disbursed"][i].tolist(),
                    first_due_date, maturity, STATUS_NAMES[status],
                    period if int(book["terminal_month"][i]) == t else None,
                    period if int(book["first_90_month"][i]) == t else None,
                )
            )  # fmt: skip
            loan_ids[i] = pk
        copy_rows(
            cursor,
            "world_loan",
            (
                "id", "world_id", "seq_no", "lender_id", "branch_id", "customer_id", "account_number",
                "product", "facility_type", "currency", "principal", "annual_rate", "term_months",
                "installment", "disbursement_date", "first_due_date", "maturity_date", "status",
                "terminal_period", "first_default_period",
            ),
            loan_rows,
        )  # fmt: skip

    # Existing loans whose status changed or that first reached 90+ DPD this month.
    updates = []
    for i in s_loan.tolist():
        key = account(int(i))
        if key not in stored:
            continue
        pk, old_status = stored[key]
        loan_ids[int(i)] = pk
        new_status = STATUS_NAMES[int(book["status"][i])]
        defaulted_now = int(book["first_90_month"][i]) == t
        if new_status != old_status or defaulted_now:
            updates.append(
                (
                    new_status,
                    period if int(book["terminal_month"][i]) == t else None,
                    period if defaulted_now else None,
                    pk,
                )
            )
    if updates:
        cursor.executemany(
            "UPDATE world_loan SET status = %s, terminal_period = COALESCE(%s, terminal_period), "
            "first_default_period = COALESCE(first_default_period, %s) WHERE id = %s",
            updates,
        )

    # The month's history rows, straight into the world's partition.
    order = np.flatnonzero(in_month)
    loans = snaps.column("loan")[order]
    _copy_columns(
        cursor,
        loan_month_partition(world.pk),
        (
            "world_id", "lender_id", "loan_id", "period", "installments_due", "installments_paid",
            "outstanding_balance", "principal_balance", "arrears_amount", "days_past_due",
            "amount_paid", "status",
        ),
        (
            [str(world.pk)] * len(order),
            [str(lender_id[int(book["lender"][i])]) for i in loans.tolist()],
            [str(loan_ids[int(i)]) for i in loans.tolist()],
            [period_text] * len(order),
            list(map(str, snaps.column("k_due")[order].tolist())),
            list(map(str, snaps.column("k_paid")[order].tolist())),
            _money(snaps.column("outstanding")[order]),
            _money(snaps.column("principal_balance")[order]),
            _money(snaps.column("arrears")[order]),
            list(map(str, snaps.column("dpd")[order].tolist())),
            _money(snaps.column("paid")[order]),
            [STATUS_NAMES[int(s)] for s in snaps.column("status")[order].tolist()],
        ),
    )  # fmt: skip
