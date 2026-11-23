"""P3.4 — the SQL console.

Done when (Document 09): tests show the console cannot read the world, another game,
or anything writeable; a heavy query is stopped by the timeout.

The console role is created once per database server by an administrator (README,
"The SQL console"); without it these tests fail and say so.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.analytics import console
from apps.bureau.core.models import Customer
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.simulation.models import Game
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Lender, World
from apps.world.provider_files import generate_submission
from tests.roles import working_as

WHEN = datetime(2027, 1, 4, 17, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    assert console.available(), (
        "Create the console role first (README, 'The SQL console'): "
        "CREATE ROLE simb_console NOLOGIN; GRANT simb_console TO simb;"
    )
    g = build_world(61, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _loaded(world: World, provider: str, owner: User | None = None) -> Game:
    game = start_game(world, owner=owner)
    lender = Lender.objects.get(world=world, code=provider)
    process_submission(
        deliver(game, generate_submission(world, lender, world.history_end).submission), at=WHEN
    )
    return game


def _refused(organization_id: int, sql: str) -> str:
    with pytest.raises(console.ConsoleError) as caught:
        console.run(organization_id, sql)
    return str(caught.value)


def test_the_console_sees_only_its_own_game(world: World) -> None:
    one, two = _loaded(world, "ATB"), _loaded(world, "MRB")
    for game in (one, two):
        result = console.run(game.organization_id, "SELECT count(*) AS n FROM customers")
        assert result.columns == ["n"]
        assert result.rows == [[Customer.objects.filter(organization=game.organization).count()]]
    lenders = console.run(one.organization_id, "SELECT DISTINCT lender FROM accounts").rows
    assert lenders == [["ATB"]]
    # The session record is rolled back with the query.
    assert not console.run(one.organization_id, "SELECT 1 AS x").truncated


def test_the_console_cannot_read_the_world_the_app_or_the_answer_key(world: World) -> None:
    org = _loaded(world, "ATB").organization_id
    assert "own tables" in _refused(org, "SELECT count(*) FROM public.world_person")
    assert "own tables" in _refused(org, "SELECT count(*) FROM public.world_loanmonth")
    assert "own tables" in _refused(org, "SELECT * FROM public.bureau_core_customer")
    assert "own tables" in _refused(org, "SELECT * FROM public.console_session")
    assert "own tables" in _refused(org, "SELECT * FROM public.accounts_user")
    assert "does not exist" in _refused(org, "SELECT * FROM world_person")  # not on its path
    assert "correct_decision" in _refused(org, "SELECT correct_decision FROM work_items")


def test_the_console_cannot_write_or_change_its_role(world: World) -> None:
    org = _loaded(world, "ATB").organization_id
    before = Customer.objects.filter(organization_id=org).count()
    _refused(org, "WITH gone AS (DELETE FROM customers RETURNING 1) SELECT count(*) FROM gone")
    assert "One statement" in _refused(org, "SELECT 1; DELETE FROM customers")
    assert "only reads" in _refused(org, "DELETE FROM customers")
    assert "role" in _refused(org, "SELECT set_config('role', 'simb', true)")
    assert "role" in _refused(
        org, "SELECT 1 FROM customers WHERE pg_catalog.SET_CONFIG('role','simb',true) IS NULL"
    )
    assert Customer.objects.filter(organization_id=org).count() == before


def test_a_heavy_query_is_stopped_and_long_answers_are_cut(world: World) -> None:
    org = _loaded(world, "ATB").organization_id
    started = time.perf_counter()
    assert "stopped after" in _refused(org, "SELECT pg_sleep(30)")
    assert time.perf_counter() - started < console.TIMEOUT_SECONDS + 5
    many = console.run(
        org, "SELECT o.*, n FROM observations o CROSS JOIN generate_series(1, 50) AS n"
    )
    assert many.truncated and len(many.rows) == console.MAX_ROWS
    # Values come back as plain JSON: amounts and dates as text.
    first = dict(zip(many.columns, many.rows[0], strict=True))
    assert isinstance(first["outstanding_balance"], str) and isinstance(
        first["reporting_date"], str
    )


def test_the_console_screen_is_the_analysts(world: World) -> None:
    owner = User.objects.create_user("analyst")
    game = _loaded(world, "ATB", owner)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/console/"
    offered = client.get(url).json()
    assert offered["available"] is True
    assert {t["table"] for t in offered["tables"]} >= {
        "customers",
        "accounts",
        "observations",
        "work_items",
        "journal_lines",
    }
    work_items = next(t for t in offered["tables"] if t["table"] == "work_items")
    assert "correct_decision" not in {c["name"] for c in work_items["columns"]}

    answered = client.post(url, {"sql": "SELECT count(*) AS n FROM accounts"}, format="json")
    assert answered.status_code == 200 and answered.json()["rows"][0][0] > 0  # the CEO may
    assert (
        client.post(url, {"sql": "SELECT * FROM public.world_person"}, format="json").status_code
        == 400
    )
    working_as(game, "DATA_OPERATIONS")
    assert client.post(url, {"sql": "SELECT 1"}, format="json").status_code == 403
    working_as(Game.objects.get(pk=game.pk), "DATA_ANALYTICS")
    assert client.post(url, {"sql": "SELECT 1 AS one"}, format="json").json()["rows"] == [[1]]
