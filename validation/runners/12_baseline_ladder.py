"""
12 Baseline ladder — how much of 9-to-30 is the model

Pre-registered criteria this runner answers: SK-25

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.baseline_ladder`` (`src/model/pack.py`
  ``baseline_ladder()``): four rungs on the SAME held-out book at the SAME
  10% budget — random contact, balance-ranked contact (`bal_avg`, "what a
  branch does today"), a logistic scorecard (`LADDER_FEATURES`, 16 columns,
  standardised, `sklearn.linear_model.LogisticRegression`), and SANKET itself
  — each with a Wilson precision CI and n. Skipped under `--quick`
  (`ladder = [] if cfg.quick else baseline_ladder(...)`), which the one run
  this lane was given did not use.

Produces
--------
* ``figures/baseline_ladder.png`` — precision@10% per rung, with CIs.
* One `Result` for SK-25: `value` is `[{rung, precision, ci, n}, ...]` in the
  pre-registered rung order; `breakdown` carries the same four cells.

Method, as pre-registered
--------------------------
"Four rungs on the same held-out book with the same CIs ... Report
precision@10% per rung. The rungs are pre-registered so the comparison set
cannot be chosen after the fact" (`criteria.yaml` SK-25 note). The rungs and
their order are `src/model/pack.py baseline_ladder()`'s own — not
re-ordered, re-selected or recomputed here.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json",)

#: The pre-registered rung order (`criteria.yaml` SK-25 note / rationale).
_RUNG_ORDER = ("random contact", "balance-ranked (what a branch does today)",
              "logistic scorecard", "SANKET (one LightGBM, six products)")


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    ladder = m.get("baseline_ladder")
    if not ladder:
        return [Result("SK-25", status="pending",
                       detail="metrics.baseline_ladder not present — the one run this lane was "
                              "given must not have used --quick, which skips this exhibit "
                              "(src/model/pack.py: `ladder = [] if cfg.quick else "
                              "baseline_ladder(...)`)")]

    by_rung = {r["rung"]: r for r in ladder}
    ordered = [by_rung[r] for r in _RUNG_ORDER if r in by_rung]
    extra = [r for r in ladder if r["rung"] not in _RUNG_ORDER]
    ordered += extra  # never silently drop a rung the run actually produced

    cells = [dict(level=r["rung"], value=round(float(r["precision"]), 4), n=r.get("n"),
                 ci=[r.get("ci_low"), r.get("ci_high")])
            for r in ordered]

    model_p = next((r["precision"] for r in ordered
                    if r["rung"] == "SANKET (one LightGBM, six products)"), None)
    random_p = next((r["precision"] for r in ordered if r["rung"] == "random contact"), None)
    balance_p = next((r["precision"] for r in ordered
                      if r["rung"] == "balance-ranked (what a branch does today)"), None)
    logistic_p = next((r["precision"] for r in ordered if r["rung"] == "logistic scorecard"), None)

    gaps = []
    if balance_p is not None and random_p is not None:
        gaps.append(f"balance-ranking over random: {(balance_p - random_p) * 100:+.2f} pp")
    if logistic_p is not None and balance_p is not None:
        gaps.append(f"logistic over balance-ranking: {(logistic_p - balance_p) * 100:+.2f} pp")
    if model_p is not None and logistic_p is not None:
        gaps.append(f"SANKET over logistic: {(model_p - logistic_p) * 100:+.2f} pp")

    detail = (f"four rungs, same held-out book, same 10% budget: "
             f"{[(c['level'], c['value']) for c in cells]}. Rung-to-rung gaps: "
             f"{'; '.join(gaps) if gaps else 'not computable — a rung is missing'}. "
             f"If a rung is within noise of the next, that is the honest finding "
             f"(criteria.yaml SK-25 rationale: 'If balance-ranking is within noise of the "
             f"model, that is the honest finding and the deck says so').")

    value = cells
    result = Result("SK-25", value=value, breakdown=cells, detail=detail)

    try:
        fig = _figure(ctx, cells)
        if fig:
            result.figures.append(fig)
    except Exception:
        pass

    return [result]


def _figure(ctx: RunnerContext, cells: list[dict]) -> str | None:
    labels = [c["level"].replace(" (", "\n(") for c in cells]
    ys = [c["value"] for c in cells]
    los = [c["ci"][0] if c["ci"][0] is not None else y for c, y in zip(cells, ys)]
    his = [c["ci"][1] if c["ci"][1] is not None else y for c, y in zip(cells, ys)]
    err = [[y - lo for y, lo in zip(ys, los)], [hi - y for y, hi in zip(ys, his)]]

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    xs = range(len(labels))
    ax.bar(xs, ys, yerr=err, capsize=5, color=["#94A3B8", "#94A3B8", "#F59E0B", "#2563EB"][:len(labels)])
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("precision @ 10% budget")
    ax.set_title("SK-25 baseline ladder: how much of 9-to-30 is the model")
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "baseline_ladder.png")
