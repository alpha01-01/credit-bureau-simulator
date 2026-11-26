# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Portfolio analytics (P3.4; Document 09): the bureau's own data, by lender, product,
region and vintage, with roll rates and the age of accounts at default.

Everything here is read from the bureau's tables only. It is the bureau's view,
errors and all: accounts it never loaded are missing, and a false merge counts
under the customer it was merged into. The default definition is 90 or more days
past due within 12 months of disbursement (D13).
"""

from __future__ import annotations

import copy
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import connection
from django.db.models import Exists, Max, Min, OuterRef

from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.bureau.providers.models import Institution, InstitutionBranch
from apps.bureau.submissions.models import Submission
from apps.standards.submission_template import CODE_LISTS, OPEN_STATUS_CODES

DEFAULT_DPD = 90  # D13: 90+ days past due ...
DEFAULT_WINDOW_MONTHS = 12  # ... within 12 months of disbursement
ARREARS_DPD = 30
BUCKETS = ("Current", "1-29", "30-59", "60-89", "90+")
CLOSED = "Closed"
AGE_BANDS = ((0, 3), (4, 6), (7, 12), (13, 24), (25, 10_000))


def bucket(dpd: int) -> str:
    if dpd <= 0:
        return "Current"
    if dpd < 30:
        return "1-29"
    if dpd < 60:
        return "30-59"
    if dpd < 90:
        return "60-89"
    return "90+"


def _t(model: Any) -> str:
    return str(model._meta.db_table)


_ACCOUNTS = f"""
SELECT ca.id, i.institution_code, ca.facility_type, COALESCE(NULLIF(b.region, ''), 'Unknown'),
       ca.disbursement_date
FROM {_t(CreditAccount)} ca
JOIN {_t(Institution)} i ON i.id = ca.institution_id
LEFT JOIN {_t(InstitutionBranch)} b ON b.id = ca.branch_id
WHERE ca.organization_id = %(org)s
"""

_AT_DATES = f"""
SELECT o.credit_account_id, o.reporting_date, o.outstanding_balance, o.days_past_due,
       o.facility_status
FROM {_t(AccountObservation)} o
JOIN {_t(CreditAccount)} ca ON ca.id = o.credit_account_id
WHERE ca.organization_id = %(org)s AND o.is_current AND o.reporting_date = ANY(%(dates)s)
"""

# Accounts reported by the reporting date: one index probe per account (P3.15: a scan of
# every observation took seconds at full size).
_REPORTED = f"""
SELECT ca.id
FROM {_t(CreditAccount)} ca
WHERE ca.organization_id = %(org)s AND EXISTS (
    SELECT 1 FROM {_t(AccountObservation)} o
    WHERE o.credit_account_id = ca.id AND o.is_current AND o.reporting_date <= %(as_of)s
)
"""

# The first month-end each account was reported 90+ days past due.
_FIRST_DEFAULT = f"""
SELECT o.credit_account_id, MIN(o.reporting_date)
FROM {_t(AccountObservation)} o
JOIN {_t(CreditAccount)} ca ON ca.id = o.credit_account_id
WHERE ca.organization_id = %(org)s AND o.is_current AND o.days_past_due >= {DEFAULT_DPD}
  AND o.reporting_date <= %(as_of)s
GROUP BY o.credit_account_id
"""


@dataclass(frozen=True)
class Account:
    institution: str
    product: str
    region: str
    disbursed: date | None


def _loaded(organization_id: int, as_of: date | None = None) -> Any:
    """The bureau's submissions with records on file.

    An observation's reporting date is its submission's reporting month (the pipeline
    sets it so), so the dates the bureau holds are these submissions' periods: found
    from a few hundred submissions rather than every observation (P3.15).
    """
    current = AccountObservation.objects.filter(source_submission=OuterRef("pk"), is_current=True)
    loaded = Submission.objects.filter(organization_id=organization_id).filter(Exists(current))
    return loaded if as_of is None else loaded.filter(reporting_period__lte=as_of)


def reporting_bounds(organization_id: int) -> tuple[date | None, date | None]:
    """The first and the latest reporting dates on file."""
    found = _loaded(organization_id).aggregate(
        first=Min("reporting_period"), last=Max("reporting_period")
    )
    return found["first"], found["last"]


def latest_reporting_date(organization_id: int) -> date | None:
    return reporting_bounds(organization_id)[1]


def lender_latest(organization_id: int, as_of: date) -> dict[str, date]:
    """Each lender's latest reporting date on file, up to ``as_of``."""
    return dict(
        _loaded(organization_id, as_of)
        .values_list("institution__institution_code")
        .annotate(latest=Max("reporting_period"))
        .values_list("institution__institution_code", "latest")
    )


