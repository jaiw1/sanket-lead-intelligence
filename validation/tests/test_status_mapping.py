"""
Status mapping: a runner's `value` -> the harness's `status`.

Two layers, per the L9 brief ("Tests ... metric arithmetic on known inputs,
status mapping"):

1. **Synthetic, exact** (`test_status_mapping_synthetic_metrics`) — a
   hand-built `data/model_metrics.json`, values chosen so the pass/fail/
   skipped_low_n answer is known in advance. This is the literal "known
   inputs" case for status mapping: it does not depend on `src/model/**`
   computing anything, only on `validation.run.grade()` reading
   `criteria.yaml` correctly and each runner passing the right `value`/`n`
   through.
2. **Real, small** (`test_status_mapping_small_pipeline_run`) — the six
   runners against `small_metrics_root` (see `conftest.py`): a genuinely
   independent, freshly-generated 8,000-row pipeline run. Nothing here is
   staged to pass or fail; the point is that no runner may raise, every
   criterion this lane owns must be graded (never left `None`), and the tiny
   population size should legitimately exercise `skipped_low_n` on SK-10 and
   `pending` on SK-07 (`--quick` skips the out-of-time exhibit) — real
   behaviour, not a fabricated edge case.
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

MY_RUNNERS = ("01_holdout", "02_oot", "03_by_cut", "04_calibration",
             "05_rank_order", "06_stability")
MY_CRITERIA = tuple(f"SK-{i:02d}" for i in range(1, 17))

_VALID_STATUSES: set[str] = {"pass", "fail", "warn", "report", "pending", "skipped_low_n", "error"}


def _run_and_grade(repo_root: Path, doc, make_ctx) -> dict[str, Result]:
    ctx = make_ctx(repo_root)
    by_id: dict[str, Result] = {}
    for name in MY_RUNNERS:
        mod = importlib.import_module(f"validation.runners.{name}")
        crits = doc.by_runner(name)
        for res in mod.run(crits, ctx):
            by_id[res.criterion_id] = grade(doc.get(res.criterion_id), res)
    return by_id


# ---------------------------------------------------------------------------
# 1. synthetic metrics.json, exact expected statuses
# ---------------------------------------------------------------------------
def _synthetic_metrics() -> dict:
    """Every value chosen to land unambiguously on one side of its band."""
    return {
        "meta": {"population": {"name": "drop-off population", "definition": "test"},
                "snapshot_month": 29},
        "metrics": {
            "baseline_dropoff_disbursement": {"value": 0.09, "ci_low": 0.08, "ci_high": 0.10, "n": 1000},
            "precision_at_10pct": {"value": 0.20, "ci_low": 0.18, "ci_high": 0.22, "n": 100},  # < 0.25 -> fail
            "precision_at": {
                "5": {"value": 0.30, "ci_low": 0.25, "ci_high": 0.35, "n": 50},
                "10": {"value": 0.20, "ci_low": 0.18, "ci_high": 0.22, "n": 100},
                "20": {"value": 0.15, "ci_low": 0.12, "ci_high": 0.18, "n": 200},
            },
            "window_respect_rate": {"value": 0.85, "ci_low": 0.80, "ci_high": 0.90, "n": 300},  # < 0.90 -> fail
            "shopper_signal_auc": {"value": 0.75, "ci_low": 0.70, "ci_high": 0.80, "n": 1000},  # >= 0.70 -> pass
            "shopper": {"auc": 0.75, "ci": [0.70, 0.80], "n": 1000},
            "headline": "9 -> 20 disbursements per 100 RM calls",
            "headline_parts": {"baseline_per_100": 9, "precision_per_100": 20, "budget": 0.10,
                               "population": "test"},
            "oot": {"status": "ok", "cut_month": 24, "n": 500, "in_time_precision": 0.20,
                   "oot_precision_at_budget": 0.05, "oot_ci": [0.03, 0.07],
                   "oot_baseline": 0.09, "oot_row_auc": 0.6,
                   "degradation_pp": 15.0},  # > 5.0 -> fail
            "per_product_auc": {
                "home": {"auc": 0.80, "auc_ci": {"ci_low": 0.75, "ci_high": 0.85, "n": 1000},
                        "n_pos_test": 50, "ece": 0.01},
                "lap": {"auc": 0.70, "auc_ci": {"ci_low": 0.60, "ci_high": 0.80, "n": 1000},  # < 0.75 -> fail
                       "n_pos_test": 10, "ece": 0.05},  # > 0.03 -> fail
                "gold": {"auc": 0.90, "auc_ci": {"ci_low": 0.85, "ci_high": 0.95, "n": 1000},
                        "n_pos_test": 60, "ece": 0.01},
                "auto": {"auc": 0.88, "auc_ci": {"ci_low": 0.83, "ci_high": 0.93, "n": 1000},
                        "n_pos_test": 70, "ece": 0.01},
                "education": {"auc": 0.85, "auc_ci": {"ci_low": 0.80, "ci_high": 0.90, "n": 1000},
                             "n_pos_test": 55, "ece": 0.01},
                "personal": {"auc": 0.82, "auc_ci": {"ci_low": 0.77, "ci_high": 0.87, "n": 1000},
                            "n_pos_test": 90, "ece": 0.01},
            },
            "per_product": {p: {"auc": 0.8, "precision_at_budget": 0.2,
                                "auc_ci": {"n": 1000}}
                           for p in ("home", "lap", "gold", "auto", "education", "personal")},
            "macro_auc": 0.90,  # >= 0.78 -> pass
            "by_cut": {
                "channel": [{"level": "app", "n": 100, "n_pos": 10, "auc": 0.7,  # n < 500 -> skipped_low_n
                            "auc_ci": [0.6, 0.8], "precision_at_budget": 0.2,
                            "precision_ci": [0.1, 0.3], "baseline": 0.1}],
                "occupation_segment": [], "income_band": [], "tenure_band": [],
                "stage_reached": [], "city_tier": [],
            },
            "ece": 0.05,  # > 0.03 -> fail
            "calibration": [{"pred": 0.1, "obs": 0.1, "n": 500}],
            "menu": {"menu_of_4_hit_rate": 0.5, "menu_of_4_hit_rate_ci": [0.4, 0.6],  # < 0.8 -> fail
                    "top_1_product_accuracy": 0.3, "top_1_product_accuracy_ci": [0.2, 0.4],
                    "dropoff_anchor_top_1_accuracy": 0.3, "n_positives": 200, "n_switched": 50,
                    "menu_hit_rate_when_product_changed": 0.4,
                    "top_1_accuracy_when_product_changed": 0.05, "k": 4},
            "signal_effects": {
                "constrained": {
                    "journey_blank_field_ratio": {"effect": -0.1, "negative": True},
                    "journey_refused_income": {"effect": 0.02, "negative": False},  # flips this one
                    "journey_fee_balk": {"effect": -0.2, "negative": True},
                    "journey_doc_refusal": {"effect": -0.15, "negative": True},
                },  # n_negative = 3 < 4 -> fail
                "unconstrained": {}, "n_rows": 999, "n_rows_available": 999,
            },
            "stability": {"psi_score_distribution": 0.25},  # > 0.10 -> fail
            "seeds": {"n": 1, "list": [7], "spread": {}},
        },
    }


@pytest.fixture()
def synthetic_root(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "model_metrics.json").write_text(json.dumps(_synthetic_metrics()), encoding="utf-8")
    return tmp_path


def test_status_mapping_synthetic_metrics(synthetic_root, criteria_doc, make_ctx):
    from validation.runners import _shared as sh

    sh.reset_cache()
    by_id = _run_and_grade(synthetic_root, criteria_doc, make_ctx)

    expected_fail = {
        "SK-02",   # precision 0.20 < [0.25, 0.35]
        "SK-04",   # window respect 0.85 < 0.90
        "SK-07",   # OOT degradation 15.0 pp > 5.0
        "SK-08",   # lap AUC 0.70 < 0.75 (worst-cell rule)
        "SK-11",   # overall ECE 0.05 > 0.03
        "SK-12",   # lap ECE 0.05 > 0.03 (worst-cell rule)
        "SK-13",   # menu-of-4 0.5 < 0.80
        "SK-15",   # only 3/4 signals negative, band is >= 4
        "SK-16",   # PSI 0.25 > 0.10
    }
    expected_pass = {"SK-01", "SK-05", "SK-09"}
    expected_report = {"SK-03", "SK-06", "SK-14"}

    for cid in expected_fail:
        assert by_id[cid].status == "fail", f"{cid}: expected fail, got {by_id[cid].status}"
    for cid in expected_pass:
        assert by_id[cid].status == "pass", f"{cid}: expected pass, got {by_id[cid].status}"
    for cid in expected_report:
        assert by_id[cid].status == "report", f"{cid}: expected report, got {by_id[cid].status}"

    # SK-10: every by_cut cell is well under min_n=500 -> the whole per-cut
    # criterion grades to its worst cell, skipped_low_n (never silently
    # dropped — the harness carries the cell's own n).
    assert by_id["SK-10"].status == "skipped_low_n"
    low_n_cells = [c for c in by_id["SK-10"].breakdown if c.get("level") == "channel:app"]
    assert low_n_cells and low_n_cells[0]["status"] == "skipped_low_n"
    assert low_n_cells[0]["n"] == 100

    # every one of this lane's 16 criteria was graded — none silently pending
    for cid in MY_CRITERIA:
        assert by_id[cid].status is not None
        assert by_id[cid].status != "pending", f"{cid} unexpectedly pending against synthetic data"


def test_status_mapping_missing_metrics_file_is_pending(tmp_path, criteria_doc, make_ctx):
    """No data/model_metrics.json at all -> every criterion pending, never a
    silent pass and never a crash."""
    from validation.runners import _shared as sh

    sh.reset_cache()
    by_id = _run_and_grade(tmp_path, criteria_doc, make_ctx)
    for cid in MY_CRITERIA:
        assert by_id[cid].status == "pending"


# ---------------------------------------------------------------------------
# 2. real, small pipeline run — an integration smoke test
# ---------------------------------------------------------------------------
def test_status_mapping_small_pipeline_run(small_metrics_root, criteria_doc, make_ctx):
    from validation.runners import _shared as sh

    sh.reset_cache()
    by_id = _run_and_grade(small_metrics_root, criteria_doc, make_ctx)

    assert set(by_id) == set(MY_CRITERIA)
    for cid, res in by_id.items():
        assert res.status in _VALID_STATUSES, f"{cid}: invalid status {res.status!r}"
        assert res.status != "error", f"{cid}: runner raised — {res.detail}"

    # --quick (this fixture's MODEL_KW) skips the out-of-time exhibit: SK-07
    # must be reported pending with a legible reason, never silently graded.
    assert by_id["SK-07"].status == "pending"
    assert "quick" in (by_id["SK-07"].detail or "")

    # at 8,000 customers every by-cut cell is well under the pre-registered
    # min_n=500 floor -> SK-10 (worst-cell rule) must show it, not hide it.
    assert by_id["SK-10"].status == "skipped_low_n"
