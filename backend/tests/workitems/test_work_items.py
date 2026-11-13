"""S5 — Work items and employees.

Done when (roadmap S5): a highly skilled employee is measurably more accurate
than a junior one over a large sample; wrong decisions really produce false
merges or wrongly rejected records in the bureau view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import AccountObservation
from apps.bureau.quality.models import CaseStatus, CaseType, Decision
from apps.bureau.quality.rules import Issue, propose_corrections
from apps.bureau.referencing.similarity import AUTO_LINK, compare_individuals, jaro_winkler
from apps.bureau.submissions.models import RecordStatus, StagingRecord
from apps.bureau.submissions.pipeline import process_submission
from apps.org.models import Employee
from apps.simulation import controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.fingerprint import fingerprint
from apps.simulation.judgement import customer_borrower, record_borrower, sync_work_items
from apps.simulation.models import Game
from apps.workitems.models import ItemStatus, ResolvedBy, WorkItem
from apps.workitems.resolution import judge, p_correct
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Lender, World
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import POOR

# Lots of the defects that need judgement, nothing that rejects whole files.
TRICKY = replace(
    POOR,
    name="TRICKY",
    wrong_identifier=0.12, name_typo=0.10, date_format=0.12, amount_format=0.08,
    inconsistent_status=0.10, missing_field=0.02, duplicate_row=0.0, omit_account=0.0,
    template_drift=0.0, late_rate=0.0,
)  # fmt: skip


WHEN = datetime(2027, 1, 4, 17, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _queue(world: World, owner: Any = None) -> Game:
    """A game whose first month of two providers' tricky files has been processed."""
    game = start_game(world, owner=owner)
    for code in ("ATB", "MRB"):
        lender = Lender.objects.get(world=world, code=code)
        world_sub = generate_submission(world, lender, world.history_end, TRICKY).submission
        process_submission(deliver(game, world_sub), at=WHEN)
    sync_work_items(game, 0)
    return game


def _true_borrowers_by_customer(game: Game) -> dict[int, set[tuple[str, int]]]:
    out: dict[int, set[tuple[str, int]]] = defaultdict(set)
    for obs in AccountObservation.objects.filter(
        credit_account__organization=game.organization
    ).select_related("credit_account"):
        out[obs.credit_account.customer_id].add(
            record_borrower(game, obs.source_file_id, obs.source_row_number)
        )
    return out


# --- Skill sets accuracy ----------------------------------------------------------------


def test_skilled_employees_are_measurably_more_accurate() -> None:
    rng = np.random.default_rng(5)
    difficulties = rng.uniform(0.1, 0.9, 3000)

    def accuracy(skill: float) -> float:
        hits = [
            judge(
                CaseType.MATCH_REVIEW, Decision.SAME_CUSTOMER, float(d), skill, 0.7, 0.0, rng
            ).correct
            for d in difficulties
        ]
        return float(np.mean(hits))

    senior, junior = accuracy(0.88), accuracy(0.55)
    assert senior - junior > 0.1
    expected = np.mean([p_correct(0.88, d) for d in difficulties])
    assert abs(senior - expected) < 0.03  # the draws follow the model


def test_harder_items_and_fatigue_lower_accuracy() -> None:
    assert p_correct(0.7, 0.2) > p_correct(0.7, 0.8)
    assert p_correct(0.7, 0.5, fatigue=0.0) > p_correct(0.7, 0.5, fatigue=1.0)
    assert p_correct(0.7, 0.5, morale=0.9) > p_correct(0.7, 0.5, morale=0.4)


# --- The queue ----------------------------------------------------------------------------


def test_pipeline_opens_cases_and_the_simulation_supplies_answers(world: World) -> None:
    game = _queue(world)
    items = WorkItem.objects.filter(organization=game.organization)
    types = set(items.values_list("item_type", flat=True))
    assert types == {CaseType.MATCH_REVIEW, CaseType.UNLOADABLE_TRIAGE}
    answers = set(items.values_list("correct_decision", flat=True))
    assert {Decision.DIFFERENT_CUSTOMER, Decision.CORRECT_AND_LOAD} <= answers
    # Held records are not loaded until someone decides.
    for item in items.filter(item_type=CaseType.MATCH_REVIEW):
        assert item.case.record.record_status == RecordStatus.PENDING_REVIEW
    # The answer agrees with the truth behind the record and the candidate.
    for item in items.filter(item_type=CaseType.MATCH_REVIEW):
        record = item.case.record
        candidate = item.case.candidate_customer_id
        assert candidate is not None
        same = record_borrower(game, record.file_id, record.source_row_number) == customer_borrower(
            game, candidate
        )
        assert item.correct_decision == (
            Decision.SAME_CUSTOMER if same else Decision.DIFFERENT_CUSTOMER
        )


# --- Decisions have real consequences -------------------------------------------------------


def test_right_decisions_keep_the_bureau_faithful(world: World) -> None:
    game = _queue(world)
    while (
        item := WorkItem.objects.filter(organization=game.organization, status=ItemStatus.OPEN)
        .order_by("item_number")
        .first()
    ):
        controls.resolve_item(game, item.item_number, item.correct_decision)
    assert all(len(b) == 1 for b in _true_borrowers_by_customer(game).values())
    assert not StagingRecord.objects.filter(
        run__submission__organization=game.organization, record_status=RecordStatus.PENDING_REVIEW
    ).exists()


