"""Credit data submission templates and code lists (industry standard, D18).

Source: Credit Reference Bureau Data Standards Committee, Consumer and
Business Credit Data Formats, version 1.1 (July 2012); summarised in
docs/references/data-formats.md. The game uses the standard's column names,
types, lengths, options and codes, cut down to the necessary columns as
approved by the owner (docs/references/template-simplification-proposal.md,
section 11): consumer credit 74 columns, business credit 63.

File conventions (standard):
  * Name: SRN-ReportingDate-DateCreated-Version-Identifier-Sequence.csv
  * CSV with a pipe delimiter, header row first, columns exactly as defined.
  * Dates YYYYMMDD. Money in whole numbers, no separators or decimals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

TEMPLATE_VERSION = "1.1"
DATE_FORMAT = "%Y%m%d"
DELIMITER = "|"

# ASSUMPTION A-014: monthly data is due by this day of the following month.
SUBMISSION_DUE_DAY = 10

# Owner's rule: a valid identifier is mandatory for facilities disbursed from this date.
ID_REQUIRED_FROM = date(2020, 1, 1)

# Resubmission deadlines in working days (standard, "Rejection and Resubmission of Data").
NOTIFY_REJECTION_WITHIN = 2
RESUBMIT_FINANCIAL_WITHIN = 2
RESUBMIT_OTHER_WITHIN = 5


class FileKind(StrEnum):
    INDIVIDUAL = "CONC"  # Consumer Credit data file
    COMMERCIAL = "BUSC"  # Business Credit data file


class Option(StrEnum):
    MANDATORY = "M"
    CONDITIONAL = "C"  # "Required Conditional"
    IF_AVAILABLE = "A"


@dataclass(frozen=True)
class Field:
    name: str
    option: Option
    kind: str  # text | numeric | date | code | phone
    length: int
    code_list: str | None = None

    @property
    def mandatory(self) -> bool:
        return self.option is Option.MANDATORY


M, C, A = Option.MANDATORY, Option.CONDITIONAL, Option.IF_AVAILABLE


def _f(name: str, option: Option, kind: str, length: int, code_list: str | None = None) -> Field:
    return Field(name, option, kind, length, code_list)


_RECORD = (
    _f("Data", M, "code", 1, "Data"),
    _f("CorrectionIndicator", M, "code", 1, "CorrectionIndicator"),
    _f("FacilityAccNum", M, "text", 25),
    _f("CustomerID", M, "text", 25),
    _f("BranchCode", A, "text", 15),
)

_FACILITY = (
    _f("CreditFacilityType", M, "code", 3, "CreditFacilityType"),
    _f("PurposeOfFacility", M, "code", 3, "PurposeOfFacility"),
    _f("FacilityTerm", M, "numeric", 3),
    _f("AmountCurrency", M, "code", 3, "Currency"),
    _f("FacilityAmount", M, "numeric", 15),
    _f("DisbursementDate", M, "date", 8),
    _f("DisbursementAmt", M, "numeric", 15),
    _f("MaturityDate", M, "date", 8),
    _f("SchdInstalAmount", C, "numeric", 15),
    _f("RepaymentFreq", M, "code", 2, "RepaymentFreq"),
    _f("LastPaymentAmount", C, "numeric", 15),
    _f("LastPaymentDate", C, "date", 8),
    _f("CurBal", M, "numeric", 15),
    _f("CurBalIndicator", M, "code", 1, "CurBalIndicator"),
    _f("AssetClassification", A, "code", 1, "AssetClassification"),
    _f("AmountInArrears", M, "numeric", 15),
    _f("NDIA", M, "numeric", 3),
    _f("LegalFlag", A, "code", 3, "LegalFlag"),
    _f("FacilityStatusCode", M, "code", 3, "FacilityStatusCode"),
    _f("FacilityStatusDate", M, "date", 8),
    _f("ClosedDate", C, "date", 8),
    _f("ClosureReason", C, "code", 3, "ClosureReason"),
    _f("WrittenOffAmt", C, "numeric", 15),
    _f("ReasonForWrittenOff", C, "code", 1, "ReasonForWrittenOff"),
    _f("DateRestructured", C, "date", 8),
    _f("ReasonForRestructure", C, "code", 1, "ReasonForRestructure"),
    _f("CreditCollateralInd", M, "code", 3, "CreditCollateralInd"),
    _f("SecurityType", C, "code", 3, "SecurityType"),
    _f("NatureOfCharge", C, "code", 1, "NatureOfCharge"),
    _f("SecurityValue", C, "numeric", 15),
    _f("SpecialCommentsCode", A, "code", 3, "SpecialCommentsCode"),
)

_GUARANTOR = (
    _f("NatureOfGuarantor", M, "code", 3, "NatureOfGuarantor"),
    _f("NameOfComGuarantor", C, "text", 50),
    _f("BusRegOfGuarantor", C, "text", 20),
    _f("G1Surname", C, "text", 60),
    _f("G1FirstName", C, "text", 60),
    _f("G1NatID", C, "text", 20),
    _f("G1Gender", C, "code", 1, "Gender"),
    _f("G1DOB", C, "date", 8),
    _f("G1Mobile", A, "phone", 30),
)

_EARLIER = (
    _f("OldCustomerID", A, "text", 25),
    _f("OldAccountNum", A, "text", 25),
)

INDIVIDUAL_FIELDS: tuple[Field, ...] = (
    *_RECORD,
    _f("NatIDNum", C, "text", 20),
    _f("VotersIDNum", C, "text", 20),
    _f("DriverLicNum", C, "text", 20),
    _f("PassportNum", C, "text", 20),
    _f("SSNum", A, "text", 20),
    _f("Gender", M, "code", 1, "Gender"),
    _f("MaritalStatus", M, "code", 1, "MaritalStatus"),
    _f("Nationality", M, "code", 3, "Country"),
    _f("DOB", M, "date", 8),
    _f("Surname", M, "text", 60),
    _f("FirstName", M, "text", 60),
    _f("MiddleNames", A, "text", 60),
    _f("PrevName", A, "text", 60),
    _f("CurResAddr1", M, "text", 100),
    _f("CurResAddr2", A, "text", 50),
    _f("OwnerOrTenant", M, "code", 1, "OwnerOrTenant"),
    _f("PostAddrLine1", M, "text", 100),
    _f("EmailAddress", A, "text", 150),
    _f("MobileTel1", M, "phone", 30),
    _f("MobileTel2", A, "phone", 30),
    _f("EmpType", M, "code", 3, "EmpType"),
    _f("EmpName", C, "text", 50),
    _f("Occupation", M, "text", 50),
    _f("IncomeCurrency", M, "code", 3, "Currency"),
    _f("Income", M, "numeric", 15),
    _f("JointOrSoleAcc", M, "code", 1, "JointOrSoleAcc"),
    _f("NoParticipantsInAcc", M, "numeric", 2),
    *_EARLIER,
    *_FACILITY,
    *_GUARANTOR,
)

COMMERCIAL_FIELDS: tuple[Field, ...] = (
    *_RECORD,
    _f("BusRegNum", M, "text", 20),
    _f("TINum", M, "text", 20),
    _f("SectorIndCode", A, "code", 3, "SectorIndCode"),
    _f("SubSecIndCode", M, "code", 3, "SubSecIndCode"),
    _f("BusType", M, "code", 3, "BusType"),
    _f("RegistrationDate", M, "date", 8),
    _f("CommencementDate", M, "date", 8),
    _f("BusinessName", M, "text", 50),
    _f("TradingName", A, "text", 50),
    _f("TurnoverCurrency", M, "code", 3, "Currency"),
    _f("TurnoverAmount", M, "numeric", 15),
    _f("CurLocAdd1", M, "text", 100),
    _f("CurLocAdd2", A, "text", 50),
    _f("PostAddrLine1", M, "text", 100),
    _f("EmailAddress", A, "text", 150),
    _f("OfficeTel1", M, "phone", 30),
    *_EARLIER,
    *_FACILITY,
    *_GUARANTOR,
)

FIELDS: dict[FileKind, tuple[Field, ...]] = {
    FileKind.INDIVIDUAL: INDIVIDUAL_FIELDS,
    FileKind.COMMERCIAL: COMMERCIAL_FIELDS,
}
FIELD_BY_NAME: dict[FileKind, dict[str, Field]] = {
    kind: {f.name: f for f in fields} for kind, fields in FIELDS.items()
}

# The fields a record cannot be loaded without, whatever the bureau's rejection
# policy (from the owner's cleanser: the row-level CLEAN gate).
CORE_FIELDS: dict[FileKind, frozenset[str]] = {
    FileKind.INDIVIDUAL: frozenset({
        "FacilityAccNum", "CustomerID", "Surname", "FirstName", "DOB", "FacilityAmount",
        "DisbursementDate", "DisbursementAmt", "MaturityDate", "CurBal",
    }),
    FileKind.COMMERCIAL: frozenset({
        "FacilityAccNum", "CustomerID", "BusinessName", "FacilityAmount", "DisbursementDate",
        "DisbursementAmt", "MaturityDate", "CurBal",
    }),
}  # fmt: skip

# Identifiers that satisfy "at least one ID" for an individual, in matching priority.
INDIVIDUAL_ID_FIELDS = ("NatIDNum", "VotersIDNum", "DriverLicNum", "PassportNum")


def header(kind: FileKind) -> tuple[str, ...]:
    return tuple(f.name for f in FIELDS[kind])


def file_name(srn: str, kind: FileKind, period: date, created: date, sequence: int = 1) -> str:
    return f"{srn}-{period:%Y%m%d}-{created:%Y%m%d}-{TEMPLATE_VERSION}-{kind.value}-{sequence}.csv"


FILE_NAME_PATTERN = re.compile(
    r"(?P<srn>\d{5})-(?P<period>\d{8})-(?P<created>\d{8})-(?P<version>\d+\.\d+)"
    r"-(?P<kind>CONC|BUSC)-(?P<sequence>\d+)\.csv"
)


# --- Code lists (standard appendices; docs/references/data-formats.md, section 4) ----

_SECTORS = {
    "10": "Agriculture, forestry and fishing", "20": "Mining and quarrying",
    "30": "Manufacturing", "40": "Construction", "50": "Electricity, gas and water",
    "60": "Commerce and finance", "70": "Transport, storage and communication",
    "80": "Services",
}  # fmt: skip

_SUB_SECTORS = {
    "101": "Cocoa production", "102": "Livestock breeding", "103": "Poultry farming",
    "104": "Other agriculture", "105": "Forestry", "106": "Logging", "107": "Fishing",
    "201": "Bauxite", "202": "Diamonds", "203": "Gold", "204": "Manganese", "205": "Quarrying",
    "206": "Other mining", "301": "Food, drink and tobacco", "302": "Textiles, clothing and footwear",
    "303": "Sawmilling and wood processing", "304": "Paper and paper products",
    "305": "Chemicals and fertilisers", "306": "Iron and steel", "307": "Boat and ship building",
    "308": "Motor vehicle manufacturing", "309": "Other manufacturing",
    "401": "Construction and works", "402": "Building construction",
    "501": "Electric light and power", "502": "Gas manufacture and distribution",
    "503": "Water supply", "601": "Motor vehicle import", "602": "Machinery and heavy equipment",
    "603": "Other imports", "604": "Cocoa exports", "605": "Timber exports",
    "606": "Other exports", "607": "Hire purchase company", "608": "Insurance company",
    "609": "Building bodies and corporations", "701": "Railway transport", "702": "Road transport",
    "703": "Water transport", "704": "Air transport", "705": "Storage and warehousing",
    "706": "Communications", "801": "Printing and publishing", "802": "Business services",
    "803": "Recreation services", "804": "Personal services", "805": "Salary credit",
    "806": "Other services, including government",
}  # fmt: skip

CODE_LISTS: dict[str, dict[str, str]] = {
    "Data": {"D": "Data record"},
    "CorrectionIndicator": {
        "0": "Normal monthly submission",
        "1": "Correction or replacement",
        "2": "Delete record (with an email giving the reason)",
    },
    "Gender": {"M": "Male", "F": "Female"},
    "MaritalStatus": {"S": "Single", "M": "Married", "D": "Divorced", "W": "Widowed", "P": "Separated"},
    "OwnerOrTenant": {"O": "Owner", "T": "Tenant", "F": "Family owned"},
    "EmpType": {
        "101": "Salaried", "102": "Unemployed", "103": "Student", "104": "Self-employed",
        "105": "Home maker", "106": "Pensioner",
    },
    "JointOrSoleAcc": {"J": "Joint", "S": "Sole"},
    "Currency": {"GHS": "Ghana cedi", "USD": "US dollar", "EUR": "Euro", "GBP": "Pound sterling"},
    # ISO 3166 alpha-3; the countries the simulated market sees.
    "Country": {
        "GHA": "Ghana", "NGA": "Nigeria", "TGO": "Togo", "BFA": "Burkina Faso",
        "CIV": "Cote d'Ivoire", "BEN": "Benin", "LBR": "Liberia", "SLE": "Sierra Leone",
        "GBR": "United Kingdom", "USA": "United States", "CHN": "China", "IND": "India",
        "LBN": "Lebanon",
    },
    "CreditFacilityType": {
        "101": "Agriculture facility", "102": "Auto loan", "103": "Bank guarantee",
        "104": "Bills discounted", "105": "Corporate credit card", "106": "Credit card",
        "107": "Education loan", "108": "Hire purchase", "109": "Housing loan", "110": "Leasing",
        "111": "Letter of credit", "112": "Loan against bank deposit",
        "113": "Loan against provident fund", "114": "Loan against life insurance",
        "115": "Salary or payroll loan", "116": "Loan against shares and securities",
        "117": "Loan to professional", "118": "Mortgage", "119": "Non-secured loan",
        "120": "Other secured loan", "121": "Overdraft", "122": "Personal loan",
        "123": "Pledge loan", "124": "Property loan", "125": "Government loan", "126": "Term loan",
        "127": "Travel finance", "128": "Student loan", "129": "Others",
    },
    "PurposeOfFacility": {
        "A": "Crisis loan", "B": "Home loan", "S": "Study loan", "C": "Other asset acquisition",
        "D": "Project finance", "E": "Capital finance", "F": "Equipment and machinery",
        "G": "Working capital", "H": "Subscription finance", "P": "Personal finance",
        "J": "Trading in securities", "K": "Consolidation loan", "L": "Other",
    },
    "RepaymentFreq": {
        "10": "Weekly", "11": "Bi-monthly", "12": "Monthly", "13": "Quarterly",
        "14": "Tri-annually", "15": "Semi-annually", "16": "Annual", "17": "Variable",
        "18": "Bullet", "19": "Demand (revolving)", "20": "Unspecified", "21": "Balloon",
    },
    "CurBalIndicator": {"D": "Debit", "C": "Credit"},
    "AssetClassification": {
        "A": "Current (up to 30 days)", "B": "31-90 days", "C": "91-180 days",
        "D": "181-360 days", "E": "Over 360 days",
    },
    "LegalFlag": {"101": "No", "102": "Yes"},
    "FacilityStatusCode": {
        "A": "Open/active", "C": "Closed", "D": "Disputed", "E": "Terms extended",
        "L": "Handed over/legal", "N": "Loan against policy", "P": "Paid up",
        "T": "Early settlement", "G": "Charge-off", "Z": "Deceased",
        "R": "Restructured/rescheduled", "B": "Approved, not disbursed", "W": "Written off",
    },
    "ClosureReason": {
        "A": "By the lender, without prejudice", "B": "Balance transfer", "C": "Death",
        "D": "End of tenure", "E": "Merger of facilities", "F": "Early settlement",
        "G": "Court order", "H": "Lost or compromised cards", "J": "Bankruptcy",
        "K": "Restructured/rescheduled",
    },
    "ReasonForWrittenOff": {
        "A": "Part settlement", "B": "Death", "C": "Unable to locate",
        "D": "Government concession", "E": "Bankruptcy", "F": "Other",
    },
    "ReasonForRestructure": {
        "T": "Top-up request", "E": "Irregular repayments", "L": "Loss of job",
        "D": "Business downturn", "F": "Force majeure", "C": "Other",
    },
    "CreditCollateralInd": {"101": "Yes", "102": "No"},
    "SecurityType": {
        "A": "Land", "B": "Shares", "C": "Government securities", "D": "Building",
        "E": "Cash/fixed deposit", "F": "Bank guarantee", "G": "Salary assignment",
        "H": "Terminal benefits", "J": "Bullion", "K": "Plant and machinery", "L": "Vehicles",
        "M": "Corporate guarantee", "N": "Individual guarantee", "P": "Government guarantee",
        "Q": "Others",
    },
    "NatureOfCharge": {"A": "Fixed", "B": "Floating"},
    "SpecialCommentsCode": {
        "101": "Paid by co-maker", "102": "Assumed by another party",
        "103": "Closed at lender's request", "104": "Transferred to another lender",
        "105": "Adjustment pending", "106": "Partial payment agreement",
        "107": "Purchased by another lender", "108": "Payroll deduction",
        "109": "Credit line suspended", "110": "Closed due to refinance",
        "111": "Closed due to transfer", "112": "Paid in full for less than the balance",
        "113": "First payment never received", "114": "Paid from collateral",
        "115": "Interest only",
    },
    "NatureOfGuarantor": {
        "101": "Individual", "102": "Commercial entity",
        "103": "No guarantor (consumer) / individual relationship (business)",
    },
    "BusType": {
        "A": "Sole proprietorship", "B": "Limited partnership", "C": "Company limited by shares",
        "D": "Company limited by guarantee", "E": "Unlimited company", "F": "Cooperative",
        "G": "Foreign/external company", "H": "Consultancy or professional body",
        "J": "Social organisation", "K": "International organisation", "L": "NGO",
    },
    "SectorIndCode": _SECTORS,
    "SubSecIndCode": _SUB_SECTORS,
}  # fmt: skip

CLOSED_STATUS_CODES = frozenset({"C", "T", "P"})
# Statuses of a live facility: everything not closed, written off, charged off or undrawn.
OPEN_STATUS_CODES = frozenset({"A", "D", "E", "L", "N", "R"})
WRITTEN_OFF_STATUS_CODES = frozenset({"W", "G"})
OVERDRAFT = "121"


def asset_classification(ndia: int) -> str:
    """Standard Appendix VIII: classification by days in arrears."""
    if ndia <= 30:
        return "A"
    if ndia <= 90:
        return "B"
    if ndia <= 180:
        return "C"
    if ndia <= 360:
        return "D"
    return "E"


def format_date(value: date) -> str:
    return value.strftime(DATE_FORMAT)


# --- Identifier formats ---------------------------------------------------------

GHANA_CARD_PATTERN = re.compile(r"GHA-(\d{9})-(\d)")


def luhn_check_digit(digits: str) -> int:
    """Luhn mod-10 check digit (ASSUMPTION A-002: used by the Ghana Card number)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def is_valid_ghana_card(value: str) -> bool:
    match = GHANA_CARD_PATTERN.fullmatch(value)
    if match is None:
        return False
    return luhn_check_digit(match.group(1)) == int(match.group(2))
