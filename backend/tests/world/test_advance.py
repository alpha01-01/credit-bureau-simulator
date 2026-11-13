"""Advancing a stored world one month at a time during play."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from apps.world.generation import build_world
from apps.world.generation.advance import extend_world
from apps.world.generation.engine import STATUS_NAMES
from apps.world.generation.persist import account_number, write_world
from apps.world.models import EconomyMonth, Lender, LenderCustomer, Loan, LoanMonth, World
from apps.world.provider_files import generate_submission, play_start
from apps.world.provider_files.profiles import CLEAN

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _saved(seed: int) -> World:
    g = build_world(seed, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def test_extending_in_memory_never_changes_the_past() -> None:
    base, longer = build_world(7, "small"), build_world(7, "small", extra_months=2)
    n = base.result.book.n
    for name in ("principal", "orig_month", "installment", "borrower", "lender", "lender_seq"):
        assert (base.result.book[name][:n] == longer.result.book[name][:n]).all(), name
    last = len(base.result.months) - 1
    earlier = longer.result.snapshots.column("month") <= last
    for name in base.result.snapshots.FIELDS:
        assert (
            base.result.snapshots.column(name) == longer.result.snapshots.column(name)[earlier]
        ).all(), name
    assert (base.result.stress == longer.result.stress[: len(base.result.stress)]).all()


def test_stored_world_gains_exactly_the_next_month() -> None:
    world = _saved(71)
    before_end = world.history_end
    period = extend_world(world.pk)
    world.refresh_from_db()
    assert period == world.history_end == date(2027, 1, 31) > before_end
    assert EconomyMonth.objects.filter(world=world, period=period).exists()

    # The stored month equals the in-memory simulation of the same month.
    expected = build_world(71, "tiny", extra_months=1)
    book, snaps = expected.result.book, expected.result.snapshots
    t = len(expected.result.months) - 1
    in_month = np.flatnonzero(snaps.column("month") == t)
    lenders = {lp.code: i for i, lp in enumerate(expected.config.lenders)}
    stored = {
        (lenders[code], number): (balance, dpd, status)
        for code, number, balance, dpd, status in LoanMonth.objects.filter(
            world=world, period=period
        ).values_list(
            "lender__code", "loan__account_number", "outstanding_balance", "days_past_due", "status"
        )
    }
    assert len(stored) == len(in_month) > 0
    for row in in_month.tolist():
        i = int(snaps.column("loan")[row])
        lp = expected.config.lenders[int(book["lender"][i])]
        key = (
            int(book["lender"][i]),
            account_number(lp.account_prefix, int(book["lender_seq"][i])),
        )
        balance, dpd, status = stored[key]
        assert balance == Decimal(int(snaps.column("outstanding")[row])) / 100
        assert dpd == int(snaps.column("dpd")[row])
        assert status == STATUS_NAMES[int(snaps.column("status")[row])]

    # Every stored loan, old and new, has the simulated status; no visible loan is missing.
    start = expected.result.history_start
    terminal = book["terminal_month"][: book.n]
    visible = np.flatnonzero((terminal < 0) | (terminal >= start))
    simulated = {}
    for i in visible.tolist():
        lp = expected.config.lenders[int(book["lender"][i])]
        number = account_number(lp.account_prefix, int(book["lender_seq"][i]))
        simulated[(lp.code, number)] = STATUS_NAMES[int(book["status"][i])]
    stored_status = dict(
        ((code, number), status)
        for code, number, status in Loan.objects.filter(world=world).values_list(
            "lender__code", "account_number", "status"
        )
    )
    assert stored_status == simulated
    # One lender customer per customer number.
    numbers = LenderCustomer.objects.filter(world=world).values_list("lender_id", "customer_number")
    assert len(numbers) == len(set(numbers))


def test_a_world_can_keep_advancing_and_providers_report_the_new_month() -> None:
    world = _saved(72)
    extend_world(world.pk)
    second = extend_world(world.pk)
    world.refresh_from_db()
    assert second == world.history_end == date(2027, 2, 28)
    # Play start stays where it was: the month after the generated history.
    assert play_start(world) == date(2027, 1, 31)
    lender = Lender.objects.get(world=world, code="ATB")
    result = generate_submission(world, lender, second, CLEAN)
    assert (
        sum(len(r.rows) for r in result.rendered.values())
        == LoanMonth.objects.filter(lender=lender, period=second).count()
    )


def test_advancing_is_deterministic() -> None:
    one, two = _saved(73), _saved(73)
    extend_world(one.pk)
    extend_world(two.pk)

    def month(world: World) -> list[tuple[Any, ...]]:
        return sorted(
            LoanMonth.objects.filter(world=world, period=world.history_end).values_list(
                "lender__code", "loan__account_number", "outstanding_balance", "days_past_due",
                "status",
            )
        )  # fmt: skip

    one.refresh_from_db()
    two.refresh_from_db()
    assert month(one) == month(two)