def test_wrong_decisions_merge_people_and_lose_records(world: World) -> None:
    game = _queue(world)
    merged = returned = 0
    while (
        item := WorkItem.objects.filter(organization=game.organization, status=ItemStatus.OPEN)
        .order_by("item_number")
        .first()
    ):
        if item.correct_decision == Decision.DIFFERENT_CUSTOMER:
            controls.resolve_item(game, item.item_number, Decision.SAME_CUSTOMER)
            merged += 1
        elif item.correct_decision == Decision.CORRECT_AND_LOAD:
            controls.resolve_item(game, item.item_number, Decision.RETURN_TO_PROVIDER)
            assert not AccountObservation.objects.filter(
                source_file=item.case.record.file,
                source_row_number=item.case.record.source_row_number,
            ).exists()
            returned += 1
        else:
            controls.resolve_item(game, item.item_number, item.correct_decision)
    assert merged and returned
    # A wrong "same customer" really puts two people's credit histories under one customer.
    false_merges = [c for c, b in _true_borrowers_by_customer(game).items() if len(b) > 1]
    assert len(false_merges) >= 1


def test_employees_work_the_queue_and_explain_every_decision(world: World) -> None:
    game = _queue(world)
    controls.advance_by(game, "day")
    done = WorkItem.objects.filter(organization=game.organization, status=ItemStatus.DONE)
    assert done.exists()
    for item in done:
        assert item.resolved_by == ResolvedBy.EMPLOYEE
        assert item.assignee is not None
        assert item.explanation.startswith(("Identifier", "Errors"))
        assert "Decided:" in item.explanation
        assert item.confidence is not None
        assert item.case.status == CaseStatus.RESOLVED
        assert item.is_correct == (item.decision == item.correct_decision)
    worked = Employee.objects.filter(organization=game.organization, done_today__gt=0)
    assert worked.exists()
    assert all(sum(e.experience.values()) > 0 for e in worked)


def test_replay_with_player_decisions_is_exact(world: World) -> None:
    original = _queue(world)
    first = WorkItem.objects.filter(organization=original.organization).order_by("item_number")[0]
    controls.resolve_item(original, first.item_number, Decision.RETURN_TO_PROVIDER)
    original = controls.advance_by(original, "hour", 2)

    copy = start_game(world)
    # Same starting point: the copy receives and processes the same files.
    for code in ("ATB", "MRB"):
        lender = Lender.objects.get(world=world, code=code)
        from apps.world.models import ProviderSubmission

        process_submission(
            deliver(copy, ProviderSubmission.objects.get(lender=lender, period=world.history_end)),
            at=WHEN,
        )
    sync_work_items(copy, 0)
    copy = controls.replay(original, copy)
    assert fingerprint(copy) == fingerprint(original)


# --- API ---------------------------------------------------------------------------------


def test_work_item_api_never_reveals_the_answer(world: World) -> None:
    owner = User.objects.create_user("data-ops-head")
    game = _queue(world, owner=owner)
    client = APIClient()
    client.force_authenticate(owner)

    listing = client.get(f"/api/v1/games/{game.pk}/work-items/?status=OPEN").json()
    assert listing
    number = listing[0]["number"]
    detail = client.get(f"/api/v1/games/{game.pk}/work-items/{number}/").json()
    body = str(listing) + str(detail)
    assert "correct" not in body
    assert detail["allowed_decisions"]

    bad = client.post(
        f"/api/v1/games/{game.pk}/work-items/{number}/resolve/",
        {"decision": "SHRUG"},
        format="json",
    )
    assert bad.status_code == 400
    decision = detail["allowed_decisions"][-1]
    done = client.post(
        f"/api/v1/games/{game.pk}/work-items/{number}/resolve/",
        {"decision": decision},
        format="json",
    ).json()
    assert (done["status"], done["resolved_by"]) == ("DONE", "PLAYER")
    staff = client.get(f"/api/v1/games/{game.pk}/employees/").json()
    assert [s["job_title"] for s in staff] == [
        "Senior Data Officer", "Data Officer", "Junior Data Officer",
    ]  # fmt: skip


# --- Matching and correction rules -------------------------------------------------------


def test_jaro_winkler_reference_values() -> None:
    assert abs(jaro_winkler("MARTHA", "MARHTA") - 0.961) < 0.001
    assert abs(jaro_winkler("DWAYNE", "DUANE") - 0.84) < 0.001
    assert jaro_winkler("KWAME", "KWAME") == 1.0


def test_identity_comparison() -> None:
    born = date(1990, 3, 12)
    typo = compare_individuals(("Kwame", "Mensa", born), ("Kwame", "Mensah", born))
    swapped = compare_individuals(("Mensah", "Kwame", born), ("Kwame", "Mensah", born))
    month_first = compare_individuals(
        ("Kwame", "Mensah", date(1990, 12, 3)), ("Kwame", "Mensah", born)
    )
    stranger = compare_individuals(("Ama", "Owusu", date(1995, 7, 1)), ("Kwame", "Mensah", born))
    assert typo.score >= AUTO_LINK and swapped.score >= AUTO_LINK
    assert stranger.score < 0.5 < month_first.score < AUTO_LINK  # needs a human


def test_corrections_are_proposed_only_when_every_error_is_fixable() -> None:
    period = date(2026, 12, 31)
    values = {
        "DATE_OF_BIRTH": "12/31/1990",
        "ORIGINAL_AMOUNT": "GHS 1,250.5",
        "ACCOUNT_STATUS": "PD",
    }
    issues = [
        Issue("F002", "DATE_OF_BIRTH", "12/31/1990"),
        Issue("F004", "ORIGINAL_AMOUNT", "GHS 1,250.5"),
        Issue("F011", "ACCOUNT_STATUS", "PD"),
    ]
    assert propose_corrections(values, issues, period) == {
        "DATE_OF_BIRTH": "31/12/1990", "ORIGINAL_AMOUNT": "1250.50", "ACCOUNT_STATUS": "AC",
    }  # fmt: skip
    assert propose_corrections(values, [*issues, Issue("F001", "GHANA_CARD_NUMBER")], period) == {}
