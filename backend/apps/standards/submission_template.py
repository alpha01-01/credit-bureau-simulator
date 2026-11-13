"""Credit data submission template v0 and code lists.

ASSUMPTION A-012 (template) and A-013 (code lists): placeholders until the real
templates (reference R1) and code lists (reference R2) are available. The
structure follows common bureau practice: one flat file per borrower type per
month, one row per credit facility, borrower details repeated on each row.

Conventions (ASSUMPTION A-012):
  * UTF-8, comma-separated, one header row, field names as below.
  * Dates DD/MM/YYYY. Amounts in the facility currency, two decimals, no
    thousands separators. Mobile numbers 10 digits starting with 0.
  * File name: {PROVIDER_CODE}_{IND|COM}_{YYYYMM}.csv (or .xlsx).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

TEMPLATE_VERSION = "SIMB-T0"
DATE_FORMAT = "%d/%m/%Y"

# ASSUMPTION A-014: monthly data is due by this day of the following month.
SUBMISSION_DUE_DAY = 10


class FileKind(StrEnum):
    INDIVIDUAL = "IND"
    COMMERCIAL = "COM"


@dataclass(frozen=True)
class Field:
    name: str
    mandatory: bool
    kind: str  # text | date | amount | integer | code | phone
    code_list: str | None = None


_ACCOUNT_FIELDS: tuple[Field, ...] = (
    Field("ACCOUNT_NUMBER", True, "text"),
    Field("FACILITY_TYPE", True, "code", "FACILITY_TYPE"),
    Field("CURRENCY", True, "code", "CURRENCY"),
    Field("DISBURSEMENT_DATE", True, "date"),
    Field("MATURITY_DATE", True, "date"),
    Field("ORIGINAL_AMOUNT", True, "amount"),
    Field("INSTALMENT_AMOUNT", True, "amount"),
    Field("REPAYMENT_FREQUENCY", True, "code", "REPAYMENT_FREQUENCY"),
    Field("CURRENT_BALANCE", True, "amount"),
    Field("ARREARS_AMOUNT", True, "amount"),
    Field("DAYS_PAST_DUE", True, "integer"),
    Field("AMOUNT_PAID", True, "amount"),
    Field("ACCOUNT_STATUS", True, "code", "ACCOUNT_STATUS"),
    Field("ASSET_CLASSIFICATION", True, "code", "ASSET_CLASSIFICATION"),
)

INDIVIDUAL_FIELDS: tuple[Field, ...] = (
    Field("REPORTING_DATE", True, "date"),
    Field("PROVIDER_CODE", True, "text"),
    Field("BRANCH_CODE", True, "text"),
    Field("CUSTOMER_NUMBER", True, "text"),
    Field("SURNAME", True, "text"),
    Field("FIRST_NAME", True, "text"),
    Field("MIDDLE_NAMES", False, "text"),
    Field("DATE_OF_BIRTH", True, "date"),
    Field("GENDER", True, "code", "GENDER"),
    Field("GHANA_CARD_NUMBER", True, "text"),
    Field("MOBILE_NUMBER", True, "phone"),
    Field("ALT_MOBILE_NUMBER", False, "phone"),
    Field("REGION", True, "code", "REGION"),
    Field("TOWN", False, "text"),
    Field("EMPLOYMENT_TYPE", False, "code", "EMPLOYMENT_TYPE"),
    *_ACCOUNT_FIELDS,
)

COMMERCIAL_FIELDS: tuple[Field, ...] = (
    Field("REPORTING_DATE", True, "date"),
    Field("PROVIDER_CODE", True, "text"),
    Field("BRANCH_CODE", True, "text"),
    Field("CUSTOMER_NUMBER", True, "text"),
    Field("REGISTERED_NAME", True, "text"),
    Field("TRADING_NAME", False, "text"),
    Field("REGISTRATION_NUMBER", True, "text"),
    Field("TIN", True, "text"),
    Field("REGISTRATION_DATE", False, "date"),
    Field("SECTOR", True, "code", "SECTOR"),
    Field("CONTACT_NUMBER", True, "phone"),
    Field("REGION", True, "code", "REGION"),
    Field("TOWN", False, "text"),
    *_ACCOUNT_FIELDS,
)

FIELDS: dict[FileKind, tuple[Field, ...]] = {
    FileKind.INDIVIDUAL: INDIVIDUAL_FIELDS,
    FileKind.COMMERCIAL: COMMERCIAL_FIELDS,
}


def header(kind: FileKind) -> tuple[str, ...]:
    return tuple(f.name for f in FIELDS[kind])


def file_name(provider_code: str, kind: FileKind, period: date, extension: str) -> str:
    return f"{provider_code}_{kind.value}_{period:%Y%m}.{extension}"


# --- Code lists (ASSUMPTION A-013) -------------------------------------------

CODE_LISTS: dict[str, dict[str, str]] = {
    "FACILITY_TYPE": {
        "TL": "Term loan",
        "MG": "Mortgage",
        "AF": "Asset finance",
        "ML": "Mobile (digital) loan",
    },
    "CURRENCY": {"GHS": "Ghana cedi"},
    "REPAYMENT_FREQUENCY": {"M": "Monthly"},
    "ACCOUNT_STATUS": {
        "AC": "Active",
        "PD": "Closed - paid in full",
        "ES": "Closed - settled early",
        "WO": "Written off",
    },
    # ASSUMPTION A-015: Bank of Ghana prudential classification by days past due.
    "ASSET_CLASSIFICATION": {
        "CUR": "Current (0-29 days past due)",
        "OLEM": "Other loans especially mentioned (30-89)",
        "SUB": "Substandard (90-179)",
        "DBT": "Doubtful (180-359)",
        "LOSS": "Loss (360 and over)",
    },
    "GENDER": {"M": "Male", "F": "Female"},
    "EMPLOYMENT_TYPE": {
        "SALARIED_PUBLIC": "Salaried, public sector",
        "SALARIED_PRIVATE": "Salaried, private sector",
        "SELF_EMPLOYED": "Self-employed",
        "INFORMAL": "Informal sector",
        "RETIRED": "Retired",
        "UNEMPLOYED": "Unemployed",
    },
    "SECTOR": {
        code: code.replace("_", " ").title()
        for code in (
            "AGRICULTURE", "TRADE", "MANUFACTURING", "CONSTRUCTION", "TRANSPORT", "HOSPITALITY",
            "SERVICES", "ICT", "FINANCE", "EDUCATION", "HEALTH", "PUBLIC_ADMINISTRATION", "MINING",
        )
    },
    "REGION": {
        name: name
        for name in (
            "Greater Accra", "Ashanti", "Eastern", "Central", "Western", "Western North", "Volta",
            "Oti", "Northern", "Savannah", "North East", "Upper East", "Upper West", "Bono",
            "Bono East", "Ahafo",
        )
    },
}  # fmt: skip

FACILITY_TYPE_CODES = {
    "TERM_LOAN": "TL",
    "MORTGAGE": "MG",
    "ASSET_FINANCE": "AF",
    "MOBILE_LOAN": "ML",
}
ACCOUNT_STATUS_CODES = {"ACTIVE": "AC", "PAID_OFF": "PD", "SETTLED": "ES", "WRITTEN_OFF": "WO"}
CLOSED_STATUS_CODES = frozenset({"PD", "ES"})


def asset_classification(days_past_due: int) -> str:
    """ASSUMPTION A-015: prudential classification bands."""
    if days_past_due < 30:
        return "CUR"
    if days_past_due < 90:
        return "OLEM"
    if days_past_due < 180:
        return "SUB"
    if days_past_due < 360:
        return "DBT"
    return "LOSS"


def format_date(value: date) -> str:
    return value.strftime(DATE_FORMAT)
