"""Validation and cleansing rules for submission records.

ASSUMPTION A-017: rule set, codes and severities are placeholders until the
real validation rules and error codes (reference R3) are available. Rules are
deliberately strict about format: a value the template does not allow is an
error unless a cleansing rule corrects it first. Pipeline v0 has exactly one
cleansing rule, C001 (phone normalisation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.standards.submission_template import (
    CLOSED_STATUS_CODES,
    CODE_LISTS,
    DATE_FORMAT,
    FIELDS,
    FileKind,
    is_valid_ghana_card,
)

RULES: dict[str, str] = {
    # File level
    "T001": "File columns do not match the submission template",
    "T002": "File name does not follow the naming convention",
    "T003": "File is identical to a file already received",
    "T004": "File could not be read",
    # Field level
    "F001": "Mandatory field is blank",
    "F002": "Date is not a valid DD/MM/YYYY date",
    "F003": "Date is after the reporting date",
    "F004": "Amount is not a number with two decimals",
    "F005": "Value is not a whole number",
    "F006": "Code is not in the code list",
    "F007": "Phone number is not a valid 10-digit mobile number",
    "F008": "Ghana Card number is not valid",
    "F009": "Provider code does not match the submitting institution",
    "F010": "Reporting date does not match the submission period",
    "F011": "Account is reported closed but has a balance outstanding",
    "F012": "Maturity date is before the disbursement date",
    # Duplicates
    "D001": "Exact duplicate of an earlier row in the file",
    "D002": "Account number repeated in the file with different values",
    # Referencing (warnings: the record is loaded, the conflict is kept for review)
    "R001": "Identifier conflicts with the bureau's records for this customer",
    "R002": "Account is already held by a different bureau customer",
    "R003": "Branch code is not known for this institution",
    # Loading
    "L001": "An observation for this account and date already exists",
    # Cleansing
    "C001": "Phone number normalised to 10-digit format",
}

AMOUNT = re.compile(r"\d+\.\d{2}")
INTEGER = re.compile(r"\d+")
DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
MOBILE = re.compile(r"0\d{9}")
_PHONE_NOISE = re.compile(r"[\s\-().]")


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


def cleanse(
    kind: FileKind, values: dict[str, str]
) -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    """Apply cleansing rules. Returns the cleansed values and (field, rule, before, after) logs."""
    out = dict(values)
    logs = []
    for f in FIELDS[kind]:
        if f.kind == "phone" and out[f.name]:
            after = normalise_phone(out[f.name])
            if after != out[f.name]:
                logs.append((f.name, "C001", out[f.name], after))
                out[f.name] = after
    return out, logs


def validate(
    kind: FileKind, values: dict[str, str], institution_code: str, period: date
) -> list[Issue]:
    """Field and cross-field validation of one cleansed record."""
    issues: list[Issue] = []
    for f in FIELDS[kind]:
        value = values[f.name]
        if not value:
            if f.mandatory:
                issues.append(Issue("F001", f.name))
            continue
        severity = "ERROR" if f.mandatory else "WARNING"
        match f.kind:
            case "date":
                parsed = parse_date(value)
                if parsed is None:
                    issues.append(Issue("F002", f.name, value, severity))
                elif parsed > period and f.name != "MATURITY_DATE":
                    issues.append(Issue("F003", f.name, value, severity))
            case "amount":
                if not AMOUNT.fullmatch(value):
                    issues.append(Issue("F004", f.name, value, severity))
            case "integer":
                if not INTEGER.fullmatch(value):
                    issues.append(Issue("F005", f.name, value, severity))
            case "code":
                if f.code_list and value not in CODE_LISTS[f.code_list]:
                    issues.append(Issue("F006", f.name, value, severity))
            case "phone":
                if not MOBILE.fullmatch(value):
                    issues.append(Issue("F007", f.name, value, severity))
            case _:
                if f.name == "GHANA_CARD_NUMBER" and not is_valid_ghana_card(value):
                    issues.append(Issue("F008", f.name, value, severity))

    if values["PROVIDER_CODE"] and values["PROVIDER_CODE"] != institution_code:
        issues.append(Issue("F009", "PROVIDER_CODE", values["PROVIDER_CODE"]))
    reporting = parse_date(values["REPORTING_DATE"])
    if reporting is not None and reporting != period:
        issues.append(Issue("F010", "REPORTING_DATE", values["REPORTING_DATE"]))
    if (
        values["ACCOUNT_STATUS"] in CLOSED_STATUS_CODES
        and AMOUNT.fullmatch(values["CURRENT_BALANCE"])
        and Decimal(values["CURRENT_BALANCE"]) > 0
    ):
        issues.append(Issue("F011", "ACCOUNT_STATUS", values["ACCOUNT_STATUS"]))
    disbursed = parse_date(values["DISBURSEMENT_DATE"])
    matures = parse_date(values["MATURITY_DATE"])
    if disbursed and matures and matures < disbursed:
        issues.append(Issue("F012", "MATURITY_DATE", values["MATURITY_DATE"]))
    return issues
