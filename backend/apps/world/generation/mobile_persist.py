"""Storing mobile loans (P3.3), beside the monthly engine's loans and in the same tables.

``write_history`` stores a new world's mobile loans with their month-end rows;
``write_month`` stores one more month as the world advances during play. A
loan is known by its lender and account number, as the engine's loans are.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from .config import WorldConfig
from .engine import PAID_OFF, STATUS_NAMES, WRITTEN_OFF
from .mobile import (
    FACILITY_TYPE,
    PRODUCT,
    MobileLoans,
    MobileMonth,
    account_prefix,
    customer_prefix,
    month_end_state,
)
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
from .population import Branch

LOAN_COLUMNS = (
    "id", "world_id", "seq_no", "lender_id", "branch_id", "customer_id", "account_number",
    "product", "facility_type", "currency", "principal", "annual_rate", "term_months",
    "installment", "disbursement_date", "first_due_date", "maturity_date", "status",
    "terminal_period", "first_default_period", "repaid_date",
)  # fmt: skip
MONTH_COLUMNS = (
    "world_id", "lender_id", "loan_id", "period", "installments_due", "installments_paid",
    "outstanding_balance", "principal_balance", "arrears_amount", "days_past_due",
    "amount_paid", "status",
)  # fmt: skip


def head_offices(branches: list[Branch], lender_count: int) -> list[int]:
    """Each lender's first branch: mobile loans are booked at head office (A-073)."""
    first: dict[int, int] = {}
    for idx, branch in enumerate(branches):
        first.setdefault(branch.lender, idx)
    return [first[lender] for lender in range(lender_count)]


def _account(config: WorldConfig, loans: MobileLoans, i: int) -> str:
    return account_number(
        account_prefix(config.lenders[int(loans.lender[i])]), int(loans.account_seq[i])
    )


def _customer(config: WorldConfig, loans: MobileLoans, i: int) -> str:
    return customer_number(
        customer_prefix(config.lenders[int(loans.lender[i])]), int(loans.customer_seq[i])
    )


def _state_by(as_of: date, loans: MobileLoans, i: int) -> tuple[str, date | None]:
    """A loan's status as of a month-end, and the day it ended if it had."""
    for day, status in ((loans.repaid[i], PAID_OFF), (loans.written_off[i], WRITTEN_OFF)):
        if not np.isnat(day) and day.astype(object) <= as_of:
            return STATUS_NAMES[status], day.astype(object)
    return "ACTIVE", None


def _month_of(day: date, period_ends: list[date]) -> date:
    return next(end for end in period_ends if end >= day)


