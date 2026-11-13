"""Loan book engine: origination and monthly repayment behaviour.

Document 07, Section 7.2. Each month:

1. The economy moves (national stress index).
2. Every active loan with an instalment due is paid, missed, or cured,
   driven by the borrower's hidden risk, debt burden, income stability,
   sector exposure to stress, and current arrears.
3. Loans are paid off, settled early, or written off by their lender.
4. Each lender originates new loans, screening applicants with its own
   (imperfect) view of their risk and, for regulated lenders, affordability.

Loans are amortising with fixed monthly instalments. State is tracked as
instalments due versus instalments paid, from which balances, arrears and
days past due follow exactly. Money is integer pesewas.

The engine is a pure function of the configuration: same seed, same world.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import PRODUCTS, WorldConfig
from .population import Branch, Businesses, People, footprint_mask
from .rng import stream

ACTIVE, PAID_OFF, SETTLED, WRITTEN_OFF = 1, 2, 3, 4
STATUS_NAMES = {
    ACTIVE: "ACTIVE",
    PAID_OFF: "PAID_OFF",
    SETTLED: "SETTLED",
    WRITTEN_OFF: "WRITTEN_OFF",
}

PERSON, BUSINESS = 0, 1

ONE_MONTH = np.timedelta64(1, "M")
ONE_DAY = np.timedelta64(1, "D")

PRODUCT_CODES: tuple[str, ...] = tuple(PRODUCTS)


def sigmoid(x: np.ndarray) -> np.ndarray:
    out: np.ndarray = 1.0 / (1.0 + np.exp(-x))
    return out


def scheduled_balance(
    principal: np.ndarray,
    rate: np.ndarray,
    installment: np.ndarray,
    k: np.ndarray,
    term: np.ndarray,
) -> np.ndarray:
    """Principal outstanding after k instalments of an annuity, in pesewas."""
    growth = np.power(1.0 + rate, k)
    balance = principal * growth - installment * (growth - 1.0) / rate
    balance = np.where(k >= term, 0.0, balance)
    return np.clip(np.rint(balance), 0, None).astype(np.int64)


def annuity_installment(principal: np.ndarray, rate: np.ndarray, term: np.ndarray) -> np.ndarray:
    """Monthly instalment in pesewas, rounded up so the loan amortises fully."""
    factor = rate / (1.0 - np.power(1.0 + rate, -term))
    instalment: np.ndarray = np.ceil(principal * factor).astype(np.int64)
    return instalment


@dataclass
class LoanBook:
    """Growable column store for every loan ever originated."""

    capacity: int = 1024
    n: int = 0
    cols: dict[str, np.ndarray] = field(default_factory=dict)

    SCHEMA = {
        "lender": np.int32,
        "product": np.int32,
        "kind": np.int8,
        "borrower": np.int64,
        "customer": np.int64,
        "branch": np.int64,
        "principal": np.int64,
        "annual_rate": np.float64,
        "rate": np.float64,
        "term": np.int32,
        "installment": np.int64,
        "disbursed": "datetime64[D]",
        "first_due": np.int64,  # absolute month index (months since 1970-01)
        "due_day": np.int64,
        "k_due": np.int32,
        "k_paid": np.int32,
        "status": np.int8,
        "orig_month": np.int32,
        "terminal_month": np.int32,
        "first_90_month": np.int32,
        "lender_seq": np.int64,  # per-lender sequence, for account numbers
    }

    def __post_init__(self) -> None:
        for name, dtype in self.SCHEMA.items():
            self.cols[name] = np.zeros(self.capacity, dtype=np.dtype(dtype))  # type: ignore[call-overload]

    def __getitem__(self, name: str) -> np.ndarray:
        return self.cols[name][: self.n]

    def append(self, values: dict[str, np.ndarray]) -> None:
        count = len(next(iter(values.values())))
        if self.n + count > self.capacity:
            new_cap = max(self.capacity * 2, self.n + count)
            for name, arr in self.cols.items():
                grown = np.zeros(new_cap, dtype=arr.dtype)
                grown[: self.n] = arr[: self.n]
                self.cols[name] = grown
            self.capacity = new_cap
        for name in self.SCHEMA:
            self.cols[name][self.n : self.n + count] = values[name]
        self.n += count


@dataclass
class Snapshots:
    """Month-end state of every loan, for months in the stored history window."""

    parts: dict[str, list[np.ndarray]] = field(default_factory=dict)

    FIELDS = (
        "loan",
        "month",
        "k_due",
        "k_paid",
        "outstanding",
        "principal_balance",
        "arrears",
        "dpd",
        "paid",
        "status",
    )

    def add(self, **arrays: np.ndarray) -> None:
        for name in self.FIELDS:
            self.parts.setdefault(name, []).append(arrays[name])

    def column(self, name: str) -> np.ndarray:
        chunks = self.parts.get(name, [])
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int64)

    def __len__(self) -> int:
        return int(sum(len(c) for c in self.parts.get("loan", [])))


@dataclass
class SimulationResult:
    months: np.ndarray  # datetime64[M], one per simulated month
    history_start: int  # index into months of the first stored month
    stress: np.ndarray  # stress index per month
    book: LoanBook
    customers: list[tuple[int, int, int]]  # (lender, kind, borrower) in creation order
    customer_seq: list[int]  # per-lender sequence number, for customer numbers
    snapshots: Snapshots


class Engine:
    def __init__(
        self, config: WorldConfig, people: People, businesses: Businesses, branches: list[Branch]
    ) -> None:
        self.config = config
        self.people = people
        self.businesses = businesses
        self.behaviour = config.behaviour
        self.lenders = config.lenders
        self.book = LoanBook(capacity=max(1024, config.scale.target_active_loans * 4))
        self.snapshots = Snapshots()
        self.customers: list[tuple[int, int, int]] = []
        self.customer_seq: list[int] = []
        self._customer_index: dict[tuple[int, int, int], int] = {}
        self._lender_customer_count = [0] * len(self.lenders)
        self._lender_loan_count = [0] * len(self.lenders)

        end_month = np.datetime64(config.history_end, "M")
        total = config.total_months
        first_month = end_month - np.timedelta64(total - 1, "M")
        self.months = first_month + np.arange(config.simulated_months).astype("timedelta64[M]")
        self._anchor_t = total - 1  # index of the original history_end month
        self.history_start = config.scale.burn_in_months
        self.stress = self._economy()

        # Branch lookup: (lender, region) -> branch indices; head office as fallback.
        self._branches: dict[tuple[int, int], list[int]] = {}
        self._head_office: dict[int, int] = {}
        for idx, br in enumerate(branches):
            self._branches.setdefault((br.lender, br.region), []).append(idx)
            self._head_office.setdefault(br.lender, idx)

        # Per-borrower attributes used by the behaviour model.
        sector_sens = np.array(list(_sector_sensitivity().values()))
        self._risk = (people.risk_z, businesses.health_z)
        self._income = (people.income, businesses.revenue)
        self._stability = (people.stability, np.full(businesses.n, 0.55))
        self._sensitivity = (sector_sens[people.sector], sector_sens[businesses.sector])
        self._region = (people.region, businesses.region)

        # Origination rates per lender so the book approaches its target size.
        total_weight = sum(lp.book_weight for lp in self.lenders)
        self._target = [
            config.scale.target_active_loans * lp.book_weight / total_weight for lp in self.lenders
        ]
        self._monthly_originations = []
        for lp, target in zip(self.lenders, self._target, strict=True):
            life = sum(
                share
                * (sum(PRODUCTS[p].term_months) / 2)
                * (0.95 if PRODUCTS[p].term_months[1] <= 3 else 0.7)
                for p, share in lp.products.items()
            )
            self._monthly_originations.append(target / max(life, 1.0))

    # -- economy -------------------------------------------------------------

    def _economy(self) -> np.ndarray:
        econ = self.config.economy
        rng = stream(self.config.seed, "economy.stress")
        shocks = rng.standard_normal(len(self.months)) * econ.stress_sigma
        stress = np.zeros(len(self.months))
        level = econ.stress_mean
        for t in range(len(self.months)):
            level = econ.stress_mean + econ.stress_phi * (level - econ.stress_mean) + shocks[t]
            stress[t] = level
        return stress

    # -- main loop -----------------------------------------------------------

    def run(self) -> SimulationResult:
        for t in range(len(self.months)):
            active_before, paid = self._evolve(t)
            first_new = self.book.n
            self._originate(t)
            originated = np.arange(first_new, self.book.n, dtype=np.int64)
            self._record(
                t,
                np.concatenate([active_before, originated]),
                np.concatenate([paid, np.zeros(len(originated), dtype=np.int64)]),
            )
        return SimulationResult(
            months=self.months,
            history_start=self.history_start,
            stress=self.stress,
            book=self.book,
            customers=self.customers,
            customer_seq=self.customer_seq,
            snapshots=self.snapshots,
        )

    # -- monthly repayment behaviour ----------------------------------------

    def _evolve(self, t: int) -> tuple[np.ndarray, np.ndarray]:
        """Apply this month's repayment behaviour.

        Returns the loans active at the start of the month and the amount each paid.
        """
        book = self.book
        if book.n == 0:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        abs_month = int(self.months[t].astype(np.int64))
        period_end = (self.months[t] + ONE_MONTH).astype("datetime64[D]") - ONE_DAY
        bm = self.behaviour
        rng = stream(self.config.seed, "loans.behaviour", t)

        status = book["status"]
        active = np.flatnonzero(status == ACTIVE)
        first_due = book["first_due"][active]
        due_now = active[first_due <= abs_month]
        if len(due_now) == 0:
            return active, np.zeros(len(active), dtype=np.int64)

        idx = due_now
        term = book["term"][idx]
        k_due_old = book["k_due"][idx]
        k_paid_old = book["k_paid"][idx]
        k_due_new = np.clip(abs_month - book["first_due"][idx] + 1, 0, term).astype(np.int32)
        arrears_before = k_due_old - k_paid_old

        kind = book["kind"][idx]
        borrower = book["borrower"][idx]
        z = self._by_kind(kind, borrower, self._risk)
        income = self._by_kind(kind, borrower, self._income).astype(np.float64)
        stability = self._by_kind(kind, borrower, self._stability)
        sensitivity = self._by_kind(kind, borrower, self._sensitivity)
        burden = self._burden(kind, borrower, active) / np.maximum(income, 1.0)
        excess = np.clip(burden - bm.burden_threshold, 0.0, None)
        stress_term = bm.miss_stress * self.stress[t] * sensitivity
        product_shift = np.array([PRODUCTS[p].miss_shift for p in PRODUCT_CODES])[
            book["product"][idx]
        ]

        miss_logit = (
            bm.miss_base
            + bm.miss_risk * z
            + bm.miss_burden * excess
            + stress_term
            - bm.miss_stability * stability
            + product_shift
        )
        p_miss = sigmoid(miss_logit)
        depth = np.maximum(arrears_before - 1, 0)
        p_cure = sigmoid(
            bm.cure_base - bm.cure_depth * depth - bm.cure_risk * z - stress_term + 0.8 * stability
        )
        p_one = sigmoid(
            bm.pay_one_base - bm.pay_one_depth * depth - bm.pay_one_risk * z - stress_term
        )

        u = rng.random(len(idx))
        k_paid_new = k_paid_old.copy()
        current = arrears_before == 0
        new_due = k_due_new > k_due_old

        # Current loans: pay this month's instalment or miss it.
        pays = current & new_due & (u >= p_miss)
        k_paid_new[pays] += 1

        # Loans in arrears: cure fully, pay one instalment, or pay nothing.
        in_arrears = ~current
        cure = in_arrears & (u < p_cure)
        pay_one = in_arrears & ~cure & (u < p_cure + (1 - p_cure) * p_one)
        k_paid_new[cure] = k_due_new[cure]
        k_paid_new[pay_one] = np.minimum(k_paid_old[pay_one] + 1, k_due_new[pay_one])

        paid_count = (k_paid_new - k_paid_old).astype(np.int64)
        installment = book["installment"][idx]
        paid_amount = paid_count * installment

        new_status = np.full(len(idx), ACTIVE, dtype=np.int8)

        # Early settlement by borrowers who are up to date.
        settle_roll = stream(self.config.seed, "loans.settlement", t).random(len(idx))
        up_to_date = (k_paid_new == k_due_new) & (k_paid_new < term)
        settles = up_to_date & (settle_roll < bm.early_settlement) & (k_paid_new >= 1)
        if settles.any():
            remaining = scheduled_balance(
                book["principal"][idx][settles].astype(np.float64),
                book["rate"][idx][settles],
                installment[settles].astype(np.float64),
                k_paid_new[settles],
                term[settles],
            )
            paid_amount[settles] += remaining
            k_paid_new[settles] = term[settles]
            new_status[settles] = SETTLED

        paid_off = (k_paid_new >= term) & (new_status == ACTIVE)
        new_status[paid_off] = PAID_OFF

        # Days past due from the oldest unpaid instalment.
        arrears_count = (k_due_new - k_paid_new).astype(np.int64)
        oldest_month = book["first_due"][idx] + k_paid_new
        oldest_due = oldest_month.astype("datetime64[M]").astype("datetime64[D]") + (
            book["due_day"][idx] - 1
        )
        dpd = np.where(arrears_count > 0, (period_end - oldest_due).astype(np.int64), 0)
        dpd = np.maximum(dpd, 0)

        writeoff_dpd = np.array([lp.writeoff_dpd for lp in self.lenders])[book["lender"][idx]]
        written_off = (dpd >= writeoff_dpd) & (new_status == ACTIVE)
        new_status[written_off] = WRITTEN_OFF

        first_90 = book["first_90_month"][idx]
        newly_90 = (dpd >= 90) & (first_90 < 0)

        cols = book.cols
        cols["k_due"][idx] = k_due_new
        cols["k_paid"][idx] = k_paid_new
        cols["status"][idx] = new_status
        terminal = new_status != ACTIVE
        cols["terminal_month"][idx[terminal]] = t
        cols["first_90_month"][idx[newly_90]] = t

        paid_full = np.zeros(book.n, dtype=np.int64)
        paid_full[idx] = paid_amount
        return active, paid_full[active]

    def _by_kind(
        self, kind: np.ndarray, borrower: np.ndarray, pair: tuple[np.ndarray, np.ndarray]
    ) -> np.ndarray:
        persons, businesses = pair
        out = np.empty(len(kind), dtype=np.result_type(persons.dtype, businesses.dtype))
        is_person = kind == PERSON
        out[is_person] = persons[borrower[is_person]]
        out[~is_person] = businesses[borrower[~is_person]]
        return out

    def _burden(self, kind: np.ndarray, borrower: np.ndarray, active: np.ndarray) -> np.ndarray:
        """Sum of instalments across all of each borrower's active loans."""
        book = self.book
        a_kind = book["kind"][active]
        a_borrower = book["borrower"][active]
        a_inst = book["installment"][active].astype(np.float64)
        person_total = np.bincount(
            a_borrower[a_kind == PERSON], weights=a_inst[a_kind == PERSON], minlength=self.people.n
        )
        business_total = np.bincount(
            a_borrower[a_kind == BUSINESS],
            weights=a_inst[a_kind == BUSINESS],
            minlength=self.businesses.n,
        )
        return self._by_kind(kind, borrower, (person_total, business_total))

    def _record(self, t: int, active_before: np.ndarray, paid: np.ndarray) -> None:
        """Store month-end state for loans active at the start of the month or opened in it."""
        if t < self.history_start or len(active_before) == 0:
            return
        book = self.book
        idx = active_before
        principal_balance = scheduled_balance(
            book["principal"][idx].astype(np.float64),
            book["rate"][idx],
            book["installment"][idx].astype(np.float64),
            book["k_paid"][idx],
            book["term"][idx],
        )
        due_balance = scheduled_balance(
            book["principal"][idx].astype(np.float64),
            book["rate"][idx],
            book["installment"][idx].astype(np.float64),
            book["k_due"][idx],
            book["term"][idx],
        )
        arrears_count = (book["k_due"][idx] - book["k_paid"][idx]).astype(np.int64)
        arrears = arrears_count * book["installment"][idx]
        arrears_interest = np.clip(arrears - (principal_balance - due_balance), 0, None)
        status = book["status"][idx]
        closed = (status == PAID_OFF) | (status == SETTLED)
        outstanding = np.where(closed, 0, principal_balance + arrears_interest)
        principal_balance = np.where(closed, 0, principal_balance)
        arrears = np.where(closed, 0, arrears)

        abs_month = int(self.months[t].astype(np.int64))
        period_end = (self.months[t] + ONE_MONTH).astype("datetime64[D]") - ONE_DAY
        oldest_month = book["first_due"][idx] + book["k_paid"][idx]
        oldest_due = oldest_month.astype("datetime64[M]").astype("datetime64[D]") + (
            book["due_day"][idx] - 1
        )
        dpd = np.where(
            (arrears_count > 0) & ~closed & (book["first_due"][idx] <= abs_month),
            (period_end - oldest_due).astype(np.int64),
            0,
        )
        self.snapshots.add(
            loan=idx.astype(np.int64),
            month=np.full(len(idx), t, dtype=np.int32),
            k_due=book["k_due"][idx].copy(),
            k_paid=book["k_paid"][idx].copy(),
            outstanding=outstanding.astype(np.int64),
            principal_balance=principal_balance.astype(np.int64),
            arrears=arrears.astype(np.int64),
            dpd=np.maximum(dpd, 0).astype(np.int32),
            paid=paid.astype(np.int64),
            status=status.copy(),
        )

    # -- origination ---------------------------------------------------------

    def _originate(self, t: int) -> None:
        month = self.months[t]
        year = int(str(month)[:4])
        months_to_end = self._anchor_t - t  # negative after the original history: growth continues
        econ = self.config.economy
        growth = (1.0 + econ.annual_lending_growth) ** (-months_to_end / 12.0)
        cycle = np.exp(-econ.lending_stress_elasticity * self.stress[t])

        active = np.flatnonzero(self.book["status"] == ACTIVE)
        person_loans = np.bincount(
            self.book["borrower"][active][self.book["kind"][active] == PERSON],
            minlength=self.people.n,
        )
        business_loans = np.bincount(
            self.book["borrower"][active][self.book["kind"][active] == BUSINESS],
            minlength=self.businesses.n,
        )
        burden = (
            np.bincount(
                self.book["borrower"][active][self.book["kind"][active] == PERSON],
                weights=self.book["installment"][active][
                    self.book["kind"][active] == PERSON
                ].astype(np.float64),
                minlength=self.people.n,
            ),
            np.bincount(
                self.book["borrower"][active][self.book["kind"][active] == BUSINESS],
                weights=self.book["installment"][active][
                    self.book["kind"][active] == BUSINESS
                ].astype(np.float64),
                minlength=self.businesses.n,
            ),
        )

        period_start = month.astype("datetime64[D]")
        days_in_month = int(
            ((month + ONE_MONTH).astype("datetime64[D]") - period_start).astype(int)
        )

        for l_idx, lender in enumerate(self.lenders):
            if year < lender.founded:
                continue
            rng = stream(self.config.seed, f"originate.{lender.code}", t)
            expected = self._monthly_originations[l_idx] * growth * cycle
            n_new = int(rng.poisson(expected))
            if n_new == 0:
                continue
            codes = list(lender.products)
            shares = np.array([lender.products[c] for c in codes])
            picks = rng.choice(len(codes), size=n_new, p=shares / shares.sum())
            for c_idx, code in enumerate(codes):
                wanted = int((picks == c_idx).sum())
                if wanted:
                    self._originate_product(
                        t,
                        l_idx,
                        code,
                        wanted,
                        rng,
                        person_loans,
                        business_loans,
                        burden,
                        period_start,
                        days_in_month,
                    )

    def _originate_product(
        self,
        t: int,
        l_idx: int,
        product_code: str,
        wanted: int,
        rng: np.random.Generator,
        person_loans: np.ndarray,
        business_loans: np.ndarray,
        burden: tuple[np.ndarray, np.ndarray],
        period_start: np.datetime64,
        days_in_month: int,
    ) -> None:
        lender = self.lenders[l_idx]
        product = PRODUCTS[product_code]
        kind = PERSON if product.borrower == "INDIVIDUAL" else BUSINESS

        if kind == PERSON:
            region = self.people.region
            base_weight = self.people.credit_demand * np.exp(-0.5 * person_loans)
            age_days = (period_start - self.people.birth_date).astype(np.int64)
            max_age = 55 if product_code == "MORTGAGE" else 70
            eligible = (age_days >= 18 * 365) & (age_days <= max_age * 365)
            income = self.people.income.astype(np.float64)
            risk = self.people.risk_z
            existing = burden[0]
        else:
            region = self.businesses.region
            base_weight = np.exp(-0.7 * business_loans)
            eligible = np.ones(self.businesses.n, dtype=bool)
            income = self.businesses.revenue.astype(np.float64)
            risk = self.businesses.health_z
            existing = burden[1]

        mask = footprint_mask(lender, region) & eligible
        pool = np.flatnonzero(mask)
        if len(pool) == 0:
            return
        weights = base_weight[pool]
        draw = min(len(pool), wanted * 5)
        # Weighted sampling without replacement via exponential keys (fast, exact).
        keys = rng.exponential(size=len(pool)) / np.maximum(weights, 1e-12)
        candidates = pool[np.argsort(keys, kind="stable")[:draw]]

        # Lender's imperfect view of risk.
        observed = risk[candidates] + lender.screening_noise * rng.standard_normal(draw)
        approved = observed < lender.approval_cutoff

        lo, hi = product.amount_income_multiple
        amount = income[candidates] * rng.uniform(lo, hi, draw)
        t_lo, t_hi = product.term_months
        term = rng.integers(t_lo, t_hi + 1, draw)
        if t_hi >= 120:
            term = (term // 12) * 12
        r_lo, r_hi = product.annual_rate
        annual = np.round(rng.uniform(r_lo, r_hi, draw) * 400) / 400  # nearest 0.25%
        rate = annual / 12.0

        # Affordability for lenders that enforce a debt-service ratio.
        if product.max_dsr is not None:
            headroom = product.max_dsr * income[candidates] - existing[candidates]
            factor = rate / (1.0 - np.power(1.0 + rate, -term))
            max_amount = np.where(headroom > 0, headroom / factor, 0.0)
            amount = np.minimum(amount, max_amount)

        step = product.round_to * 100
        amount = np.floor(amount / step) * step
        min_amt, max_amt = product.amount_bounds[0] * 100, product.amount_bounds[1] * 100
        amount = np.minimum(amount, max_amt)
        approved &= amount >= min_amt

        chosen = np.flatnonzero(approved)[:wanted]
        if len(chosen) == 0:
            return
        borrowers = candidates[chosen]
        principal = amount[chosen].astype(np.int64)
        term_c = term[chosen].astype(np.int32)
        rate_c = rate[chosen]
        installment = annuity_installment(principal.astype(np.float64), rate_c, term_c)

        day = rng.integers(1, days_in_month + 1, len(chosen))
        disbursed = period_start + (day - 1).astype("timedelta64[D]")
        due_day = np.minimum(day, 28)
        first_due = np.full(len(chosen), int(self.months[t].astype(np.int64)) + 1, dtype=np.int64)

        customer = np.empty(len(chosen), dtype=np.int64)
        branch = np.empty(len(chosen), dtype=np.int64)
        lender_seq = np.empty(len(chosen), dtype=np.int64)
        for i, b in enumerate(borrowers.tolist()):
            customer[i] = self._customer(l_idx, kind, b)
            options = self._branches.get((l_idx, int(region[b])))
            branch[i] = (
                options[int(rng.integers(len(options)))] if options else self._head_office[l_idx]
            )
            self._lender_loan_count[l_idx] += 1
            lender_seq[i] = self._lender_loan_count[l_idx]
            if kind == PERSON:
                person_loans[b] += 1
            else:
                business_loans[b] += 1

        n = len(chosen)
        self.book.append(
            {
                "lender": np.full(n, l_idx),
                "product": np.full(n, PRODUCT_CODES.index(product_code)),
                "kind": np.full(n, kind),
                "borrower": borrowers,
                "customer": customer,
                "branch": branch,
                "principal": principal,
                "annual_rate": annual[chosen],
                "rate": rate_c,
                "term": term_c,
                "installment": installment,
                "disbursed": disbursed,
                "first_due": first_due,
                "due_day": due_day,
                "k_due": np.zeros(n),
                "k_paid": np.zeros(n),
                "status": np.full(n, ACTIVE),
                "orig_month": np.full(n, t),
                "terminal_month": np.full(n, -1),
                "first_90_month": np.full(n, -1),
                "lender_seq": lender_seq,
            }
        )

    def _customer(self, lender: int, kind: int, borrower: int) -> int:
        key = (lender, kind, borrower)
        idx = self._customer_index.get(key)
        if idx is None:
            idx = len(self.customers)
            self.customers.append(key)
            self._lender_customer_count[lender] += 1
            self.customer_seq.append(self._lender_customer_count[lender])
            self._customer_index[key] = idx
        return idx


def _sector_sensitivity() -> dict[str, float]:
    from .config import SECTORS

    return SECTORS


def simulate(
    config: WorldConfig, people: People, businesses: Businesses, branches: list[Branch]
) -> SimulationResult:
    return Engine(config, people, businesses, branches).run()
