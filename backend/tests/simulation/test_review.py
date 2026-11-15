"""P2.3 — Data assets, consequence chains and the monthly Data Quality Review.

Done when (Document 08): after one month the review reports figures that the
tests confirm against the truth, and each one drills down to its records.

The checks here recompute every figure from the world directly, with the ORM,
rather than through the code under test.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import (
    AccountObservation,
    CreditAccount,
    CustomerIdentifier,
    ProviderCustomerLink,
)
from apps.bureau.quality.models import CaseType, Decision
from apps.bureau.reports.enquiries import enquire
from apps.bureau.submissions.models import RecordStatus, StagingRecord
from apps.bureau.submissions.pipeline import process_submission
from apps.commercial.models import Subscriber
from apps.simulation import controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.consequences import trace
from apps.simulation.engine import advance
from apps.simulation.fingerprint import fingerprint
from apps.simulation.judgement import sync_work_items
from apps.simulation.models import (
    Consequence,
    DataQualityReview,
    Delivery,
    EnquiryJudgement,
    EventType,
    Game,
    Notice,
    ScheduledEvent,
)
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import (
    FileDefect,
    Lender,
    LenderCustomer,
    Loan,
    LoanMonth,
    ProviderFileRow,
    World,
)
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import POOR

# Defects that need judgement, plus repeated rows; nothing that rejects whole files.
TRICKY = replace(
    POOR,
    name="TRICKY",
    wrong_identifier=0.12, name_typo=0.10, date_format=0.12, amount_format=0.08,
    inconsistent_status=0.10, missing_field=0.02, duplicate_row=0.03, omit_account=0.0,
    template_drift=0.0, late_rate=0.0,
)  # fmt: skip
JANUARY = date(2027, 1, 31)

Borrower = tuple[str, int]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _start(world: World, owner: Any = None) -> Game:
    """A game whose first files are tricky: plenty of judgement work for the team."""
    game = advance(start_game(world, owner=owner), 1)
    codes = ("ATB", "MRB")
    ScheduledEvent.objects.filter(
        game=game, event_type=EventType.PROVIDER_FILES_ARRIVE, payload__lender__in=codes
    ).delete()
    for code in codes:
        lender = Lender.objects.get(world=world, code=code)
        world_sub = generate_submission(
            world, lender, world.history_end, TRICKY, replace=True
        ).submission
        process_submission(deliver(game, world_sub), at=datetime(2027, 1, 4, 9, 0, tzinfo=UTC))
    sync_work_items(game, game.current_tick)
    return controls.set_pause_rules(game, [], deadlines=False)


def _play_january(game: Game) -> Game:
    while controls.state(game).now.month == 1:
        game = controls.advance_by(game, "next_event")
    return game


# --- The truth, worked out directly -------------------------------------------------------


def _who(lender_customer: LenderCustomer) -> Borrower:
    if lender_customer.person_id is not None:
        return ("person", lender_customer.person_id)
    return ("business", int(lender_customer.business_id or 0))


def _row_borrower(game: Game, file_id: int, row: int) -> Borrower:
    world_file = Delivery.objects.get(game=game, bureau_file_id=file_id).world_file_id
    loan = ProviderFileRow.objects.get(file_id=world_file, row_number=row).loan
    return _who(loan.customer)


def _link_borrower(game: Game, link: ProviderCustomerLink) -> Borrower:
    return _who(
        LenderCustomer.objects.get(
            lender__world=game.world,
            lender__code=link.institution.institution_code,
            customer_number=link.provider_customer_number,
        )
    )


def _customer_borrower(game: Game, customer_id: int) -> Borrower:
    first = ProviderCustomerLink.objects.filter(customer_id=customer_id).order_by("pk").first()
    assert first is not None
    return _link_borrower(game, first)


def _account_loan(game: Game, account: CreditAccount) -> Loan:
    return Loan.objects.get(
        lender__world=game.world,
        lender__code=account.institution.institution_code,
        account_number=account.facility_account_number,
    )


# --- The review reports what the truth confirms -------------------------------------------


def test_the_review_counts_decisions_as_the_truth_confirms(world: World) -> None:
    game = _play_january(_start(world))
    review = DataQualityReview.objects.get(game=game, period=JANUARY)
    f, refs = review.figures, review.refs
    assert Notice.objects.filter(game=game, kind="REVIEW_READY").exists()

    items = WorkItem.objects.filter(
        organization=game.organization, status=ItemStatus.DONE, resolved_tick__gt=0
    ).select_related("case__record")
    merges, splits, right = [], [], []
    for item in items.filter(item_type=CaseType.MATCH_REVIEW):
        case = item.case
        actual = _row_borrower(game, case.record.file_id, case.record.source_row_number)
        same = (
            case.candidate_customer_id is not None
            and _customer_borrower(game, case.candidate_customer_id) == actual
        )
        truth = Decision.SAME_CUSTOMER if same else Decision.DIFFERENT_CUSTOMER
        if item.decision == truth:
            right.append(item.item_number)
        elif item.decision == Decision.SAME_CUSTOMER:
            merges.append(item.item_number)
        elif item.decision == Decision.DIFFERENT_CUSTOMER:
            splits.append(item.item_number)

    assert f["match"]["total"] == items.filter(item_type=CaseType.MATCH_REVIEW).count() > 0
    assert sorted(refs.get("match.right", [])) == sorted(right)
    assert sorted(refs.get("match.false_merge", [])) == sorted(merges)
    assert sorted(refs.get("match.false_split", [])) == sorted(splits)
    assert f["match"]["false_merges"] == len(merges)
    assert f["triage"]["total"] == items.filter(item_type=CaseType.UNLOADABLE_TRIAGE).count() > 0


def test_the_review_counts_records_not_loaded_and_which_were_genuine(world: World) -> None:
    game = _play_january(_start(world))
    review = DataQualityReview.objects.get(game=game, period=JANUARY)
    rejected = review.figures["rejected"]

    not_loaded = StagingRecord.objects.filter(
        run__submission__organization=game.organization,
        run__completed_at__month=1,
        record_status__in=[RecordStatus.UNLOADABLE, RecordStatus.DUPLICATE],
    )
    assert rejected["total"] == not_loaded.count() > 0
    genuine = 0
    for record in not_loaded.select_related("file"):
        world_file = Delivery.objects.get(game=game, bureau_file_id=record.file_id).world_file_id
        repeated = FileDefect.objects.filter(
            file_id=world_file, row_number=record.source_row_number, defect_type="DUPLICATE_ROW"
        ).exists()
        genuine += not repeated
    assert rejected["genuine"] == genuine
    duplicates = next(r for r in rejected["rules"] if r["rule"] == "DUPLICATE")
    assert duplicates["records"] > duplicates["genuine"]  # most were really sent twice
    assert sum(r["records"] for r in rejected["rules"]) == rejected["total"]


def test_the_review_reveals_the_true_data_assets(world: World) -> None:
    game = _play_january(_start(world))
    review = DataQualityReview.objects.get(game=game, period=JANUARY)
    truth = review.figures["assets"]["truth"]
    visible = review.figures["assets"]["visible"]

    # Identity integrity: who each bureau customer really is, from its provider links.
    people_of: dict[int, set[Borrower]] = defaultdict(set)
    customers_of: dict[Borrower, set[int]] = defaultdict(set)
    for link in ProviderCustomerLink.objects.filter(organization=game.organization).select_related(
        "institution"
    ):
        who = _link_borrower(game, link)
        people_of[link.customer_id].add(who)
        customers_of[who].add(link.customer_id)
    assert truth["identity"]["false_merges"] == sum(len(p) > 1 for p in people_of.values())
    assert truth["identity"]["false_splits"] == sum(len(c) > 1 for c in customers_of.values())
    assert truth["identity"]["false_merges"] + truth["identity"]["false_splits"] > 0

    # Accuracy: each account's latest balance and arrears against the world's month.
    right = total = 0
    held: set[Borrower] = set()
    for account in CreditAccount.objects.filter(organization=game.organization).select_related(
        "institution"
    ):
        loan = _account_loan(game, account)
        held.add(_who(loan.customer))
        latest = (
            AccountObservation.objects.filter(credit_account=account, is_current=True)
            .order_by("-reporting_date")
            .first()
        )
        if latest is None:
            continue
        total += 1
        month = LoanMonth.objects.filter(loan=loan, period=latest.reporting_date).first()
        right += bool(
            month is not None
            and abs(latest.outstanding_balance - round(month.outstanding_balance)) <= Decimal(1)
            and latest.days_past_due == month.days_past_due
        )
    assert (truth["accuracy"]["accounts"], truth["accuracy"]["right"]) == (total, right)

    # Coverage: the world's active borrowers at the end of December with an account on file.
    active = {
        _who(m.loan.customer)
        for m in LoanMonth.objects.filter(
            world=game.world, period=date(2026, 12, 31), status="ACTIVE"
        ).select_related("loan__customer")
    }
    assert visible["coverage"]["active_borrowers"] == len(active)
    assert visible["coverage"]["covered"] == len(active & held)
    # The player's estimates come from a sample, with a margin.
    assert visible["audit"]["accuracy"]["sample"] == 100
    assert 0 < visible["audit"]["accuracy"]["margin"] < 0.1


def test_every_figure_drills_down_to_its_records(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _play_january(_start(world, owner=owner))
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}"

    listing = client.get(f"{base}/reviews/").json()
    assert [r["period"] for r in listing][-1] == "2027-01"
    detail = client.get(f"{base}/reviews/2027-01/").json()
    review = DataQualityReview.objects.get(game=game, period=JANUARY)
    assert detail["figures"] == review.figures
    for key in detail["drill"]:
        drill = client.get(f"{base}/reviews/2027-01/drill/", {"key": key}).json()
        assert len(drill["rows"]) == len(review.refs[key]), key
        if drill["kind"] == "work_items":
            assert all(set(review.refs[key]) >= {r["item"] for r in drill["rows"]} for _ in [0])
            assert all(r["why_right"] for r in drill["rows"])
        if drill["kind"] == "records":
            assert all(r["submission"].startswith("SUB-") and r["row"] for r in drill["rows"])
    assert client.get(f"{base}/reviews/2027-01/drill/", {"key": "nope"}).status_code == 400
    assert client.get(f"{base}/reviews/2026-13/").status_code == 404

    seen = client.get(f"{base}/data-assets/").json()
    assert seen["source"] == "month_end"
    assert "truth" not in seen and "identity" not in seen  # only what the bureau can see
    assert seen["coverage"] == review.figures["assets"]["visible"]["coverage"]


# --- Consequence chains -----------------------------------------------------------------------


def test_a_wrong_merge_is_traced_from_the_report_back_to_the_decision(world: World) -> None:
    game = _start(world)
    wrong = next(
        i
        for i in WorkItem.objects.filter(
            organization=game.organization,
            item_type=CaseType.MATCH_REVIEW,
            status=ItemStatus.OPEN,
            correct_decision=Decision.DIFFERENT_CUSTOMER,
            case__candidate_customer__isnull=False,
        ).order_by("item_number")
    )
    controls.resolve_item(game, wrong.item_number, Decision.SAME_CUSTOMER)  # a false merge
    candidate = wrong.case.candidate_customer_id
    assert candidate is not None

    # A lender checks the person the record was wrongly merged into.
    identifier = CustomerIdentifier.objects.filter(customer_id=candidate).first()
    assert identifier is not None
    subscriber = Subscriber.objects.filter(organization=game.organization).first()
    report = enquire(
        game.organization, subscriber, "CONSUMER_BASIC", "NEW_CREDIT", "C-1",
        identifier.identifier_type, identifier.identifier_value, "Test",
        datetime(2027, 1, 5, 10, 0, tzinfo=UTC),
    )  # fmt: skip
    applicant = _customer_borrower(game, candidate)
    chains = trace(game, report, applicant, "ATB", game.current_tick, report.enquired_at)

    mixed = [c for c in chains if c.effect == "MIXED_REPORT"]
    assert mixed, "the merged record's account was shown on the wrong person's report"
    chain = next(c for c in mixed if c.work_item_id == wrong.pk)
    assert chain.cause == "DECISION"
    assert f"work item {wrong.item_number}" in chain.detail and "by you" in chain.detail
    assert wrong.case.record.cleansed["CustomerID"] == chain.provider_customer


def test_recorded_chains_agree_with_the_truth(world: World) -> None:
    game = _play_january(_start(world))
    chains = list(Consequence.objects.filter(game=game).select_related("enquiry", "work_item"))
    assert chains, "the tricky month produces at least one wrong report"
    for chain in chains:
        judgement = EnquiryJudgement.objects.select_related("application").get(
            enquiry=chain.enquiry
        )
        app = judgement.application
        applicant: Borrower = (
            ("person", app.person_id) if app.person_id else ("business", int(app.business_id or 0))
        )
        link = ProviderCustomerLink.objects.select_related("institution").get(
            organization=game.organization,
            institution__institution_code=chain.provider,
            provider_customer_number=chain.provider_customer,
        )
        if chain.effect == "MIXED_REPORT":
            assert link.customer_id == chain.enquiry.customer_id
            assert _link_borrower(game, link) != applicant
        else:
            assert link.customer_id != chain.enquiry.customer_id
            assert _link_borrower(game, link) == applicant
        if chain.cause == "DECISION":
            assert chain.work_item is not None and chain.work_item.status == ItemStatus.DONE


def test_reviews_and_chains_replay_exactly(world: World) -> None:
    # An ordinary game: a replay starts from what the action log alone can reproduce.
    original = _play_january(controls.set_pause_rules(start_game(world), [], deadlines=False))
    assert DataQualityReview.objects.filter(game=original, period=JANUARY).exists()
    copy = controls.replay(original, start_game(world))
    assert fingerprint(copy) == fingerprint(original)
