"""P2.5 — Data Operations depth II: templates, rules and feedback.

Done when (Document 08): a drifted file can be mapped and loaded by the player;
a player-written cleansing rule changes the next run's results, measured
against the truth.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.quality.models import TransformationLog
from apps.bureau.submissions.mapping import suggest
from apps.bureau.submissions.models import (
    FeedbackReport,
    FileStatus,
    RecordStatus,
    StagingRecord,
    Submission,
    TemplateMapping,
)
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation import controls
from apps.simulation.bridge import deliver, start_game
from apps.simulation.engine import ClockError, advance
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import DataQualityReview, EventType, Game, ScheduledEvent
from apps.standards.submission_template import FileKind
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import FileDefect, Lender, ProviderFile, World
from apps.world.provider_files import generate_submission, layout_for, month_end
from apps.world.provider_files.profiles import AVERAGE

# A provider that changed its extract (every file drifts) but is otherwise tidy.
DRIFTED = replace(AVERAGE, name="DRIFTED", template_drift=1.0, late_rate=0.0)
# A provider whose system writes Gender as a word ("Male") in a fifth of rows.
WORDY = replace(AVERAGE, name="WORDY", code_words=0.2, template_drift=0.0, late_rate=0.0)
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


def _previous(period: date) -> date:
    return month_end(period.year - (period.month == 1), (period.month - 2) % 12 + 1)


def _game(world: World, owner: Any = None) -> Game:
    """A game past its first tick, with the month's file arrivals taken out of its hands."""
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    game = advance(game, 1)
    ScheduledEvent.objects.filter(game=game, event_type=EventType.PROVIDER_FILES_ARRIVE).delete()
    return game


# --- Template mapping ----------------------------------------------------------------------------


