"""P2.0c — Dishonoured cheques and court judgments.

Done when (Document 08, P2.0): the world produces bounced cheques and court
judgments; providers report them on their own templates (COND, CONJ); the
bureau loads them and shows them on credit reports.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from apps.bureau.core.models import CourtJudgment as BureauJudgment
from apps.bureau.core.models import CreditAccount, CustomerIdentifier, IdentifierType
from apps.bureau.core.models import DishonouredCheque as BureauCheque
from apps.bureau.quality.models import ValidationIssue
from apps.bureau.quality.rules import validate
from apps.bureau.reports.enquiries import build_report
from apps.bureau.submissions.models import RecordStatus, StagingRecord, Submission
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.standards.submission_template import FileKind, header
from apps.world.generation import build_world
from apps.world.generation.events import MIN_CLAIM, ensure_events
from apps.world.generation.persist import write_world
from apps.world.models import (
    CourtJudgment,
    DishonouredCheque,
    EventMonth,
    Lender,
    LoanMonth,
    World,
)
from apps.world.provider_files import generate_submission, month_end
from apps.world.provider_files.profiles import CLEAN

# These tests need a small world (a tiny one has too few events). They commit and are
# cleaned up by truncation: rolling back a world this size leaves the world tables full
# of dead rows, which slows every test that runs after it.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _build(seed: int = 61) -> World:
    g = build_world(seed, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


@pytest.fixture
def world() -> World:
    return _build()


def _months(world: World) -> list[date]:
    out, period = [], world.history_end
    while period >= world.history_start:
        out.append(period)
        period = month_end(period.year - (period.month == 1), (period.month - 2) % 12 + 1)
    return out[::-1]


def _snapshot(world: World) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    cheques = sorted(
        DishonouredCheque.objects.filter(world=world).values_list(
            "lender__code", "loan__seq_no", "period", "account_number", "cheque_number",
            "date_issued", "date_bounced", "reason", "amount",
        )
    )  # fmt: skip
    judgments = sorted(
        CourtJudgment.objects.filter(world=world).values_list(
            "lender__code", "loan__seq_no", "period", "case_number", "court_name", "filing_date",
            "case_type", "amount",
        )
    )  # fmt: skip
    return cheques, judgments


# --- The world ------------------------------------------------------------------------


def test_events_are_deterministic_whatever_the_order_months_are_asked_for(world: World) -> None:
    months = _months(world)[-12:]
    for period in months:
        ensure_events(world, period)
        ensure_events(world, period)  # idempotent
    first = _snapshot(world)
    assert first[0] and first[1], "expected cheques and judgments over a year"

    for model in (DishonouredCheque, CourtJudgment, EventMonth):
        model.objects.filter(world=world).delete()
    for period in reversed(months):
        ensure_events(world, period)
    assert _snapshot(world) == first

    # Another world built from the same seed has the same events (no database ids leak in).
    twin = _build()
    for period in months:
        ensure_events(twin, period)
    assert _snapshot(twin) == first


def test_events_agree_with_the_credit_history(world: World) -> None:
    months = _months(world)[-12:]
    for period in months:
        ensure_events(world, period)
    for cheque in DishonouredCheque.objects.filter(world=world).select_related(
        "lender", "loan__customer"
    ):
        assert cheque.lender.lender_type in ("COMMERCIAL_BANK", "SAVINGS_AND_LOANS")
        assert cheque.loan.customer.person_id is not None
        assert cheque.date_issued <= cheque.date_bounced
        assert (cheque.date_bounced.year, cheque.date_bounced.month) == (
            cheque.period.year,
            cheque.period.month,
        )
        assert cheque.reason in ("11", "12")
    # A lender sues over a written-off loan once, not again every month it could.
    sued = list(CourtJudgment.objects.filter(world=world).values_list("loan_id", flat=True))
    assert sued and len(sued) == len(set(sued))
    # Every judgment follows a write-off of the same loan, 2 to 8 months earlier.
    for case in CourtJudgment.objects.filter(world=world).select_related("loan__customer"):
        assert case.loan.customer.person_id is not None
        written_off = LoanMonth.objects.get(loan_id=case.loan_id, status="WRITTEN_OFF")
        lag = (case.period.year * 12 + case.period.month) - (
            written_off.period.year * 12 + written_off.period.month
        )
        assert 2 <= lag <= 8
        assert written_off.outstanding_balance >= MIN_CLAIM
        assert case.amount >= written_off.outstanding_balance
    # Borrowers in arrears bounce cheques far more often than those who are current.
    bounced = set(DishonouredCheque.objects.filter(world=world).values_list("loan_id", "period"))
    banks = Lender.objects.filter(
        world=world, lender_type__in=("COMMERCIAL_BANK", "SAVINGS_AND_LOANS")
    )
    rates = {}
    for label, lookup in (("current", {"days_past_due": 0}), ("arrears", {"days_past_due__gt": 0})):
        months_ = LoanMonth.objects.filter(
            world=world, period__in=months, status="ACTIVE", lender__in=banks,
            loan__customer__person__isnull=False, **lookup,
        ).values_list("loan_id", "period")  # fmt: skip
        pairs = list(months_)
        rates[label] = sum(p in bounced for p in pairs) / len(pairs)
    assert rates["arrears"] > 5 * rates["current"]


# --- The bureau -------------------------------------------------------------------------


def _busiest(world: World) -> tuple[Lender, date]:
    """A lender and month with both bounced cheques and judgments."""
    for period in reversed(_months(world)):
        ensure_events(world, period)
        for lender in Lender.objects.filter(world=world).order_by("code"):
            if (
                DishonouredCheque.objects.filter(lender=lender, period=period).exists()
                and CourtJudgment.objects.filter(lender=lender, period=period).exists()
            ):
                return lender, period
    raise AssertionError("no month with both kinds of event")


def test_events_are_reported_loaded_and_shown_on_the_report(world: World) -> None:
    lender, period = _busiest(world)
    game = start_game(world)
    sub = generate_submission(world, lender, period, CLEAN, replace=True).submission
    kinds = set(sub.files.values_list("kind", flat=True))
    assert {"COND", "CONJ"} <= kinds
    run = process_submission(deliver(game, sub))
    assert run.records_accepted == run.records_received
    assert run.reconciles

    truth_cheques = DishonouredCheque.objects.filter(lender=lender, period=period)
    truth_cases = CourtJudgment.objects.filter(lender=lender, period=period)
    cheques = BureauCheque.objects.filter(organization=game.organization)
    cases = BureauJudgment.objects.filter(organization=game.organization)
    assert cheques.count() == truth_cheques.count()
    assert cases.count() == truth_cases.count()

    # Each event is on the bureau customer of the real person, the same customer who
    # holds that person's credit accounts at the lender.
    for truth in truth_cheques.select_related("loan__customer__person"):
        loaded = cheques.get(account_number=truth.account_number, cheque_number=truth.cheque_number)
        assert loaded.amount == Decimal(truth.amount)
        assert (loaded.date_issued, loaded.date_bounced) == (truth.date_issued, truth.date_bounced)
        person = truth.loan.customer.person
        assert person is not None
        card = person.ghana_card
        assert CustomerIdentifier.objects.get(
            organization=game.organization, identifier_type=IdentifierType.GHANA_CARD,
            identifier_value=card,
        ).customer_id == loaded.customer_id  # fmt: skip
        account = CreditAccount.objects.filter(
            organization=game.organization, facility_account_number=truth.loan.account_number
        ).first()
        if account is not None:
            assert account.customer_id == loaded.customer_id
    for case in truth_cases:
        judgment = cases.get(case_number=case.case_number)
        assert (judgment.court_name, judgment.filing_date) == (case.court_name, case.filing_date)
        assert judgment.amount == Decimal(case.amount)

    # The credit report shows them.
    subject = cases.first()
    assert subject is not None
    report = build_report(subject.customer, datetime(2100, 1, 1, tzinfo=UTC))
    assert report["layout"] == "SIMB-R1"
    assert report["summary"]["judgments"] >= 1
    assert subject.case_number in {j["case_number"] for j in report["judgments"]}

    # Processing the same files again loads nothing twice.
    again = process_submission(Submission.objects.get(pk=run.submission_id))
    assert cheques.count() == truth_cheques.count() and cases.count() == truth_cases.count()
    events = StagingRecord.objects.filter(run=again, file__file_kind__in=("COND", "CONJ"))
    assert events.exists()
    assert all(r.record_status == RecordStatus.UNLOADABLE for r in events)
    assert (
        ValidationIssue.objects.filter(run=again, rule_code="L001", record__in=events).count()
        == events.count()
    )


# --- Rules -------------------------------------------------------------------------------


def _cheque(**changes: str) -> dict[str, str]:
    values = dict.fromkeys(header(FileKind.CHEQUE), "")
    values |= {
        "Data": "D", "CorrectionIndicator": "0", "FacilityAccNum": "01101000000251",
        "CustomerID": "AT1", "Gender": "F", "MaritalStatus": "S", "Nationality": "GHA",
        "DOB": "19900315", "Surname": "Mensah", "FirstName": "Ama", "CurResAddr1": "H/No. 4",
        "OwnerOrTenant": "T", "PostAddrLine1": "P.O. Box 4", "MobileTel1": "0244123456",
        "EmpType": "104", "Occupation": "Trader", "IncomeCurrency": "GHS", "Income": "2500",
        "JointOrSoleAcc": "S", "NoParticipantsInAcc": "1", "ChequeNumber": "243138",
        "DateIssued": "20251201", "DateBounced": "20251205", "ReasonReturned": "11",
        "Currency": "GHS", "ChequeAmount": "800", "VotersIDNum": "1234567890",
    }  # fmt: skip
    return values | changes


def _errors(values: dict[str, str]) -> set[tuple[str, str]]:
    checked = validate(FileKind.CHEQUE, values, month_end(2025, 12))
    return {(i.rule_code, i.field) for i in checked.issues if i.severity == "ERROR"}


def test_cheque_rules() -> None:
    assert _errors(_cheque()) == set()
    assert ("F015", "DateBounced") in _errors(_cheque(DateIssued="20251210"))
    assert ("F006", "ReasonReturned") in _errors(_cheque(ReasonReturned="13"))
    assert ("F003", "DateBounced") in _errors(_cheque(DateBounced="20260105"))
    # The ID rule goes by the date the cheque bounced.
    assert ("F013", "NatIDNum") in _errors(_cheque(VotersIDNum=""))
    old = _cheque(VotersIDNum="", DateIssued="20191201", DateBounced="20191205")
    assert ("F013", "NatIDNum") not in _errors(old)