def _month_end_before(day: date) -> date:
    return date(day.year, day.month, 1) - timedelta(days=1)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _quarter(day: date | None) -> str:
    if day is None:
        return "Unknown"
    return f"{day.year} Q{(day.month - 1) // 3 + 1}"


def _empty() -> dict[str, Any]:
    return {"as_of": None, "groups": {}, "roll_rates": None, "vintages": [], "age_at_default": []}


# Analytics computed, by (organisation, reporting date, data version): the figures change
# only when observations or accounts are added, and at full size they take seconds to
# compute (P3.15). Observations are never changed in place or made not current, and an
# account changes only in a processing run, which adds observations; ids only grow. So
# the newest observation and account ids name the data, and a hit is exactly what a new
# computation would give.
_CACHE: OrderedDict[tuple[int, date, int, int], dict[str, Any]] = OrderedDict()
_CACHE_SIZE = 32


def _version() -> tuple[int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT (SELECT MAX(id) FROM {_t(AccountObservation)}), "
            f"(SELECT MAX(id) FROM {_t(CreditAccount)})"
        )
        observation, account = cursor.fetchone()
    return observation or 0, account or 0


def portfolio(organization_id: int, as_of: date | None = None) -> dict[str, Any]:
    """The bureau's portfolio analytics at a reporting date (by default, the latest)."""
    as_of = as_of or latest_reporting_date(organization_id)
    if as_of is None:
        return _empty()
    key = (organization_id, as_of, *_version())
    if key not in _CACHE:
        _CACHE[key] = _portfolio(organization_id, as_of)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    _CACHE.move_to_end(key)
    return copy.deepcopy(_CACHE[key])


