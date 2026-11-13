"""Turn a provider's true book into the rows it actually submits.

Pure functions: truth records + Data Quality Profile + random stream in, file
rows and a complete defect ledger out. Each cell is altered at most once, and
a defect is recorded only when the submitted value really differs from the
truth, so (file vs truth) differences and ledger entries correspond exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from apps.standards.submission_template import FileKind, format_date, header

from .profiles import COMMERCIAL_BLANKABLE, INDIVIDUAL_BLANKABLE, DataQualityProfile
from .truth import STALE_FIELDS, TruthRecord

PHONE_FIELDS = {
    FileKind.INDIVIDUAL: ("MOBILE_NUMBER", "ALT_MOBILE_NUMBER"),
    FileKind.COMMERCIAL: ("CONTACT_NUMBER",),
}
IDENTIFIER_FIELD = {FileKind.INDIVIDUAL: "GHANA_CARD_NUMBER", FileKind.COMMERCIAL: "TIN"}
NAME_FIELDS = {
    FileKind.INDIVIDUAL: ("SURNAME", "FIRST_NAME"),
    FileKind.COMMERCIAL: ("REGISTERED_NAME",),
}
DATE_FIELDS = {
    FileKind.INDIVIDUAL: ("DATE_OF_BIRTH", "DISBURSEMENT_DATE"),
    FileKind.COMMERCIAL: ("REGISTRATION_DATE", "DISBURSEMENT_DATE"),
}
AMOUNT_FIELDS = ("ORIGINAL_AMOUNT", "INSTALMENT_AMOUNT", "CURRENT_BALANCE", "ARREARS_AMOUNT")

# Plausible alternative column names used when a provider changes its extract.
HEADER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "GHANA_CARD_NUMBER": ("NATIONAL_ID", "GHANA_CARD_NO"),
    "MOBILE_NUMBER": ("PHONE", "MOBILE_NO"),
    "CURRENT_BALANCE": ("OUTSTANDING_BALANCE", "BALANCE"),
    "DAYS_PAST_DUE": ("DPD", "DAYS_IN_ARREARS"),
    "DATE_OF_BIRTH": ("DOB", "BIRTH_DATE"),
    "ARREARS_AMOUNT": ("AMOUNT_IN_ARREARS", "ARREARS"),
    "ORIGINAL_AMOUNT": ("LOAN_AMOUNT", "AMOUNT_DISBURSED"),
    "ACCOUNT_NUMBER": ("ACCOUNT_NO", "LOAN_ACCOUNT_NO"),
    "CUSTOMER_NUMBER": ("CUSTOMER_ID", "CIF_NUMBER"),
    "SURNAME": ("LAST_NAME",),
    "REGISTRATION_NUMBER": ("REG_NO",),
    "CONTACT_NUMBER": ("PHONE_NUMBER",),
    "TIN": ("TAX_ID",),
}


@dataclass
class Defect:
    defect_type: str
    field: str = ""
    true_value: str = ""
    submitted_value: str = ""
    loan_id: int | None = None
    row_number: int | None = None  # filled in once rows are numbered


@dataclass
class _Row:
    loan_id: int
    values: dict[str, str]
    defects: list[Defect] = field(default_factory=list)
    duplicate_of: _Row | None = None


@dataclass(frozen=True)
class Layout:
    """The column layout a provider actually uses (template drift)."""

    columns: tuple[str, ...]  # canonical field names, in submitted order
    names: tuple[str, ...]  # header text as written, same order

    @classmethod
    def standard(cls, kind: FileKind) -> Layout:
        cols = header(kind)
        return cls(cols, cols)

    def drift_defects(self, kind: FileKind) -> list[Defect]:
        expected = header(kind)
        out = []
        for position, (column, name) in enumerate(zip(self.columns, self.names, strict=True)):
            if name != column:
                out.append(Defect("TEMPLATE_DRIFT", column, column, name))
            if expected.index(column) != position:
                out.append(
                    Defect(
                        "TEMPLATE_DRIFT",
                        column,
                        f"column {expected.index(column) + 1}",
                        f"column {position + 1}",
                    )
                )
        return out


@dataclass
class RenderedFile:
    kind: FileKind
    layout: Layout
    rows: list[list[str]]  # in layout order
    loan_ids: list[int]  # true loan for each row
    defects: list[Defect]  # row and file defects, row numbers resolved
    phone_columns: tuple[int, ...]  # positions of phone fields (for XLSX typing)


def drifted_layout(kind: FileKind, rng: np.random.Generator) -> Layout:
    """A provider's changed extract: one to three renamed columns, maybe two swapped."""
    columns = list(header(kind))
    renamable = [c for c in columns if c in HEADER_SYNONYMS]
    picks = rng.choice(len(renamable), size=int(rng.integers(1, 4)), replace=False)
    names: dict[str, str] = {}
    for i in sorted(picks.tolist()):
        options = HEADER_SYNONYMS[renamable[i]]
        names[renamable[i]] = options[int(rng.integers(len(options)))]
    if rng.random() < 0.5:
        i = int(rng.integers(4, len(columns) - 1))  # never moves the leading identification block
        columns[i], columns[i + 1] = columns[i + 1], columns[i]
    return Layout(tuple(columns), tuple(names.get(c, c) for c in columns))


