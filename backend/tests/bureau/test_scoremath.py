"""P3.5 — the scorecard statistics, against known answers."""

from __future__ import annotations

from itertools import product
from math import log

import numpy as np
import pytest

from apps.bureau.analytics import scoremath as sm


def test_auc_and_ks_agree_with_counting_every_pair() -> None:
    rng = np.random.default_rng(7)
    risk = rng.integers(0, 12, 300).astype(float)  # many ties
    bad = rng.random(300) < 1 / (1 + np.exp(-(risk - 6) / 2))
    bads, goods = risk[bad], risk[~bad]
    pairs = sum((b > g) + 0.5 * (b == g) for b, g in product(bads, goods))
    assert sm.auc(bad, risk) == pytest.approx(pairs / (len(bads) * len(goods)))
    assert sm.gini(bad, risk) == pytest.approx(2 * sm.auc(bad, risk) - 1)
    thresholds = np.unique(risk)
    gaps = [abs((bads >= t).mean() - (goods >= t).mean()) for t in thresholds]
    assert sm.ks(bad, risk) == pytest.approx(max(gaps))
    assert sm.auc(bad, -risk) == pytest.approx(1 - sm.auc(bad, risk))


def test_logistic_regression_recovers_known_coefficients() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=(20_000, 2))
    true = np.array([0.8, -1.3])
    y = rng.random(20_000) < 1 / (1 + np.exp(-(-1.0 + x @ true)))
    intercept, coefficients = sm.fit_logistic(x, y.astype(float))
    assert intercept == pytest.approx(-1.0, abs=0.06)
    assert coefficients == pytest.approx(true, abs=0.06)


def test_woe_and_iv_follow_their_definitions() -> None:
    values = np.repeat([1.0, 2.0, 3.0], 100)
    bad = np.r_[np.zeros(90, bool), np.ones(10, bool), np.zeros(70, bool), np.ones(30, bool),
                np.zeros(40, bool), np.ones(60, bool)]  # fmt: skip
    binning = sm.bin_feature("x", values, bad)
    assert binning.goods == [90, 70, 40] and binning.bads == [10, 30, 60]
    g = np.array([90, 70, 40]) + sm.SMOOTHING
    b = np.array([10, 30, 60]) + sm.SMOOTHING
    woe = np.log((g / g.sum()) / (b / b.sum()))
    assert binning.woe == pytest.approx(woe.tolist(), abs=1e-6)
    assert binning.iv == pytest.approx(float(np.sum((g / g.sum() - b / b.sum()) * woe)), abs=1e-6)
    assert binning.transform(np.array([1.0, 3.0])) == pytest.approx([woe[0], woe[2]], abs=1e-6)
    assert woe[0] > 0 > woe[2]  # the safe bin has positive WoE


def test_scores_are_scaled_600_at_30_to_1_and_20_points_double_the_odds() -> None:
    p_at_30 = 1 / 31
    assert sm.score_of(np.array([p_at_30]))[0] == 600
    p_at_60 = 1 / 61
    assert sm.score_of(np.array([p_at_60]))[0] == 620
    assert sm.score_of(np.array([0.999999]))[0] == sm.SCORE_MIN
    assert sm.score_of(np.array([1e-9]))[0] == sm.SCORE_MAX
    assert [sm.band_of(s) for s in (800, 700, 610, 550, 400)] == ["A", "B", "C", "D", "E"]
    assert pytest.approx(600 - 20 / log(2) * log(30)) == sm.OFFSET


def test_population_stability() -> None:
    rng = np.random.default_rng(3)
    base = rng.normal(600, 50, 5_000)
    edges = [520.0, 600.0, 680.0, 750.0]
    assert sm.psi(base, rng.normal(600, 50, 5_000), edges) < 0.02
    assert sm.psi(base, rng.normal(540, 60, 5_000), edges) > 0.25
