"""P2.7 — Disputes and compliance.

Done when (Document 08): a false merge can be followed from the decision to the
dispute and its correction, and a missed deadline produces a regulator finding.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from apps.bureau.core.models import CreditAccount, CustomerIdentifier, ProviderCustomerLink
from apps.bureau.quality.models import CaseType, CorrectionRecord, Decision, Dispute
from apps.bureau.reports.enquiries import enquire
from apps.bureau.submissions.pipeline import process_submission
from apps.commercial.models import Subscriber
from apps.finance.models import JournalEntry
from apps.org.models import Employee
from apps.simulation import compliance, controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.consequences import trace
from apps.simulation.engine import advance
from apps.simulation.judgement import sync_work_items
from apps.simulation.models import (
    DataQualityReview,
    EnquiryJudgement,
    EventType,
    Game,
    Notice,
    RegulatorFinding,
    RegulatorStanding,
    ScheduledEvent,
)
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Lender, LenderCustomer, LoanApplication, World
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import POOR

TRICKY = replace(
    POOR,
    name="TRICKY",
    wrong_identifier=0.12, name_typo=0.10, date_format=0.12, amount_format=0.08,
    inconsistent_status=0.10, missing_field=0.02, duplicate_row=0.0, omit_account=0.0,
    template_drift=0.0, late_rate=0.0,
)  # fmt: skip
WHEN = datetime(2027, 1, 4, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture(autouse=True)
def _subjects_always_dispute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compliance, "DISPUTE_WRONG_REPORT", 1.0)


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _queue(world: World) -> Game:
    """Tricky files processed straight away, a quiet team, and no pauses."""
    game = controls.set_pause_rules(advance(start_game(world), 1), [], deadlines=False)
    ScheduledEvent.objects.filter(game=game, event_type=EventType.PROVIDER_FILES_ARRIVE).delete()
    for code in ("ATB", "MRB"):
        lender = Lender.objects.get(world=world, code=code)
        sub = generate_submission(world, lender, world.history_end, TRICKY, replace=True).submission
        process_submission(deliver(game, sub), at=WHEN)
    sync_work_items(game, game.current_tick)
    Employee.objects.filter(organization=game.organization).update(is_active=False)
    # Compliance's other duties are done, so only disputes bring findings here (P3.7).
    for item in WorkItem.objects.filter(
        organization=game.organization, item_type=CaseType.REGULATORY_RETURN
    ):
        controls.resolve_item(game, item.item_number, Decision.FILE_RETURN)
    controls.review_access(game)
    return game


def _false_merge_and_report(game: Game) -> tuple[WorkItem, Dispute]:
    """The player merges two people; a lender checks one of them; she disputes."""
    wrong = (
        WorkItem.objects.filter(
            organization=game.organization,
            item_type=CaseType.MATCH_REVIEW,
            status=ItemStatus.OPEN,
            correct_decision=Decision.DIFFERENT_CUSTOMER,
            case__candidate_customer__isnull=False,
        )
        .order_by("item_number")
        .first()
    )
    assert wrong is not None
    controls.resolve_item(game, wrong.item_number, Decision.SAME_CUSTOMER)
    candidate = wrong.case.candidate_customer_id
    assert candidate is not None

    # The candidate's real person applies for credit and the lender checks the bureau.
    link = ProviderCustomerLink.objects.filter(customer_id=candidate).order_by("pk").first()
    assert link is not None
    lc = LenderCustomer.objects.get(
        lender__world=game.world,
        lender__code=link.institution.institution_code,
        customer_number=link.provider_customer_number,
    )
    application = LoanApplication.objects.filter(world=game.world).first()
    assert application is not None
    application.person_id, application.business_id = lc.person_id, lc.business_id
    application.save()
    identifier = CustomerIdentifier.objects.filter(customer_id=candidate).first()
    assert identifier is not None
    subscriber = Subscriber.objects.filter(organization=game.organization).first()
    report = enquire(
        game.organization, subscriber, "CONSUMER_BASIC", "NEW_CREDIT", "C-1",
        identifier.identifier_type, identifier.identifier_value, "Test Subject", WHEN,
    )  # fmt: skip
    EnquiryJudgement.objects.create(
        game=game, enquiry=report, application=application, should_hit=True, hit=True,
        correct_person=True, outcome="CORRECT_HIT",
    )  # fmt: skip
    applicant = ("person", lc.person_id) if lc.person_id else ("business", lc.business_id or 0)
    chains = trace(game, report, applicant, "ATB", game.current_tick, WHEN)
    assert any(c.effect == "MIXED_REPORT" and c.work_item_id == wrong.pk for c in chains)
    assert compliance.maybe_dispute(game, report, "Test Subject", chains, game.current_tick)

    game = controls.advance_by(game, "day", 9)  # the subject files within 2-8 working days
    dispute = Dispute.objects.get(organization=game.organization, enquiry=report)
    return wrong, dispute


def test_a_false_merge_is_followed_to_the_dispute_and_its_correction(world: World) -> None:
    game = _queue(world)
    wrong, dispute = _false_merge_and_report(game)
    assert Notice.objects.filter(game=game, kind="DISPUTE_RECEIVED").exists()

    # While it is open, the disputed accounts are flagged on reports.
    held = CustomerIdentifier.objects.filter(customer=dispute.customer).first()
    assert held is not None
    report = enquire(
        game.organization, Subscriber.objects.filter(organization=game.organization).first(),
        "CONSUMER_BASIC", "NEW_CREDIT", "C-2", held.identifier_type, held.identifier_value,
        "Again", WHEN,
    )  # fmt: skip
    flagged = {(a["lender"], a["account"]) for a in report.report["accounts"] if a["disputed"]}
    assert len(flagged) == len(dispute.accounts) > 0

    # The dispute is a work item whose right answer, from the truth, is to uphold.
    item = WorkItem.objects.get(organization=game.organization, case__dispute=dispute)
    assert item.item_type == CaseType.DISPUTE
    assert item.correct_decision == Decision.UPHOLD_DISPUTE
    assert item.due_tick is not None

    # Upheld: the merged accounts move to a customer of their own, each one recorded.
    accounts_before = set(
        CreditAccount.objects.filter(customer=dispute.customer).values_list("pk", flat=True)
    )
    controls.resolve_item(game, item.item_number, Decision.UPHOLD_DISPUTE)
    dispute.refresh_from_db()
    assert (dispute.status, dispute.outcome) == ("RESOLVED", "UPHELD")
    corrections = CorrectionRecord.objects.filter(dispute=dispute)
    assert corrections.count() >= len(dispute.accounts)
    for correction in corrections:
        assert correction.from_customer_id == dispute.customer_id
        assert correction.to_customer_id != dispute.customer_id
        assert correction.credit_account.customer_id == correction.to_customer_id
        assert correction.approved_by
    assert not {c.credit_account_id for c in corrections} - accounts_before
    # The wrongly merged provider customer now points at its own customer.
    merged = wrong.case.record
    assert merged is not None
    link = ProviderCustomerLink.objects.get(
        institution=merged.run.submission.institution,
        provider_customer_number=merged.cleansed["CustomerID"],
    )
    assert link.customer_id != dispute.customer_id

    # The month's review replays the chain: decision -> wrong report -> dispute -> correction.
    while controls.state(game).now.month == 1:
        game = controls.advance_by(game, "next_event")
    review = DataQualityReview.objects.get(game=game, period__month=1, period__year=2027)
    chain = next(
        c for c in review.figures["consequences"]["chains"] if c["work_item"] == wrong.item_number
    )
    assert chain["dispute"]["number"] == dispute.dispute_number
    assert chain["dispute"]["outcome"] == "UPHELD" and chain["dispute"]["corrections"] > 0


def test_a_missed_deadline_produces_a_regulator_finding(world: World) -> None:
    game = _queue(world)
    _, dispute = _false_merge_and_report(game)
    while controls.state(game).now.date() <= dispute.due_date:  # nobody settles it
        game = controls.advance_by(game, "day")
    game = controls.advance_by(game, "day")
    finding = RegulatorFinding.objects.get(game=game, reference=str(dispute.dispute_number))
    assert finding.kind == "MISSED_DISPUTE_DEADLINE"
    assert Notice.objects.filter(game=game, kind="REGULATOR_FINDING").exists()
    standing = RegulatorStanding.objects.get(game=game)
    assert standing.level == 1  # a concern letter
    assert Notice.objects.filter(game=game, kind="REGULATOR_LADDER").count() == 1
    # One finding per dispute, however long it stays open. (Other disputes the world
    # raises meanwhile may bring findings of their own.)
    game = controls.advance_by(game, "day", 3)
    assert (
        RegulatorFinding.objects.filter(game=game, reference=str(dispute.dispute_number)).count()
        == 1
    )


def test_the_ladder_climbs_with_findings_and_fines_the_bureau(world: World) -> None:
    game = controls.set_pause_rules(start_game(world), [], deadlines=False)
    at = datetime(2027, 1, 4, 8, 0, tzinfo=UTC)
    notices: list[tuple[str, str]] = []

    def add(kind: str, severity: str, *_: Any) -> None:
        notices.append((kind, severity))

    for n in range(1, 8):
        RegulatorFinding.objects.create(
            game=game, kind="MISSED_DISPUTE_DEADLINE", reference=str(n), raised_at=at, detail=""
        )
        compliance._climb(game, at.date(), at, add)
    assert RegulatorStanding.objects.get(game=game).level == 4
    assert compliance.suspended(game)
    assert [k for k, _ in notices] == [
        "REGULATOR_LADDER"
    ] * 4  # letter, directive, penalty, suspension
    assert notices[-1][1] == "CRITICAL"
    fine = JournalEntry.objects.get(
        organization=game.organization, source_type="REGULATORY_PENALTY"
    )
    assert fine.lines.filter(debit__gt=0).first().debit == compliance.PENALTY  # type: ignore[union-attr]

    # Six months on, the findings have aged out: back in good standing.
    later = datetime(2027, 8, 2, 8, 0, tzinfo=UTC)
    compliance._climb(game, later.date(), later, add)
    assert RegulatorStanding.objects.get(game=game).level == 0
    assert notices[-1] == ("REGULATOR_LADDER", "INFO")
