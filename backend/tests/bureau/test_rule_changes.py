"""P2.0b — A data standard change made mid-game applies only from its effective date (D19).

A trial edition 1.2 of the data standard (a new optional column, a later
deadline) takes effect from the second month. The first month's data stays
under 1.1, including when it is processed again; the second month's files
are written and judged under 1.2; a file on the outdated version is refused.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from apps.bureau.quality.models import ValidationIssue
from apps.bureau.submissions.intake import read_rows, receive_file
from apps.bureau.submissions.models import FileStatus, ProcessingRun, Submission
from apps.bureau.submissions.pipeline import process_submission
from apps.simulation.bridge import deliver, start_game
from apps.standards.rulebook import DATA_STANDARDS, STANDARD_1_1, DataStandard
from apps.standards.submission_template import Field, FileKind, Option
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import Lender, World
from apps.world.provider_files import generate_submission, month_end
from apps.world.provider_files.profiles import CLEAN

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world() -> World:
    g = build_world(51, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _edition_1_2(effective: date) -> DataStandard:
    fields = dict(STANDARD_1_1.fields)
    paypoint = Field("PayPoint", Option.IF_AVAILABLE, "text", 100)
    fields[FileKind.INDIVIDUAL] = (*fields[FileKind.INDIVIDUAL], paypoint)
    return replace(
        STANDARD_1_1, version="1.2", effective=effective, fields=fields, submission_due_day=15,
        note="test edition",
    )  # fmt: skip


def test_a_template_change_applies_from_its_effective_date_only(world: World) -> None:
    end = world.history_end
    first = month_end(end.year - (end.month == 1), (end.month - 2) % 12 + 1)
    second = end
    game = start_game(world)
    lender = Lender.objects.get(world=world, code="ATB")

    def run(period: date) -> ProcessingRun:
        sub = generate_submission(world, lender, period, CLEAN).submission
        return process_submission(deliver(game, sub))

    with DATA_STANDARDS.trial(_edition_1_2(date(second.year, second.month, 1))):
        before, after = run(first), run(second)

        # Each month follows the standard in force for its reporting period.
        assert (before.template_version, after.template_version) == ("1.1", "1.2")
        old, new = (Submission.objects.get(pk=r.submission_id) for r in (before, after))
        assert old.template_version == "1.1" and new.template_version == "1.2"
        assert all("-1.1-" in f.file_name for f in old.files.all())
        assert all("-1.2-" in f.file_name for f in new.files.all())
        assert new.due_date.day >= 15 > old.due_date.day
        consumer = new.files.get(file_kind="CONC")
        names, _ = read_rows(consumer)
        assert names[-1] == "PayPoint"
        assert after.records_accepted == after.records_received > 0
        assert before.records_accepted == before.records_received > 0

        # Processing the old month again still judges it under 1.1.
        again = process_submission(old)
        assert again.template_version == "1.1"
        assert not ValidationIssue.objects.filter(run=again, rule_code="T001").exists()
        assert again.records_received == before.records_received

        # A provider still sending the 1.1 layout for a 1.2 period is refused.
        stale = old.files.get(file_kind="CONC")
        data = (Path(settings.STORAGE_ROOT) / stale.storage_path).read_bytes()
        name = stale.file_name.replace(f"-{first:%Y%m%d}-", f"-{second:%Y%m%d}-")
        refused = receive_file(
            game.organization, new.institution, second, name, data, datetime(2030, 1, 1, tzinfo=UTC)
        )
        assert (refused.file_status, refused.rejection_reason) == (FileStatus.REJECTED, "T005")

    # The trial is over: the series is as released.
    assert DATA_STANDARDS.at(second) is STANDARD_1_1