def render(
    kind: FileKind,
    period: date,
    records: list[TruthRecord],
    profile: DataQualityProfile,
    rng: np.random.Generator,
    layout: Layout | None = None,
) -> RenderedFile:
    layout = layout or Layout.standard(kind)
    blank_weights = profile.blank_weights or (
        INDIVIDUAL_BLANKABLE if kind is FileKind.INDIVIDUAL else COMMERCIAL_BLANKABLE
    )
    identifiers = [r.values[IDENTIFIER_FIELD[kind]] for r in records]

    rows: list[_Row] = []
    omitted: list[Defect] = []
    for record in records:
        if rng.random() < profile.omit_account:
            omitted.append(Defect("OMITTED_ACCOUNT", loan_id=record.loan_id))
            continue
        row = _Row(record.loan_id, dict(record.values))
        _apply_row_defects(row, record, kind, period, profile, rng, identifiers, blank_weights)
        rows.append(row)

    rows = _insert_duplicates(rows, profile, rng)

    defects: list[Defect] = layout.drift_defects(kind)
    position = {id(r): n for n, r in enumerate(rows, start=1)}
    for n, row in enumerate(rows, start=1):
        for d in row.defects:
            d.row_number = n
            d.loan_id = row.loan_id
            defects.append(d)
        if row.duplicate_of is not None:
            original = position[id(row.duplicate_of)]
            defects.append(Defect("DUPLICATE_ROW", "", f"row {original}", "", row.loan_id, n))
    defects.extend(omitted)

    phones = PHONE_FIELDS[kind]
    return RenderedFile(
        kind=kind,
        layout=layout,
        rows=[[r.values[c] for c in layout.columns] for r in rows],
        loan_ids=[r.loan_id for r in rows],
        defects=defects,
        phone_columns=tuple(i for i, c in enumerate(layout.columns) if c in phones),
    )


