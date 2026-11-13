"""S2 — Provider files and the defect ledger.

Done when (roadmap S2): every defect in a file is recorded in the defect
ledger, and a clean profile produces a file that matches the truth exactly.
Files are read back from disk, as the bureau will read them.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from apps.standards.submission_template import (
    CODE_LISTS,
    FIELDS,
    SUBMISSION_DUE_DAY,
    FileKind,
    asset_classification,
    format_date,
    header,
)
from apps.world.generation import build_world
from apps.world.generation.config import EMPLOYMENT_TYPES, REGIONS, SECTORS
from apps.world.generation.persist import delete_world, write_world
from apps.world.models import (
    FileDefect,
    Lender,
    Loan,
    LoanMonth,
    ProviderFile,
    ProviderFileRow,
    ProviderSubmission,
    World,
)
from apps.world.provider_files import (
    generate_submission,
    layout_for,
    month_end,
    play_start,
    schedule,
    submission_dir,
)
from apps.world.provider_files.profiles import CLEAN, POOR, DataQualityProfile
from apps.world.provider_files.render import Layout
from apps.world.provider_files.truth import load_truth

ROW_DEFECTS = {
    "MISSING_FIELD", "PHONE_FORMAT", "AMOUNT_FORMAT", "NAME_TYPO", "NAME_SWAP",
    "WRONG_IDENTIFIER", "STALE_VALUE", "INCONSISTENT_STATUS", "DATE_FORMAT", "FUTURE_DATE",
}  # fmt: skip

# Every defect switched on at a high rate, so a small file exercises them all.
HEAVY = replace(
    POOR,
    name="HEAVY",
    missing_field=0.12, phone_format=0.12, amount_format=0.12, name_typo=0.12, name_swap=0.12,
    wrong_identifier=0.12, stale_values=0.12, inconsistent_status=0.12, date_format=0.12,
    future_date=0.12, duplicate_row=0.05, omit_account=0.05, template_drift=1.0, late_rate=1.0,
)  # fmt: skip


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    generated = build_world(41, "tiny")
    world_id = write_world(
        generated.config,
        generated.people,
        generated.businesses,
        generated.branches,
        generated.result,
        generated.stats,
    )
    return World.objects.get(pk=world_id)


def _lender(world: World) -> Lender:
    """The lender with the most individual and business accounts at the last month."""
    counts = Counter(
        LoanMonth.objects.filter(world=world, period=world.history_end).values_list(
            "lender_id", flat=True
        )
    )
    business = set(
        Loan.objects.filter(world=world, customer__business__isnull=False).values_list(
            "lender_id", flat=True
        )
    )
    best = max((n, lid) for lid, n in counts.items() if lid in business)[1]
    return Lender.objects.get(pk=best)


def read_file(stored: ProviderFile, root: Path) -> tuple[list[str], list[list[str]]]:
    """Read a provider file back from storage, as text."""
    path = root / stored.storage_path
    if stored.file_format == "CSV":
        with path.open(encoding="utf-8", newline="") as handle:
            lines = list(csv.reader(handle))
        return lines[0], lines[1:]
    workbook = load_workbook(io.BytesIO(path.read_bytes()), read_only=True)
    rows = [
        ["" if v is None else str(v) for v in row]
        for row in workbook["Data"].iter_rows(values_only=True)
    ]
    return rows[0], rows[1:]


# --- A clean profile reproduces the truth exactly --------------------------------


def test_clean_file_matches_the_truth_exactly(world: World, tmp_path: Path) -> None:
    lender = _lender(world)
    period = world.history_end
    result = generate_submission(world, lender, period, CLEAN)

    files = {f.kind: f for f in result.submission.files.all()}
    assert set(files) == {"IND", "COM"}
    assert not FileDefect.objects.filter(submission=result.submission).exists()
    assert not result.schedule.is_late

    reported = 0
    for kind_code, stored in files.items():
        kind = FileKind(kind_code)
        names, rows = read_file(stored, tmp_path)
        assert names == list(header(kind))
        assert stored.row_count == len(rows)
        row_map = dict(
            ProviderFileRow.objects.filter(file=stored).values_list("row_number", "loan_id")
        )
        for n, raw in enumerate(rows, start=1):
            values = dict(zip(names, raw, strict=True))
            _assert_matches_world(values, row_map[n], kind, period)
        reported += len(rows)

    # Every account with a true state this month is reported, once.
    assert reported == LoanMonth.objects.filter(lender=lender, period=period).count()


def _assert_matches_world(
    values: dict[str, str], loan_id: int, kind: FileKind, period: date
) -> None:
    """Independent check of one row against the world tables, via the ORM."""
    loan = Loan.objects.select_related("customer__person", "customer__business", "branch").get(
        pk=loan_id
    )
    month = LoanMonth.objects.get(loan=loan, period=period)
    assert values["REPORTING_DATE"] == format_date(period)
    assert values["ACCOUNT_NUMBER"] == loan.account_number
    assert values["CUSTOMER_NUMBER"] == loan.customer.customer_number
    assert values["BRANCH_CODE"] == loan.branch.code
    assert Decimal(values["ORIGINAL_AMOUNT"]) == loan.principal
    assert Decimal(values["INSTALMENT_AMOUNT"]) == loan.installment
    assert values["DISBURSEMENT_DATE"] == format_date(loan.disbursement_date)
    assert Decimal(values["CURRENT_BALANCE"]) == month.outstanding_balance
    assert Decimal(values["ARREARS_AMOUNT"]) == month.arrears_amount
    assert int(values["DAYS_PAST_DUE"]) == month.days_past_due
    assert Decimal(values["AMOUNT_PAID"]) == month.amount_paid
    assert values["ASSET_CLASSIFICATION"] == asset_classification(month.days_past_due)
    if kind is FileKind.INDIVIDUAL:
        person = loan.customer.person
        assert person is not None
        assert values["GHANA_CARD_NUMBER"] == person.ghana_card
        assert values["SURNAME"] == person.last_name
        assert values["FIRST_NAME"] == person.first_name
        assert values["DATE_OF_BIRTH"] == format_date(person.date_of_birth)
        assert values["MOBILE_NUMBER"] == person.phone_primary
    else:
        business = loan.customer.business
        assert business is not None
        assert values["REGISTERED_NAME"] == business.registered_name
        assert values["TIN"] == business.tin
        assert values["REGISTRATION_NUMBER"] == business.registration_number


# --- Every defect is in the ledger ----------------------------------------------


@pytest.mark.parametrize("file_format", ["CSV", "XLSX"])
def test_every_difference_from_the_truth_is_in_the_defect_ledger(
    world: World, tmp_path: Path, file_format: str
) -> None:
    lender = _lender(world)
    period = world.history_end
    profile = replace(HEAVY, file_format=file_format)
    result = generate_submission(world, lender, period, profile, drift_from=world.history_start)
    seen: Counter[str] = Counter()

    for stored in result.submission.files.all():
        kind = FileKind(stored.kind)
        truth = {
            r.loan_id: r.values for r in load_truth(world.pk, lender.pk, lender.code, period, kind)
        }
        ledger = list(FileDefect.objects.filter(file=stored))
        seen.update(d.defect_type for d in ledger)
        names, rows = read_file(stored, tmp_path)
        columns = _canonical_columns(names, kind, ledger)

        row_loans = dict(
            ProviderFileRow.objects.filter(file=stored).values_list("row_number", "loan_id")
        )
        assert len(row_loans) == len(rows)

        duplicates = {
            d.row_number: int(d.true_value.split()[-1])
            for d in ledger
            if d.defect_type == "DUPLICATE_ROW"
        }
        omitted = {d.loan_id for d in ledger if d.defect_type == "OMITTED_ACCOUNT"}
        recorded = {
            (d.row_number, d.field): (d.true_value, d.submitted_value)
            for d in ledger
            if d.defect_type in ROW_DEFECTS
        }
        assert len(recorded) == sum(d.defect_type in ROW_DEFECTS for d in ledger), (
            "one defect per cell"
        )

        found: dict[tuple[int, str], tuple[str, str]] = {}
        originals: list[int] = []
        for n, raw in enumerate(rows, start=1):
            if n in duplicates:
                # A repeated row is an exact copy of an earlier one.
                assert duplicates[n] < n
                assert raw == rows[duplicates[n] - 1]
                assert row_loans[n] == row_loans[duplicates[n]]
                continue
            originals.append(row_loans[n])
            values = dict(zip(columns, raw, strict=True))
            for name, true_value in truth[row_loans[n]].items():
                if values[name] != true_value:
                    found[(n, name)] = (true_value, values[name])

        assert found == recorded
        # Each account appears exactly once, apart from recorded duplicates and omissions.
        assert sorted(originals) == sorted(set(originals))
        assert set(originals) | omitted == set(truth)
        assert not set(originals) & omitted

    late = FileDefect.objects.filter(submission=result.submission, defect_type="LATE_SUBMISSION")
    assert late.count() == 1 and late[0].file_id is None
    assert ROW_DEFECTS | {"DUPLICATE_ROW", "OMITTED_ACCOUNT", "TEMPLATE_DRIFT"} <= set(seen)


def _canonical_columns(names: list[str], kind: FileKind, ledger: list[FileDefect]) -> list[str]:
    """Undo template drift using only the ledger, and check the ledger explains it all."""
    renamed = {
        d.submitted_value: d.field
        for d in ledger
        if d.defect_type == "TEMPLATE_DRIFT" and not d.true_value.startswith("column ")
    }
    moved = {
        d.field: (d.true_value, d.submitted_value)
        for d in ledger
        if d.defect_type == "TEMPLATE_DRIFT" and d.true_value.startswith("column ")
    }
    columns = [renamed.get(name, name) for name in names]
    expected = list(header(kind))
    assert sorted(columns) == sorted(expected)
    actual_moves = {
        c: (f"column {expected.index(c) + 1}", f"column {i + 1}")
        for i, c in enumerate(columns)
        if expected.index(c) != i
    }
    assert actual_moves == moved
    assert all(
        name not in expected or name in renamed or name == col
        for name, col in zip(names, columns, strict=True)
    )
    return columns


# --- Determinism, schedule and drift ------------------------------------------------


def test_same_world_and_month_give_identical_files_and_ledger(world: World) -> None:
    lender = _lender(world)

    def fingerprint() -> tuple[list[tuple[str, str]], list[tuple[Any, ...]]]:
        sub = ProviderSubmission.objects.get(lender=lender, period=world.history_end)
        files = sorted(sub.files.values_list("file_name", "sha256"))
        defects = sorted(
            FileDefect.objects.filter(submission=sub).values_list(
                "file__kind", "row_number", "loan_id", "defect_type", "field", "true_value",
                "submitted_value",
            ),
            key=repr,
        )  # fmt: skip
        return files, defects

    generate_submission(world, lender, world.history_end, HEAVY, drift_from=world.history_start)
    first = fingerprint()
    generate_submission(
        world, lender, world.history_end, HEAVY, replace=True, drift_from=world.history_start
    )
    assert fingerprint() == first


def test_existing_month_is_not_silently_overwritten(world: World) -> None:
    lender = _lender(world)
    generate_submission(world, lender, world.history_end, CLEAN)
    with pytest.raises(FileExistsError):
        generate_submission(world, lender, world.history_end, CLEAN)


def test_periods_outside_history_are_refused(world: World) -> None:
    lender = _lender(world)
    with pytest.raises(ValueError, match="outside"):
        generate_submission(world, lender, month_end(2030, 1), CLEAN)


def test_arrivals_follow_the_profile() -> None:
    periods = [month_end(2024 + i // 12, i % 12 + 1) for i in range(36)]
    for profile, expected_late in ((CLEAN, 0.0), (POOR, POOR.late_rate)):
        plans = [schedule(7, "XYZ", p, profile) for p in periods * 10]
        late = [s for s in plans if s.is_late]
        assert all(s.due_date.day == SUBMISSION_DUE_DAY for s in plans)
        assert all((s.arrival_date - s.due_date).days <= profile.late_days_max for s in late)
        assert abs(len(late) / len(plans) - expected_late) < 0.1
        on_time = [s for s in plans if not s.is_late]
        lo, hi = profile.arrival_days
        assert all(lo <= s.arrival_date.day <= hi for s in on_time)


def test_template_drift_persists_once_it_happens() -> None:
    start = month_end(2024, 1)
    profile: DataQualityProfile = replace(CLEAN, template_drift=0.08)
    layouts = [
        layout_for(
            3, "XYZ", FileKind.INDIVIDUAL, start, month_end(2024 + i // 12, i % 12 + 1), profile
        )
        for i in range(36)
    ]
    standard = Layout.standard(FileKind.INDIVIDUAL)
    changed = [i for i, layout in enumerate(layouts) if layout != standard]
    assert changed, "expected at least one change over 36 months at this hazard"
    first = changed[0]
    assert changed == list(range(first, 36))
    assert len(set(layouts[first:])) == 1


def test_no_template_drift_before_play_starts(world: World, tmp_path: Path) -> None:
    """Layouts were agreed long ago; drift is something that happens during play."""
    lender = _lender(world)
    always = replace(CLEAN, template_drift=1.0)
    result = generate_submission(world, lender, world.history_end, always)
    for stored in result.submission.files.all():
        names, _ = read_file(stored, tmp_path)
        assert names == list(header(FileKind(stored.kind)))
    assert not FileDefect.objects.filter(defect_type="TEMPLATE_DRIFT").exists()
    start = play_start(world)
    assert start > world.history_end
    kind = FileKind.INDIVIDUAL
    assert layout_for(1, "XYZ", kind, start, world.history_end, always) == Layout.standard(kind)
    assert layout_for(1, "XYZ", kind, start, start, always) != Layout.standard(kind)


# --- Template and code lists ----------------------------------------------------


def test_code_lists_cover_every_value_the_world_produces() -> None:
    assert set(REGIONS) <= set(CODE_LISTS["REGION"])
    assert set(SECTORS) <= set(CODE_LISTS["SECTOR"])
    assert {e.code for e in EMPLOYMENT_TYPES} <= set(CODE_LISTS["EMPLOYMENT_TYPE"])
    for fields in FIELDS.values():
        for f in fields:
            assert f.code_list is None or f.code_list in CODE_LISTS


@pytest.mark.parametrize(
    ("dpd", "expected"),
    [(0, "CUR"), (29, "CUR"), (30, "OLEM"), (89, "OLEM"), (90, "SUB"), (179, "SUB"),
     (180, "DBT"), (359, "DBT"), (360, "LOSS")],
)  # fmt: skip
def test_asset_classification_bands(dpd: int, expected: str) -> None:
    assert asset_classification(dpd) == expected


# --- Deleting a world removes its submissions and files --------------------------


def test_deleting_a_world_removes_submissions_and_files(
    world: World, django_capture_on_commit_callbacks: Callable[..., Any]
) -> None:
    lender = _lender(world)
    generate_submission(world, lender, world.history_end, CLEAN)
    directory = submission_dir(world.pk, lender.code, world.history_end)
    assert any(directory.iterdir())

    with django_capture_on_commit_callbacks(execute=True):
        delete_world(world.pk)

    assert not ProviderSubmission.objects.filter(world_id=world.pk).exists()
    assert not FileDefect.objects.exists()
    assert not directory.exists()


def test_xlsx_carries_no_save_time() -> None:
    """openpyxl stamps the current time into XLSX files; it must be replaced."""
    import zipfile

    from apps.world.provider_files.files import to_bytes
    from apps.world.provider_files.render import RenderedFile

    kind = FileKind.INDIVIDUAL
    rendered = RenderedFile(kind, Layout.standard(kind), [["x"] * len(header(kind))], [1], [], ())
    data = to_bytes(rendered, "XLSX", month_end(2026, 12))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        core = archive.read("docProps/core.xml").decode()
        assert all(info.date_time == (2026, 12, 31, 0, 0, 0) for info in archive.infolist())
    assert core.count("2026-12-31T00:00:00Z") == 2
