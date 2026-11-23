"""Mobile loans (P3.3; Document 09; owner's answers of 23 November 2026).

Banks, savings and loans companies, microfinance lenders and digital lenders
lend small sums through mobile money: GHS 10 to GHS 20,000, for a week to three
months, repaid in one payment (a bullet) with a flat fee. They are the most
numerous loans in the market. This module adds them to a world as a stream of
its own, beside the monthly loan engine, which it leaves untouched: a world
generated without mobile loans is exactly the world it always was.

Each month is generated from the seed and that month alone (with each person's
fixed traits and the month's economic stress), so a world advanced by a month
regenerates the same history. Numbers are given in creation order per lender, in
series of their own (a mobile wallet customer and account), so they never
depend on the monthly engine's numbering. ASSUMPTION A-073 for every parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import LenderProfile, WorldConfig
from .engine import ACTIVE, ONE_DAY, ONE_MONTH, PAID_OFF, WRITTEN_OFF, sigmoid
from .population import People
from .rng import stream

PRODUCT = "MOBILE_LOAN"
FACILITY_TYPE = "122"  # personal loan: what lenders mostly use (owner, 23 November 2026)

# Lenders with a mobile product, and their share of the mobile market (A-073).
MOBILE_LENDERS: dict[str, float] = {
    "SWC": 0.30, "QLD": 0.22, "ATB": 0.14, "MRB": 0.12, "UNS": 0.12, "HZF": 0.10,
}  # fmt: skip

USER_SHARE = 0.30  # adults who borrow on mobile money at all
EXTRA_LENDER = 0.25  # chance of each of two more lenders (stacking: 1 to 3 lenders)
MONTHLY_PROPENSITY = (0.25, 0.85)  # a user's chance of borrowing in a month
EXTRA_LOANS = 0.30  # mean further loans in a month a user borrows (Poisson), at most 3
MIN_CEDIS, MAX_CEDIS = 10, 20_000
SIZE_OF_INCOME = 0.12  # a user's typical loan, as a share of monthly income
SIZE_BOUNDS = (30, 2_000)  # cedis: the typical loan, before the spread
SIZE_SPREAD = 0.7  # log-normal sd of one loan around the user's typical loan
TERMS = np.array([7, 14, 30, 60, 90])  # days
TERM_SHARES = np.array([0.30, 0.25, 0.30, 0.10, 0.05])
FEES = np.array([0.04, 0.06, 0.09, 0.15, 0.20])  # flat fee, share of the amount, by term
DEFAULT = (-3.1, 1.2, 1.5)  # intercept, risk, stress: never repaid
LATE = (-1.6, 0.6)  # intercept, risk: repaid, but late
LATE_DAYS_MEAN = 12  # days late, geometric, at most 60
WRITE_OFF_DAYS = 120  # a defaulted mobile loan is written off this many days past due


@dataclass
class MobileLoans:
    """Every mobile loan the world ever made, in creation order."""

    lender: np.ndarray  # index into config.lenders
    person: np.ndarray  # index into People
    customer_seq: np.ndarray  # per-lender mobile customer number
    account_seq: np.ndarray  # per-lender mobile account number
    month: np.ndarray  # index into the simulated months of origination
    disbursed: np.ndarray  # datetime64[D]
    due: np.ndarray  # datetime64[D]
    term_days: np.ndarray
    principal: np.ndarray  # pesewas
    fee: np.ndarray  # pesewas
    repaid: np.ndarray  # datetime64[D]; NaT if never repaid
    written_off: np.ndarray  # datetime64[D]; NaT if repaid

    @property
    def n(self) -> int:
        return len(self.lender)

    @property
    def owed(self) -> np.ndarray:
        result: np.ndarray = self.principal + self.fee
        return result

    def terminal(self) -> np.ndarray:
        """The day each loan ended: repaid or written off."""
        result: np.ndarray = np.where(np.isnat(self.repaid), self.written_off, self.repaid)
        return result


@dataclass
class MobileMonth:
    """Month-end state of the mobile loans that have one in a given month."""

    loan: np.ndarray  # index into MobileLoans
    status: np.ndarray  # ACTIVE, PAID_OFF or WRITTEN_OFF (engine codes)
    outstanding: np.ndarray  # pesewas
    principal_balance: np.ndarray
    arrears: np.ndarray
    dpd: np.ndarray
    paid: np.ndarray
    k_due: np.ndarray
    k_paid: np.ndarray


def mobile_lenders(config: WorldConfig) -> tuple[np.ndarray, np.ndarray]:
    """Indices into config.lenders of the mobile lenders, and their market shares."""
    codes = [lp.code for lp in config.lenders]
    present = [(codes.index(c), w) for c, w in MOBILE_LENDERS.items() if c in codes]
    index = np.array([i for i, _ in present], dtype=np.int64)
    weight = np.array([w for _, w in present], dtype=np.float64)
    return index, weight / weight.sum()


def _traits(config: WorldConfig, people: People) -> dict[str, np.ndarray]:
    """Who borrows on mobile money, how often, from which lenders, and how much."""
    rng = stream(config.seed, "mobile-traits")
    n = people.n
    user = rng.random(n) < USER_SHARE
    propensity = rng.uniform(*MONTHLY_PROPENSITY, n)
    lender_index, share = mobile_lenders(config)
    k = len(lender_index)
    # Each user's lenders: a first by market share, then up to two more (stacking).
    first = rng.choice(k, size=n, p=share)
    more = rng.random((n, 2)) < EXTRA_LENDER
    second = rng.choice(k, size=n, p=share)
    third = rng.choice(k, size=n, p=share)
    lenders = np.stack([first, np.where(more[:, 0], second, first), np.where(more[:, 1], third, first)], axis=1)  # fmt: skip
    income_cedis = people.income.astype(np.float64) / 100
    typical = np.clip(income_cedis * SIZE_OF_INCOME, *SIZE_BOUNDS)
    return {
        "user": user,
        "propensity": propensity,
        "lenders": lender_index[lenders],
        "typical": typical,
    }


def generate(
    config: WorldConfig, people: People, months: np.ndarray, stress: np.ndarray
) -> MobileLoans:
    """Every mobile loan of the simulated months, month by month."""
    traits = _traits(config, people)
    users = np.flatnonzero(traits["user"])
    parts: dict[str, list[np.ndarray]] = {}
    customer_seq: dict[tuple[int, int], int] = {}  # (lender, person) -> number
    next_customer = [0] * len(config.lenders)
    next_account = [0] * len(config.lenders)
    for t, month in enumerate(months):
        rng = stream(config.seed, "mobile-month", t)
        borrows = rng.random(len(users)) < traits["propensity"][users]
        who = users[borrows]
        count = 1 + np.minimum(rng.poisson(EXTRA_LOANS, len(who)), 3)
        person = np.repeat(who, count)
        n = len(person)
        if n == 0:
            continue
        lender = traits["lenders"][person, rng.integers(0, 3, n)]
        start = month.astype("datetime64[D]")
        days_in_month = int(((month + ONE_MONTH).astype("datetime64[D]") - start).astype(int))
        disbursed = start + rng.integers(0, days_in_month, n).astype("timedelta64[D]")
        term = TERMS[rng.choice(len(TERMS), size=n, p=TERM_SHARES)]
        fee_rate = FEES[np.searchsorted(TERMS, term)]
        size = traits["typical"][person] * np.exp(rng.normal(0.0, SIZE_SPREAD, n))
        cedis = np.clip(np.rint(size), MIN_CEDIS, MAX_CEDIS).astype(np.int64)
        principal = cedis * 100
        fee = np.rint(principal * fee_rate).astype(np.int64)
        due = disbursed + term.astype("timedelta64[D]")
        risk = people.risk_z[person]
        defaulted = rng.random(n) < sigmoid(DEFAULT[0] + DEFAULT[1] * risk + DEFAULT[2] * stress[t])
        late = ~defaulted & (rng.random(n) < sigmoid(LATE[0] + LATE[1] * risk))
        late_days = np.minimum(rng.geometric(1 / LATE_DAYS_MEAN, n), 60)
        repaid = np.where(
            defaulted,
            np.datetime64("NaT", "D"),
            due + np.where(late, late_days, 0).astype("timedelta64[D]"),
        )
        written_off = np.where(
            defaulted, due + np.timedelta64(WRITE_OFF_DAYS, "D"), np.datetime64("NaT", "D")
        )
        c_seq = np.empty(n, dtype=np.int64)
        a_seq = np.empty(n, dtype=np.int64)
        for j, (lend, who_j) in enumerate(zip(lender.tolist(), person.tolist(), strict=True)):
            key = (lend, who_j)
            if key not in customer_seq:
                next_customer[lend] += 1
                customer_seq[key] = next_customer[lend]
            c_seq[j] = customer_seq[key]
            next_account[lend] += 1
            a_seq[j] = next_account[lend]
        for name, values in (
            ("lender", lender), ("person", person), ("customer_seq", c_seq),
            ("account_seq", a_seq), ("month", np.full(n, t, dtype=np.int32)),
            ("disbursed", disbursed), ("due", due), ("term_days", term),
            ("principal", principal), ("fee", fee), ("repaid", repaid),
            ("written_off", written_off),
        ):  # fmt: skip
            parts.setdefault(name, []).append(values)
    if not parts:
        empty = np.zeros(0, dtype=np.int64)
        nat = np.zeros(0, dtype="datetime64[D]")
        return MobileLoans(
            empty, empty, empty, empty, empty, nat, nat, empty, empty, empty, nat, nat
        )
    return MobileLoans(**{k: np.concatenate(v) for k, v in parts.items()})


def month_end_state(loans: MobileLoans, months: np.ndarray, t: int) -> MobileMonth:
    """The month-end state of every mobile loan alive during month ``t``.

    A loan has a row in each month from its disbursement to the month it ends:
    repaid (status PAID_OFF, the amount paid that month) or written off. Open
    after its due date, the whole amount is in arrears and days past due count
    from the due date.
    """
    start = months[t].astype("datetime64[D]")
    end = (months[t] + ONE_MONTH).astype("datetime64[D]") - ONE_DAY
    ended = loans.terminal()
    alive = (loans.disbursed <= end) & (ended >= start)
    idx = np.flatnonzero(alive)
    repaid_now = ~np.isnat(loans.repaid[idx]) & (loans.repaid[idx] <= end)
    off_now = ~np.isnat(loans.written_off[idx]) & (loans.written_off[idx] <= end)
    owed = loans.owed[idx]
    overdue = end > loans.due[idx]
    dpd = np.where(overdue, (end - loans.due[idx]).astype(np.int64), 0)
    status = np.where(repaid_now, PAID_OFF, np.where(off_now, WRITTEN_OFF, ACTIVE))
    open_ = status == ACTIVE
    dpd = np.where(off_now, WRITE_OFF_DAYS, np.where(open_, dpd, 0))
    return MobileMonth(
        loan=idx,
        status=status.astype(np.int8),
        outstanding=np.where(open_ | off_now, owed, 0),
        principal_balance=np.where(open_ | off_now, loans.principal[idx], 0),
        arrears=np.where((open_ & overdue) | off_now, owed, 0),
        dpd=dpd.astype(np.int32),
        paid=np.where(repaid_now, owed, 0),
        k_due=(end >= loans.due[idx]).astype(np.int32),
        k_paid=repaid_now.astype(np.int32),
    )


def customer_prefix(lender: LenderProfile) -> str:
    """Mobile wallet customers have a series of their own at each lender (A-073)."""
    return f"{lender.customer_prefix}M"


def account_prefix(lender: LenderProfile) -> str:
    return f"{lender.account_prefix}M"
