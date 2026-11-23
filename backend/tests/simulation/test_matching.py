"""P2.4 — Data Operations depth I: matching.

Done when (Document 08): raising or lowering a threshold measurably trades
false merges against false splits, shown in the Data Quality Review.

The games here start with an empty bureau and no staff, and every provider's
first files carry many identifier defects (a blank Ghana Card, another person's
card) and misspelt names, so that matching, not reviewers, decides who is who.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import LinkMethod, ProviderCustomerLink
from apps.bureau.submissions.models import RecordStatus
from apps.bureau.submissions.pipeline import _mark_duplicates, _Row, process_submission
from apps.finance.models import JournalEntry
from apps.org.models import Employee
from apps.simulation import controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.engine import ClockError, advance
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import DataQualityReview, EventType, Game, ScheduledEvent
from apps.standards.submission_template import FileKind
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import FileDefect, Lender, LenderCustomer, ProviderSubmission, World
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import AVERAGE
from tests.roles import working_as

# Identifier trouble and misspelt names; nothing that rejects whole files.
IDS = replace(
    AVERAGE,
    name="IDS",
    missing_field=0.2,
    blank_weights={"NatIDNum": 1.0, "BusRegNum": 1.0, "TINum": 1.0},
    wrong_identifier=0.1,
    name_typo=0.3,
    template_drift=0.0,
    late_rate=0.0,
)
WHEN = datetime(2027, 1, 4, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _january(world: World, tooling: str, auto_link: float, review: float) -> Game:
    """A first month in which matching alone decides who is who."""
    game = controls.set_pause_rules(start_game(world), [], deadlines=False)
    game = controls.set_matching_tooling(game, tooling)
    game = controls.set_matching_thresholds(game, auto_link, review)
    Employee.objects.filter(organization=game.organization).update(is_active=False)
    game = advance(game, 1)
    ScheduledEvent.objects.filter(game=game, event_type=EventType.PROVIDER_FILES_ARRIVE).delete()
    codes = list(game.organization.institutions.values_list("institution_code", flat=True))
    for lender in Lender.objects.filter(world=world, code__in=codes).order_by("code"):
        existing = ProviderSubmission.objects.filter(lender=lender, period=world.history_end)
        if existing.filter(profile__name="IDS").exists():
            submission = existing.get()
        else:
            submission = generate_submission(
                world, lender, world.history_end, IDS, replace=True
            ).submission
        process_submission(deliver(game, submission), at=WHEN)
    while controls.state(game).now.month == 1:
        game = controls.advance_by(game, "next_event")
    return game


def _identity(game: Game) -> dict[str, int]:
    review = DataQualityReview.objects.get(game=game, period__month=1, period__year=2027)
    identity: dict[str, int] = review.figures["assets"]["truth"]["identity"]
    return identity


# --- The trade-off ---------------------------------------------------------------------------


@pytest.mark.slow
def test_thresholds_trade_false_merges_against_false_splits(world: World) -> None:
    basic = _identity(_january(world, "BASIC", 0.92, 0.75))
    low = _identity(_january(world, "STANDARD", 0.60, 0.50))
    default = _identity(_january(world, "STANDARD", 0.92, 0.75))
    high = _identity(_january(world, "STANDARD", 0.99, 0.98))

    # Lowering the thresholds links more boldly: more false merges, fewer false splits.
    assert low["false_merges"] > default["false_merges"] >= high["false_merges"]
    assert low["false_splits"] <= default["false_splits"] <= high["false_splits"]
    assert low["false_merges"] >= 10 and high["false_splits"] >= 1
    # Fuzzy matching finds people that identifiers alone miss.
    assert basic["false_splits"] > default["false_splits"]
    assert basic["false_merges"] == 0


@pytest.mark.slow
def test_the_review_shows_how_each_way_of_linking_did(world: World) -> None:
    game = _january(world, "STANDARD", 0.60, 0.50)
    review = DataQualityReview.objects.get(game=game, period__month=1, period__year=2027)
    matching = review.figures["matching"]
    assert (matching["tooling"], matching["auto_link"], matching["review"]) == (
        "STANDARD", 0.6, 0.5,
    )  # fmt: skip

    # Recompute each link's truth directly: who it names, and who its customer is.
    first_of: dict[int, tuple[str, int]] = {}
    expected: dict[str, dict[str, int]] = defaultdict(lambda: {"links": 0, "wrong_merges": 0})
    for link in (
        ProviderCustomerLink.objects.filter(organization=game.organization)
        .select_related("institution")
        .order_by("pk")
    ):
        lc = LenderCustomer.objects.get(
            lender__world=world,
            lender__code=link.institution.institution_code,
            customer_number=link.provider_customer_number,
        )
        who = ("person", lc.person_id) if lc.person_id else ("business", int(lc.business_id or 0))
        tally = expected[link.method]
        tally["links"] += 1
        if link.customer_id in first_of and first_of[link.customer_id] != who:
            tally["wrong_merges"] += 1
        first_of.setdefault(link.customer_id, who)
    for method, tally in expected.items():
        assert matching["methods"][method]["links"] == tally["links"], method
        assert matching["methods"][method]["wrong_merges"] == tally["wrong_merges"], method
    # The bold fuzzy links are where the false merges came from.
    fuzzy = matching["methods"][LinkMethod.FUZZY]
    assert fuzzy["wrong_merges"] > fuzzy["links"] / 2


# --- Near-duplicates ---------------------------------------------------------------------------


def _row(n: int, first_name: str, balance: str = "500") -> _Row:
    values = {
        "FacilityAccNum": "ACC1", "CustomerID": "C1", "DisbursementDate": "20240105",
        "Surname": "Mensah", "FirstName": first_name, "CurBal": balance,
    }  # fmt: skip
    return _Row(None, n, values, values, [])  # type: ignore[arg-type]


def test_matching_tooling_recognises_a_near_duplicate() -> None:
    rows = [_row(1, "Kwabena"), _row(2, "Kwabeena")]  # resent with the name retyped
    _mark_duplicates(FileKind.INDIVIDUAL, rows, "STANDARD", 0.92)
    assert [r.status for r in rows] == [RecordStatus.ACCEPTED, RecordStatus.DUPLICATE]
    assert rows[1].duplicate_of == 1
    assert "alike" in rows[1].issues[0].value

    without = [_row(1, "Kwabena"), _row(2, "Kwabeena")]
    _mark_duplicates(FileKind.INDIVIDUAL, without, "BASIC", 0.92)
    assert [r.status for r in without] == [RecordStatus.ACCEPTED, RecordStatus.ACCEPTED]

    different = [_row(1, "Kwabena"), _row(2, "Esi")]  # same account, another name: not a repeat
    _mark_duplicates(FileKind.INDIVIDUAL, different, "STANDARD", 0.92)
    assert different[1].status == RecordStatus.ACCEPTED


def test_providers_resend_some_rows_with_the_name_retyped(world: World) -> None:
    lender = Lender.objects.filter(world=world).order_by("code").first()
    assert lender is not None
    noisy = replace(AVERAGE, name="REPEATS", duplicate_row=0.2, near_duplicate=0.5)
    sub = generate_submission(world, lender, world.history_end, noisy, replace=True).submission
    repeats = FileDefect.objects.filter(submission=sub, defect_type="DUPLICATE_ROW")
    retyped = FileDefect.objects.filter(
        submission=sub,
        defect_type="NAME_TYPO",
        row_number__in=repeats.values_list("row_number", flat=True),
    )
    assert repeats.count() > 10
    assert 0 < retyped.count() < repeats.count()


# --- Policy, cost and replay --------------------------------------------------------------------


@pytest.mark.slow
def test_matching_policy_is_a_replayable_action_and_tooling_costs_money(world: World) -> None:
    owner = User.objects.create_user("player")
    game = working_as(start_game(world, owner=owner), "DATA_OPERATIONS")
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/matching-policy/"

    policy = client.get(url).json()
    assert (policy["tooling"], policy["auto_link"], policy["review"]) == ("BASIC", 0.92, 0.75)
    costs = {o["level"]: Decimal(o["monthly_cost"]) for o in policy["options"]}
    assert costs["BASIC"] == 0 < costs["STANDARD"] < costs["ADVANCED"]

    # Thresholds are Data Operations' to set; tooling is an investment, the Chief Executive's
    # (P3.1). Changing both at once needs both roles, so it is refused as a whole.
    both = client.post(
        url, {"tooling": "ADVANCED", "auto_link": 0.95, "review": 0.8}, format="json"
    )
    assert both.status_code == 403 and "Chief Executive" in both.json()["detail"]
    changed = client.post(url, {"auto_link": 0.95, "review": 0.8}, format="json").json()
    assert (changed["tooling"], changed["auto_link"], changed["review"]) == ("BASIC", 0.95, 0.8)
    assert client.post(url, {"auto_link": 0.7, "review": 0.8}, format="json").status_code == 400
    game = working_as(Game.objects.get(pk=game.pk), "CEO")
    changed = client.post(url, {"tooling": "ADVANCED"}, format="json").json()
    assert (changed["tooling"], changed["auto_link"], changed["review"]) == ("ADVANCED", 0.95, 0.8)
    assert client.post(url, {"tooling": "PREMIUM"}, format="json").status_code == 400

    game.refresh_from_db()
    game = controls.set_pause_rules(game, [], deadlines=False)
    while controls.state(game).now.month < 2:
        game = controls.advance_by(game, "next_event")
    licence = JournalEntry.objects.get(
        organization=game.organization, source_type="IT_TOOLING", transaction_date__month=2
    )
    assert "advanced" in licence.description

    copy = controls.replay(game, start_game(world))
    assert fingerprint(copy) == fingerprint(game)


def test_thresholds_must_be_in_order(world: World) -> None:
    game = start_game(world)
    with pytest.raises(ClockError):
        controls.set_matching_thresholds(game, 0.8, 0.9)
    with pytest.raises(ClockError):
        controls.set_matching_thresholds(game, 1.2, 0.9)
