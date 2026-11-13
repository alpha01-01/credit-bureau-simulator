"""Each provider's true book for one month, in template form.

Reads the world tables and returns one record per facility the provider
should report: every loan with a true month-end state for the period (live
loans, and loans that closed or were written off during the month). Values
are already formatted as the template requires, so a clean file is simply
these values written out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import connection

from apps.standards.submission_template import (
    ACCOUNT_STATUS_CODES,
    FACILITY_TYPE_CODES,
    FileKind,
    asset_classification,
    format_date,
)

# Fields that a provider forgets to refresh when it re-sends last month's extract.
STALE_FIELDS = (
    "CURRENT_BALANCE",
    "ARREARS_AMOUNT",
    "DAYS_PAST_DUE",
    "AMOUNT_PAID",
    "ACCOUNT_STATUS",
    "ASSET_CLASSIFICATION",
)


@dataclass(frozen=True)
class TruthRecord:
    loan_id: int
    values: dict[str, str]
    previous: dict[str, str] | None  # last month's values of STALE_FIELDS, if reported then


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _state(
    balance: Decimal, arrears: Decimal, dpd: int, paid: Decimal, status: str
) -> dict[str, str]:
    return {
        "CURRENT_BALANCE": _money(balance),
        "ARREARS_AMOUNT": _money(arrears),
        "DAYS_PAST_DUE": str(dpd),
        "AMOUNT_PAID": _money(paid),
        "ACCOUNT_STATUS": ACCOUNT_STATUS_CODES[status],
        "ASSET_CLASSIFICATION": asset_classification(dpd),
    }


_ACCOUNT_COLUMNS = """
    l.id, br.code, c.customer_number, l.account_number, l.facility_type, l.currency,
    l.disbursement_date, l.maturity_date, l.principal, l.installment,
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

_INDIVIDUAL_SQL = (
    "SELECT"
    + _ACCOUNT_COLUMNS
    + """, p.last_name, p.first_name, p.middle_name, p.date_of_birth, p.gender, p.ghana_card,
         p.phone_primary, p.phone_secondary, p.region, p.town, p.employment_type"""
    + _ACCOUNT_JOINS.format(borrower_join="JOIN world_person p ON p.id = c.person_id")
)

_COMMERCIAL_SQL = (
    "SELECT"
    + _ACCOUNT_COLUMNS
    + """, b.registered_name, b.trading_name, b.registration_number, b.tin, b.registration_date,
         b.sector, o.phone_primary, b.region, b.town"""
    + _ACCOUNT_JOINS.format(
        borrower_join="JOIN world_business b ON b.id = c.business_id "
        "JOIN world_person o ON o.id = b.owner_id"
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
    return [_record(row, kind, lender_code, period) for row in rows]


def _record(row: tuple[Any, ...], kind: FileKind, lender_code: str, period: date) -> TruthRecord:
    (loan_id, branch, customer, account, facility, currency, disbursed, maturity, principal,
     installment, bal, arr, dpd, paid, status, p_bal, p_arr, p_dpd, p_paid, p_status) = row[:20]  # fmt: skip
    borrower = row[20:]
    values = {
        "REPORTING_DATE": format_date(period),
        "PROVIDER_CODE": lender_code,
        "BRANCH_CODE": branch,
        "CUSTOMER_NUMBER": customer,
    }
    if kind is FileKind.INDIVIDUAL:
        last, first, middle, dob, gender, card, phone, phone2, region, town, employment = borrower
        values |= {
            "SURNAME": last,
            "FIRST_NAME": first,
            "MIDDLE_NAMES": middle,
            "DATE_OF_BIRTH": format_date(dob),
            "GENDER": gender,
            "GHANA_CARD_NUMBER": card,
            "MOBILE_NUMBER": phone,
            "ALT_MOBILE_NUMBER": phone2,
            "REGION": region,
            "TOWN": town,
            "EMPLOYMENT_TYPE": employment,
        }
    else:
        name, trading, reg_no, tin, reg_date, sector, phone, region, town = borrower
        values |= {
            "REGISTERED_NAME": name,
            "TRADING_NAME": trading,
            "REGISTRATION_NUMBER": reg_no,
            "TIN": tin,
            "REGISTRATION_DATE": format_date(reg_date),
            "SECTOR": sector,
            "CONTACT_NUMBER": phone,
            "REGION": region,
            "TOWN": town,
        }
    values |= {
        "ACCOUNT_NUMBER": account,
        "FACILITY_TYPE": FACILITY_TYPE_CODES[facility],
        "CURRENCY": currency,
        "DISBURSEMENT_DATE": format_date(disbursed),
        "MATURITY_DATE": format_date(maturity),
        "ORIGINAL_AMOUNT": _money(principal),
        "INSTALMENT_AMOUNT": _money(installment),
        "REPAYMENT_FREQUENCY": "M",
    }
    values |= _state(bal, arr, dpd, paid, status)
    previous = None if p_status is None else _state(p_bal, p_arr, p_dpd, p_paid, p_status)
    return TruthRecord(loan_id=loan_id, values=values, previous=previous)
