"""The rule book: versioned rules with effective dates (Document 07, D19).

Rules change in the real world: the regulator revises the data standard,
the government changes tax rates. A game must follow those changes without
rewriting its past. So every rule that can change is published as an
**edition** with a version and an effective date, in a **series**:

  DATA_STANDARDS  the credit data standard: templates, code lists, core
                  fields, validation thresholds, deadlines. Chosen by the
                  *reporting period* of the data: December's data follows the
                  standard in force for December, whenever it is processed.
  TAX_RULES       VAT and levies, PAYE bands, SSNIT rates, remittance day.
                  Chosen by the *transaction date* (invoice issue, pay day).

Whatever uses a rule records the version it used (submission, processing run,
journal entry), and later work on the same thing (review, reprocessing) uses
that recorded version, not today's.

Released editions are frozen. ``rulebook.lock.json`` holds a digest of each;
a test fails if a released edition changes. To change a rule, add a new
edition with a later effective date, then add its digest to the lock file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from bisect import bisect_right
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from . import submission_template as t1
from .submission_template import Field, FileKind


class Edition(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def effective(self) -> date: ...


class Series[E: Edition]:
    """Editions of one kind of rule, ordered by effective date."""

    def __init__(self, name: str, editions: tuple[E, ...]) -> None:
        self.name = name
        self._editions: list[E] = []
        for edition in editions:
            self._add(edition)

    def _add(self, edition: E) -> None:
        if any(e.version == edition.version for e in self._editions):
            raise ValueError(f"{self.name} {edition.version} already exists")
        if any(e.effective == edition.effective for e in self._editions):
            raise ValueError(f"Two {self.name} editions take effect on {edition.effective}")
        self._editions.append(edition)
        self._editions.sort(key=lambda e: e.effective)

    @property
    def editions(self) -> tuple[E, ...]:
        return tuple(self._editions)

    def at(self, day: date) -> E:
        """The edition in force on ``day``."""
        i = bisect_right([e.effective for e in self._editions], day)
        if i == 0:
            raise LookupError(f"No {self.name} in force on {day}")
        return self._editions[i - 1]

    def get(self, version: str) -> E:
        for edition in self._editions:
            if edition.version == version:
                return edition
        raise LookupError(f"No {self.name} version {version}")

    @contextmanager
    def trial(self, edition: E) -> Iterator[E]:
        """Publish an extra edition for the duration of a block (tests and what-if runs)."""
        self._add(edition)
        try:
            yield edition
        finally:
            self._editions.remove(edition)


def digest(edition: object) -> str:
    """A stable fingerprint of an edition's content, for the lock file."""

    def plain(value: Any) -> Any:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
        if isinstance(value, Mapping):
            return {str(plain(k)): plain(v) for k, v in value.items()}
        if isinstance(value, tuple | list):
            return [plain(v) for v in value]
        if isinstance(value, frozenset | set):
            return sorted(plain(v) for v in value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, date | Decimal):
            return str(value)
        return value

    text = json.dumps(plain(edition), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


# --- The credit data standard -------------------------------------------------------


@dataclass(frozen=True, eq=False)
class DataStandard:
    """One edition of the credit data standard (templates and validation rules)."""

    version: str  # as written in file names, e.g. "1.1"
    effective: date  # the first reporting period it governs
    fields: Mapping[FileKind, tuple[Field, ...]]
    core_fields: Mapping[FileKind, frozenset[str]]
    code_lists: Mapping[str, Mapping[str, str]]
    id_fields: tuple[str, ...]  # any one satisfies "a valid ID" for an individual
    id_required_from: date  # disbursement date from which an ID is mandatory
    submission_due_day: int  # day of the following month
    note: str = ""

    def header(self, kind: FileKind) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields[kind])

    def field(self, kind: FileKind, name: str) -> Field | None:
        return next((f for f in self.fields[kind] if f.name == name), None)


STANDARD_1_1 = DataStandard(
    version="1.1",
    effective=date(2020, 1, 1),
    fields=t1.FIELDS,
    core_fields=t1.CORE_FIELDS,
    code_lists=t1.CODE_LISTS,
    id_fields=t1.INDIVIDUAL_ID_FIELDS,
    id_required_from=t1.ID_REQUIRED_FROM,
    submission_due_day=t1.SUBMISSION_DUE_DAY,
    note="Consumer and business credit templates as simplified (proposal v2, D18). "
    "ASSUMPTION A-038: treated as in force for all data from January 2020.",
)

DATA_STANDARDS: Series[DataStandard] = Series("data standard", (STANDARD_1_1,))


# --- Tax and payroll rules ----------------------------------------------------------


@dataclass(frozen=True, eq=False)
class TaxRules:
    version: str
    effective: date  # first transaction date it applies to
    vat_and_levies: Decimal  # one combined rate on bureau services
    ssnit_employer: Decimal
    ssnit_employee: Decimal
    # Monthly PAYE bands: (width of band in GHS, rate); the last band is unbounded.
    paye_bands: tuple[tuple[Decimal | None, Decimal], ...]
    remittance_day: int  # PAYE and SSNIT due by this day of the following month
    note: str = ""


TAX_2024 = TaxRules(
    version="GH-2024.1",
    effective=date(2024, 1, 1),
    vat_and_levies=Decimal("0.20"),
    ssnit_employer=Decimal("0.13"),
    ssnit_employee=Decimal("0.055"),
    paye_bands=(
        (Decimal("490"), Decimal("0")),
        (Decimal("110"), Decimal("0.05")),
        (Decimal("130"), Decimal("0.10")),
        (Decimal("3166.67"), Decimal("0.175")),
        (Decimal("16000"), Decimal("0.25")),
        (Decimal("30520"), Decimal("0.30")),
        (None, Decimal("0.35")),
    ),
    remittance_day=14,
    note="ASSUMPTION A-031 (VAT 15%, NHIL 2.5%, GETFund 2.5%) and A-032 (PAYE, SSNIT).",
)

TAX_RULES: Series[TaxRules] = Series("tax rules", (TAX_2024,))

SERIES: dict[str, Series[Any]] = {"data_standard": DATA_STANDARDS, "tax_rules": TAX_RULES}
