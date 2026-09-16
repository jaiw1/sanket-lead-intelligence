"""
Status mapping for runners 07-12 (SK-17..SK-25) — the L9B lane.

Mirrors `test_status_mapping.py`'s two-layer approach for 01-06:

1. **Synthetic, exact** — a hand-built `data/model_metrics.json` for the four
   criteria that are pure adapters over it with no refit dependency (SK-20,
   SK-21, SK-25), where "known inputs -> known status" is cheap to assert
   without paying for a small-book refit.
2. **Real, small** (`small_metrics_root`, see `conftest.py`) — all six
   runners (07-12) against a genuinely independent, freshly-generated
   8,000-row `--quick` pipeline run. 08_ablation and 10_stress never read
   `data/model_metrics.json` at all (they generate their own small book via
   `validation/runners/_refit.py`), so this is also where their refit
   machinery gets exercised for real, once — `_refit`'s process-level cache
   (keyed on `repo_root`) means every test below that touches it after the
   first pays close to nothing extra.

A missing-metrics-file check is included too, and it deliberately expects
DIFFERENT behaviour for 07/09/11/12 (pending — they read the file) than for
08/10 (still graded — they refit their own small book regardless of whether
`data/model_metrics.json` exists at all).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.criteria import Result
from validation.run import grade

MY_RUNNERS = ("07_leakage", "08_ablation", "09_seeds", "10_stress",
             "11_fairness", "12_baseline_ladder")
MY_CRITERIA = tuple(f"SK-{i:02d}" for i in range(17, 26))
#: Runners whose graded criteria depend on `data/model_metrics.json` existing.
_METRICS_DEPENDENT = {"07_leakage": ("SK-17", "SK-18"), "09_seeds": ("SK-20", "SK-21"),
                      "11_fairness": ("SK-23", "SK-24"), "12_baseline_ladder": ("SK-25",)}
#: 08_ablation (SK-19) / 10_stress (SK-22) generate their own small book and
#: never read data/model_metrics.json — see their module docstrings.
_REFIT_ONLY = {"SK-19", "SK-22"}

_VALID_STATUSES: set[str] = {"pass", "fail", "warn", "report", "pending", "skipped_low_n", "error"}


def _run_and_grade(repo_root: Path, doc, make_ctx, runners=MY_RUNNERS) -> dict[str, Result]:
    ctx = make_ctx(repo_root)
    by_id: dict[str, Result] = {}
    for name in runners:
        mod = importlib.import_module(f"validation.runners.{name}")
        crits = doc.by_runner(name)
        for res in mod.run(crits, ctx):
            by_id[res.criterion_id] = grade(doc.get(res.criterion_id), res)
    return by_id


# ---------------------------------------------------------------------------
# 1. synthetic metrics.json, exact expected statuses — the no-refit adapters
# ---------------------------------------------------------------------------
def _synthetic_metrics(*, n_seeds=5, width_pp=1.5, ladder=None, air=0.5, gig_within15=0.7) -> dict:
    return {
        "meta": {"population": {"name": "drop-off population", "definition": "test"},
                "snapshot_month": 29},
        "metrics": {
            "leakage": {"forbidden_inputs_used": 0, "forbidden_set_size": 60,
                       "permuted_label_auc": 0.505},
            "seeds": {
                "n": n_seeds, "list": list(range(7, 7 + n_seeds)),
                "spread": {"precision_at_budget": {
                    "mean": 0.29, "n": n_seeds, "pct_low": 0.29 - width_pp / 200,
                    "pct_high": 0.29 + width_pp / 200, "pct_width_pp": width_pp}},
                "per_seed": [{"seed": 7 + i,
                             "precision": {"0.1": {"precision": 0.29 + 0.001 * i}}}
                            for i in range(n_seeds)],
            },
            "baseline_ladder": ladder,
            "fairness": [
                {"dim": "Segment", "group": "gig", "sel_rate": 0.05, "ratio": air, "n": 800},
                {"dim": "Segment", "group": "salaried", "sel_rate": 0.10, "ratio": 1.0, "n": 3000},
            ],
            "income_acc": {"within15": 0.95, "gig_within15": gig_within15, "median_err": 0.02,
                          "gig_median_err": 0.08, "n": 1500, "n_gig": 250},
            "registered": {"adverse_impact_ratio": air, "gig_worker_failure_disclosure": True},
        },
    }


@pytest.fixture()
def synthetic_root(tmp_path: Path):
    """`synthetic_root(**kw)` -> a fresh `repo_root` (a new subdirectory of
    `tmp_path` each call, so two calls in the same test never collide) with
    `data/model_metrics.json` built from `_synthetic_metrics(**kw)`."""
    counter = {"i": 0}

    def _make(**kw) -> Path:
        counter["i"] += 1
        root = tmp_path / f"root_{counter['i']}"
        data_dir = root / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "model_metrics.json").write_text(
            json.dumps(_synthetic_metrics(**kw)), encoding="utf-8")
        return root
    return _make


def test_seeds_status_mapping_synthetic(synthetic_root, criteria_doc, make_ctx):
    # SK-20 (>=5) and SK-21 (<=4.0 pp) both pass on comfortable synthetic values
    root = synthetic_root(n_seeds=5, width_pp=1.5)
    by_id = _run_and_grade(root, criteria_doc, make_ctx, runners=("09_seeds",))
    assert by_id["SK-20"].status == "pass"
    assert by_id["SK-21"].status == "pass"

    # fewer than 5 seeds -> SK-20 fails; a wide cross-seed spread -> SK-21 fails
    root2 = synthetic_root(n_seeds=3, width_pp=8.0)
    by_id2 = _run_and_grade(root2, criteria_doc, make_ctx, runners=("09_seeds",))
    assert by_id2["SK-20"].status == "fail"
    assert by_id2["SK-21"].status == "fail"


def test_baseline_ladder_pending_when_ladder_empty(synthetic_root, criteria_doc, make_ctx):
    # metrics.baseline_ladder == [] is exactly what a --quick run leaves behind
    # (src/model/pack.py: `ladder = [] if cfg.quick else baseline_ladder(...)`)
    root = synthetic_root(ladder=[])
    by_id = _run_and_grade(root, criteria_doc, make_ctx, runners=("12_baseline_ladder",))
    assert by_id["SK-25"].status == "pending"
    assert "quick" in (by_id["SK-25"].detail or "")


def test_baseline_ladder_reports_when_populated(synthetic_root, criteria_doc, make_ctx):
    ladder = [
        {"rung": "random contact", "precision": 0.09, "ci_low": 0.08, "ci_high": 0.10, "n": 2000},
        {"rung": "balance-ranked (what a branch does today)", "precision": 0.095,
         "ci_low": 0.085, "ci_high": 0.105, "n": 2000},
        {"rung": "logistic scorecard", "precision": 0.25, "ci_low": 0.23, "ci_high": 0.27, "n": 2000},
        {"rung": "SANKET (one LightGBM, six products)", "precision": 0.29, "ci_low": 0.27,
         "ci_high": 0.31, "n": 2000},
    ]
    root = synthetic_root(ladder=ladder)
    by_id = _run_and_grade(root, criteria_doc, make_ctx, runners=("12_baseline_ladder",))
    assert by_id["SK-25"].status == "report"  # severity: report, op: report — never pass/fail
    assert len(by_id["SK-25"].breakdown) == 4
    assert [c["level"] for c in by_id["SK-25"].breakdown] == [r["rung"] for r in ladder]


def test_fairness_air_below_band_still_reports_not_fails(synthetic_root, criteria_doc, make_ctx):
    """SK-23 is `severity: report` in criteria.yaml — a ratio under the 0.80
    four-fifths line must be visible as the observed value (never softened
    upward) but must grade to `report`, never `fail`, because that is the
    severity the pre-registered band actually carries. Mirrors the real gig
    finding (ratio 0.69) without paying for a small-book refit twice."""
    root = synthetic_root(air=0.69, gig_within15=0.764)
    by_id = _run_and_grade(root, criteria_doc, make_ctx, runners=("11_fairness",))
    assert by_id["SK-23"].value == 0.69
    assert by_id["SK-23"].status == "report"
    gig_cells = [c for c in by_id["SK-23"].breakdown if c["level"] == "Segment:gig"]
    assert gig_cells and gig_cells[0]["value"] == 0.69
    assert "FAILS" in (by_id["SK-23"].detail or "")
    assert by_id["SK-24"].status == "report"
    assert by_id["SK-24"].value is True


# ---------------------------------------------------------------------------
# 2. missing metrics.json -> pending for the four file-dependent runners,
#    but NOT for 08_ablation / 10_stress (they never read that file)
# ---------------------------------------------------------------------------
def test_missing_metrics_file_pending_only_where_it_should_be(tmp_path, criteria_doc, make_ctx):
    from validation.runners import _shared as sh

    sh.reset_cache()
    by_id = _run_and_grade(tmp_path, criteria_doc, make_ctx,
                           runners=("07_leakage", "09_seeds", "11_fairness", "12_baseline_ladder"))
    for cid in ("SK-17", "SK-18", "SK-20", "SK-21", "SK-23", "SK-24", "SK-25"):
        assert by_id[cid].status == "pending", f"{cid}: expected pending, got {by_id[cid].status}"


# ---------------------------------------------------------------------------
# 3. real, small pipeline run — the integration smoke test, incl. 08/10's
#    own small-book refit (this is where that machinery is exercised for real)
# ---------------------------------------------------------------------------
def test_l9b_status_mapping_small_pipeline_run(small_metrics_root, criteria_doc, make_ctx):
    from validation.runners import _refit as rf
    from validation.runners import _shared as sh

    sh.reset_cache()
    rf.reset_cache()
    by_id = _run_and_grade(small_metrics_root, criteria_doc, make_ctx)

    assert set(by_id) == set(MY_CRITERIA)
    for cid, res in by_id.items():
        assert res.status in _VALID_STATUSES, f"{cid}: invalid status {res.status!r}"
        assert res.status != "error", f"{cid}: runner raised — {res.detail}"

    # --quick (small_metrics_root's MODEL_KW) skips the permuted-label retrain
    # and the baseline ladder — both must be pending with a legible reason,
    # never silently graded off a NaN or an empty list.
    assert by_id["SK-18"].status == "pending"
    assert "quick" in (by_id["SK-18"].detail or "")
    assert by_id["SK-25"].status == "pending"
    assert "quick" in (by_id["SK-25"].detail or "")

    # SK-17 (name-level guard + truncation-diff), SK-20/21 (seed sweep) and
    # SK-23/24 (fairness) do not depend on --quick at all.
    assert by_id["SK-17"].status not in ("pending", "error")
    assert by_id["SK-20"].status not in ("pending", "error")
    assert by_id["SK-21"].status not in ("pending", "error")
    assert by_id["SK-23"].status not in ("pending", "error")
    assert by_id["SK-24"].status not in ("pending", "error")

    # 08_ablation / 10_stress refit their own small book regardless of
    # data/model_metrics.json's contents — they must be `report` (their
    # registered severity), never `pending`.
    assert by_id["SK-19"].status == "report"
    assert set(by_id["SK-19"].value) == {
        "income", "balance", "outflow", "debt", "life_event", "profile",
        "journey", "shopper", "contact", "product",
    }, "every FEATURE_FAMILIES family must have an ablation cell"
    assert len(by_id["SK-19"].breakdown) == 10

    assert by_id["SK-22"].status == "report"
    assert set(by_id["SK-22"].value) == {
        "2x_base_rate_reweight_positives", "channel_missing_contact",
    }
    assert len(by_id["SK-22"].breakdown) == 2


def test_missing_metrics_file_still_grades_ablation_and_stress(tmp_path, criteria_doc, make_ctx):
    """08_ablation and 10_stress must NOT go pending just because
    data/model_metrics.json is absent — see their module docstrings on why
    they refit their own book instead of reading it."""
    from validation.runners import _refit as rf

    rf.reset_cache()
    by_id = _run_and_grade(tmp_path, criteria_doc, make_ctx, runners=("08_ablation", "10_stress"))
    assert by_id["SK-19"].status == "report"
    assert by_id["SK-22"].status == "report"
