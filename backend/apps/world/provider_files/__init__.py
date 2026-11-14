"""Provider files (roadmap S2; Document 07, Section 7.3).

Each month every reporting provider sends its book to the bureau: one file
for individual borrowers and one for businesses, in the submission template,
distorted by the provider's Data Quality Profile. This package produces those
files from the world's truth and records every injected defect, with the
correct value, in the defect ledger (``FileDefect``).

Everything is deterministic: the same world, provider and month always give
byte-identical files and the same ledger.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from apps.standards.calendar import next_working_day
from apps.standards.submission_template import (
    SUBMISSION_DUE_DAY,
    TEMPLATE_VERSION,
    FileKind,
    file_name,
)

from ..generation.config import LENDER_SRN
from ..generation.persist import copy_rows
from ..generation.rng import stream
from ..models import Lender, ProviderFile, ProviderSubmission, World
from .files import to_bytes
from .profiles import DataQualityProfile, profile_for
from .render import Defect, Layout, RenderedFile, drifted_layout, render
from .truth import load_truth

__all__ = [
    "SubmissionResult",
    "delete_submission_files",
    "generate_submission",
    "month_end",
    "month_index",
    "play_start",
    "submission_dir",
]


def month_end(year: int, month: int) -> date:
    first_of_next = date(year + month // 12, month % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def month_index(period: date) -> int:
    return period.year * 12 + period.month - 1


def months_between(start: date, end: date) -> int:
    return month_index(end) - month_index(start)


@dataclass(frozen=True)
class Schedule:
    due_date: date
    arrival_date: date

    @property
    def is_late(self) -> bool:
        return self.arrival_date > self.due_date


def schedule(seed: int, lender_code: str, period: date, profile: DataQualityProfile) -> Schedule:
    """When the provider sends this month's files (ASSUMPTION A-014 for the deadline)."""
    rng = stream(seed, f"submission-arrival:{lender_code}", month_index(period))
    next_month = period + timedelta(days=1)
    due = next_working_day(next_month.replace(day=SUBMISSION_DUE_DAY))
    if rng.random() < profile.late_rate and profile.late_days_max > 0:
        arrival = due + timedelta(days=int(rng.integers(1, profile.late_days_max + 1)))
    else:
        first, last = profile.arrival_days
        arrival = next_month.replace(
            day=int(rng.integers(first, min(last, SUBMISSION_DUE_DAY) + 1))
        )
    return Schedule(due, arrival)


def play_start(world: World) -> date:
    """The first month of play: the month after the originally generated history.

    Fixed for the life of the world: advancing the world during play does not move it.
    """
    generated_end = date.fromisoformat(world.config["history_end"])
    nxt = generated_end + timedelta(days=1)
    return month_end(nxt.year, nxt.month)


def layout_for(
    seed: int,
    lender_code: str,
    kind: FileKind,
    drift_from: date,
    period: date,
    profile: DataQualityProfile,
) -> Layout:
    """The provider's column layout this month.

    Providers use the standard layout before ``drift_from`` (by default the
    start of play: the bureau has long since agreed layouts with its providers).
    From then on, each month there is a ``template_drift`` chance that the
    provider changes its extract without notice; once changed, the new layout
    persists in later months.
    """
    if period < drift_from:
        return Layout.standard(kind)
    months = months_between(drift_from, period) + 1
    hazard = stream(seed, f"template-drift:{lender_code}:{kind.value}").random(months)
    if profile.template_drift > 0 and (hazard < profile.template_drift).any():
        return drifted_layout(kind, stream(seed, f"template-layout:{lender_code}:{kind.value}"))
    return Layout.standard(kind)


def submission_dir(world_id: int, lender_code: str, period: date) -> Path:
    return (
        Path(settings.STORAGE_ROOT)
        / "provider_files"
        / f"world_{world_id}"
        / lender_code
        / f"{period:%Y%m}"
    )


def relative_storage_path(path: Path) -> str:
    return path.relative_to(Path(settings.STORAGE_ROOT)).as_posix()


@dataclass(frozen=True)
class SubmissionResult:
    submission: ProviderSubmission
    rendered: dict[FileKind, RenderedFile]
    schedule: Schedule


