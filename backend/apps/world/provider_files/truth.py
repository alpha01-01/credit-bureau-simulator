"""Each provider's true book for one month, in the standard template (D18).

Reads the world tables and returns one record per facility the provider
should report: every loan with a true month-end state for the period (live
loans, and loans that closed or were written off during the month). Values
are already formatted as the standard requires (whole-number amounts,
YYYYMMDD dates, catalogue codes), so a clean file is these values written out.

How world products map to the standard (ASSUMPTION A-037):

  product              facility type             purpose       collateral
  PERSONAL_LOAN        115 salary loan (salaried) P personal   none
                       122 personal loan (others)
  MORTGAGE             118 mortgage              B home        D building
  AUTO_LOAN            102 auto loan             C asset       L vehicles
  MICRO_LOAN           122 personal loan         P personal    none
  DIGITAL_LOAN         119 non-secured loan      A crisis      none
  BUSINESS_TERM_LOAN   126 term loan             G working cap none
  MICRO_BUSINESS_LOAN  126 term loan             G working cap none

Business loans name the owner as an individual guarantor; consumer loans have none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import connection

from apps.standards.rulebook import DATA_STANDARDS
from apps.standards.submission_template import (
    FileKind,
    asset_classification,
    format_date,
)
from apps.world.models import World

from .details import business_details, person_details

# Fields a provider forgets to refresh when it re-sends last month's extract.
STALE_FIELDS = (
    "LastPaymentAmount",
    "LastPaymentDate",
    "CurBal",
    "AmountInArrears",
    "NDIA",
    "AssetClassification",
    "FacilityStatusCode",
    "FacilityStatusDate",
    "ClosedDate",
    "ClosureReason",
    "WrittenOffAmt",
    "ReasonForWrittenOff",
)

STATUS_CODES = {"ACTIVE": "A", "PAID_OFF": "C", "SETTLED": "T", "WRITTEN_OFF": "W"}
CLOSURE_REASONS = {"PAID_OFF": "D", "SETTLED": "F"}  # end of tenure; early settlement

# product -> (facility type, purpose, security type or "")
PRODUCT_CODES: dict[str, tuple[str, str, str]] = {
    "PERSONAL_LOAN": ("122", "P", ""),
    "MORTGAGE": ("118", "B", "D"),
    "AUTO_LOAN": ("102", "C", "L"),
    "MICRO_LOAN": ("122", "P", ""),
    "DIGITAL_LOAN": ("119", "A", ""),
    "BUSINESS_TERM_LOAN": ("126", "G", ""),
    "MICRO_BUSINESS_LOAN": ("126", "G", ""),
}
SECURITY_COVER = {"D": Decimal("1.4"), "L": Decimal("1.2")}  # security value / loan amount
SALARY_LOAN, PAYROLL_DEDUCTION = "115", "108"


@dataclass(frozen=True)
class TruthRecord:
    loan_id: int
    values: dict[str, str]
    previous: dict[str, str] | None  # last month's values of STALE_FIELDS, if reported then


def whole(value: Decimal | int) -> str:
    """Money as the standard requires: whole units, rounded half up."""
    return str(int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _payment_date(period: date, due_day: int) -> date:
    return period.replace(day=min(due_day, period.day))


def _position(
    period: date,
    disbursed: date,
    due_day: int,
    balance: Decimal,
    arrears: Decimal,
    dpd: int,
    paid: Decimal,
    status: str,
    earlier_payment: tuple[str, str] = ("", ""),
) -> dict[str, str]:
    """The month-end fields of a facility, from its true state."""
    code = STATUS_CODES[status]
    closed = status in CLOSURE_REASONS
    if paid > 0:
        last_amount, last_date = whole(paid), format_date(_payment_date(period, due_day))
    else:
        last_amount, last_date = earlier_payment
    return {
        "LastPaymentAmount": last_amount,
        "LastPaymentDate": last_date,
        "CurBal": "0" if closed else whole(balance),
        "AmountInArrears": "0" if closed else whole(arrears),
        "NDIA": str(min(dpd, 999)),
        "AssetClassification": asset_classification(dpd),
        "FacilityStatusCode": code,
        "FacilityStatusDate": format_date(disbursed if code == "A" else period),
        "ClosedDate": format_date(period) if closed else "",
        "ClosureReason": CLOSURE_REASONS.get(status, ""),
        "WrittenOffAmt": whole(balance) if code == "W" else "",
        "ReasonForWrittenOff": "F" if code == "W" else "",
    }


_ACCOUNT_COLUMNS = """
    l.id, br.code, c.customer_number, l.account_number, l.product, l.currency,
    l.disbursement_date, l.first_due_date, l.maturity_date, l.principal, l.installment,
    l.term_months,
    m.outstanding_balance, m.arrears_amount, m.days_past_due, m.amount_paid, m.status,
    pm.outstanding_balance, pm.arrears_amount, pm.days_past_due, pm.amount_paid, pm.status
