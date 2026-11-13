"""S3 — Pipeline v0.

Done when (roadmap S3): month 1 loads; month 2 for the same provider creates
new observations on existing accounts, not new accounts; every loaded
observation traces to its source file and row; processing totals reconcile
(received = accepted + unloadable + duplicate).

These tests may read the world to check the bureau's results against the
truth; the bureau code under test may not (import-linter).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from apps.bureau.core.models import AccountObservation, CreditAccount, Customer
from apps.bureau.quality.models import TransformationLog, ValidationIssue
from apps.bureau.quality.rules import normalise_phone, validate
from apps.bureau.submissions.intake import read_rows, receive_file
from apps.bureau.submissions.models import (
    FileStatus,
    ProcessingRun,
    RecordStatus,
    StagingRecord,
    Submission,
)
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.simulation.models import Delivery, Game
from apps.standards.submission_template import FileKind
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import FileDefect, Lender, Loan, ProviderFileRow, World
from apps.world.provider_files import generate_submission, month_end
from apps.world.provider_files.profiles import CLEAN, POOR, DataQualityProfile

pytestmark = pytest.mark.django_db

# Dirty data the pipeline must cope with, but no template drift (that rejects whole files).
DIRTY = replace(
    POOR,
    name="DIRTY",
    missing_field=0.08, phone_format=0.15, amount_format=0.05, name_typo=0.05,
    wrong_identifier=0.03, stale_values=0.05, inconsistent_status=0.05, date_format=0.05,
    future_date=0.02, duplicate_row=0.05, omit_account=0.03, template_drift=0.0, late_rate=0.0,
)  # fmt: skip


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world() -> World:
    generated = build_world(51, "tiny")
    world_id = write_world(
        generated.config,
        generated.people,
        generated.businesses,
        generated.branches,
        generated.result,
        generated.stats,
    )
    return World.objects.get(pk=world_id)


@pytest.fixture
def game(world: World) -> Game:
    return start_game(world)


def _months(world: World) -> tuple[Any, Any]:
    end = world.history_end
    previous = month_end(end.year - (end.month == 1), (end.month - 2) % 12 + 1)
    return previous, end


def _run(game: Game, code: str, period: Any, profile: DataQualityProfile) -> ProcessingRun:
    lender = Lender.objects.get(world=game.world, code=code)
    world_sub = generate_submission(game.world, lender, period, profile).submission
    return process_submission(deliver(game, world_sub))


# --- Month 1 loads; month 2 adds observations, not accounts ------------------------


def test_second_month_adds_observations_to_existing_accounts(game: Game) -> None:
    first, second = _months(game.world)
    run1 = _run(game, "ATB", first, CLEAN)
    accounts_after_first = set(
        CreditAccount.objects.values_list("facility_account_number", flat=True)
    )
    assert run1.records_accepted == run1.records_received > 0
    assert run1.accounts_created == len(accounts_after_first) == run1.records_accepted

    run2 = _run(game, "ATB", second, CLEAN)
    reported = {r.cleansed["ACCOUNT_NUMBER"] for r in StagingRecord.objects.filter(run=run2)}
    assert run2.records_accepted == run2.records_received
    # Only accounts never reported before are new.
    assert run2.accounts_created == len(reported - accounts_after_first)
    for number in reported & accounts_after_first:
        account = CreditAccount.objects.get(facility_account_number=number)
        dates = sorted(account.observations.values_list("reporting_date", flat=True))
        assert dates == [first, second]
    # Customers seen in month 1 are not created again.
    assert run2.customers_created < run1.customers_created


# --- The bureau view is faithful when the data is clean -----------------------------


def test_clean_data_gives_one_bureau_customer_per_real_borrower(game: Game) -> None:
    first, second = _months(game.world)
    for code in ("ATB", "MRB", "UNS"):
        for period in (first, second):
            _run(game, code, period, CLEAN)

    borrowers_of: dict[int, set[tuple[str, int]]] = defaultdict(set)
    customers_of: dict[tuple[str, int], set[int]] = defaultdict(set)
    for obs in AccountObservation.objects.select_related("credit_account"):
        truth = _true_borrower(game, obs)
        borrowers_of[obs.credit_account.customer_id].add(truth)
        customers_of[truth].add(obs.credit_account.customer_id)

    assert borrowers_of, "nothing loaded"
    assert all(len(b) == 1 for b in borrowers_of.values()), "false merge"
    assert all(len(c) == 1 for c in customers_of.values()), "split customer"
    # Someone borrowing from two of these lenders is one bureau customer.
    assert any(
        len(set(CreditAccount.objects.filter(customer_id=c).values_list("institution", flat=True)))
        > 1
        for c in borrowers_of
    )


def _true_borrower(game: Game, obs: AccountObservation) -> tuple[str, int]:
    """Follow lineage back to the world: bureau file row -> world file row -> loan -> borrower."""
    delivery = Delivery.objects.get(game=game, bureau_file_id=obs.source_file_id)
    loan_id = ProviderFileRow.objects.get(
        file_id=delivery.world_file_id, row_number=obs.source_row_number
    ).loan_id
    customer = Loan.objects.select_related("customer").get(pk=loan_id).customer
    if customer.person_id is not None:
        return ("person", customer.person_id)
    assert customer.business_id is not None
    return ("business", customer.business_id)


# --- Lineage --------------------------------------------------------------------------


def test_every_observation_traces_to_its_source_file_and_row(game: Game, tmp_path: Path) -> None:
    first, _ = _months(game.world)
    _run(game, "ATB", first, DIRTY)
    observations = AccountObservation.objects.select_related("credit_account", "source_file")
    assert observations.exists()
    rows_by_file = {}
    for obs in observations:
        stored = obs.source_file
        if stored.pk not in rows_by_file:
            rows_by_file[stored.pk] = read_rows(stored)
        names, rows = rows_by_file[stored.pk]
        source = dict(zip(names, rows[obs.source_row_number - 1], strict=True))
        record = StagingRecord.objects.get(
            run=obs.processing_run, file=stored, source_row_number=obs.source_row_number
        )
        assert record.record_status == RecordStatus.ACCEPTED
        assert record.raw == source
        assert source["ACCOUNT_NUMBER"] == obs.credit_account.facility_account_number
        assert obs.source_submission_id == stored.submission_id


# --- Totals reconcile, and dirty data is handled as the rules say ---------------------


def test_totals_reconcile_and_defects_are_caught(game: Game) -> None:
    first, _ = _months(game.world)
    run = _run(game, "ATB", first, DIRTY)
    world_sub = Delivery.objects.filter(game=game).first().world_submission  # type: ignore[union-attr]
    ledger = FileDefect.objects.filter(submission=world_sub)

    assert run.reconciles
    assert run.records_received == sum(f.row_count for f in world_sub.files.all())
    statuses = StagingRecord.objects.filter(run=run).values_list("record_status", flat=True)
    assert run.records_received == len(statuses)
    # Every repeated row the provider sent is caught as a duplicate.
    assert run.records_duplicated == ledger.filter(defect_type="DUPLICATE_ROW").count() > 0
    # A blank mandatory field makes the record unloadable.
    for defect in ledger.filter(defect_type="MISSING_FIELD").exclude(field="MATURITY_DATE"):
        record = _record_for(run, defect)
        if defect.field in ("BRANCH_CODE", "GHANA_CARD_NUMBER", "DATE_OF_BIRTH", "GENDER",
                            "MOBILE_NUMBER", "TIN", "REGISTRATION_NUMBER", "CONTACT_NUMBER"):  # fmt: skip
            assert record.record_status != RecordStatus.ACCEPTED
            assert record.issues.filter(rule_code="F001", field=defect.field).exists()
    # Badly formatted phone numbers are cleansed back to the true value.
    cleansed = 0
    for defect in ledger.filter(defect_type="PHONE_FORMAT"):
        record = _record_for(run, defect)
        assert record.cleansed[defect.field] == defect.true_value
        assert TransformationLog.objects.filter(
            record=record, field=defect.field, rule_code="C001"
        ).exists()
        cleansed += 1
    assert cleansed > 0
    # A closed status with a balance is rejected.
    for defect in ledger.filter(defect_type="INCONSISTENT_STATUS"):
        assert _record_for(run, defect).issues.filter(rule_code="F011").exists()


def _record_for(run: ProcessingRun, defect: FileDefect) -> StagingRecord:
    delivery = Delivery.objects.get(world_file_id=defect.file_id)
    if defect.row_number is None:
        raise ValueError(f"{defect} is not a row defect")
    return StagingRecord.objects.get(
        run=run, file_id=delivery.bureau_file_id, source_row_number=defect.row_number
    )


# --- File-level rejections ------------------------------------------------------------


def test_a_file_whose_columns_drifted_is_rejected_whole(game: Game) -> None:
    first, _ = _months(game.world)
    run = _run(game, "ATB", first, replace(CLEAN, template_drift=1.0))
    assert run.records_received == 0
    files = Submission.objects.get(pk=run.submission_id).files.all()
    assert files and all(f.file_status == FileStatus.REJECTED for f in files)
    assert all(f.rejection_reason == "T001" for f in files)
    assert ValidationIssue.objects.filter(run=run, rule_code="T001").count() == len(files)


def test_repeated_and_misnamed_files_are_rejected(game: Game) -> None:
    first, _ = _months(game.world)
    run = _run(game, "ATB", first, CLEAN)
    original = Submission.objects.get(pk=run.submission_id).files.first()
    assert original is not None
    payload = (Path(settings.STORAGE_ROOT) / original.storage_path).read_bytes()
    institution = original.submission.institution
    when = datetime(2030, 1, 1, tzinfo=UTC)

    again = receive_file(game.organization, institution, first, original.file_name, payload, when)
    assert (again.file_status, again.rejection_reason) == (FileStatus.REJECTED, "T003")
    misnamed = receive_file(game.organization, institution, first, "atb data.csv", b"x", when)
    assert (misnamed.file_status, misnamed.rejection_reason) == (FileStatus.REJECTED, "T002")
    # The originals are kept, never overwritten.
    assert (Path(settings.STORAGE_ROOT) / original.storage_path).read_bytes() == payload


def test_reprocessing_does_not_duplicate_observations(game: Game) -> None:
    first, _ = _months(game.world)
    run1 = _run(game, "ATB", first, CLEAN)
    before = AccountObservation.objects.count()
    run2 = process_submission(Submission.objects.get(pk=run1.submission_id))
    assert run2.run_number == 2
    assert AccountObservation.objects.count() == before
    assert run2.records_unloadable == run2.records_received
    assert (
        ValidationIssue.objects.filter(run=run2, rule_code="L001").count() == run2.records_received
    )
    assert run2.reconciles


def test_bureau_data_belongs_to_its_own_organisation(world: World) -> None:
    first, _ = _months(world)
    lender = Lender.objects.get(world=world, code="ATB")
    world_sub = generate_submission(world, lender, first, CLEAN).submission
    game_a, game_b = start_game(world), start_game(world)
    process_submission(deliver(game_a, world_sub))
    process_submission(deliver(game_b, world_sub))
    count_a = Customer.objects.filter(organization=game_a.organization).count()
    count_b = Customer.objects.filter(organization=game_b.organization).count()
    assert count_a == count_b > 0


# --- Rules ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["0244123456", "+233244123456", "233244123456", "024 412 3456", "244123456", "244-123-456"],
)
def test_phone_numbers_are_normalised(raw: str) -> None:
    assert normalise_phone(raw) == "0244123456"


@pytest.mark.parametrize("raw", ["12345", "+44 20 7946 0958", "02441234567"])
def test_unrecognisable_phone_numbers_are_left_alone(raw: str) -> None:
    assert normalise_phone(raw) == raw


def test_validation_flags_formats_and_cross_field_rules() -> None:
    period = month_end(2026, 12)
    values = {
        "REPORTING_DATE": "31/12/2026", "PROVIDER_CODE": "ATB", "BRANCH_CODE": "ATB-001",
        "CUSTOMER_NUMBER": "AT1", "SURNAME": "Mensah", "FIRST_NAME": "Ama", "MIDDLE_NAMES": "",
        "DATE_OF_BIRTH": "12/31/1990", "GENDER": "F", "GHANA_CARD_NUMBER": "GHA-123456789-0",
        "MOBILE_NUMBER": "0244123456", "ALT_MOBILE_NUMBER": "", "REGION": "Ashanti", "TOWN": "",
        "EMPLOYMENT_TYPE": "", "ACCOUNT_NUMBER": "011", "FACILITY_TYPE": "XX", "CURRENCY": "GHS",
        "DISBURSEMENT_DATE": "01/01/2027", "MATURITY_DATE": "01/01/2026",
        "ORIGINAL_AMOUNT": "1,000.00", "INSTALMENT_AMOUNT": "100.00", "REPAYMENT_FREQUENCY": "M",
        "CURRENT_BALANCE": "500.00", "ARREARS_AMOUNT": "0.00", "DAYS_PAST_DUE": "0",
        "AMOUNT_PAID": "100.00", "ACCOUNT_STATUS": "PD", "ASSET_CLASSIFICATION": "CUR",
    }  # fmt: skip
    codes = {(i.rule_code, i.field) for i in validate(FileKind.INDIVIDUAL, values, "ATB", period)}
    assert ("F002", "DATE_OF_BIRTH") in codes  # month-first date, day > 12
    assert ("F008", "GHANA_CARD_NUMBER") in codes  # bad check digit
    assert ("F006", "FACILITY_TYPE") in codes
    assert ("F003", "DISBURSEMENT_DATE") in codes
    assert ("F004", "ORIGINAL_AMOUNT") in codes
    assert ("F011", "ACCOUNT_STATUS") in codes
    assert ("F012", "MATURITY_DATE") in codes
