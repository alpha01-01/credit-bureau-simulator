"""Template mapping: reading a file whose provider changed its column layout (P2.5; D17).

A drifted file is rejected (T001). The bureau suggests which template column
each received header is; a person confirms or corrects the mapping, which is
then kept for that provider and file kind and applied to its later files.

Suggestions use only what the bureau can see: the received header text and the
template. ASSUMPTION A-050: an exact or punctuation-insensitive match first,
then the closest name by Jaro-Winkler similarity (at least 0.75); a header that
matches nothing well is left for the person to choose.
"""

from __future__ import annotations

import re
from datetime import datetime

from apps.bureau.referencing.similarity import jaro_winkler
from apps.standards.rulebook import DATA_STANDARDS
from apps.standards.submission_template import FileKind

from .intake import read_rows
from .models import Submission, SubmissionFile, TemplateMapping

SUGGEST_AT = 0.75


class MappingError(Exception):
    pass


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def template_columns(stored: SubmissionFile) -> tuple[str, ...]:
    standard = DATA_STANDARDS.get(stored.submission.template_version)
    return tuple(standard.header(FileKind(stored.file_kind)))


def received_headers(stored: SubmissionFile) -> list[str]:
    names, _ = read_rows(stored)
    return names


def suggest(received: list[str], columns: tuple[str, ...]) -> list[str]:
    """A template column for each received header ('' where nothing fits well)."""
    out = [""] * len(received)
    free = set(columns)
    by_key = {_key(c): c for c in columns}
    for i, name in enumerate(received):  # exact, then punctuation and case aside
        match = name if name in free else by_key.get(_key(name))
        if match in free:
            out[i] = match
            free.discard(match)
    pairs = sorted(
        (
            (-jaro_winkler(_key(name), _key(column)), i, column)
            for i, name in enumerate(received)
            if not out[i]
            for column in free
        ),
    )
    for score, i, column in pairs:  # closest pairs first
        if -score < SUGGEST_AT:
            break
        if not out[i] and column in free:
            out[i] = column
            free.discard(column)
    return out


def check(received: list[str], mapped: list[str], columns: tuple[str, ...]) -> None:
    if len(mapped) != len(received):
        raise MappingError("Give a template column for every received header")
    if sorted(mapped) != sorted(columns):
        missing = sorted(set(columns) - set(mapped))
        repeated = sorted({c for c in mapped if mapped.count(c) > 1})
        unknown = sorted(set(mapped) - set(columns))
        problems = [
            f"missing {', '.join(missing)}" if missing else "",
            f"used twice: {', '.join(repeated)}" if repeated else "",
            f"not in the template: {', '.join(unknown)}" if unknown else "",
        ]
        raise MappingError("; ".join(p for p in problems if p))


def saved_mapping(
    submission: Submission, kind: FileKind, received: list[str]
) -> TemplateMapping | None:
    """The mapping kept for this provider, file kind and headers, if there is one."""
    return (
        TemplateMapping.objects.filter(
            institution_id=submission.institution_id, file_kind=kind.value, received=received
        )
        .order_by("-pk")
        .first()
    )


def save_mapping(
    stored: SubmissionFile, mapped: list[str], decided_by: str, at: datetime
) -> TemplateMapping:
    received = received_headers(stored)
    check(received, mapped, template_columns(stored))
    submission = stored.submission
    return TemplateMapping.objects.create(
        organization_id=submission.organization_id,
        institution_id=submission.institution_id,
        file_kind=stored.file_kind,
        received=received,
        columns=mapped,
        created_at=at,
        created_by=decided_by[:120],
    )