"""

_ACCOUNT_JOINS = """
    FROM world_loanmonth m
    JOIN world_loan l ON l.id = m.loan_id
    JOIN world_branch br ON br.id = l.branch_id
    JOIN world_lendercustomer c ON c.id = l.customer_id
    {borrower_join}
    LEFT JOIN world_loanmonth pm
           ON pm.world_id = m.world_id AND pm.loan_id = m.loan_id AND pm.period = %(previous)s
    WHERE m.world_id = %(world)s AND m.lender_id = %(lender)s AND m.period = %(period)s
    ORDER BY br.code, l.account_number
"""

_PERSON = """p.seq_no, p.last_name, p.first_name, p.middle_name, p.date_of_birth, p.gender,
    p.ghana_card, p.phone_primary, p.phone_secondary, p.town, p.employment_type, p.monthly_income"""

_INDIVIDUAL_SQL = (
    "SELECT"
    + _ACCOUNT_COLUMNS
    + ", "
    + _PERSON
    + _ACCOUNT_JOINS.format(borrower_join="JOIN world_person p ON p.id = c.person_id")
)

_COMMERCIAL_SQL = (
    "SELECT"
    + _ACCOUNT_COLUMNS
    + """, b.seq_no, b.registered_name, b.trading_name, b.registration_number, b.tin,
         b.registration_date, b.sector, b.size_band, b.town, b.monthly_revenue, """
    + _PERSON
    + _ACCOUNT_JOINS.format(
        borrower_join="JOIN world_business b ON b.id = c.business_id "
        "JOIN world_person p ON p.id = b.owner_id"
    )
)


def previous_month_end(period: date) -> date:
    return date(period.year, period.month, 1) - timedelta(days=1)


def load_truth(
    world_id: int, lender_id: int, lender_code: str, period: date, kind: FileKind
) -> list[TruthRecord]:
    params: dict[str, int | date] = {
        "world": world_id,
        "lender": lender_id,
        "period": period,
        "previous": previous_month_end(period),
    }
    sql = _INDIVIDUAL_SQL if kind is FileKind.INDIVIDUAL else _COMMERCIAL_SQL
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    seed = World.objects.values_list("seed", flat=True).get(pk=world_id)
    columns = DATA_STANDARDS.at(period).header(kind)
    return [_project(_record(row, kind, seed, period), columns) for row in rows]


def _project(record: TruthRecord, columns: tuple[str, ...]) -> TruthRecord:
    """The record in the columns of the data standard in force for its period (D19).

    The world knows the values of the standard's fields; a field a later
    edition adds is blank until the world is taught to produce it.
    """
    values = {name: record.values.get(name, "") for name in columns}
    previous = (
        {k: v for k, v in record.previous.items() if k in values}
        if record.previous is not None
        else None
    )
    return TruthRecord(record.loan_id, values, previous)


def _record(row: tuple[Any, ...], kind: FileKind, seed: int, period: date) -> TruthRecord:
    (loan_id, branch, customer, account, product, currency, disbursed, first_due, maturity,
     principal, installment, term, bal, arr, dpd, paid, status,
     p_bal, p_arr, p_dpd, p_paid, p_status) = row[:22]  # fmt: skip
    rest = row[22:]
    due_day = first_due.day
    previous_period = previous_month_end(period)
    previous = None
    if p_status is not None:
        previous = _position(
            previous_period, disbursed, due_day, p_bal, p_arr, p_dpd, p_paid, p_status
        )
    earlier = (previous["LastPaymentAmount"], previous["LastPaymentDate"]) if previous else ("", "")

    facility_type, purpose, security = PRODUCT_CODES[product]
    values = {
        "Data": "D",
        "CorrectionIndicator": "0",
        "FacilityAccNum": account,
        "CustomerID": customer,
        "BranchCode": branch,
    }
    if kind is FileKind.INDIVIDUAL:
        (seq, last, first, middle, born, gender, card, phone, phone2, town, employment,
         income) = rest  # fmt: skip
        details = person_details(seed, seq, employment, born, town, period)
        if product == "PERSONAL_LOAN" and employment.startswith("SALARIED"):
            facility_type = "115"
        values |= {
            "NatIDNum": card,
            "VotersIDNum": "",
            "DriverLicNum": "",
            "PassportNum": "",
            "SSNum": details["SSNum"],
            "Gender": gender,
            "MaritalStatus": details["MaritalStatus"],
            "Nationality": details["Nationality"],
            "DOB": format_date(born),
            "Surname": last,
            "FirstName": first,
            "MiddleNames": middle,
            "PrevName": "",
            "CurResAddr1": details["CurResAddr1"],
            "CurResAddr2": details["CurResAddr2"],
            "OwnerOrTenant": details["OwnerOrTenant"],
            "PostAddrLine1": details["PostAddrLine1"],
            "EmailAddress": "",
            "MobileTel1": phone,
            "MobileTel2": phone2,
            "EmpType": details["EmpType"],
            "EmpName": details["EmpName"],
            "Occupation": details["Occupation"],
            "IncomeCurrency": "GHS",
            "Income": whole(income),
            "JointOrSoleAcc": "S",
            "NoParticipantsInAcc": "1",
        }
        guarantor = {
            "NatureOfGuarantor": "103",
            "NameOfComGuarantor": "", "BusRegOfGuarantor": "", "G1Surname": "",
            "G1FirstName": "", "G1NatID": "", "G1Gender": "", "G1DOB": "", "G1Mobile": "",
        }  # fmt: skip
    else:
        (b_seq, name, trading, reg_no, tin, registered, sector, size, b_town, revenue,
         _o_seq, o_last, o_first, _o_middle, o_born, o_gender, o_card, o_phone, _o_phone2,
         _o_town, _o_employment, _o_income) = rest  # fmt: skip
        details = business_details(seed, b_seq, size, sector, b_town)
        values |= {
            "BusRegNum": reg_no,
            "TINum": tin,
            "SectorIndCode": details["SectorIndCode"],
            "SubSecIndCode": details["SubSecIndCode"],
            "BusType": details["BusType"],
            "RegistrationDate": format_date(registered),
            "CommencementDate": format_date(registered),
            "BusinessName": name,
            "TradingName": trading,
            "TurnoverCurrency": "GHS",
            "TurnoverAmount": whole(revenue * 12),
            "CurLocAdd1": details["CurLocAdd1"],
            "CurLocAdd2": details["CurLocAdd2"],
            "PostAddrLine1": details["PostAddrLine1"],
            "EmailAddress": "",
            "OfficeTel1": o_phone,
        }
        # The owner stands as an individual guarantor.
        guarantor = {
            "NatureOfGuarantor": "101", "NameOfComGuarantor": "", "BusRegOfGuarantor": "",
            "G1Surname": o_last, "G1FirstName": o_first, "G1NatID": o_card,
            "G1Gender": o_gender, "G1DOB": format_date(o_born), "G1Mobile": o_phone,
        }  # fmt: skip

    values |= {"OldCustomerID": "", "OldAccountNum": ""}
    values |= {
        "CreditFacilityType": facility_type,
        "PurposeOfFacility": purpose,
        "FacilityTerm": str(term),
        "AmountCurrency": currency,
        "FacilityAmount": whole(principal),
        "DisbursementDate": format_date(disbursed),
        "DisbursementAmt": whole(principal),
        "MaturityDate": format_date(maturity),
        "SchdInstalAmount": whole(installment),
        "RepaymentFreq": "12",
    }
    position = _position(period, disbursed, due_day, bal, arr, dpd, paid, status, earlier)
    values |= {k: position[k] for k in ("LastPaymentAmount", "LastPaymentDate", "CurBal")}
    values["CurBalIndicator"] = "D"
    values |= {k: position[k] for k in ("AssetClassification", "AmountInArrears", "NDIA")}
    values["LegalFlag"] = "101"
    values |= {
        k: position[k]
        for k in ("FacilityStatusCode", "FacilityStatusDate", "ClosedDate", "ClosureReason",
                  "WrittenOffAmt", "ReasonForWrittenOff")
    }  # fmt: skip
    values |= {
        "DateRestructured": "",
        "ReasonForRestructure": "",
        "CreditCollateralInd": "101" if security else "102",
        "SecurityType": security,
        "NatureOfCharge": "A" if security else "",
        "SecurityValue": whole(principal * SECURITY_COVER[security]) if security else "",
        "SpecialCommentsCode": PAYROLL_DEDUCTION if facility_type == SALARY_LOAN else "",
    }
    values |= guarantor
    return TruthRecord(loan_id=loan_id, values=values, previous=previous)