def generate_submission(
    world: World,
    lender: Lender,
    period: date,
    profile: DataQualityProfile | None = None,
    replace: bool = False,
    drift_from: date | None = None,
) -> SubmissionResult:
    """Produce, store and record one provider's submission for one month.

    ``drift_from`` is the first month template drift can occur; it defaults to
    the start of play. Scenarios and tests may move it earlier.
    """
    if not world.history_start <= period <= world.history_end:
        raise ValueError(
            f"{period} is outside the world's history ({world.history_start} to {world.history_end})"
        )
    if period != month_end(period.year, period.month):
        raise ValueError(f"{period} is not a month-end")
    if profile is None:
        profile = profile_for(
            lender.code, lender.lender_type, float(lender.profile.get("sophistication", 0.5))
        )

    existing = ProviderSubmission.objects.filter(lender=lender, period=period)
    if existing.exists():
        if not replace:
            raise FileExistsError(f"{lender.code} {period:%Y-%m} has already been generated")
        _delete_submissions([s.pk for s in existing])

    plan = schedule(world.seed, lender.code, period, profile)
    rendered: dict[FileKind, RenderedFile] = {}
    for kind in FileKind:
        records = load_truth(world.pk, lender.pk, lender.code, period, kind)
        if not records:
            continue
        layout = layout_for(
            world.seed, lender.code, kind, drift_from or play_start(world), period, profile
        )
        rng = stream(world.seed, f"provider-rows:{lender.code}:{kind.value}", month_index(period))
        rendered[kind] = render(kind, period, records, profile, rng, layout)

    directory = submission_dir(world.pk, lender.code, period)
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)

    with transaction.atomic():
        submission = ProviderSubmission.objects.create(
            world=world,
            lender=lender,
            period=period,
            due_date=plan.due_date,
            arrival_date=plan.arrival_date,
            profile=profile.snapshot(),
            template_version=TEMPLATE_VERSION,
        )
        defects: list[tuple[int | None, Defect]] = []
        if plan.is_late:
            days = (plan.arrival_date - plan.due_date).days
            defects.append(
                (
                    None,
                    Defect(
                        "LATE_SUBMISSION",
                        "",
                        plan.due_date.isoformat(),
                        f"{plan.arrival_date.isoformat()} ({days} days late)",
                    ),
                )
            )
        for kind, result in rendered.items():
            stored = _store_file(submission, kind, result, period, plan.arrival_date, directory)
            with connection.cursor() as cursor:
                copy_rows(
                    cursor,
                    "world_providerfilerow",
                    ("file_id", "row_number", "loan_id"),
                    ((stored.pk, n, loan) for n, loan in enumerate(result.loan_ids, start=1)),
                )
            defects.extend((stored.pk, d) for d in result.defects)

        with connection.cursor() as cursor:
            copy_rows(
                cursor,
                "world_filedefect",
                (
                    "submission_id", "file_id", "row_number", "loan_id", "defect_type", "field",
                    "true_value", "submitted_value",
                ),
                (
                    (
                        submission.pk, file_id, d.row_number, d.loan_id, d.defect_type, d.field,
                        d.true_value, d.submitted_value,
                    )
                    for file_id, d in defects
                ),
            )  # fmt: skip

    return SubmissionResult(submission, rendered, plan)


def _store_file(
    submission: ProviderSubmission,
    kind: FileKind,
    rendered: RenderedFile,
    period: date,
    created: date,
    directory: Path,
) -> ProviderFile:
    """Write the file under the standard's name: SRN, reporting date, creation date, version."""
    data = to_bytes(rendered)
    name = file_name(LENDER_SRN[submission.lender.code], kind, period, created)
    path = directory / name
    path.write_bytes(data)
    return ProviderFile.objects.create(
        submission=submission,
        kind=kind.value,
        file_name=name,
        file_format="CSV",
        storage_path=relative_storage_path(path),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        header=list(rendered.layout.names),
        row_count=len(rendered.rows),
    )


def _delete_submissions(submission_ids: list[int]) -> None:
    """Set-based delete: the ORM cascade would load every row-map entry."""
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM world_filedefect WHERE submission_id = ANY(%s)", [submission_ids]
        )
        cursor.execute(
            "DELETE FROM world_providerfilerow WHERE file_id IN "
            "(SELECT id FROM world_providerfile WHERE submission_id = ANY(%s))",
            [submission_ids],
        )
        cursor.execute(
            "DELETE FROM world_providerfile WHERE submission_id = ANY(%s)", [submission_ids]
        )
        cursor.execute("DELETE FROM world_providersubmission WHERE id = ANY(%s)", [submission_ids])


def delete_submission_files(world_id: int) -> None:
    """Remove a world's provider files from storage (they can be regenerated exactly)."""
    shutil.rmtree(
        Path(settings.STORAGE_ROOT) / "provider_files" / f"world_{world_id}", ignore_errors=True
    )