def _portfolio(organization_id: int, as_of: date) -> dict[str, Any]:
    params: dict[str, Any] = {"org": organization_id, "as_of": as_of}
    with connection.cursor() as cursor:
        cursor.execute(_ACCOUNTS, params)
        accounts = {
            pk: Account(inst, product, region, disbursed)
            for pk, inst, product, region, disbursed in cursor.fetchall()
        }
        # Each lender's latest file: lenders report at different times, so the newest month
        # across the bureau would show only the lenders that have sent it so far.
        latest = lender_latest(organization_id, as_of)
        if not latest:
            return _empty()
        lender_before = {code: _month_end_before(day) for code, day in latest.items()}
        cursor.execute(
            _AT_DATES,
            {**params, "dates": sorted({*latest.values(), *lender_before.values()})},
        )
        state: dict[tuple[int, date], tuple[Decimal, int, str]] = {
            (pk, day): (Decimal(bal), int(dpd), status)
            for pk, day, bal, dpd, status in cursor.fetchall()
        }
        cursor.execute(_REPORTED, params)
        reported = {pk for (pk,) in cursor.fetchall()}
        cursor.execute(_FIRST_DEFAULT, params)
        first_default = dict(cursor.fetchall())
    first_report = reporting_bounds(organization_id)[0]
    if first_report is None:  # cannot be, with a lender's file on record; for the types
        return _empty()
    records_start = first_report.replace(day=1)

    # The live book: accounts open in their lender's latest file.
    live: dict[int, tuple[date, Decimal, int, str]] = {}
    for pk, account in accounts.items():
        day = latest.get(account.institution)
        now = state.get((pk, day)) if day else None
        if day and now and now[2] in OPEN_STATUS_CODES:
            live[pk] = (day, *now)
    dimensions: dict[str, Callable[[Account], str]] = {
        "lender": lambda a: a.institution,
        "product": lambda a: a.product,
        "region": lambda a: a.region,
        "vintage": lambda a: _quarter(a.disbursed),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for name, key_of in dimensions.items():
        tally: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "accounts": 0,
                "balance": Decimal(0),
                "arrears_30": 0,
                "default_90": 0,
                "balance_90": Decimal(0),
            }
        )
        for pk, (_day, balance, dpd, _status) in live.items():
            row = tally[key_of(accounts[pk])]
            row["accounts"] += 1
            row["balance"] += balance
            row["arrears_30"] += dpd >= ARREARS_DPD
            if dpd >= DEFAULT_DPD:
                row["default_90"] += 1
                row["balance_90"] += balance
        groups[name] = [
            {
                "key": key,
                "label": CODE_LISTS["CreditFacilityType"].get(key, key)
                if name == "product"
                else key,
                **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()},
                "arrears_30_share": row["arrears_30"] / row["accounts"],
                "default_90_share": row["default_90"] / row["accounts"],
            }
            for key, row in sorted(tally.items())
        ]

    # Roll rates: last month's arrears bucket against this month's, for accounts open then.
    matrix: dict[str, dict[str, int]] = {b: dict.fromkeys((*BUCKETS, CLOSED), 0) for b in BUCKETS}
    for pk, account in accounts.items():
        if account.institution not in latest:
            continue
        then = state.get((pk, lender_before[account.institution]))
        now = state.get((pk, latest[account.institution]))
        if then is None or now is None or then[2] not in OPEN_STATUS_CODES:
            continue
        to = bucket(now[1]) if now[2] in OPEN_STATUS_CODES else CLOSED
        matrix[bucket(then[1])][to] += 1

    # Vintages: the share of each quarter's accounts in default within 12 months (D13). Only
    # accounts opened since the bureau's records began: earlier first months were never seen.
    vintage: dict[str, dict[str, int]] = defaultdict(
        lambda: {"accounts": 0, "defaulted": 0, "mature": 0, "mature_defaulted": 0}
    )
    ages: dict[tuple[int, int], int] = dict.fromkeys(AGE_BANDS, 0)
    for pk, account in accounts.items():
        if account.disbursed is None or pk not in reported or account.disbursed < records_start:
            continue
        row = vintage[_quarter(account.disbursed)]
        row["accounts"] += 1
        first = first_default.get(pk)
        within = (
            first is not None and _months_between(account.disbursed, first) <= DEFAULT_WINDOW_MONTHS
        )
        row["defaulted"] += within
        if _months_between(account.disbursed, as_of) >= DEFAULT_WINDOW_MONTHS:
            row["mature"] += 1
            row["mature_defaulted"] += within
        if first is not None:
            age = _months_between(account.disbursed, first)
            band = next(b for b in AGE_BANDS if b[0] <= age <= b[1])
            ages[band] += 1
    return {
        "as_of": max(latest.values()).isoformat(),
        "lenders_as_of": {code: day.isoformat() for code, day in sorted(latest.items())},
        "records_start": records_start.isoformat(),
        "default_definition": f"{DEFAULT_DPD}+ days past due within {DEFAULT_WINDOW_MONTHS} months of disbursement",
        "live_accounts": len(live),
        "groups": groups,
        "roll_rates": {"from": list(BUCKETS), "to": [*BUCKETS, CLOSED], "counts": matrix},
        "vintages": [
            {
                "quarter": quarter,
                **row,
                "default_rate": row["mature_defaulted"] / row["mature"] if row["mature"] else None,
                "default_rate_so_far": row["defaulted"] / row["accounts"],
            }
            for quarter, row in sorted(vintage.items())
        ],
        "age_at_default": [
            {"months": f"{lo}-{hi}" if hi < 10_000 else f"{lo}+", "accounts": n}
            for (lo, hi), n in ages.items()
        ],
    }
