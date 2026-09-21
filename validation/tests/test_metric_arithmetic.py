"""
Metric arithmetic on known inputs.

Two layers:

1. `validation/runners/_shared.py`'s own small helpers (`wilson_ci`,
   `spread_ci`, `seed_mean_note`) against hand-built `metrics.json`-shaped
   dicts, where the expected output is exact.
2. The `src/model/metrics.py` functions the runners reuse (`wilson`, `psi`),
   against inputs chosen so the answer is provable by hand — this is not a
   test of `src/model/**` (out of scope for this lane, and that file is
   frozen for L9), it is a guard that this lane's assumptions about what those
   functions return have not drifted.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT, REPO_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from validation.criteria import Criterion
from validation.runners import _shared as sh


def _crit(**over) -> Criterion:
    base = dict(id="SK-99", runner="01_holdout", metric="m", scope="overall",
               op="ge", threshold=0.9, min_n=0, severity="fail",
               rationale="r", source="s")
    base.update(over)
    return Criterion(**base)


# ---------------------------------------------------------------------------
# _shared.wilson_ci
# ---------------------------------------------------------------------------
def test_wilson_ci_reads_ci_low_high():
    assert sh.wilson_ci({"value": 0.5, "ci_low": 0.4123, "ci_high": 0.5877}) == (0.4123, 0.5877)


def test_wilson_ci_rounds_to_4dp():
    assert sh.wilson_ci({"ci_low": 0.123456, "ci_high": 0.654321}) == (0.1235, 0.6543)


@pytest.mark.parametrize("block", [None, {}, {"ci_low": None, "ci_high": 0.5}, {"value": 0.5}])
def test_wilson_ci_none_when_incomplete(block):
    assert sh.wilson_ci(block) is None


# ---------------------------------------------------------------------------
# _shared.spread_ci
# ---------------------------------------------------------------------------
def test_spread_ci_reads_percentile_spread():
    m = {"seeds": {"spread": {"baseline": {"n": 5, "pct_low": 0.081, "pct_high": 0.099,
                                           "mean": 0.09}}}}
    ci, frag = sh.spread_ci(m, "baseline")
    assert ci == (0.081, 0.099)
    assert "5-SEED SPREAD" in frag
    assert "NOT a confidence interval" in frag


def test_spread_ci_never_calls_itself_a_confidence_interval():
    """Review §10: a 5-seed percentile spread is training-seed variability, and
    labelling it "95% CI" beside a seed-7 point estimate put estimates outside
    their own displayed interval."""
    m = {"seeds": {"spread": {"baseline": {"n": 5, "pct_low": 0.081, "pct_high": 0.099,
                                           "mean": 0.09}}}}
    _, frag = sh.spread_ci(m, "baseline")
    assert "95% CI" not in frag


def test_spread_ci_says_when_the_packed_seed_falls_outside_the_spread():
    m = {"seeds": {"spread": {"baseline": {"n": 5, "pct_low": 0.081, "pct_high": 0.099,
                                           "mean": 0.09}}}}
    _, inside = sh.spread_ci(m, "baseline", 0.090)
    assert "lies outside" not in inside
    _, outside = sh.spread_ci(m, "baseline", 0.105)
    assert "lies outside this spread" in outside
    assert "0.1050" in outside


@pytest.mark.parametrize("spread", [
    {},                                                   # key absent
    {"baseline": {"n": 1, "pct_low": 0.09, "pct_high": 0.09}},   # single seed
    {"baseline": {"n": 5}},                                # no percentile fields
])
def test_spread_ci_none_when_not_available(spread):
    m = {"seeds": {"spread": spread}}
    ci, frag = sh.spread_ci(m, "baseline")
    assert ci is None and frag is None


def test_spread_ci_missing_seeds_block():
    assert sh.spread_ci({}, "baseline") == (None, None)


# ---------------------------------------------------------------------------
# _shared.seed_mean_note — the SK-04-style "disagreement" flag
# ---------------------------------------------------------------------------
def test_seed_mean_note_flags_disagreement():
    crit = _crit(op="ge", threshold=0.90)
    m = {"seeds": {"spread": {"window_respect_rate": {"n": 5, "mean": 0.8813}}}}
    note = sh.seed_mean_note(crit, 0.9009, m, "window_respect_rate")
    assert note is not None
    assert "0.9009" in note and "passes" in note
    assert "0.8813" in note and "fails" in note


def test_seed_mean_note_silent_when_they_agree():
    crit = _crit(op="ge", threshold=0.90)
    m = {"seeds": {"spread": {"window_respect_rate": {"n": 5, "mean": 0.95}}}}
    assert sh.seed_mean_note(crit, 0.98, m, "window_respect_rate") is None


def test_seed_mean_note_none_without_spread():
    crit = _crit(op="ge", threshold=0.90)
    assert sh.seed_mean_note(crit, 0.98, {}, "window_respect_rate") is None


# ---------------------------------------------------------------------------
# src/model/metrics.py — reused, not reimplemented; assumptions checked here
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def M():
    import model.metrics as _M

    return _M


def test_wilson_symmetric_at_half(M):
    lo, hi = M.wilson(50, 100)
    # a 50/100 Wilson interval must straddle 0.5 exactly (symmetric case)
    assert lo < 0.5 < hi
    assert math.isclose((lo + hi) / 2, 0.5, abs_tol=1e-9)
    assert 0.40 < lo < 0.41   # the textbook Wilson 95% interval for k=50,n=100
    assert 0.59 < hi < 0.60


def test_wilson_degenerate_n_zero(M):
    lo, hi = M.wilson(0, 0)
    assert math.isnan(lo) and math.isnan(hi)


def test_psi_is_zero_for_identical_distributions(M):
    x = np.linspace(0, 1, 500)
    assert M.psi(x, x) == pytest.approx(0.0, abs=1e-9)


def test_psi_is_large_for_a_shifted_distribution(M):
    expected = np.random.default_rng(0).normal(0, 1, 2000)
    actual = np.random.default_rng(1).normal(6, 1, 2000)   # fully separated
    assert M.psi(expected, actual) > 1.0   # far past the SK-16 ceiling of 0.10


def test_psi_small_for_a_barely_shifted_distribution(M):
    rng = np.random.default_rng(0)
    expected = rng.normal(0, 1, 5000)
    actual = expected + rng.normal(0, 0.01, 5000)   # a tiny nudge
    assert M.psi(expected, actual) < 0.10   # inside the SK-16 "no meaningful shift" band


def test_precision_at_matches_hand_count(M):
    # 10 rows, top-3 by score are indices with y = [1, 1, 0] -> precision 2/3
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 1])
    score = np.array([9, 8, 7, 1, 2, 3, 4, 5, 6, 0])
    out = M.precision_at(y, score, budget=0.3)
    assert out["k"] == 3
    assert out["hits"] == 2
    assert out["precision"] == pytest.approx(2 / 3)