def _apply_row_defects(
    row: _Row,
    record: TruthRecord,
    kind: FileKind,
    period: date,
    profile: DataQualityProfile,
    rng: np.random.Generator,
    identifiers: list[str],
    blank_weights: dict[str, float],
) -> None:
    touched: set[str] = set()

    def change(name: str, new: str, defect_type: str) -> None:
        old = row.values[name]
        if name in touched or new == old:
            return
        row.defects.append(Defect(defect_type, name, old, new))
        row.values[name] = new
        touched.add(name)

    # Last month's extract re-sent for this account.
    if record.previous is not None and rng.random() < profile.stale_values:
        for name in STALE_FIELDS:
            change(name, record.previous[name], "STALE_VALUE")

    if (
        rng.random() < profile.inconsistent_status
        and row.values["ACCOUNT_STATUS"] == "AC"
        and float(row.values["CURRENT_BALANCE"]) > 0
    ):
        change("ACCOUNT_STATUS", "PD", "INCONSISTENT_STATUS")

    if rng.random() < profile.wrong_identifier and len(identifiers) > 1:
        other = identifiers[int(rng.integers(len(identifiers)))]
        change(IDENTIFIER_FIELD[kind], other, "WRONG_IDENTIFIER")

    if rng.random() < profile.missing_field:
        names = [n for n in blank_weights if n in row.values]
        weights = np.array([blank_weights[n] for n in names])
        name = names[int(rng.choice(len(names), p=weights / weights.sum()))]
        change(name, "", "MISSING_FIELD")

    if rng.random() < profile.name_typo:
        candidates = NAME_FIELDS[kind]
        name = candidates[int(rng.integers(len(candidates)))]
        change(name, _typo(row.values[name], rng), "NAME_TYPO")

    if kind is FileKind.INDIVIDUAL and rng.random() < profile.name_swap:
        surname, first = row.values["SURNAME"], row.values["FIRST_NAME"]
        if not touched & {"SURNAME", "FIRST_NAME"} and surname and first and surname != first:
            change("SURNAME", first, "NAME_SWAP")
            change("FIRST_NAME", surname, "NAME_SWAP")

    phones = PHONE_FIELDS[kind]
    if rng.random() < profile.phone_format:
        name = phones[int(rng.integers(len(phones)))]
        if row.values[name]:
            change(name, _phone_variant(row.values[name], rng), "PHONE_FORMAT")

    if rng.random() < profile.date_format:
        dates = DATE_FIELDS[kind]
        name = dates[int(rng.integers(len(dates)))]
        if row.values[name]:
            day, month, year = row.values[name].split("/")
            change(name, f"{month}/{day}/{year}", "DATE_FORMAT")

    if rng.random() < profile.future_date:
        future = period + timedelta(days=int(rng.integers(1, 400)))
        change("DISBURSEMENT_DATE", format_date(future), "FUTURE_DATE")

    if rng.random() < profile.amount_format:
        name = AMOUNT_FIELDS[int(rng.integers(len(AMOUNT_FIELDS)))]
        change(name, _amount_variant(row.values[name], rng), "AMOUNT_FORMAT")

    # Excel strips the leading zero from phone numbers stored as numbers.
    if profile.file_format == "XLSX" and profile.xlsx_numeric_phones:
        for name in phones:
            value = row.values[name]
            if value.startswith("0") and value.isdigit():
                change(name, value[1:], "PHONE_FORMAT")


def _insert_duplicates(
    rows: list[_Row], profile: DataQualityProfile, rng: np.random.Generator
) -> list[_Row]:
    if profile.duplicate_row <= 0 or not rows:
        return rows
    picks = np.flatnonzero(rng.random(len(rows)) < profile.duplicate_row)
    out = list(rows)
    for i in picks.tolist():
        original = rows[i]
        copy = _Row(original.loan_id, dict(original.values), [], duplicate_of=original)
        start = next(j for j, r in enumerate(out) if r is original) + 1
        out.insert(int(rng.integers(start, len(out) + 1)), copy)
    return out


def _typo(name: str, rng: np.random.Generator) -> str:
    if len(name) < 3:
        return name
    i = int(rng.integers(1, len(name) - 1))
    match int(rng.integers(4)):
        case 0:  # dropped letter: Mensah -> Mensh
            return name[:i] + name[i + 1 :]
        case 1:  # doubled letter: Owusu -> Owwusu
            return name[:i] + name[i] + name[i:]
        case 2:  # transposed letters: Boateng -> Baoteng
            return name[: i - 1] + name[i] + name[i - 1] + name[i + 1 :]
        case _:  # vowel confusion: Kwesi -> Kwasi
            vowels = "aeiou"
            positions = [j for j, ch in enumerate(name) if ch in vowels]
            if not positions:
                return name
            j = positions[int(rng.integers(len(positions)))]
            options = [v for v in vowels if v != name[j]]
            return name[:j] + options[int(rng.integers(len(options)))] + name[j + 1 :]


def _phone_variant(number: str, rng: np.random.Generator) -> str:
    rest = number[1:]
    variants = (
        f"+233{rest}",
        f"233{rest}",
        f"{number[:3]} {number[3:6]} {number[6:]}",
        rest,
        f"{rest[:3]}-{rest[3:6]}-{rest[6:]}",
    )
    return variants[int(rng.integers(len(variants)))]


def _amount_variant(amount: str, rng: np.random.Generator) -> str:
    whole, cents = amount.split(".")
    grouped = f"{int(whole):,}"
    variants = [f"{grouped}.{cents}", f"GHS {amount}", f"GHS{grouped}.{cents}"]
    if cents.endswith("0"):
        variants.append(whole if cents == "00" else f"{whole}.{cents[0]}")
    return variants[int(rng.integers(len(variants)))]
