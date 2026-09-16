"""
08 Ablation — what each feature family is worth

Pre-registered criteria this runner answers: SK-19

Consumes
--------
* the small-book refit harness (`validation/runners/_refit.py`) — a fresh
  8,000-customer / 30-month book (`realism.generate_book_and_journeys`, SD-S7's
  convention), point-in-time frame and customer-grouped split, built once and
  reused across every fit this runner makes. `data/model_metrics.json` never
  answers SK-19: the one full run was never asked to drop a family, so there
  is no adapter path here, only a refit — exactly what the L9 brief carves
  out of the "no second full run" rule for this criterion.
* `model.frame.FEATURE_FAMILIES` (`src/model/frame.py`) — the ten-family
  partition of `FEATURES` the module itself names as "also the ablation map
  runner 08 / SK-19 needs": income, balance, outflow, debt, life_event,
  profile, journey, shopper, contact, product. Every model input belongs to
  exactly one family (`FEATURES` is *derived* from this dict), so dropping a
  family and refitting is a clean, unambiguous ablation rather than a
  judgement call about which columns count as "cross-bank" or "dwell".

Produces
--------
* ``figures/ablation_deltas.png`` — precision@10% for each family-dropped
  refit against the small-book full-feature baseline, with CIs.
* One `Result` for SK-19: `value` is `{family: delta_precision_pp}`;
  `breakdown` carries one cell per family with the ablated precision, its CI,
  the baseline comparison and the AUC delta.

Method, as pre-registered
--------------------------
"Refit with each feature family removed in turn ... and report the change in
precision@10% with CIs. No band is pre-registered" (`criteria.yaml` SK-19
note). Ten refits (one per family) plus one full-feature baseline, all on the
small book, all against `model.train.fit_ranker` — the model's own training
function, never reimplemented. "No family may raise AUC beyond noise" (the L9
brief) is checked against the baseline's own Hanley-McNeil AUC interval and
reported in `detail` as an interpretive flag, not a second gate — SK-19 is
`severity: report` and no threshold was invented for it in `criteria.yaml`.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _refit as rf
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ()  # generates its own small book; see module docstring


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    h = rf.harness(ctx)
    if h.get("error"):
        return [Result("SK-19", status="pending",
                       detail=f"small-book refit harness failed: {h['error']}")]

    F = h["F"]
    base = rf.baseline(h)
    families = list(F.FEATURE_FAMILIES)

    cells = []
    raised_beyond_noise = []
    for fam in families:
        kept = tuple(f for f in F.FEATURES if f not in F.FEATURE_FAMILIES[fam])
        ablated = rf.fit_and_score(h, kept)
        delta_pp = round((base["precision"] - ablated["precision"]) * 100, 3)
        auc_delta = (round(ablated["auc"] - base["auc"], 4)
                    if ablated.get("auc") is not None and base.get("auc") is not None else None)
        beyond_noise = (ablated.get("auc") is not None and base.get("auc_ci")
                        and ablated["auc"] > base["auc_ci"][1])
        if beyond_noise:
            raised_beyond_noise.append(fam)
        cells.append(dict(
            level=fam, value=delta_pp, n=ablated["n"],
            ci=[ablated["ci_low"], ablated["ci_high"]],
            n_features_dropped=len(F.FEATURE_FAMILIES[fam]),
            columns_dropped=list(F.FEATURE_FAMILIES[fam]),
            ablated_precision=ablated["precision"], baseline_precision=base["precision"],
            ablated_auc=ablated.get("auc"), baseline_auc=base.get("auc"), delta_auc=auc_delta,
        ))

    noise_note = (f"Families whose ablated AUC rose ABOVE the baseline's own 95% Hanley-McNeil "
                 f"interval {base.get('auc_ci')} (i.e. dropping them helped beyond noise, "
                 f"which the L9 brief flags as worth a second look): {raised_beyond_noise}."
                 if raised_beyond_noise else
                 f"No family's ablated AUC rose above the baseline's 95% Hanley-McNeil interval "
                 f"{base.get('auc_ci')} — every drop that changed AUC changed it downward or "
                 f"within noise.")

    detail = (f"small-book refit (n={h['n_customers']:,} customers, single seed {rf.SMALL_SEED}, "
             f"150-tree LightGBM — see validation/runners/_refit.py for why this is a smaller, "
             f"noisier, single-seed estimate rather than a production-scale rerun). Baseline "
             f"(all {len(F.FEATURES)} features): precision@10%={base['precision']:.4f} "
             f"[{base['ci_low']:.4f}, {base['ci_high']:.4f}], AUC={base.get('auc')}. "
             f"delta_pp = baseline - ablated, in percentage points of precision@10% "
             f"(positive = the family helps; negative = dropping it improved precision on "
             f"this refit). 'product' drops the categorical that differentiates the six "
             f"candidate rows per customer-month by construction, so its ablation is expected "
             f"to collapse ranking rather than reveal a bug. {noise_note}")

    value = {c["level"]: c["value"] for c in cells}
    result = Result("SK-19", value=value, breakdown=cells, detail=detail)

    try:
        fig = _figure(ctx, base, cells)
        if fig:
            result.figures.append(fig)
    except Exception:
        pass

    return [result]


def _figure(ctx: RunnerContext, base: dict, cells: list[dict]) -> str | None:
    cells_sorted = sorted(cells, key=lambda c: c["value"], reverse=True)
    labels = [c["level"] for c in cells_sorted]
    ys = [c["ablated_precision"] for c in cells_sorted]
    los = [c["ci"][0] if c["ci"][0] is not None else y for c, y in zip(cells_sorted, ys)]
    his = [c["ci"][1] if c["ci"][1] is not None else y for c, y in zip(cells_sorted, ys)]
    err = [np.array(ys) - np.array(los), np.array(his) - np.array(ys)]

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    xs = np.arange(len(labels))
    ax.bar(xs, ys, yerr=err, capsize=3, color="#7C3AED", alpha=0.85, label="family dropped")
    sh.band_line(ax, base["precision"], f"baseline (all features) {base['precision']:.3f}", "h")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("precision @ 10% budget (small-book refit)")
    ax.set_title("SK-19 ablation: precision@10% with each feature family dropped")
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "ablation_deltas.png")
