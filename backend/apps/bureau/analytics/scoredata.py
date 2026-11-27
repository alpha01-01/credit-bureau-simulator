"""Scorecard data and building (P3.5; Document 09): the bureau's own data only.

A scorecard is built for one term (short, mid or long) at an observation date T:

* **population**: individual customers with an account of that term reported open at T;
* **outcome** ("bad"): an account of that term 90+ days past due within the window after T
  (D13: 12 months; a shorter window may be chosen while the data is young);
* **features**: what the bureau knew at T, the plan's recommended sets per term, and the
  restricted attribute (gender) if the analyst chooses it.

Each feature is classed into bins, replaced by its weight of evidence, and the model is a
logistic regression on those, fitted on 70% of customers and validated on the rest.
"""

# ruff: noqa: S608  (SQL is built from model table names only, never from input)

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from django.db import connection

from apps.bureau.core.models import (
    AccountObservation,
    CourtJudgment,
    CreditAccount,
    Customer,
    DishonouredCheque,
    Enquiry,
    IndividualProfile,
)
from apps.standards.submission_template import OPEN_STATUS_ON_FILE

from . import scoremath as sm

SHORT, MID, LONG, ALL, COMPOSITE = "SHORT", "MID", "LONG", "ALL", "COMPOSITE"
TERMS = (SHORT, MID, LONG)
# One scorecard for every loan, whatever its term: the plan's comparison for the term scorecards.
BUILDABLE = (*TERMS, ALL)
SHORT_DAYS, MID_DAYS = 92, 366
DEFAULT_DPD = 90
REVOLVING = {"121", "106"}  # overdraft, credit card
SECURED = {"102", "108", "109", "110", "118", "120", "124"}
RESTRICTED = {"gender"}
HOLDOUT_SHARE = 0.3

# Feature -> (description, terms it is recommended for). Values the bureau cannot know are -1.
FEATURES: dict[str, tuple[str, tuple[str, ...]]] = {
    "short_loans_3m": ("Short-term loans taken in the last 3 months", (SHORT,)),
    "short_loans_6m": ("Short-term loans taken in the last 6 months", (SHORT,)),
    "short_on_time_share": ("Share of closed short-term loans never in arrears", (SHORT,)),
    "short_worst_dpd_6m": ("Worst days past due on short-term loans, last 6 months", (SHORT,)),
    "short_lenders_open": ("Lenders with a short-term loan open now (stacking)", (SHORT,)),
    "enquiries_30d": ("Enquiries in the last 30 days", (SHORT,)),
    "short_months_since_first": ("Months since the first short-term loan", (SHORT,)),
    "short_size_trend": ("Recent short-term loan size against earlier ones", (SHORT,)),
    "worst_dpd_12m": ("Worst days past due, last 12 months", (SHORT, MID)),
    "months_since_delinquency": ("Months since last in arrears", (SHORT, MID, LONG)),
    "revolving_utilisation": ("Overdraft and card balances against limits", (MID,)),
    "open_accounts": ("Accounts open now", (MID,)),
    "enquiries_6m": ("Enquiries in the last 6 months", (MID,)),
    "file_age_months": ("Months since the first account on file", (MID,)),
    "short_loans_ever": ("Short-term loans ever (mobile-loan history)", (MID,)),
    "worst_dpd_24m": ("Worst days past due, last 24 months", (LONG,)),
    "oldest_account_months": ("Age of the oldest account, months", (LONG,)),
    "secured_share": ("Share of open balances that are secured", (LONG,)),
    "instalment_burden": ("Instalments against open balances", (LONG,)),
    "cheques_and_judgments": ("Dishonoured cheques and court judgments", (LONG,)),
    "facilities_ever": ("Facilities ever on file", (LONG,)),
    "gender": ("Gender (restricted: may not be used to decide credit)", ()),
}


def recommended(term: str) -> list[str]:
    if term == ALL:
        return [name for name, (_, terms) in FEATURES.items() if terms]
    return [name for name, (_, terms) in FEATURES.items() if term in terms]


def _in(term: str, account_term: str) -> bool:
    return term == ALL or account_term == term


