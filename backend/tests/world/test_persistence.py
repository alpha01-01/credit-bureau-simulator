"""S1 — Persisting a world to PostgreSQL, and deleting it."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection

from apps.world.generation import GeneratedWorld, build_world
from apps.world.generation.persist import delete_world, loan_month_partition, write_world
from apps.world.models import Business, Lender, LenderCustomer, Loan, LoanMonth, Person, World

pytestmark = pytest.mark.django_db


def _save(seed: int = 21) -> tuple[int, GeneratedWorld]:
    world = build_world(seed, "tiny")
    world_id = write_world(
        world.config, world.people, world.businesses, world.branches, world.result, world.stats
    )
    return world_id, world


def test_world_is_stored_completely() -> None:
    world_id, generated = _save()
    world = World.objects.get(pk=world_id)

    assert world.seed == 21
    assert Person.objects.filter(world=world).count() == generated.people.n
    assert Business.objects.filter(world=world).count() == generated.businesses.n
    assert Lender.objects.filter(world=world).count() == len(generated.config.lenders)
    assert LoanMonth.objects.filter(world=world).count() == len(generated.result.snapshots)
    assert world.history_end == generated.config.history_end


def test_money_is_stored_exactly() -> None:
    world_id, generated = _save()
    person = Person.objects.get(world_id=world_id, seq_no=1)
    assert person.monthly_income == Decimal(int(generated.people.income[0])) / 100


def test_every_loan_has_one_borrower_and_a_history() -> None:
    world_id, _ = _save()
    customers = LenderCustomer.objects.filter(world_id=world_id)
    assert customers.filter(person__isnull=True, business__isnull=True).count() == 0
    loans = Loan.objects.filter(world_id=world_id)
    assert loans.exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM world_loan l WHERE l.world_id = %s "
            "AND NOT EXISTS (SELECT 1 FROM world_loanmonth m WHERE m.loan_id = l.id)",
            [world_id],
        )
        assert cursor.fetchone() == (0,)


def test_history_rows_belong_to_their_loans_lender_and_world() -> None:
    world_id, _ = _save()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM world_loanmonth m JOIN world_loan l ON l.id = m.loan_id "
            "WHERE m.world_id = %s AND (l.lender_id <> m.lender_id OR l.world_id <> m.world_id)",
            [world_id],
        )
        assert cursor.fetchone() == (0,)


def test_account_numbers_are_unique_per_lender() -> None:
    world_id, _ = _save()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM (SELECT lender_id, account_number FROM world_loan WHERE world_id = %s "
            "GROUP BY 1, 2 HAVING count(*) > 1) d",
            [world_id],
        )
        assert cursor.fetchone() == (0,)


def test_each_world_gets_its_own_partition_and_can_be_deleted() -> None:
    first, _ = _save(31)
    second, _ = _save(32)
    partition = loan_month_partition(first)

    delete_world(first)

    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [partition])
        assert cursor.fetchone() == (None,)
    assert not World.objects.filter(pk=first).exists()
    assert not Person.objects.filter(world_id=first).exists()
    assert not LoanMonth.objects.filter(world_id=first).exists()
    # The other world is untouched.
    assert LoanMonth.objects.filter(world_id=second).exists()
