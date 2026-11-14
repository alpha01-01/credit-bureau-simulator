"""Cleansing and validation of submitted records (industry standard, D18).

Follows the Data Standards Committee format (docs/references/data-formats.md):
field types, lengths, catalogue codes, mandatory and conditional fields, and
the financial-logic checks. Cleansing comes first, as in the owner's cleanser:
values that are recognisably right but badly formatted are corrected and
logged, so only genuine problems reach a person.

How strictly a record is rejected is a bureau policy (D18):

  STANDARD  any mandatory or applicable conditional field missing or invalid
            rejects the record, as the standard says;
  CORE      only the core fields (the cleanser's CLEAN gate) reject; other
            missing values are warnings and other invalid values are blanked.

Financial-logic errors (closed with a balance, maturity before disbursement)
and a missing identifier (owner's rule, from 2020) reject under both policies.

ASSUMPTION A-017: rule codes and messages are the game's own; the bureau's
real error codes (reference R3) are still needed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from apps.standards.rulebook import DATA_STANDARDS, DataStandard
from apps.standards.submission_template import (
    CLOSED_STATUS_CODES,
    DATE_FORMAT,
    FileKind,
    is_valid_ghana_card,
)

STANDARD, CORE = "STANDARD", "CORE"
POLICIES = {
    STANDARD: "Reject when any mandatory or required conditional field is missing or invalid",
    CORE: "Reject only when the core fields fail; clean or blank the rest",
}

RULES: dict[str, str] = {
    # File level
    "T001": "File columns do not match the template",
    "T002": "File name does not follow the naming convention",
    "T003": "File is identical to a file already received",
    "T004": "File could not be read",
    "T005": "File uses a template version not in force for its reporting period",
    # Field level
    "F001": "Mandatory field is blank",
    "F002": "Date is not a valid YYYYMMDD date",
    "F003": "Date is after the reporting date",
    "F004": "Amount is not a whole number",
    "F005": "Value is not a whole number",
    "F006": "Code is not in the catalogue",
    "F007": "Phone number is not a valid 10-digit mobile number",
    "F008": "Ghana Card number is not valid",
    "F009": "Value is longer than the field allows",
    "F011": "Account is reported closed but has a balance outstanding",
    "F012": "Maturity date is before the disbursement date",
    "F013": "No valid identifier for a facility disbursed from 2020",
    "F014": "Required conditional field is blank",
    # Duplicates
    "D001": "Duplicate of another row in the file (the lower balance is kept)",
    "D002": "Account number repeated in the file for a different customer",
    # Referencing
    "R001": "Identifier conflicts with the bureau's records for this customer",
    "R002": "Account is already held by a different bureau customer",
    "R003": "Branch code is not known for this institution",
    "R004": "Disbursement date differs from the account on file",
    # Loading
    "L001": "An observation for this account and date already exists",
    # Cleansing
    "C001": "Phone number normalised to 10-digit format",
    "C002": "Date normalised to YYYYMMDD",
    "C003": "Amount normalised to a whole number",
    "C004": "Code normalised",
    "C005": "Invalid optional value blanked (core-fields policy)",
    # Review
    "M001": "Corrected by a reviewer",
    "Q001": "Returned to the provider by a reviewer",
}

WHOLE = re.compile(r"\d+")
DATE = re.compile(r"\d{8}")
MOBILE = re.compile(r"0\d{9}")
_PHONE_NOISE = re.compile(r"[\s\-().]")
_AMOUNT_NOISE = re.compile(r"^(GHS|GH¢|¢)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    rule_code: str
    field: str = ""
    value: str = ""
    severity: str = "ERROR"

    @property
    def message(self) -> str:
        return RULES[self.rule_code]


def parse_date(value: str) -> date | None:
    if not DATE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


# --- Cleansing ------------------------------------------------------------------------


def normalise_phone(value: str) -> str:
    """C001: bring a Ghanaian mobile number to the 10-digit 0XXXXXXXXX form, if possible."""
    digits = _PHONE_NOISE.sub("", value)
    if digits.startswith("+233"):
        digits = "0" + digits[4:]
    elif digits.startswith("233") and len(digits) == 12:
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits.isdigit() and not digits.startswith("0"):
        digits = "0" + digits
    return digits if MOBILE.fullmatch(digits) else value


def normalise_date(value: str) -> str:
    """C002: dates whose meaning is certain become YYYYMMDD.

    Covers DD/MM/YYYY (and DD-MM-YYYY), YYYY-MM-DD, and YYYYDDMM when the
    "month" is over 12. A day and month swapped where both are 12 or less
    cannot be detected, and is left as submitted.
    """
    text = value.strip()
    if m := re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text):
        candidate = f"{m[3]}{int(m[2]):02d}{int(m[1]):02d}"
    elif m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
        candidate = f"{m[1]}{m[2]}{m[3]}"
    elif DATE.fullmatch(text) and parse_date(text) is None:
        swapped = f"{text[:4]}{text[6:]}{text[4:6]}"
        candidate = swapped
    else:
        return value
    return candidate if parse_date(candidate) is not None else value


def normalise_amount(value: str) -> str:
    """C003: separators, currency and decimals removed; rounded to whole units."""
    cleaned = _AMOUNT_NOISE.sub("", value.strip()).replace(",", "")
    if re.fullmatch(r"\d+(\.\d+)?", cleaned):
        whole, _, fraction = cleaned.partition(".")
        rounded = int(whole) + (1 if fraction and int(fraction[0]) >= 5 else 0)
        return str(rounded)
    return value


def cleanse(
    kind: FileKind, values: dict[str, str], standard: DataStandard
) -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    """Apply cleansing rules. Returns the cleansed values and (field, rule, before, after) logs.

    Field types come from the data standard the record is governed by.
    """
    out = dict(values)
    logs = []

    def fix(name: str, rule: str, after: str) -> None:
        if after != out[name]:
            logs.append((name, rule, out[name], after))
            out[name] = after

    for f in standard.fields[kind]:
        value = out.get(f.name, "")
        if not value:
            continue
        if value != value.strip():
            out[f.name] = value = value.strip()
        if f.kind == "phone":
            fix(f.name, "C001", normalise_phone(value))
        elif f.kind == "date":
            fix(f.name, "C002", normalise_date(value))
        elif f.kind == "numeric":
            fix(f.name, "C003", normalise_amount(value))
        elif f.kind == "code" and value.upper() != value:
            fix(f.name, "C004", value.upper())
    return out, logs


# --- Validation ------------------------------------------------------------------------


@dataclass
class Validation:
    issues: list[Issue] = field(default_factory=list)
    blanked: dict[str, str] = field(default_factory=dict)  # field -> invalid value removed

    @property
    def rejected(self) -> bool:
        return any(i.severity == "ERROR" for i in self.issues)


def _format_issue(
    name: str,
    kind: str,
    length: int,
    value: str,
    code_list: str | None,
    code_lists: Mapping[str, Mapping[str, str]],
) -> str | None:
    if len(value) > length:
        return "F009"
    if kind == "date":
        return None if parse_date(value) else "F002"
    if kind == "numeric":
        return None if WHOLE.fullmatch(value) else "F004"
    if kind == "code":
        return None if code_list and value in code_lists[code_list] else "F006"
    if kind == "phone":
        return None if MOBILE.fullmatch(value) else "F007"
    if name == "NatIDNum" or name == "G1NatID":
        return None if is_valid_ghana_card(value) else "F008"
    return None


def validate(
    kind: FileKind,
    values: dict[str, str],
    period: date,
    policy: str = STANDARD,
    standard: DataStandard | None = None,
) -> Validation:
    """Field, conditional and financial-logic checks of one cleansed record.

    ``standard`` is the data standard governing the record; by default, the one
    in force for its reporting period.
    """
    standard = standard or DATA_STANDARDS.at(period)
    result = Validation()
    core = standard.core_fields[kind]
    strict = policy == STANDARD

    def problem(code: str, name: str, value: str = "", always: bool = False) -> None:
        fatal = always or strict or name in core
        result.issues.append(Issue(code, name, value, "ERROR" if fatal else "WARNING"))

    # Types, lengths and catalogues.
    for f in standard.fields[kind]:
        value = values.get(f.name, "")
        if not value:
            if f.mandatory:
                problem("F001", f.name)
            continue
        code = _format_issue(f.name, f.kind, f.length, value, f.code_list, standard.code_lists)
        if code is None:
            continue
        if strict or f.name in core:
            problem(code, f.name, value)
        else:
            result.issues.append(Issue(code, f.name, value, "WARNING"))
            result.blanked[f.name] = value

    def present(name: str) -> bool:
        return bool(values.get(name)) and name not in result.blanked

    def require(name: str, when: bool) -> None:
        if when and not present(name):
            problem("F014", name)

    # Identity: at least one valid ID, mandatory from 2020 (owner's rule).
    disbursed = parse_date(values.get("DisbursementDate", ""))
    if kind is FileKind.INDIVIDUAL:
        has_id = any(present(n) and not _bad_id(n, values[n]) for n in standard.id_fields)
        if not has_id and disbursed is not None and disbursed >= standard.id_required_from:
            problem("F013", "NatIDNum", always=True)
        require("EmpName", values.get("CreditFacilityType") == "115")
    elif not (present("BusRegNum") or present("TINum")):
        problem("F013", "BusRegNum", always=True)

    # Conditional fields.
    status = values.get("FacilityStatusCode", "")
    require("ClosedDate", status in CLOSED_STATUS_CODES)
    require("ClosureReason", status in CLOSED_STATUS_CODES)
    require("WrittenOffAmt", status == "W")
    require("ReasonForWrittenOff", status == "W")
    secured = values.get("CreditCollateralInd") == "101"
    for name in ("SecurityType", "NatureOfCharge", "SecurityValue"):
        require(name, secured)
    guarantor = values.get("NatureOfGuarantor")
    require("NameOfComGuarantor", guarantor == "102")
    require("BusRegOfGuarantor", guarantor == "102")
    for name in ("G1Surname", "G1FirstName", "G1Gender", "G1DOB"):
        require(name, guarantor == "101")
    require("LastPaymentDate", present("LastPaymentAmount"))
    require("LastPaymentAmount", present("LastPaymentDate"))

    # Financial logic: rejects under every policy (the standard's own examples).
    balance = values.get("CurBal", "")
    if status in CLOSED_STATUS_CODES and WHOLE.fullmatch(balance) and int(balance) > 0:
        problem("F011", "FacilityStatusCode", status, always=True)
    matures = parse_date(values.get("MaturityDate", ""))
    if disbursed and matures and matures < disbursed:
        problem("F012", "MaturityDate", values["MaturityDate"], always=True)
    for name in ("DisbursementDate", "DOB", "RegistrationDate", "LastPaymentDate"):
        when = parse_date(values.get(name, ""))
        if when is not None and when > period:
            problem("F003", name, values[name], always=name == "DisbursementDate")
    return result


def _bad_id(name: str, value: str) -> bool:
    return name == "NatIDNum" and not is_valid_ghana_card(value)


# --- Proposed corrections for triage (ASSUMPTION A-022) ----------------------------------

CORRECTABLE = frozenset({"F011"})
CLOSURE_FIELDS = frozenset({"ClosedDate", "ClosureReason"})


def propose_corrections(
    values: dict[str, str], issues: list[Issue], period: date
) -> dict[str, str]:
    """Corrections a reviewer could apply, when every error is of a correctable kind.

    Format problems are fixed by cleansing before anyone sees them. What is left
    for a person is judgement: an account reported closed with a balance could
    be a live account (make it active) or a closed one whose balance was never
    zeroed (send it back).
    """
    errors = [i for i in issues if i.severity == "ERROR"]
    reopened = any(i.rule_code == "F011" for i in errors)

    def covered(issue: Issue) -> bool:
        # Making the account active also removes the need for closure details.
        return issue.rule_code in CORRECTABLE or (
            reopened and issue.rule_code == "F014" and issue.field in CLOSURE_FIELDS
        )

    if not errors or not all(covered(i) for i in errors):
        return {}
    proposal: dict[str, str] = {}
    for issue in errors:
        if issue.rule_code == "F011":
            proposal["FacilityStatusCode"] = "A"
            proposal["ClosedDate"] = ""
            proposal["ClosureReason"] = ""
    return proposal