def term_of(disbursed: date | None, maturity: date | None, facility_type: str) -> str:
    if facility_type in REVOLVING or disbursed is None or maturity is None:
        return MID
    days = (maturity - disbursed).days
    return SHORT if days <= SHORT_DAYS else MID if days <= MID_DAYS else LONG


def months_back(day: date, months: int) -> date:
    """The month-end ``months`` months before a month-end."""
    first = date(day.year, day.month, 1)
    total = first.year * 12 + first.month - 1 - months + 1
    return date(total // 12, total % 12 + 1, 1) - timedelta(days=1)


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _t(model: Any) -> str:
    return str(model._meta.db_table)


_ACCOUNTS = f"""
SELECT ca.id, ca.customer_id, ca.institution_id, ca.facility_type, ca.disbursement_date,
       ca.maturity_date, ca.original_amount,
       MAX(o.days_past_due) FILTER (WHERE o.reporting_date <= %(t)s AND o.reporting_date > %(t6)s),
       MAX(o.days_past_due) FILTER (WHERE o.reporting_date <= %(t)s AND o.reporting_date > %(t12)s),
       MAX(o.days_past_due) FILTER (WHERE o.reporting_date <= %(t)s AND o.reporting_date > %(t24)s),
       MAX(o.days_past_due) FILTER (WHERE o.reporting_date <= %(t)s),
       MAX(o.reporting_date) FILTER (WHERE o.reporting_date <= %(t)s AND o.days_past_due > 0),
       MAX(o.reporting_date) FILTER (WHERE o.reporting_date <= %(t)s),
       (ARRAY_AGG(o.facility_status ORDER BY o.reporting_date DESC)
            FILTER (WHERE o.reporting_date <= %(t)s))[1],
       (ARRAY_AGG(o.outstanding_balance ORDER BY o.reporting_date DESC)
            FILTER (WHERE o.reporting_date <= %(t)s))[1],
       (ARRAY_AGG(o.instalment_amount ORDER BY o.reporting_date DESC)
            FILTER (WHERE o.reporting_date <= %(t)s))[1],
       (ARRAY_AGG(o.days_past_due ORDER BY o.reporting_date DESC)
            FILTER (WHERE o.reporting_date <= %(t)s))[1],
       MAX(o.days_past_due) FILTER (WHERE o.reporting_date > %(t)s AND o.reporting_date <= %(w)s)
FROM {_t(CreditAccount)} ca
JOIN {_t(Customer)} c ON c.id = ca.customer_id AND c.customer_type = 'INDIVIDUAL'
JOIN {_t(AccountObservation)} o ON o.credit_account_id = ca.id AND o.is_current
WHERE ca.organization_id = %(org)s AND ca.disbursement_date <= %(w)s
GROUP BY ca.id
"""


@dataclass
class _Account:
    customer: int
    lender: int
    facility_type: str
    term: str
    disbursed: date
    amount: float
    worst6: int
    worst12: int
    worst24: int
    worst_ever: int
    last_delinquent: date | None
    last_seen: date | None
    status: str | None
    balance: float
    instalment: float
    dpd_now: int
    worst_after: int


@dataclass
class Dataset:
    term: str
    observation: date
    window_end: date
    customers: np.ndarray
    bad: np.ndarray
    features: dict[str, np.ndarray] = field(default_factory=dict)
    # Whether each customer has an account of each term open at the observation date.
    present: dict[str, np.ndarray] = field(default_factory=dict)


def _accounts(organization_id: int, t: date, window_end: date) -> list[_Account]:
    params: dict[str, Any] = {
        "org": organization_id, "t": t, "w": window_end,
        "t6": months_back(t, 6), "t12": months_back(t, 12), "t24": months_back(t, 24),
    }  # fmt: skip
    with connection.cursor() as cursor:
        cursor.execute(_ACCOUNTS, params)
        rows = cursor.fetchall()
    return [
        _Account(
            customer=row[1],
            lender=row[2],
            facility_type=row[3],
            term=term_of(row[4], row[5], row[3]),
            disbursed=row[4],
            amount=float(row[6]),
            worst6=row[7] or 0,
            worst12=row[8] or 0,
            worst24=row[9] or 0,
            worst_ever=row[10] or 0,
            last_delinquent=row[11],
            last_seen=row[12],
            status=row[13],
            balance=float(row[14] or 0),
            instalment=float(row[15] or 0),
            dpd_now=row[16] or 0,
            worst_after=row[17] or 0,
        )
        for row in rows
        if row[4] is not None
    ]


def _counts(
    organization_id: int, model: Any, date_column: str, since: date, t: date
) -> dict[int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT customer_id, count(*) FROM {_t(model)} WHERE organization_id = %s "
            f"AND customer_id IS NOT NULL AND {date_column} > %s AND {date_column} <= %s "
            "GROUP BY customer_id",
            [organization_id, since, t],
        )
        return dict(cursor.fetchall())


def dataset(
    organization_id: int, term: str, t: date, window_months: int, scoring: bool = False
) -> Dataset:
    """The population, outcome and every feature for one term at observation date ``t``.

    ``scoring`` is for scoring rather than building (P3.6): everyone with an account on
    file at ``t``, those in default included, and no outcome.
    """
    window_end = months_back(t, -window_months)
    accounts = _accounts(organization_id, t, window_end)
    known = [a for a in accounts if a.disbursed <= t]
    by_customer: dict[int, list[_Account]] = defaultdict(list)
    for a in known:
        by_customer[a.customer].append(a)
    later: dict[int, list[_Account]] = defaultdict(list)
    for a in accounts:
        later[a.customer].append(a)

    def open_now(a: _Account) -> bool:
        return a.last_seen == t and a.status in OPEN_STATUS_ON_FILE

    # Customers already in default at T are left out (they are not a prediction), as the
    # world's "first default" also counts only new defaults (P3.5).
    population = sorted(
        c
        for c, accts in by_customer.items()
        if any(_in(term, a.term) and open_now(a) for a in accts)
        and not any(open_now(a) and a.dpd_now >= DEFAULT_DPD for a in accts)
    )
    if scoring:
        population = sorted(by_customer)
    bad = np.array(
        [
            any(_in(term, a.term) and a.worst_after >= DEFAULT_DPD for a in later[c])
            for c in population
        ],
        dtype=bool,
    )
    enquiries_30d = _counts(
        organization_id, Enquiry, "enquired_at::date", t - timedelta(days=30), t
    )
    enquiries_6m = _counts(organization_id, Enquiry, "enquired_at::date", months_back(t, 6), t)
    events: dict[int, int] = defaultdict(int)
    for model, column in ((DishonouredCheque, "date_bounced"), (CourtJudgment, "filing_date")):
        for customer, n in _counts(organization_id, model, column, date(1900, 1, 1), t).items():
            events[customer] += n
    genders = dict(
        IndividualProfile.objects.filter(customer_id__in=population).values_list(
            "customer_id", "gender_code"
        )
    )

    columns: dict[str, list[float]] = {name: [] for name in FEATURES}
    for c in population:
        accts = by_customer[c]
        short = [a for a in accts if a.term == SHORT]
        opened = [a for a in accts if open_now(a)]
        closed_short = [
            a for a in short if a.status is not None and a.status not in OPEN_STATUS_ON_FILE
        ]
        recent = [a.amount for a in short if a.disbursed > months_back(t, 3)]
        earlier = [a.amount for a in short if a.disbursed <= months_back(t, 3)]
        delinquent = [a.last_delinquent for a in accts if a.last_delinquent]
        open_balance = sum(a.balance for a in opened)
        revolving = [a for a in opened if a.facility_type in REVOLVING and a.amount > 0]
        first = min(a.disbursed for a in accts)
        values = {
            "short_loans_3m": sum(a.disbursed > months_back(t, 3) for a in short),
            "short_loans_6m": sum(a.disbursed > months_back(t, 6) for a in short),
            "short_on_time_share": (
                sum(a.worst_ever == 0 for a in closed_short) / len(closed_short)
                if closed_short
                else -1
            ),
            "short_worst_dpd_6m": max((a.worst6 for a in short), default=-1),
            "short_lenders_open": len({a.lender for a in short if open_now(a)}),
            "enquiries_30d": enquiries_30d.get(c, 0),
            "short_months_since_first": (
                months_between(min(a.disbursed for a in short), t) if short else -1
            ),
            "short_size_trend": (
                (sum(recent) / len(recent)) / (sum(earlier) / len(earlier))
                if recent and earlier
                else -1
            ),
            "worst_dpd_12m": max(a.worst12 for a in accts),
            "months_since_delinquency": months_between(max(delinquent), t) if delinquent else 99,
            "revolving_utilisation": (
                sum(a.balance for a in revolving) / sum(a.amount for a in revolving)
                if revolving
                else -1
            ),
            "open_accounts": len(opened),
            "enquiries_6m": enquiries_6m.get(c, 0),
            "file_age_months": months_between(first, t),
            "short_loans_ever": len(short),
            "worst_dpd_24m": max(a.worst24 for a in accts),
            "oldest_account_months": months_between(first, t),
            "secured_share": (
                sum(a.balance for a in opened if a.facility_type in SECURED) / open_balance
                if open_balance > 0
                else -1
            ),
            "instalment_burden": (
                sum(a.instalment for a in opened) / open_balance if open_balance > 0 else -1
            ),
            "cheques_and_judgments": events.get(c, 0),
            "facilities_ever": len(accts),
            "gender": {"F": 1, "M": 0}.get(genders.get(c, ""), -1),
        }
        for name in FEATURES:
            columns[name].append(float(values[name]))
    return Dataset(
        term=term,
        observation=t,
        window_end=window_end,
        customers=np.array(population, dtype=np.int64),
        bad=bad,
        features={name: np.array(v) for name, v in columns.items()},
        present={
            k: np.array(
                [any(a.term == k and open_now(a) for a in by_customer[c]) for c in population]
            )
            for k in TERMS
        },
    )


# --- Building --------------------------------------------------------------------------------


def split(customers: np.ndarray, seed: int) -> np.ndarray:
    """True for the holdout (validation) customers: a fixed share, chosen by the seed."""
    rng = np.random.default_rng(seed)
    holdout: np.ndarray = rng.random(len(customers)) < HOLDOUT_SHARE
    return holdout


def build(data: Dataset, features: list[str], seed: int) -> dict[str, Any]:
    """Bin, fit, scale and validate a scorecard on ``data``. Returns everything a model
    needs to be stored, shown and applied."""
    if not features:
        raise ValueError("Choose at least one feature")
    unknown = sorted(set(features) - set(FEATURES))
    if unknown:
        raise ValueError(f"Unknown features: {', '.join(unknown)}")
    if len(data.customers) < 100 or data.bad.sum() < 10 or (~data.bad).sum() < 10:
        raise ValueError(
            f"Too little data: {len(data.customers)} customers, {int(data.bad.sum())} in default. "
            "Choose an earlier observation date, a longer window or another term."
        )
    holdout = split(data.customers, seed)
    train = ~holdout
    binnings = [sm.bin_feature(f, data.features[f][train], data.bad[train]) for f in features]
    woe = np.column_stack([b.transform(data.features[b.feature]) for b in binnings])
    intercept, coefficients = sm.fit_logistic(woe[train], data.bad[train].astype(float))
    p_bad = sm.predict_bad(intercept, coefficients, woe)
    scores = sm.score_of(p_bad)

    def measures(mask: np.ndarray) -> dict[str, float | int | None]:
        return {
            "customers": int(mask.sum()),
            "bads": int(data.bad[mask].sum()),
            "auc": finite(sm.auc(data.bad[mask], p_bad[mask])),
            "gini": finite(sm.gini(data.bad[mask], p_bad[mask])),
            "ks": finite(sm.ks(data.bad[mask], p_bad[mask])),
        }

    points = [
        {
            "feature": b.feature,
            "description": FEATURES[b.feature][0],
            "iv": round(b.iv, 4),
            "coefficient": round(float(coef), 4),
            "bins": [
                {
                    "upper": None if edge == float("inf") else edge,
                    "goods": g,
                    "bads": bd,
                    "woe": w,
                    "points": round(-float(coef) * w * sm.FACTOR, 1),
                }
                for edge, g, bd, w in zip(b.edges, b.goods, b.bads, b.woe, strict=True)
            ],
        }
        for b, coef in zip(binnings, coefficients, strict=True)
    ]
    return {
        "term": data.term,
        "observation": data.observation.isoformat(),
        "window_end": data.window_end.isoformat(),
        "features": features,
        "intercept": intercept,
        "coefficients": [float(c) for c in coefficients],
        "binnings": [
            {"feature": b.feature, "edges": stored_edges(b.edges), "woe": b.woe} for b in binnings
        ],
        "characteristics": points,
        "train": measures(train),
        "holdout": measures(holdout),
        "score_bands": _bands(scores, data.bad),
        "fairness": fairness(data, features, scores),
        "scores": {
            "customers": data.customers.tolist(),
            "scores": scores.tolist(),
            "holdout": holdout.tolist(),
        },
    }


def _bands(scores: np.ndarray, bad: np.ndarray) -> list[dict[str, Any]]:
    """Customers and bad rate in each risk band (bands run from their floor to the next's)."""
    rows = []
    ceiling = sm.SCORE_MAX + 1
    for code, floor, label in sm.BANDS:  # highest band first
        in_band = (scores >= floor) & (scores < ceiling)
        rows.append({
            "band": code, "label": label, "from": floor, "customers": int(in_band.sum()),
            "bad_rate": float(bad[in_band].mean()) if in_band.any() else None,
        })  # fmt: skip
        ceiling = floor
    return rows


PROXY_IV = 0.1  # a feature this predictive of the restricted attribute stands in for it


def fairness(data: Dataset, features: list[str], scores: np.ndarray) -> dict[str, Any]:
    """Restricted attributes used, likely proxies, and outcomes by group (gender)."""
    gender = data.features["gender"]
    known = gender >= 0
    female = (gender == 1)[known]
    proxies = []
    for f in features:
        if f in RESTRICTED or not known.any() or female.all() or not female.any():
            continue
        iv = sm.bin_feature(f, data.features[f][known], female).iv
        if iv >= PROXY_IV:
            proxies.append({"feature": f, "iv_for_gender": round(iv, 4)})
    groups = []
    for code, label in ((1, "Women"), (0, "Men")):
        mask = gender == code
        if mask.any():
            groups.append({
                "group": label, "customers": int(mask.sum()),
                "mean_score": round(float(scores[mask].mean()), 1),
                "score_600_or_more": round(float((scores[mask] >= sm.BASE_SCORE).mean()), 4),
                "default_rate": round(float(data.bad[mask].mean()), 4),
            })  # fmt: skip
    return {
        "restricted_used": sorted(RESTRICTED & set(features)),
        "proxies": proxies,
        "groups": groups,
    }


def stored_edges(edges: list[float]) -> list[float | None]:
    """Bin edges as JSON can hold them: the open top edge (infinity) as null."""
    return [None if e == float("inf") else e for e in edges]


def loaded_edges(edges: list[float | None]) -> list[float]:
    return [float("inf") if e is None else float(e) for e in edges]


def finite(value: float) -> float | None:
    """A measure rounded for storage, or None where it is undefined (one class only)."""
    return None if value != value else round(value, 4)  # NaN is not equal to itself


def stored_binning(b: dict[str, Any]) -> sm.Binning:
    woe = b["woe"]
    return sm.Binning(b["feature"], loaded_edges(b["edges"]), woe, [0] * len(woe), [0] * len(woe))


def apply(model: dict[str, Any], data: Dataset) -> np.ndarray:
    """A stored model's scores for the customers of ``data``."""
    columns = []
    for b in model["binnings"]:
        columns.append(stored_binning(b).transform(data.features[b["feature"]]))
    woe = np.column_stack(columns)
    return sm.score_of(sm.predict_bad(model["intercept"], np.array(model["coefficients"]), woe))
