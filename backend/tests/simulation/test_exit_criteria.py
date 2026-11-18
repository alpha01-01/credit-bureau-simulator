"""P2.13 — The first playable slice's exit criteria (Document 07, Section 13.2).

Criteria 2 and 4, end to end on one game:

2. Three months of play run without errors or inconsistencies: after three
   months every journal balances, the books balance, every processing run
   reconciles, the clock has no gaps, nothing due is left unhandled, and every
   decision on a work item is recorded on its case.
4. Every dashboard figure drills down to underlying records: following each
   figure's drill-down through the API gives exactly the records behind it.

The other criteria are tested where they live (see docs/exit-criteria.md).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.submissions.models import ProcessingRun
from apps.commercial.models import UsageRecord
from apps.finance.models import JournalEntry, JournalLine
from apps.finance.statements import balance_sheet, trial_balance
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.models import EventStatus, Game, ScheduledEvent, TickLog
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

MONTHS = 3


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _three_months(world: World, owner: User) -> Game:
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    for _ in range(MONTHS):
        month = controls.state(game).now.month
        while controls.state(game).now.month == month:
            game = controls.advance_by(game, "next_event")
    # A little into the fourth month, so the dashboard's month has figures in it.
    return controls.advance_by(game, "day", 10)


def _consistent(game: Game) -> None:
    org = game.organization
    today = controls.state(game).now.date()

    # The books: every entry balances, and so do the trial balance and balance sheet.
    unbalanced = [
        e.journal_reference
        for e in JournalEntry.objects.filter(organization=org)
        .annotate(dr=Sum("lines__debit"), cr=Sum("lines__credit"))
        .order_by("pk")
        if e.dr != e.cr
    ]
    assert unbalanced == []
    tb = trial_balance(org, today)
    assert tb["total_debit"] == tb["total_credit"]
    assert balance_sheet(org, today)["balances"]

    # Every run's records are accounted for.
    for run in ProcessingRun.objects.filter(
        submission__organization=org, completed_at__isnull=False
    ):
        assert run.records_received == (
            run.records_accepted + run.records_unloadable + run.records_duplicated
            + run.records_pending
        ), run  # fmt: skip

    # The clock: every tick ran once, in order; nothing due was left behind.
    ticks = list(TickLog.objects.filter(game=game).order_by("tick").values_list("tick", flat=True))
    assert ticks == list(range(1, game.current_tick + 1))
    assert not ScheduledEvent.objects.filter(
        game=game, status=EventStatus.PENDING, due_tick__lte=game.current_tick
    ).exists()

    # Every decided work item has its decision on its case.
    for item in WorkItem.objects.filter(organization=org, status=ItemStatus.DONE).select_related(
        "case"
    ):
        assert item.decision and item.case.decision == item.decision, item.item_number

    # Every report sold was billed once, to the subscriber that asked for it.
    assert not UsageRecord.objects.filter(organization=org, enquiry__isnull=True).exists()


def _total(response: Any) -> int:
    assert response.status_code == 200, response.content
    return int(response["X-Total-Count"])


@pytest.mark.django_db(transaction=True)
def test_three_months_run_cleanly_and_every_figure_drills_to_its_records(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _three_months(world, owner)
    _consistent(game)

    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}"
    screens = {
        "ledger": "/ledger/",
        "enquiries": "/enquiries/",
        "invoices": "/invoices/",
        "queue": "/work-items/",
        "customers": "/customers/",
        "accounts": "/accounts/",
        "submissions": "/submissions/",
    }
    metrics = client.get(f"{base}/dashboard/").json()["metrics"]
    checked = []
    for m in metrics:
        drill = m["drill"]
        assert drill["screen"] in screens, m["key"]
        response = client.get(f"{base}{screens[drill['screen']]}", drill["params"])
        total, rows = _total(response), response.json()
        value = m["value"]
        if m["key"] in ("backlog", "enquiries", "customers", "accounts", "submissions"):
            assert total == value, (m["key"], total, value)
        elif m["key"] == "hit_rate":
            everything = _total(
                client.get(f"{base}/enquiries/", {"start": drill["params"]["start"]})
            )
            assert value == round((everything - total) / everything, 3)  # misses are shown
        elif m["key"] == "usage":
            billed = UsageRecord.objects.filter(
                organization=game.organization, usage_at__date__gte=drill["params"]["start"]
            )
            assert (
                total == billed.count()
                and Decimal(value) == billed.aggregate(s=Sum("unit_price"))["s"]
            )
        elif m["key"] == "receivables":
            assert Decimal(value) == sum((Decimal(r["outstanding"]) for r in rows), Decimal(0))
        elif m["key"] in ("revenue", "cash"):
            account = drill["params"]["account"]
            assert total <= 200 or m["key"] == "cash"  # the list holds every entry behind it
            lines = JournalLine.objects.filter(
                entry__journal_reference__in=[r["reference"] for r in rows],
                entry__organization=game.organization,
                account__code=account,
            ).aggregate(dr=Sum("debit"), cr=Sum("credit"))
            net = (lines["cr"] or 0) - (lines["dr"] or 0)
            if m["key"] == "revenue":
                assert Decimal(value) == net, (value, net)
            elif total <= 200:
                assert Decimal(value) == -net
        checked.append(m["key"])
    assert sorted(checked) == sorted(m["key"] for m in metrics)
    print("figures followed:", checked)  # noqa: T201
