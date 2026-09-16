"""
report.json's schema, and REPORT.md's section order.

The L9 brief: "REPORT.md renders the pre-registration + amendment block
first." `validation/report.py render_markdown()` writes, in order: the verdict
line, `## Pre-registration` (the registration timestamp, rulings, and —
because `criteria.yaml` carries the 2026-09-16 amendment — the amendments
block), *then* failures, pending, and `## All criteria`. This file checks that
order holds, and that `report.json` — the file the deploy pipeline's verify
step and the G5 honesty gate both read — has the shape they expect, using this
lane's own six runners against the small real pipeline run
(`small_metrics_root`, see `conftest.py`) rather than a hand-typed stand-in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation import report as report_mod
from validation.run import execute

#: `execute()` with `only=None` runs every runner `criteria.yaml` references —
#: this lane's six real ones plus the six still-`NotImplementedError` stubs
#: (07-12), exactly what `python3 -m validation.run` does. Using the real
#: public entry point here (rather than hand-dispatching just this lane's
#: runners) is what makes `report.json`'s full 25-criterion shape — and the
#: "some criteria pending" mix — a faithful test rather than a re-derivation.
def _execute_all(repo_root, doc, out_dir):
    return execute(doc, repo_root, out_dir)


def test_report_json_schema(small_metrics_root, criteria_doc, tmp_path):
    from validation.runners import _shared as sh

    sh.reset_cache()
    out_dir = tmp_path / "report"
    results = _execute_all(small_metrics_root, criteria_doc, out_dir)
    report_mod.write(criteria_doc, results, out_dir, strict=False)

    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))

    for key in ("product", "schema_version", "registered_at", "registered_by",
               "provenance", "verdict", "strict", "counts", "criteria",
               "amendments", "rulings"):
        assert key in payload, f"report.json missing top-level key {key!r}"

    assert payload["product"] == "SANKET"
    assert payload["verdict"] in (
        "PASS", "FAIL", "PASS (with pending runners — not yet the G7 gate)")
    assert isinstance(payload["criteria"], list) and len(payload["criteria"]) > 0
    assert isinstance(payload["amendments"], list) and len(payload["amendments"]) >= 1
    assert payload["provenance"]["criteria_registered_at"] == criteria_doc.registered_at.isoformat()

    graded_ids = {c["result"]["criterion_id"] for c in payload["criteria"]}
    assert {f"SK-{i:02d}" for i in range(1, 17)} <= graded_ids

    valid_status = {"pass", "fail", "warn", "report", "pending", "skipped_low_n", "error"}
    for entry in payload["criteria"]:
        assert "id" in entry and "runner" in entry and "metric" in entry   # the Criterion fields
        res = entry["result"]
        assert res["criterion_id"] == entry["id"]
        assert res["status"] in valid_status
        assert "value" in res and "ci" in res and "n" in res and "breakdown" in res and "figures" in res


def test_report_json_counts_match_results(small_metrics_root, criteria_doc, tmp_path):
    from validation.runners import _shared as sh

    sh.reset_cache()
    out_dir = tmp_path / "report"
    results = _execute_all(small_metrics_root, criteria_doc, out_dir)
    report_mod.write(criteria_doc, results, out_dir, strict=False)
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))

    counts = payload["counts"]
    by_status = {}
    for entry in payload["criteria"]:
        s = entry["result"]["status"]
        by_status[s] = by_status.get(s, 0) + 1
    for status, n in by_status.items():
        assert counts.get(status, 0) == n, f"counts[{status!r}] mismatched"
    # every criterion this pack registers appears exactly once (16 graded by
    # this lane's runners + 9 left pending by the unimplemented ones)
    assert sum(counts.values()) == len(criteria_doc.criteria)


def test_report_markdown_pre_registration_before_all_criteria(small_metrics_root, criteria_doc, tmp_path):
    from validation.runners import _shared as sh

    sh.reset_cache()
    out_dir = tmp_path / "report"
    results = _execute_all(small_metrics_root, criteria_doc, out_dir)
    md = report_mod.render_markdown(criteria_doc, results, out_dir, strict=False)

    verdict_idx = md.index("**Verdict:")
    prereg_idx = md.index("## Pre-registration")
    all_crit_idx = md.index("## All criteria")

    # the verdict line leads, then pre-registration, then the per-criterion
    # tables — never the other way around
    assert verdict_idx < prereg_idx < all_crit_idx

    # the amendment block (this pack carries the 2026-09-16 SK-01/SK-02
    # scoping amendment) renders INSIDE the pre-registration section, not
    # after it
    amend_idx = md.index("Amendments after registration")
    assert prereg_idx < amend_idx < all_crit_idx

    # the registration timestamp itself is quoted in that section
    assert criteria_doc.registered_at.isoformat() in md[prereg_idx:all_crit_idx]


def test_report_markdown_renders_every_amendment(small_metrics_root, criteria_doc, tmp_path):
    from validation.runners import _shared as sh

    sh.reset_cache()
    out_dir = tmp_path / "report"
    results = _execute_all(small_metrics_root, criteria_doc, out_dir)
    md = report_mod.render_markdown(criteria_doc, results, out_dir, strict=False)
    for amendment in criteria_doc.amendments:
        assert amendment.at.isoformat() in md
        # a real (non-)loosening amendment must not be silently marked one way
        if amendment.loosening:
            assert "LOOSENING" in md
