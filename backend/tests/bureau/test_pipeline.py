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
from apps.bureau.quality.rules import (
    CORE,
    normalise_amount,
    normalise_date,
    normalise_phone,
    propose_corrections,
    validate,
)
from apps.bureau.submissions.intake import read_rows, receive_file
from apps.bureau.submissions.models import (
    FileStatus,
    ProcessingRun,
    RecordStatus,
    StagingRecord,
    Submission,
)
from apps.bureau.submissions.pipeline import _mark_duplicates, _Row, process_submission
from apps.simulation.bridge import deliver, start_game
from apps.simulation.models import Delivery, Game
from apps.standards.submission_template import FIELD_BY_NAME, FileKind, header, luhn_check_digit
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


def _run(
    game: Game, code: str, period: Any, profile: DataQualityProfile, drift_from: Any = None
) -> ProcessingRun:
    lender = Lender.objects.get(world=game.world, code=code)
    world_sub = generate_submission(
        game.world, lender, period, profile, drift_from=drift_from
    ).submission
    return process_submission(deliver(game, world_sub))


# --- Month 1 loads; month 2 adds observations, not accounts ------------------------


def test_second_month_adds_observations_to_existing_accounts(game: Game) -> None:
    first, second = _months(game.world)
    run1 = _run(game, "ATB", first, CLEAN)
    accounts_after_first = set(
        CreditAccount.objects.values_list("facility_account_number", flat=True)
    )
    assert run1.records_accepted == run1.records_received > 0
    credit = {"file__file_kind__in": ("CONC", "BUSC")}  # cheques and judgments are not accounts
    loaded = StagingRecord.objects.filter(run=run1, record_status=RecordStatus.ACCEPTED, **credit)
    assert run1.accounts_created == len(accounts_after_first) == loaded.count()

    run2 = _run(game, "ATB", second, CLEAN)
    reported = {
        r.cleansed["FacilityAccNum"] for r in StagingRecord.objects.filter(run=run2, **credit)
    }
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
        assert source["FacilityAccNum"] == obs.credit_account.facility_account_number
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
    # Under the standard policy a blank mandatory field makes the record unloadable.
    blanks = 0
    for defect in ledger.filter(defect_type="MISSING_FIELD"):
        record = _record_for(run, defect)
        if record.record_status == RecordStatus.DUPLICATE:
            continue
        mandatory = FIELD_BY_NAME[FileKind(record.file.file_kind)][defect.field].mandatory
        if mandatory:
            assert record.record_status == RecordStatus.UNLOADABLE
            assert record.issues.filter(rule_code="F001", field=defect.field).exists()
            blanks += 1
        elif defect.field == "NatIDNum" and record.raw["DisbursementDate"] >= "20200101":
            assert record.issues.filter(rule_code="F013").exists()
    assert blanks > 0
    # Badly formatted phone numbers are cleansed back to the true value.
    cleansed = 0
    for defect in ledger.filter(defect_type="PHONE_FORMAT"):
        record = _record_for(run, defect)
        if record.record_status == RecordStatus.DUPLICATE:
            continue
        assert record.cleansed[defect.field] == defect.true_value
        assert TransformationLog.objects.filter(
            record=record, field=defect.field, rule_code="C001"
        ).exists()
        cleansed += 1
    assert cleansed > 0
    # Badly formatted dates and amounts are cleansed too.
    for defect in ledger.filter(defect_type__in=("DATE_FORMAT", "AMOUNT_FORMAT")):
        record = _record_for(run, defect)
        if record.record_status == RecordStatus.DUPLICATE or not defect.true_value:
            continue
        if defect.defect_type == "DATE_FORMAT" and _ambiguous(defect.true_value):
            continue  # day and month both 12 or less: a swap cannot be detected
        assert record.cleansed[defect.field] == defect.true_value, defect
    # A closed status with a balance is rejected.
    for defect in ledger.filter(defect_type="INCONSISTENT_STATUS"):
        record = _record_for(run, defect)
        if record.record_status != RecordStatus.DUPLICATE:
            assert record.issues.filter(rule_code="F011").exists()


def _ambiguous(value: str) -> bool:
    return int(value[6:]) <= 12 and int(value[4:6]) <= 12


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
    run = _run(
        game, "ATB", first, replace(CLEAN, template_drift=1.0), drift_from=game.world.history_start
    )
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
    # Another provider's SRN in the name is rejected too.
    other_srn = "99999" + original.file_name[5:]
    misnamed = receive_file(game.organization, institution, first, other_srn, b"y", when)
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


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("15/03/2024", "20240315"), ("5/3/2024", "20240305"), ("2024-03-15", "20240315"),
     ("20241503", "20240315"), ("20240315", "20240315")],
)  # fmt: skip
def test_dates_are_normalised_when_their_meaning_is_certain(raw: str, clean: str) -> None:
    assert normalise_date(raw) == clean


@pytest.mark.parametrize("raw", ["20240305", "31/02/2024", "March 2024", "2024"])
def test_ambiguous_or_impossible_dates_are_left_alone(raw: str) -> None:
    assert normalise_date(raw) == raw


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("1,234", "1234"), ("GHS 1234", "1234"), ("1234.00", "1234"), ("1234.50", "1235"),
     ("1234.49", "1234"), ("12a", "12a")],
)  # fmt: skip
def test_amounts_are_normalised_to_whole_cedis(raw: str, clean: str) -> None:
    assert normalise_amount(raw) == clean


