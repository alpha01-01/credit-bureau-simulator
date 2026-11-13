"""Calibration statistics for a simulated world.

Used by tests (plausibility bands) and by the generate_world command's report.
Default definition (Document 07, D13): 90+ days past due within 12 months.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import WorldConfig
from .engine import ACTIVE, PRODUCT_CODES, WRITTEN_OFF, SimulationResult

PERFORMANCE_WINDOW = 12


@dataclass(frozen=True)
class WorldStats:
    active_loans_at_end: int
    active_by_lender: dict[str, int]
    borrowers_with_active_loan: int
    default_rate_12m: float  # all products, cohorts with a full window inside the simulation
    default_rate_by_product: dict[str, float]
    cohort_size: int
    written_off_total: int
    dpd_buckets_at_end: dict[str, int]
    stress_min: float
    stress_max: float

    def as_lines(self) -> list[str]:
        lines = [
            f"Active loans at end of history: {self.active_loans_at_end:,}",
            f"Borrowers with an active loan:  {self.borrowers_with_active_loan:,}",
            f"12-month default rate (90+ DPD): {self.default_rate_12m:.1%} over {self.cohort_size:,} loans",
        ]
        lines += [f"  {p:<20} {r:.1%}" for p, r in self.default_rate_by_product.items()]
        lines.append("Active loans by lender:")
        lines += [f"  {code:<5} {n:,}" for code, n in self.active_by_lender.items()]
        lines.append("Arrears at end of history:")
        lines += [f"  {b:<8} {n:,}" for b, n in self.dpd_buckets_at_end.items()]
        lines.append(f"Written off (all time): {self.written_off_total:,}")
        lines.append(f"Economic stress range: {self.stress_min:+.2f} to {self.stress_max:+.2f}")
        return lines


def compute_stats(config: WorldConfig, result: SimulationResult) -> WorldStats:
    book = result.book
    last = len(result.months) - 1
    status = book["status"]
    active = status == ACTIVE

    active_by_lender = {
        lp.code: int((active & (book["lender"] == i)).sum()) for i, lp in enumerate(config.lenders)
    }
    borrowers = {
        (int(k), int(b))
        for k, b in zip(book["kind"][active], book["borrower"][active], strict=True)
    }

    # Cohorts whose 12-month window (from first instalment) ends inside the simulation.
    orig = book["orig_month"]
    in_cohort = orig + 1 + PERFORMANCE_WINDOW <= last
    first_90 = book["first_90_month"]
    defaulted = (first_90 >= 0) & (first_90 <= orig + PERFORMANCE_WINDOW)
    # A write-off before reaching 90 DPD also counts as default.
    defaulted |= (status == WRITTEN_OFF) & (book["terminal_month"] <= orig + PERFORMANCE_WINDOW)
    by_product = {}
    for p_idx, code in enumerate(PRODUCT_CODES):
        mask = in_cohort & (book["product"] == p_idx)
        if mask.any():
            by_product[code] = float(defaulted[mask].mean())
    rate = float(defaulted[in_cohort].mean()) if in_cohort.any() else 0.0

    # DPD buckets at the final month from snapshots.
    months = result.snapshots.column("month")
    final = months == last
    dpd = result.snapshots.column("dpd")[final]
    snap_status = result.snapshots.column("status")[final]
    live = snap_status == ACTIVE
    buckets = {
        "current": int(((dpd == 0) & live).sum()),
        "1-30": int(((dpd >= 1) & (dpd <= 30) & live).sum()),
        "31-90": int(((dpd >= 31) & (dpd <= 90) & live).sum()),
        "91-180": int(((dpd >= 91) & (dpd <= 180) & live).sum()),
        "181+": int(((dpd >= 181) & live).sum()),
    }

    return WorldStats(
        active_loans_at_end=int(active.sum()),
        active_by_lender=active_by_lender,
        borrowers_with_active_loan=len(borrowers),
        default_rate_12m=rate,
        default_rate_by_product=by_product,
        cohort_size=int(in_cohort.sum()),
        written_off_total=int((status == WRITTEN_OFF).sum()),
        dpd_buckets_at_end=buckets,
        stress_min=float(np.min(result.stress)),
        stress_max=float(np.max(result.stress)),
    )
