"""P3.3 — Mobile loans in the world.

Done when (Document 09): the world produces mobile loans whose amounts, terms,
repeat borrowing and default rates are recorded (A-073) and checked by tests;
they flow through the pipeline into the bureau with lineage, and the month's
replay still matches; a default month still computes inside the P3.0 target.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from django.db import transaction

from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.bureau.quality.rules import validate
from apps.bureau.submissions.models import StagingRecord
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.standards.submission_template import FILE_NAME_PATTERN, FileKind
from apps.world.generation import build_world
from apps.world.generation.advance import extend_world
from apps.world.generation.mobile import (
    MAX_CEDIS,
    MIN_CEDIS,
    TERMS,
    month_end_state,
)
from apps.world.generation.persist import loan_month_partition, write_world
from apps.world.models import Lender, Loan, LoanMonth, ProviderFileRow, World
from apps.world.provider_files import generate_submission

WHEN = datetime(2027, 1, 4, 17, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def test_mobile_loans_are_small_short_repeated_and_stacked() -> None:
    g = build_world(81, "small")
    m = g.result.mobile
    assert m is not None and m.n > 1000
    cedis = m.principal // 100
    assert cedis.min() >= MIN_CEDIS and cedis.max() <= MAX_CEDIS
    assert set(np.unique(m.term_days).tolist()) == set(TERMS.tolist())
    assert (m.due - m.disbursed).astype(int).tolist() == m.term_days.tolist()
    assert (m.fee > 0).all()

    # Repeat borrowing: many users borrow in many months.
    months_per_person = defaultdict(set)
    lenders_in_month = defaultdict(set)
    for person, month, lender in zip(
        m.person.tolist(), m.month.tolist(), m.lender.tolist(), strict=True
    ):
        months_per_person[person].add(month)
        lenders_in_month[(person, month)].add(lender)
    assert np.median([len(v) for v in months_per_person.values()]) >= 6
    # Stacking: some borrowers hold loans from more than one lender in the same month.
    stacked = sum(len(v) > 1 for v in lenders_in_month.values()) / len(lenders_in_month)
    assert 0.02 < stacked < 0.4

    # Defaults: a few percent overall, and more among the riskier borrowers.
    defaulted = ~np.isnat(m.written_off)
    assert 0.03 < defaulted.mean() < 0.12
    risk = g.people.risk_z[m.person]
    assert (
        defaulted[risk > np.quantile(risk, 0.75)].mean()
        > 2 * defaulted[risk < np.quantile(risk, 0.25)].mean()
    )


def test_a_world_without_mobile_loans_is_the_world_it_always_was() -> None:
    plain = build_world(61, "tiny", mobile_loans=False)
    mobile = build_world(61, "tiny")
    assert plain.result.mobile is None and mobile.result.mobile is not None
    for name in plain.result.book.SCHEMA:
        assert np.array_equal(plain.result.book[name], mobile.result.book[name]), name


def test_one_more_month_leaves_mobile_history_unchanged() -> None:
    before = build_world(61, "tiny")
    after = build_world(61, "tiny", extra_months=1)
    b, a = before.result.mobile, after.result.mobile
    assert a.n > b.n
    for name in (
        "lender",
        "person",
        "customer_seq",
        "account_seq",
        "principal",
        "fee",
        "disbursed",
        "due",
        "term_days",
    ):
        assert np.array_equal(getattr(a, name)[: b.n], getattr(b, name)), name
    last = len(before.result.months) - 1
    for t in (last - 1, last):
        x = month_end_state(b, before.result.months, t)
        y = month_end_state(a, after.result.months, t)
        # Loans that end after the last month are open in both, with the same balances.
        assert np.array_equal(x.loan, y.loan) and np.array_equal(x.outstanding, y.outstanding)


@pytest.mark.django_db(transaction=True)
def test_mobile_loans_are_stored_advanced_and_sent_in_their_own_files() -> None:
    g = build_world(61, "tiny")
    with transaction.atomic():
        world = World.objects.get(
            pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
        )
    assert world.config["mobile_loans"] is True
    mobile = Loan.objects.filter(world=world, product="MOBILE_LOAN")
    assert mobile.exists() and set(mobile.values_list("facility_type", flat=True)) == {"122"}
    assert all("M" in a for a in mobile.values_list("account_number", flat=True))
    history = list(
        LoanMonth.objects.filter(world=world, loan__product="MOBILE_LOAN")
        .order_by("loan_id", "period")
        .values_list("loan_id", "period", "outstanding_balance", "days_past_due", "status")
    )

    # A month of play: the world lives through it; the past is unchanged.
    period = extend_world(world.pk)
    world.refresh_from_db()
    after = list(
        LoanMonth.objects.filter(world=world, loan__product="MOBILE_LOAN", period__lt=period)
        .order_by("loan_id", "period")
        .values_list("loan_id", "period", "outstanding_balance", "days_past_due", "status")
    )
    assert after == history
    new_rows = LoanMonth.objects.filter(world=world, loan__product="MOBILE_LOAN", period=period)
    assert new_rows.exists()
    repaid = Loan.objects.filter(
        world=world, product="MOBILE_LOAN", status="PAID_OFF", terminal_period=period
    )
    assert repaid.exists() and not repaid.filter(repaid_date__isnull=True).exists()
    assert loan_month_partition(world.pk) == f"world_loanmonth_w{world.pk}"

    # SwiftCash's month: one ordinary consumer file and one mobile file.
    lender = Lender.objects.get(world=world, code="SWC")
    sub = generate_submission(world, lender, period).submission
    files = {f.kind: f for f in sub.files.all()}
    assert {FileKind.INDIVIDUAL.value, FileKind.MOBILE.value} <= set(files)
    parsed = FILE_NAME_PATTERN.fullmatch(files["CONCMOBILE"].file_name)
    assert parsed and parsed["kind"] == "CONCMOBILE"
    on_file = {
        kind: set(ProviderFileRow.objects.filter(file=f).values_list("loan__product", flat=True))
        for kind, f in files.items()
        if kind in ("CONC", "CONCMOBILE")
    }
    assert on_file["CONCMOBILE"] == {"MOBILE_LOAN"}
    assert "MOBILE_LOAN" not in on_file["CONC"]


@pytest.mark.django_db
def test_the_bureau_loads_mobile_files_with_lineage() -> None:
    g = build_world(61, "tiny")
    world = World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )
    game = start_game(world)
    lender = Lender.objects.get(world=world, code="SWC")
    sub = generate_submission(world, lender, world.history_end).submission
    run = process_submission(deliver(game, sub), at=WHEN)
    files = {f.file_kind: f for f in run.submission.files.all()}
    assert "CONCMOBILE" in files
    staged = StagingRecord.objects.filter(run=run, file=files["CONCMOBILE"])
    assert staged.exists()
    loaded = CreditAccount.objects.filter(
        organization=game.organization, facility_account_number__contains="M"
    )
    assert loaded.exists()
    # Every loaded mobile account's month traces back to its row in the mobile file.
    observations = AccountObservation.objects.filter(credit_account__in=loaded)
    assert observations.count() >= loaded.count()
    assert set(observations.values_list("source_file__file_kind", flat=True)) == {"CONCMOBILE"}
    assert not observations.filter(source_row_number__lt=1).exists()


def test_a_long_facility_in_a_mobile_file_is_flagged_not_rejected() -> None:
    values = {"DisbursementDate": "20261001", "MaturityDate": "20270215"}  # four and a half months
    flagged = validate(FileKind.MOBILE, values, date(2026, 12, 31))
    f016 = [i for i in flagged.issues if i.rule_code == "F016"]
    assert len(f016) == 1 and f016[0].severity == "WARNING"
    assert not [
        i
        for i in validate(FileKind.INDIVIDUAL, values, date(2026, 12, 31)).issues
        if i.rule_code == "F016"
    ]
    short = {"DisbursementDate": "20261001", "MaturityDate": "20261231"}
    assert not [
        i
        for i in validate(FileKind.MOBILE, short, date(2026, 12, 31)).issues
        if i.rule_code == "F016"
    ]
