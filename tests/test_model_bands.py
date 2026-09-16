"""SM-2 — the pre-registered bands, and the statistics underneath them.

``validation/criteria.yaml`` was committed before any model result existed. The
model transcribes its bands into ``model.metrics.REGISTERED_BANDS`` so the packed
JSON can carry a verdict beside every number. Two files holding the same
thresholds is a drift hazard, so the first test here reads the YAML and asserts
the transcription — if anyone edits either side, this fails.

The rest is the arithmetic: Wilson intervals, equal-count ECE, PSI, the seed
spread, and the rule that a failing band is **reported**, never hidden and never
quietly turned into a pass.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

yaml = pytest.importorskip("yaml")

from model.metrics import (  # noqa: E402
    REGISTERED_BANDS,
    Z95,
    bands,
    ece,
    precision_at,
    psi,
    reliability,
    spread,
    wilson,
)

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "validation" / "criteria.yaml"


@pytest.fixture(scope="module")
def registered() -> dict:
    return {c["id"]: c for c in yaml.safe_load(CRITERIA.read_text())["criteria"]}


# --------------------------------------------------------------------------- #
# the transcription
# --------------------------------------------------------------------------- #

def test_every_criterion_is_transcribed(registered: dict) -> None:
    assert set(REGISTERED_BANDS) == set(registered), (
        set(REGISTERED_BANDS) ^ set(registered))


def test_the_transcribed_thresholds_match_the_yaml(registered: dict) -> None:
    """The model may not carry a looser band than the one that was registered."""
    for cid, (metric, op, thr, severity) in REGISTERED_BANDS.items():
        c = registered[cid]
        assert c["metric"] == metric, cid
        assert severity == c["severity"], cid
        expected = c["threshold"]
        if c["op"] == "report" or c["severity"] == "report":
            # reported criteria may carry a reference line (SK-23's 0.80) that the
            # model still measures; the band itself is never gated.
            continue
        assert op == c["op"], cid
        if isinstance(expected, list):
            assert list(thr) == expected, cid
        else:
            assert thr == expected, cid


def test_the_headline_bands_are_the_two_the_gate_reads(registered: dict) -> None:
    """G3 reads SK-01 and SK-02; nothing may move them."""
    assert registered["SK-01"]["threshold"] == [0.08, 0.10]
    assert registered["SK-02"]["threshold"] == [0.25, 0.35]
    assert registered["SK-13"]["threshold"] == 0.80
    assert registered["SK-08"]["threshold"] == 0.75
    assert registered["SK-15"]["threshold"] == 4


def test_the_amendment_is_scoping_not_loosening() -> None:
    """The 16 Sep amendment re-scoped SK-01/02/17/18 to the drop-off population."""
    doc = yaml.safe_load(CRITERIA.read_text())
    a = doc["amendments"][-1]
    assert a["loosening"] is False
    assert set(a["criteria"]) == {"SK-01", "SK-02", "SK-17", "SK-18"}


# --------------------------------------------------------------------------- #
# verdicts
# --------------------------------------------------------------------------- #

def test_a_value_outside_its_band_fails_and_is_still_reported() -> None:
    b = bands({"SK-02": 0.44, "SK-01": 0.09, "SK-13": 0.62})
    assert b["SK-02"]["verdict"] == "fail"
    assert b["SK-02"]["value"] == 0.44, "a failing value is kept, not blanked"
    assert b["SK-01"]["verdict"] == "pass"
    assert b["SK-13"]["verdict"] == "fail"


def test_an_unmeasured_criterion_is_never_a_pass() -> None:
    b = bands({})
    assert b["SK-04"]["verdict"] == "not_measured"
    assert b["SK-16"]["verdict"] == "not_measured"
    assert b["SK-03"]["verdict"] == "not_run"
    assert all(v["verdict"] != "pass" for v in b.values())


def test_a_reported_failure_is_marked_non_gating() -> None:
    """SK-23 is the documented gig-worker gap: it can fail *and* be disclosed."""
    b = bands({"SK-23": 0.69, "SK-02": 0.29})
    assert b["SK-23"]["verdict"] == "fail" and b["SK-23"]["gating"] is False
    assert b["SK-02"]["gating"] is True


def test_the_seed_mean_verdict_is_reported_beside_the_packed_one() -> None:
    """A band that clears on one split and not on the mean has not cleared."""
    b = bands({"SK-04": 0.901}, seed_means={"SK-04": 0.881})
    assert b["SK-04"]["verdict"] == "pass"
    assert b["SK-04"]["verdict_on_seed_mean"] == "fail"
    assert b["SK-04"]["agrees_across_seeds"] is False


def test_a_nan_is_not_a_pass() -> None:
    assert bands({"SK-05": float("nan")})["SK-05"]["verdict"] == "not_measured"


def test_report_criteria_stay_report() -> None:
    b = bands({"SK-03": {"anything": 1}, "SK-25": [1, 2, 3]})
    assert b["SK-03"]["verdict"] == "report"
    assert b["SK-25"]["verdict"] == "report"


def test_every_band_is_in_the_export_with_a_verdict(packed: SimpleNamespace) -> None:
    b = packed.out["metrics"]["bands"]
    assert set(b) == set(REGISTERED_BANDS)
    for cid, v in b.items():
        assert v["verdict"] in {"pass", "fail", "report", "not_measured", "not_run"}, cid
        assert "value" in v and "threshold" in v and "metric" in v
        assert v["gating"] is (v["severity"] == "fail")


def test_the_registered_block_is_keyed_by_the_yaml_metric_names(
        packed: SimpleNamespace, registered: dict) -> None:
    """A validation runner reads a value; it does not re-derive one."""
    reg = packed.out["metrics"]["registered"]
    for cid in ("SK-01", "SK-02", "SK-04", "SK-05", "SK-09", "SK-13", "SK-14",
                "SK-15", "SK-17", "SK-20"):
        assert registered[cid]["metric"] in reg, cid


# --------------------------------------------------------------------------- #
# the statistics
# --------------------------------------------------------------------------- #

def test_wilson_brackets_the_point_estimate_and_stays_inside_zero_one() -> None:
    for k, n in [(0, 50), (1, 50), (25, 100), (99, 100), (100, 100)]:
        lo, hi = wilson(k, n)
        assert 0.0 <= lo <= k / n <= hi <= 1.0, (k, n)
    assert wilson(5, 20)[1] - wilson(5, 20)[0] > wilson(50, 200)[1] - wilson(50, 200)[0]


def test_precision_at_ranks_by_the_score_and_carries_its_interval() -> None:
    y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    s = np.array([9, 8, 7, 6, 5, 4, 3, 2, 1, 0], dtype=float)
    a = precision_at(y, s, 0.2)
    assert a["k"] == 2 and a["hits"] == 1 and a["precision"] == 0.5
    assert a["ci_low"] < 0.5 < a["ci_high"]


def test_ece_is_zero_for_a_perfectly_calibrated_score() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 40_000)
    y = (rng.random(40_000) < p).astype(int)
    assert ece(p, y) < 0.02


def test_ece_catches_a_score_that_is_twice_the_truth() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.45, 40_000)
    y = (rng.random(40_000) < p / 2).astype(int)
    assert ece(p, y) > 0.08


def test_ece_uses_equal_count_bins() -> None:
    """Equal-width bins would put a near-zero score distribution in one bucket."""
    p = np.concatenate([np.full(9_500, 0.001), np.linspace(0.3, 0.9, 500)])
    y = np.concatenate([np.zeros(9_500), np.ones(500)]).astype(int)
    r = reliability(p, y, bins=10)
    assert len({x["n"] for x in r}) <= 2, "bins are not equal-count"
    assert r[-1]["obs"] > r[0]["obs"]


def test_psi_is_zero_on_itself_and_large_on_a_shift() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(size=20_000)
    assert psi(a, a) < 1e-6
    assert psi(a, a + 1.0) > 0.25


def test_spread_reports_both_the_normal_and_the_percentile_interval() -> None:
    s = spread([0.28, 0.29, 0.30, 0.31, 0.32])
    assert abs(s["mean"] - 0.30) < 1e-9
    assert s["n"] == 5
    assert s["ci_low"] < s["mean"] < s["ci_high"]
    assert s["min"] == 0.28 and s["max"] == 0.32
    assert 0 < s["pct_width_pp"] <= 4.0
    assert abs(s["ci_high"] - s["ci_low"] - 2 * Z95 * s["sd"] / np.sqrt(5)) < 1e-9


def test_seed_spread_is_reported_for_every_headline_number(packed: SimpleNamespace) -> None:
    sp = packed.out["metrics"]["seeds"]
    assert sp["n"] == len(sp["per_seed"])
    for k in ("baseline", "precision_at_budget", "macro_auc", "menu_of_4_hit_rate"):
        assert k in sp["spread"], k
        assert "pct_width_pp" in sp["spread"][k]
