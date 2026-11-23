"""The statistics of a scorecard (P3.5), in plain numpy.

Coarse classing into bins, weight of evidence (WoE) and information value (IV);
logistic regression on WoE (Newton-Raphson); score scaling (points to double the
odds); and validation measures (AUC, Gini, KS, population stability). Every
function is pure and deterministic, so the workbench's results can be replayed
and tested against known answers.

"Bad" is the event modelled (a default), "good" its absence. WoE is
ln(share of goods / share of bads): positive for bins safer than average.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log

import numpy as np

SMOOTHING = 0.5  # added to each bin's goods and bads, so an empty side has a finite WoE
MAX_BINS = 5
MIN_BIN_SHARE = 0.05  # a bin holds at least this share of the sample, or it is merged


@dataclass(frozen=True)
class Binning:
    """Upper edges of numeric bins (the last is +inf) and each bin's WoE."""

    feature: str
    edges: list[float]
    woe: list[float]
    goods: list[int]
    bads: list[int]

    @property
    def iv(self) -> float:
        g, b = np.array(self.goods) + SMOOTHING, np.array(self.bads) + SMOOTHING
        pg, pb = g / g.sum(), b / b.sum()
        return float(np.sum((pg - pb) * np.log(pg / pb)))

    def bin_of(self, values: np.ndarray) -> np.ndarray:
        result: np.ndarray = np.searchsorted(np.array(self.edges[:-1]), values, side="left")
        return result

    def transform(self, values: np.ndarray) -> np.ndarray:
        result: np.ndarray = np.array(self.woe)[self.bin_of(values)]
        return result


def bin_feature(name: str, values: np.ndarray, bad: np.ndarray) -> Binning:
    """Quantile bins (at most MAX_BINS), merged until each holds MIN_BIN_SHARE of the sample."""
    values = values.astype(np.float64)
    cuts = np.unique(np.quantile(values, np.linspace(0, 1, MAX_BINS + 1)[1:-1]))
    edges = [*cuts.tolist(), float("inf")]
    while len(edges) > 1:
        idx = np.searchsorted(np.array(edges[:-1]), values, side="left")
        counts = np.bincount(idx, minlength=len(edges))
        small = int(np.argmin(counts))
        if counts[small] >= MIN_BIN_SHARE * len(values):
            break
        # Merge the smallest bin with a neighbour by dropping an edge between them.
        drop = small if small < len(edges) - 1 else small - 1
        edges.pop(drop)
    idx = np.searchsorted(np.array(edges[:-1]), values, side="left")
    goods = np.bincount(idx[~bad], minlength=len(edges)).astype(int)
    bads = np.bincount(idx[bad], minlength=len(edges)).astype(int)
    g, b = goods + SMOOTHING, bads + SMOOTHING
    woe = np.log((g / g.sum()) / (b / b.sum()))
    return Binning(name, edges, woe.round(6).tolist(), goods.tolist(), bads.tolist())


def fit_logistic(x: np.ndarray, y: np.ndarray, iterations: int = 50) -> tuple[float, np.ndarray]:
    """Maximum-likelihood logistic regression of ``y`` (1 = bad) on ``x``. Returns
    (intercept, coefficients). A tiny ridge keeps the Hessian invertible."""
    n, k = x.shape
    design = np.hstack([np.ones((n, 1)), x])
    beta = np.zeros(k + 1)
    ridge = 1e-6 * np.eye(k + 1)
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-(design @ beta)))
        gradient = design.T @ (y - p)
        hessian = design.T @ (design * (p * (1 - p))[:, None]) + ridge
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(beta[0]), beta[1:]


def predict_bad(intercept: float, coefficients: np.ndarray, x: np.ndarray) -> np.ndarray:
    result: np.ndarray = 1.0 / (1.0 + np.exp(-(intercept + x @ coefficients)))
    return result


# --- Scaling: 600 points at odds of 30 goods to 1 bad; 20 points double the odds ------------

BASE_SCORE, BASE_ODDS, POINTS_TO_DOUBLE = 600, 30.0, 20
SCORE_MIN, SCORE_MAX = 300, 850
FACTOR = POINTS_TO_DOUBLE / log(2)
OFFSET = BASE_SCORE - FACTOR * log(BASE_ODDS)
BANDS = (
    ("A", 750, "Very low"),
    ("B", 680, "Low"),
    ("C", 600, "Medium"),
    ("D", 520, "High"),
    ("E", SCORE_MIN, "Very high"),
)


def score_of(p_bad: np.ndarray) -> np.ndarray:
    """Scores from probabilities of default: OFFSET + FACTOR * ln(good:bad odds), clipped."""
    p = np.clip(p_bad, 1e-9, 1 - 1e-9)
    result: np.ndarray = np.clip(
        np.rint(OFFSET + FACTOR * np.log((1 - p) / p)), SCORE_MIN, SCORE_MAX
    ).astype(int)
    return result


def band_of(score: int) -> str:
    return next(code for code, floor, _ in BANDS if score >= floor)


# --- Validation ------------------------------------------------------------------------------


def auc(bad: np.ndarray, risk: np.ndarray) -> float:
    """The chance a random bad is ranked riskier than a random good (ties count half)."""
    bad = bad.astype(bool)
    n_bad, n_good = int(bad.sum()), int((~bad).sum())
    if n_bad == 0 or n_good == 0:
        return float("nan")
    order = np.argsort(risk, kind="mergesort")
    ranks = np.empty(len(risk), dtype=np.float64)
    sorted_risk = risk[order]
    # Average ranks for ties.
    _unique, start, counts = np.unique(sorted_risk, return_index=True, return_counts=True)
    average = start + (counts - 1) / 2.0 + 1.0
    ranks[order] = np.repeat(average, counts)
    return float((ranks[bad].sum() - n_bad * (n_bad + 1) / 2) / (n_bad * n_good))


def gini(bad: np.ndarray, risk: np.ndarray) -> float:
    return 2 * auc(bad, risk) - 1


def ks(bad: np.ndarray, risk: np.ndarray) -> float:
    """The largest gap between the cumulative shares of bads and goods, riskiest first."""
    bad = bad.astype(bool)
    if bad.all() or not bad.any():
        return float("nan")
    order = np.argsort(-risk, kind="mergesort")
    cum_bad = np.cumsum(bad[order]) / bad.sum()
    cum_good = np.cumsum(~bad[order]) / (~bad).sum()
    # Only at the ends of tied groups.
    risk_sorted = risk[order]
    ends = np.r_[risk_sorted[1:] != risk_sorted[:-1], True]
    return float(np.max(np.abs(cum_bad - cum_good)[ends]))


def psi(expected: np.ndarray, actual: np.ndarray, edges: list[float]) -> float:
    """Population stability index of ``actual`` against ``expected`` over score bands."""
    cuts = np.array(edges)
    e = (
        np.bincount(np.searchsorted(cuts, expected, side="right"), minlength=len(cuts) + 1)
        + SMOOTHING
    )
    a = (
        np.bincount(np.searchsorted(cuts, actual, side="right"), minlength=len(cuts) + 1)
        + SMOOTHING
    )
    pe, pa = e / e.sum(), a / a.sum()
    return float(np.sum((pa - pe) * np.log(pa / pe)))