def _record(**changes: str) -> dict[str, str]:
    values = dict.fromkeys(header(FileKind.INDIVIDUAL), "")
    values |= {
        "Data": "D", "CorrectionIndicator": "0", "FacilityAccNum": "011", "CustomerID": "AT1",
        "BranchCode": "ATB-001", "NatIDNum": GOOD_CARD, "Gender": "F",
        "MaritalStatus": "S", "Nationality": "GHA", "DOB": "19900315", "Surname": "Mensah",
        "FirstName": "Ama", "CurResAddr1": "H/No. 4 Main Street", "CurResAddr2": "Kumasi",
        "OwnerOrTenant": "T", "PostAddrLine1": "P.O. Box 4, Kumasi",
        "IncomeCurrency": "GHS", "Income": "2500", "MobileTel1": "0244123456", "EmpType": "104",
        "Occupation": "Trader", "JointOrSoleAcc": "S", "NoParticipantsInAcc": "1",
        "CreditFacilityType": "122", "PurposeOfFacility": "P", "FacilityTerm": "12",
        "AmountCurrency": "GHS", "FacilityAmount": "1000", "DisbursementDate": "20250105",
        "DisbursementAmt": "1000", "MaturityDate": "20260105", "SchdInstalAmount": "100",
        "RepaymentFreq": "12", "CurBal": "500", "CurBalIndicator": "D",
        "AssetClassification": "A", "AmountInArrears": "0", "NDIA": "0", "LegalFlag": "102",
        "FacilityStatusCode": "A", "FacilityStatusDate": "20250105",
        "CreditCollateralInd": "102", "NatureOfGuarantor": "103",
    }  # fmt: skip
    return values | changes


GOOD_CARD = f"GHA-123456789-{luhn_check_digit('123456789')}"
BAD_CARD = f"GHA-123456789-{(luhn_check_digit('123456789') + 1) % 10}"


def _codes(values: dict[str, str], policy: str = "STANDARD") -> set[tuple[str, str]]:
    checked = validate(FileKind.INDIVIDUAL, values, month_end(2025, 12), policy)
    return {(i.rule_code, i.field) for i in checked.issues if i.severity == "ERROR"}


def test_a_complete_record_passes() -> None:
    assert _codes(_record()) == set()


def test_validation_flags_formats_and_cross_field_rules() -> None:
    values = _record(
        DOB="19901503", NatIDNum=BAD_CARD, CreditFacilityType="999",
        DisbursementDate="20260105", MaturityDate="20250105", FacilityAmount="1,000.00",
        FacilityStatusCode="C",
    )  # fmt: skip
    codes = _codes(values)
    assert ("F002", "DOB") in codes  # validate sees what it is given; cleansing comes first
    assert ("F008", "NatIDNum") in codes  # bad check digit
    assert ("F006", "CreditFacilityType") in codes
    assert ("F003", "DisbursementDate") in codes
    assert ("F004", "FacilityAmount") in codes
    assert ("F011", "FacilityStatusCode") in codes
    assert ("F014", "ClosedDate") in codes
    assert ("F012", "MaturityDate") in codes


def test_an_identifier_is_required_for_facilities_from_2020() -> None:
    assert ("F013", "NatIDNum") in _codes(_record(NatIDNum=""))
    assert ("F013", "NatIDNum") not in _codes(_record(NatIDNum="", DisbursementDate="20191231"))
    assert ("F013", "NatIDNum") not in _codes(_record(NatIDNum="", VotersIDNum="1234567890"))


def test_core_policy_rejects_only_on_core_fields_and_blanks_bad_values() -> None:
    values = _record(Occupation="", Gender="Q", Surname="")
    assert {("F001", "Occupation"), ("F006", "Gender"), ("F001", "Surname")} <= _codes(values)
    checked = validate(FileKind.INDIVIDUAL, values, month_end(2025, 12), CORE)
    errors = {(i.rule_code, i.field) for i in checked.issues if i.severity == "ERROR"}
    assert errors == {("F001", "Surname")}
    assert checked.blanked == {"Gender": "Q"}
    # Financial logic rejects under every policy.
    closed = _record(FacilityStatusCode="T", ClosedDate="20251231", ClosureReason="F")
    assert ("F011", "FacilityStatusCode") in _codes(closed, CORE)


def test_reopening_a_closed_account_is_proposed_only_when_that_is_the_whole_problem() -> None:
    period = month_end(2025, 12)
    closed = _record(FacilityStatusCode="C")
    issues = validate(FileKind.INDIVIDUAL, closed, period).issues
    assert propose_corrections(closed, issues, period)["FacilityStatusCode"] == "A"
    broken = _record(FacilityStatusCode="C", Surname="")
    issues = validate(FileKind.INDIVIDUAL, broken, period).issues
    assert propose_corrections(broken, issues, period) == {}


def test_of_duplicate_records_the_lower_balance_is_kept() -> None:
    def row(n: int, balance: str, **changes: str) -> _Row:
        values = _record(CurBal=balance, **changes)
        return _Row(None, n, values, values, [])  # type: ignore[arg-type]

    rows = [row(1, "900"), row(2, "400"), row(3, "400"), row(4, "100", FirstName="Kofi")]
    _mark_duplicates(FileKind.INDIVIDUAL, rows)
    # Rows 1-3 are one record: the lower balance (row 2, the first of the two at 400) wins.
    assert [r.status for r in rows] == [
        RecordStatus.DUPLICATE, RecordStatus.ACCEPTED, RecordStatus.DUPLICATE,
        RecordStatus.ACCEPTED,
    ]  # fmt: skip
    assert rows[0].duplicate_of == rows[2].duplicate_of == 2
    # Row 4's names disagree, so it is not a duplicate (the repeated account is D002).
    assert rows[3].duplicate_of is None