def test_a_drifted_file_is_mapped_by_the_player_and_loaded(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _game(world, owner)
    lender = Lender.objects.get(world=world, code="ATB")
    earlier, period = _previous(world.history_end), world.history_end
    drift_from = world.history_start
    first = generate_submission(
        world, lender, earlier, DRIFTED, replace=True, drift_from=drift_from
    )
    run = process_submission(deliver(game, first.submission), at=WHEN)
    credit = run.submission.files.get(file_kind=FileKind.INDIVIDUAL.value)
    assert (credit.file_status, credit.rejection_reason) == (FileStatus.REJECTED, "T001")

    # The bureau offers a mapping; most of it is right, and what it is unsure of it leaves blank.
    client = APIClient()
    client.force_authenticate(owner)
    detail = client.get(
        f"/api/v1/games/{game.pk}/submissions/{run.submission.submission_reference}/"
    ).json()
    offer = next(f for f in detail["files"] if f["name"] == credit.file_name)["mapping"]
    truth = layout_for(world.seed, "ATB", FileKind.INDIVIDUAL, drift_from, earlier, DRIFTED)
    assert offer["received"] == list(truth.names)
    suggested = offer["suggested"]
    assert sum(s == t for s, t in zip(suggested, truth.columns, strict=True)) >= 0.9 * len(
        truth.columns
    )
    assert all(s in ("", t) for s, t in zip(suggested, truth.columns, strict=True))

    # A mapping that leaves a column out is refused, with the reason.
    bad = client.post(
        f"/api/v1/games/{game.pk}/submissions/{run.submission.submission_reference}/files/"
        f"{credit.file_name}/mapping/",
        {"columns": [*suggested[:-1], ""]},
        format="json",
    )
    assert bad.status_code == 400 and "missing" in bad.json()["detail"]

    # The player completes it; the file loads, every row of it.
    ok = client.post(
        f"/api/v1/games/{game.pk}/submissions/{run.submission.submission_reference}/files/"
        f"{credit.file_name}/mapping/",
        {"columns": list(truth.columns)},
        format="json",
    )
    assert ok.status_code == 200
    credit.refresh_from_db()
    assert credit.file_status == FileStatus.ACCEPTED and credit.mapping is not None
    world_file = ProviderFile.objects.get(
        submission=first.submission, kind=FileKind.INDIVIDUAL.value
    )
    staged = StagingRecord.objects.filter(file=credit)
    assert staged.count() == world_file.row_count
    assert staged.filter(record_status=RecordStatus.ACCEPTED).count() > 0.8 * world_file.row_count

    # The provider's next file, in the same layout, is read with the mapping kept.
    second = generate_submission(
        world, lender, period, DRIFTED, replace=True, drift_from=drift_from
    )
    run2 = process_submission(deliver(game, second.submission), at=WHEN)
    later = run2.submission.files.get(file_kind=FileKind.INDIVIDUAL.value)
    assert later.file_status == FileStatus.ACCEPTED and later.mapping_id == credit.mapping_id
    assert TemplateMapping.objects.filter(organization=game.organization).count() == 1


def test_suggestions_never_guess_a_column_wrongly_where_the_names_are_close() -> None:
    columns = ("Surname", "FirstName", "DOB", "NatIDNum")
    assert suggest(["Surname", "First_Name", "dob", "NatIDNum"], columns) == list(columns)
    # Too far from anything: left for the person, not guessed.
    assert suggest(["Surname", "FirstName", "DOB", "GhanaCardNo"], columns)[3] == ""


def test_only_a_file_rejected_for_its_columns_can_be_mapped(world: World) -> None:
    game = _game(world)
    lender = Lender.objects.get(world=world, code="ATB")
    clean = generate_submission(world, lender, world.history_end, AVERAGE, replace=True)
    run = process_submission(deliver(game, clean.submission), at=WHEN)
    loaded = run.submission.files.first()
    assert loaded is not None
    with pytest.raises(ClockError):
        controls.map_template(game, run.submission.submission_reference, loaded.file_name, [])


# --- The bureau's own rules ----------------------------------------------------------------------


def _wordy_january(world: World, rules: list[tuple[str, str]], relax: bool = False) -> Game:
    """Every provider writes some genders as words; the bureau may have rules for them."""
    game = _game(world)
    for find, code in rules:
        controls.add_cleansing_rule(game, "Gender", "REPLACE", find, code)
    if relax:
        controls.set_rule_override(game, "F009", "WARNING")
        controls.set_rule_override(game, "F006", "WARNING")
    codes = list(game.organization.institutions.values_list("institution_code", flat=True))
    for lender in Lender.objects.filter(world=world, code__in=codes).order_by("code"):
        existing = lender.submissions.filter(period=world.history_end, profile__name="WORDY")
        sub = (
            existing.get()
            if existing.exists()
            else generate_submission(
                world, lender, world.history_end, WORDY, replace=True
            ).submission
        )
        process_submission(deliver(game, sub), at=WHEN)
    while controls.state(game).now.month == 1:
        game = controls.advance_by(game, "next_event")
    return game


def _unloadable(game: Game) -> int:
    return StagingRecord.objects.filter(
        run__submission__organization=game.organization, record_status=RecordStatus.UNLOADABLE
    ).count()


def test_a_cleansing_rule_changes_the_next_run_measured_against_the_truth(world: World) -> None:
    without = _wordy_january(world, [])
    with_rules = _wordy_january(world, [("Male", "M"), ("Female", "F")])
    words = FileDefect.objects.filter(
        submission__lender__world=world, defect_type="CODE_WORD", file__kind="CONC"
    ).count()
    assert words > 20

    # The rules turned the words back into codes, so those records loaded.
    fixed = TransformationLog.objects.filter(
        record__run__submission__organization=with_rules.organization,
        rule_code__in=["U01", "U02"],
    )
    assert fixed.count() >= words * 0.9  # (a few rows carry other defects as well)
    assert set(fixed.values_list("value_after", flat=True)) == {"M", "F"}
    assert _unloadable(with_rules) < _unloadable(without) - words * 0.8

    # The review measures each rule against the truth: every change was right.
    review = DataQualityReview.objects.get(game=with_rules, period__month=1, period__year=2027)
    measured = {r["code"]: r for r in review.figures["rules"]["cleansing"]}
    assert measured["U01"]["changes"] + measured["U02"]["changes"] == fixed.count()
    assert measured["U01"]["right"] == measured["U01"]["changes"] > 0
    assert "'Male' becomes 'M'" in measured["U01"]["description"]
    assert review.refs["rule.U01.right"]


def test_a_careless_rule_is_measured_as_wrong(world: World) -> None:
    game = _game(world)
    controls.add_cleansing_rule(game, "Surname", "REMOVE", "a")  # mangles real names
    lender = Lender.objects.get(world=world, code="ATB")
    sub = generate_submission(world, lender, world.history_end, AVERAGE, replace=True).submission
    process_submission(deliver(game, sub), at=WHEN)
    while controls.state(game).now.month == 1:
        game = controls.advance_by(game, "next_event")
    review = DataQualityReview.objects.get(game=game, period__month=1, period__year=2027)
    measured = review.figures["rules"]["cleansing"][0]
    assert measured["changes"] > 10 and measured["right"] == 0


def test_relaxing_a_check_loads_records_that_are_measured_against_the_truth(world: World) -> None:
    game = _wordy_january(world, [], relax=True)
    review = DataQualityReview.objects.get(game=game, period__month=1, period__year=2027)
    relaxed = {r["code"]: r for r in review.figures["rules"]["relaxed"]}
    loaded = sum(r["changes"] for r in relaxed.values())
    assert loaded > 20  # the records with words for codes loaded, as sent ...
    assert sum(r["right"] for r in relaxed.values()) == 0  # ... and every one is wrong


def test_rules_are_validated(world: World) -> None:
    game = _game(world)
    with pytest.raises(ClockError):
        controls.add_cleansing_rule(game, "Shoe size", "REPLACE", "9", "10")
    with pytest.raises(ClockError):
        controls.add_cleansing_rule(game, "Gender", "SHOUT", "m", "M")
    with pytest.raises(ClockError):
        controls.set_rule_override(game, "F001", "WARNING")  # a blank mandatory field stands


# --- Feedback reports ----------------------------------------------------------------------------


def test_providers_get_a_feedback_report_of_what_was_rejected_and_why(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _game(world, owner)
    lender = Lender.objects.get(world=world, code="ATB")
    sub = generate_submission(world, lender, world.history_end, WORDY, replace=True).submission
    run = process_submission(deliver(game, sub), at=WHEN)
    reference = run.submission.submission_reference
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/submissions/{reference}/feedback/"

    report = client.get(url).json()
    unloadable = StagingRecord.objects.filter(
        run=run, record_status=RecordStatus.UNLOADABLE
    ).count()
    assert report["records_unloadable"] == unloadable > 0
    assert all(row["problems"] for row in report["rows"])
    gender = [p for row in report["rows"] for p in row["problems"] if p["field"] == "Gender"]
    assert gender and all(p["value"].lower() in ("male", "female") for p in gender)
    assert sum(r["records"] for r in report["rules"]) >= unloadable
    assert report["sent"] == []

    csv = client.get(url, {"download": "csv"})
    assert csv["Content-Type"].startswith("text/csv")
    assert csv.content.decode().splitlines()[0].startswith("File|Row|Account")

    sent = client.post(url).json()
    assert len(sent["sent"]) == 1
    kept = FeedbackReport.objects.get(submission__submission_reference=reference)
    assert kept.report["records_unloadable"] == unloadable


# --- Replay -------------------------------------------------------------------------------------


def test_mapping_rules_and_feedback_replay_exactly(world: World) -> None:
    original = controls.set_pause_rules(start_game(world), [], deadlines=False)
    controls.add_cleansing_rule(original, "Gender", "REPLACE", "Male", "M", provider="ATB")
    controls.set_rule_override(original, "F011", "WARNING")
    while controls.state(original).now.month == 1:
        original = controls.advance_by(original, "next_event")
    reference = (
        Submission.objects.filter(organization=original.organization)
        .order_by("submission_reference")
        .values_list("submission_reference", flat=True)
        .first()
    )
    assert reference is not None
    controls.send_feedback(original, reference)
    controls.set_cleansing_rule_active(original, "U01", False)

    copy = controls.replay(original, start_game(world))
    assert fingerprint(copy) == fingerprint(original)
