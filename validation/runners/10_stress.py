"""
10 Stress — the book under two pre-registered shifts

Pre-registered criteria this runner answers: SK-22

Consumes
--------
* the small-book refit harness (`validation/runners/_refit.py`) — same book,
  frame and split `08_ablation` uses, and (when both runners execute in the
  same `python3 -m validation.run` process) the SAME cached full-feature
  baseline fit, so this runner's own cost is one extra refit plus one
  zero-refit re-score.

Produces
--------
* ``figures/stress_precision.png`` — precision@10% under each scenario
  against the small-book baseline, with CIs.
* One `Result` for SK-22: `value` is `{scenario: delta_precision_pp}`;
  `breakdown` carries one cell per scenario.

Method, as pre-registered
--------------------------
`criteria.yaml` SK-22's rationale names four scenarios (consent withdrawal at
scale, a suppression-rule sweep, cross-bank transaction data unavailable, a
doubled window-shopper share) and registers no band ("no threshold was
invented"). This lane's brief narrows execution to the two that are tractable
as a refit/re-score on the small book within the remaining budget, and says
so rather than silently substituting:

1. **2x base rate** — eligible, training-split POSITIVE rows are duplicated
   before fitting (`_refit.reweighted_fit_and_score`), then scored against the
   unduplicated held population. A refit, because a base-rate shift changes
   what the ranker learns, not just what it is fed at inference.
2. **channel-missing** — the `contact` family (`contacts_30d`, `contacts_90d`,
   `campaign_contacts_6m`, `last_contact_days`,
   `last_campaign_matches_product` — the bank's own contact-history channel)
   is blanked to NaN in a COPY of the frame and re-scored through the
   ALREADY-FITTED baseline ranker (`_refit.blanked_score`, zero extra fits) —
   deliberately an inference-time channel outage, not a retrain that never
   knew the channel existed, which is the more realistic production failure
   mode and also the cheaper one to run.

The other two registered scenarios (consent withdrawal at scale, a
suppression-rule sweep) are reported `not computed this pass`, with the
reason, rather than approximated: both are about which rows enter the
*population* the labels/suppression layer (`journeys.labels`) builds, which
this runner cannot alter without re-running `journeys.build` under different
generator parameters — a second full generator run, which this lane's refit
budget does not cover twice over.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _refit as rf
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ()  # generates its own small book; see module docstring

_BLANKED_FAMILY = "contact"

_NOT_COMPUTED = (
    "consent withdrawal at scale",
    "suppression-rule sweep (plan §B L6 SD-S6)",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    h = rf.harness(ctx)
    if h.get("error"):
        return [Result("SK-22", status="pending",
                       detail=f"small-book refit harness failed: {h['error']}")]

    base = rf.baseline(h)
    reweighted = rf.reweighted_fit_and_score(h, multiplier=2)
    blanked = rf.blanked_score(h, base["ranker"], _BLANKED_FAMILY)

    cells = [
        dict(level="2x_base_rate_reweight_positives",
            value=round((reweighted["precision"] - base["precision"]) * 100, 3),
            n=reweighted["n"], ci=[reweighted["ci_low"], reweighted["ci_high"]],
            precision=reweighted["precision"], auc=reweighted.get("auc"),
            n_fit_positives_added=reweighted.get("n_fit_positives_added")),
        dict(level=f"channel_missing_{_BLANKED_FAMILY}",
            value=round((blanked["precision"] - base["precision"]) * 100, 3),
            n=blanked["n"], ci=[blanked["ci_low"], blanked["ci_high"]],
            precision=blanked["precision"], auc=blanked.get("auc"),
            blanked_columns=blanked.get("blanked_columns")),
    ]

    detail = (f"small-book refit (n={h['n_customers']:,} customers, single seed {rf.SMALL_SEED} "
             f"— see validation/runners/_refit.py). Baseline: precision@10%="
             f"{base['precision']:.4f} [{base['ci_low']:.4f}, {base['ci_high']:.4f}], AUC="
             f"{base.get('auc')}. delta_pp = scenario - baseline (positive = the scenario "
             f"IMPROVED precision, negative = it degraded). 2x base rate: "
             f"{reweighted.get('n_fit_positives_added')} duplicate positive training rows added "
             f"to the fit split only, scored against the unduplicated held population — precision@10%="
             f"{reweighted['precision']:.4f}. channel-missing ({_BLANKED_FAMILY}): "
             f"{blanked.get('blanked_columns')} blanked to NaN in a copy of the SAME fitted "
             f"baseline ranker's scoring frame (no retrain) — precision@10%="
             f"{blanked['precision']:.4f}. Registered scenarios NOT computed this pass "
             f"(reason: each needs a second generator run under altered parameters, which the "
             f"refit budget does not cover twice over — not approximated, not silently dropped): "
             f"{list(_NOT_COMPUTED)}.")

    value = {c["level"]: c["value"] for c in cells}
    result = Result("SK-22", value=value, breakdown=cells, detail=detail)

    try:
        fig = _figure(ctx, base, cells)
        if fig:
            result.figures.append(fig)
    except Exception:
        pass

    return [result]


def _figure(ctx: RunnerContext, base: dict, cells: list[dict]) -> str | None:
    labels = ["baseline"] + [c["level"] for c in cells]
    ys = [base["precision"]] + [c["precision"] for c in cells]
    los = [base["ci_low"]] + [c["ci"][0] if c["ci"][0] is not None else c["precision"] for c in cells]
    his = [base["ci_high"]] + [c["ci"][1] if c["ci"][1] is not None else c["precision"] for c in cells]
    err = [np.array(ys) - np.array(los), np.array(his) - np.array(ys)]

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    xs = np.arange(len(labels))
    colors = ["#2563EB"] + ["#F59E0B"] * len(cells)
    ax.bar(xs, ys, yerr=err, capsize=4, color=colors)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("precision @ 10% budget (small-book refit)")
    ax.set_title("SK-22 stress scenarios vs small-book baseline")
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "stress_precision.png")
