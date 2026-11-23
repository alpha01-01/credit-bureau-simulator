"""P3.4 — Analytics I: portfolio analytics.

Done when (Document 09): the analytics figures agree with independent queries over
the same records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.analytics.portfolio import AGE_BANDS, bucket, portfolio
from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.simulation.bridge import start_game
from apps.simulation.models import Game
from apps.standards.submission_template import OPEN_STATUS_CODES
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def game(db: None) -> Game:
    g = build_world(61, "tiny")
    world = World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )
    return start_game(world, owner=User.objects.create_user("analyst"), history_months=4)


def _months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _month_end_before(day: date) -> date:
    return date(day.year, day.month, 1) - timedelta(days=1)


def _independent(game: Game) -> dict[str, Any]:
    """The same figures, account by account through the ORM: each lender at its own
    latest file, and vintages only for accounts opened since the records began."""
    observations = list(
        AccountObservation.objects.filter(
            credit_account__organization=game.organization, is_current=True
        ).select_related("credit_account__institution")
    )
    at = {(o.credit_account_id, o.reporting_date): o for o in observations}
    lender_latest: dict[str, date] = {}
    for o in observations:
        code = o.credit_account.institution.institution_code
        lender_latest[code] = max(lender_latest.get(code, o.reporting_date), o.reporting_date)
    records_start = min(o.reporting_date for o in observations).replace(day=1)
    first_default: dict[int, date] = {}
    for o in sorted(observations, key=lambda o: o.reporting_date):
        if o.days_past_due >= 90:
            first_default.setdefault(o.credit_account_id, o.reporting_date)
    accounts = {
        a.pk: a
        for a in CreditAccount.objects.filter(organization=game.organization).select_related(
            "institution"
        )
    }
    live = 0
    by_lender: dict[str, Counter[str]] = defaultdict(Counter)
    rolls: Counter[tuple[str, str]] = Counter()
    for pk, account in accounts.items():
        code = account.institution.institution_code
        if code not in lender_latest:
            continue
        now = at.get((pk, lender_latest[code]))
        if now is not None and now.facility_status in OPEN_STATUS_CODES:
            live += 1
            row = by_lender[code]
            row["accounts"] += 1
            row["arrears_30"] += now.days_past_due >= 30
            row["default_90"] += now.days_past_due >= 90
        then = at.get((pk, _month_end_before(lender_latest[code])))
        if then is not None and now is not None and then.facility_status in OPEN_STATUS_CODES:
            to = bucket(now.days_past_due) if now.facility_status in OPEN_STATUS_CODES else "Closed"
            rolls[(bucket(then.days_past_due), to)] += 1
    ages: Counter[str] = Counter()
    for pk, first in first_default.items():
        disbursed = accounts[pk].disbursement_date
        if disbursed is None or disbursed < records_start:
            continue
        age = _months(disbursed, first)
        lo, hi = next(b for b in AGE_BANDS if b[0] <= age <= b[1])
        ages[f"{lo}-{hi}" if hi < 10_000 else f"{lo}+"] += 1
    return {
        "live": live, "by_lender": by_lender, "rolls": rolls, "ages": ages,
        "lender_latest": lender_latest, "records_start": records_start,
    }  # fmt: skip


def test_portfolio_analytics_agree_with_the_records(game: Game) -> None:
    result = portfolio(game.organization_id)
    assert result["as_of"] is not None
    expected = _independent(game)
    assert result["lenders_as_of"] == {
        k: v.isoformat() for k, v in expected["lender_latest"].items()
    }
    assert result["records_start"] == expected["records_start"].isoformat()

    assert result["live_accounts"] == expected["live"] > 0
    lenders = {row["key"]: row for row in result["groups"]["lender"]}
    assert set(lenders) == set(expected["by_lender"])
    for code, counts in expected["by_lender"].items():
        row = lenders[code]
        assert (row["accounts"], row["arrears_30"], row["default_90"]) == (
            counts["accounts"], counts["arrears_30"], counts["default_90"],
        )  # fmt: skip
        assert row["arrears_30_share"] == counts["arrears_30"] / counts["accounts"]
    # Every grouping covers the same live book.
    for name in ("product", "region", "vintage"):
        assert sum(row["accounts"] for row in result["groups"][name]) == expected["live"]

    counts = result["roll_rates"]["counts"]
    got = Counter({(a, b): n for a, row in counts.items() for b, n in row.items() if n})
    assert got == expected["rolls"] and sum(got.values()) > 0
    assert {r["months"]: r["accounts"] for r in result["age_at_default"] if r["accounts"]} == dict(
        expected["ages"]
    )

    # Vintages: only quarters since the records began; a matured quarter's rate is its
    # defaults within 12 months over its accounts.
    assert all(v["quarter"] >= f"{expected['records_start'].year} Q1" for v in result["vintages"])
    for v in result["vintages"]:
        assert v["defaulted"] <= v["accounts"]
        if v["mature"]:
            assert v["default_rate"] == v["mature_defaulted"] / v["mature"]


def test_the_analytics_screen(game: Game) -> None:
    client = APIClient()
    assert game.owner is not None
    client.force_authenticate(game.owner)
    shown = client.get(f"/api/v1/games/{game.pk}/analytics/").json()
    assert shown["default_definition"] == "90+ days past due within 12 months of disbursement"
    assert shown["groups"]["product"][0]["label"] != shown["groups"]["product"][0]["key"]
    assert client.get(f"/api/v1/games/{game.pk}/analytics/?as_of=nonsense").status_code == 400
    # The bureau's view only: nothing from the world's truth is on the screen.
    for secret in ("risk_z", "health_z", "true_", "world"):
        assert secret not in str(shown)