def _loan_row(
    pk: int, seq_no: int, world_id: int, config: WorldConfig, loans: MobileLoans, i: int,
    as_of: date, period_ends: list[date], lender_ids: list[int], branch_id: int, customer_id: int,
) -> tuple[Any, ...]:  # fmt: skip
    status, ended = _state_by(as_of, loans, i)
    default_day = loans.due[i] + np.timedelta64(90, "D")
    defaulted = not np.isnat(loans.written_off[i]) and default_day.astype(object) <= as_of
    repaid = loans.repaid[i]
    term_days = int(loans.term_days[i])
    principal = int(loans.principal[i])
    fee = int(loans.fee[i])
    return (
        pk, world_id, seq_no, lender_ids[int(loans.lender[i])], branch_id, customer_id,
        _account(config, loans, i), PRODUCT, FACILITY_TYPE, "GHS",
        _money(np.array([principal]))[0], f"{fee / principal * 365 / term_days:.4f}",
        -(-term_days // 30), _money(np.array([principal + fee]))[0],
        loans.disbursed[i].astype(object), loans.due[i].astype(object),
        loans.due[i].astype(object), status,
        _month_of(ended, period_ends) if ended else None,
        _month_of(default_day.astype(object), period_ends) if defaulted else None,
        repaid.astype(object) if status == "PAID_OFF" else None,
    )  # fmt: skip


def _month_rows(
    world_id: int, state: MobileMonth, loans: MobileLoans, loan_ids: dict[int, int],
    lender_ids: list[int], period: str,
) -> tuple[list[str], ...]:  # fmt: skip
    n = len(state.loan)
    return (
        [str(world_id)] * n,
        [str(lender_ids[int(loans.lender[i])]) for i in state.loan.tolist()],
        [str(loan_ids[int(i)]) for i in state.loan.tolist()],
        [period] * n,
        list(map(str, state.k_due.tolist())),
        list(map(str, state.k_paid.tolist())),
        _money(state.outstanding),
        _money(state.principal_balance),
        _money(state.arrears),
        list(map(str, state.dpd.tolist())),
        _money(state.paid),
        [STATUS_NAMES[int(s)] for s in state.status.tolist()],
    )


def write_history(
    cursor: Any,
    world_id: int,
    config: WorldConfig,
    loans: MobileLoans,
    months: np.ndarray,
    history_start: int,
    branches: list[Branch],
    lender_ids: list[int],
    branch_ids: list[int],
    person_ids: list[int],
    first_seq_no: int,
) -> int:
    """Store a new world's mobile loans and their month-end rows. Returns the loans stored."""
    period_ends = [_month_end(m) for m in months]
    states = {t: month_end_state(loans, months, t) for t in range(history_start, len(months))}
    visible = sorted({int(i) for state in states.values() for i in state.loan.tolist()})
    if not visible:
        return 0
    offices = head_offices(branches, len(config.lenders))

    keys = sorted({(int(loans.lender[i]), int(loans.customer_seq[i])) for i in visible})
    customer_pk = dict(
        zip(keys, _reserve_ids(cursor, "world_lendercustomer", len(keys)), strict=True)
    )
    person_of = {
        (int(loans.lender[i]), int(loans.customer_seq[i])): int(loans.person[i]) for i in visible
    }
    copy_rows(
        cursor,
        "world_lendercustomer",
        ("id", "world_id", "lender_id", "person_id", "business_id", "customer_number"),
        (
            (
                customer_pk[key], world_id, lender_ids[key[0]], person_ids[person_of[key]], None,
                customer_number(customer_prefix(config.lenders[key[0]]), key[1]),
            )
            for key in keys
        ),
    )  # fmt: skip

    as_of = period_ends[-1]
    loan_pk = dict(zip(visible, _reserve_ids(cursor, "world_loan", len(visible)), strict=True))
    copy_rows(
        cursor,
        "world_loan",
        LOAN_COLUMNS,
        (
            _loan_row(
                loan_pk[i], first_seq_no + n, world_id, config, loans, i, as_of, period_ends,
                lender_ids, branch_ids[offices[int(loans.lender[i])]],
                customer_pk[(int(loans.lender[i]), int(loans.customer_seq[i]))],
            )
            for n, i in enumerate(visible)
        ),
    )  # fmt: skip
    partition = loan_month_partition(world_id)
    for t, state in states.items():
        if len(state.loan):
            _copy_columns(
                cursor,
                partition,
                MONTH_COLUMNS,
                _month_rows(
                    world_id, state, loans, loan_pk, lender_ids, period_ends[t].isoformat()
                ),
            )
    return len(visible)


def write_month(
    cursor: Any,
    world_id: int,
    config: WorldConfig,
    loans: MobileLoans,
    months: np.ndarray,
    branches: list[Branch],
    t: int,
    period: date,
) -> None:
    """Store month ``t`` of an advancing world: its new loans and customers, the loans that
    ended, and every live loan's month-end row."""
    from apps.world.models import Branch as BranchRow
    from apps.world.models import Lender, LenderCustomer, Loan, Person

    state = month_end_state(loans, months, t)
    if not len(state.loan):
        return
    period_ends = [_month_end(m) for m in months[: t + 1]]
    lender_ids = [
        dict(Lender.objects.filter(world_id=world_id).values_list("code", "id"))[lp.code]
        for lp in config.lenders
    ]
    lender_index = {pk: i for i, pk in enumerate(lender_ids)}
    stored = {
        (lender_index[lender], number): (pk, status)
        for pk, lender, number, status in Loan.objects.filter(
            world_id=world_id, product=PRODUCT
        ).values_list("id", "lender_id", "account_number", "status")
    }
    rows = state.loan.tolist()
    key_of = {i: (int(loans.lender[i]), _account(config, loans, i)) for i in rows}
    new = [i for i in rows if key_of[i] not in stored]

    known = {
        (lender_index[lender], number): pk
        for pk, lender, number in LenderCustomer.objects.filter(world_id=world_id).values_list(
            "id", "lender_id", "customer_number"
        )
    }
    wanted = sorted({(int(loans.lender[i]), _customer(config, loans, i)) for i in new} - set(known))
    if wanted:
        people = dict(Person.objects.filter(world_id=world_id).values_list("seq_no", "id"))
        person_of = {
            (int(loans.lender[i]), _customer(config, loans, i)): int(loans.person[i]) for i in new
        }
        for key, pk in zip(
            wanted, _reserve_ids(cursor, "world_lendercustomer", len(wanted)), strict=True
        ):
            known[key] = pk
        copy_rows(
            cursor,
            "world_lendercustomer",
            ("id", "world_id", "lender_id", "person_id", "business_id", "customer_number"),
            (
                (known[key], world_id, lender_ids[key[0]], people[person_of[key] + 1], None, key[1])
                for key in wanted
            ),
        )  # fmt: skip

    loan_pk: dict[int, int] = {i: stored[key_of[i]][0] for i in rows if key_of[i] in stored}
    if new:
        offices = head_offices(branches, len(config.lenders))
        branch_pk = {
            (lender, code): pk
            for pk, lender, code in BranchRow.objects.filter(lender__world_id=world_id).values_list(
                "id", "lender_id", "code"
            )
        }
        next_seq = (
            Loan.objects.filter(world_id=world_id)
            .order_by("-seq_no")
            .values_list("seq_no", flat=True)
            .first()
            or 0
        ) + 1
        for i, pk in zip(new, _reserve_ids(cursor, "world_loan", len(new)), strict=True):
            loan_pk[i] = pk
        copy_rows(
            cursor,
            "world_loan",
            LOAN_COLUMNS,
            (
                _loan_row(
                    loan_pk[i], next_seq + n, world_id, config, loans, i, period, period_ends,
                    lender_ids,
                    branch_pk[(lender_ids[int(loans.lender[i])], branches[offices[int(loans.lender[i])]].code)],
                    known[(int(loans.lender[i]), _customer(config, loans, i))],
                )
                for n, i in enumerate(new)
            ),
        )  # fmt: skip

    # Loans already stored that ended, or first reached 90 days past due, this month.
    updates = []
    for i in rows:
        if key_of[i] not in stored:
            continue
        pk, old_status = stored[key_of[i]]
        status, ended = _state_by(period, loans, i)
        default_day = (loans.due[i] + np.timedelta64(90, "D")).astype(object)
        defaulted_now = (
            not np.isnat(loans.written_off[i])
            and _month_of(default_day, [*period_ends, date.max]) == period
        )
        if status != old_status or defaulted_now:
            updates.append(
                (
                    status,
                    period if ended else None,
                    period if defaulted_now else None,
                    loans.repaid[i].astype(object) if status == "PAID_OFF" else None,
                    pk,
                )
            )
    if updates:
        cursor.executemany(
            "UPDATE world_loan SET status = %s, terminal_period = COALESCE(%s, terminal_period), "
            "first_default_period = COALESCE(first_default_period, %s), "
            "repaid_date = COALESCE(%s, repaid_date) WHERE id = %s",
            updates,
        )
    _copy_columns(
        cursor,
        loan_month_partition(world_id),
        MONTH_COLUMNS,
        _month_rows(world_id, state, loans, loan_pk, lender_ids, period.isoformat()),
    )
