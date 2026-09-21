"""
04 Calibration — the probability the RM is shown

Pre-registered criteria this runner answers: SK-11, SK-12

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.ece`` (overall, SK-11),
  ``metrics.per_product_auc[*].ece`` (per product, SK-12) and
  ``metrics.calibration`` (the ten equal-count reliability bins
  `src/model/metrics.py reliability()` emits: `pred`, `obs`, `n` per bin) for
  the reliability plot.

Produces
--------
* ``figures/reliability_overall.png`` — predicted vs observed rate, ten
  equal-count bins, against the identity line.
* ``figures/ece_by_product.png`` — per-product ECE against the 0.03 floor.
* SK-11 (overall ECE, `le 0.03`), SK-12 (per-product ECE, `breakdown`: one
  cell per product, the same 0.03 band applied to each).

Method
------
Isotonic per-product calibration and the ECE computation both already
happened inside the one `score_and_pack.py` run (`src/model/train.py`'s
per-product isotonic fit, `src/model/metrics.py ece()` / `reliability()`).
This runner reads the result and grades it against `criteria.yaml`
independently of `metrics.bands`.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json",)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    results: list[Result] = []

    # -- SK-11: overall ECE --------------------------------------------------- #
    ece = m.get("ece")
    if ece is None:
        results.append(Result("SK-11", status="pending", detail="metrics.ece not present"))
    else:
        ci, frag = sh.spread_ci(m, "ece_overall", round(float(ece), 5))
        calib = m.get("calibration") or []
        n = sum(b.get("n", 0) for b in calib) or None
        results.append(Result("SK-11", value=round(float(ece), 5), ci=ci, n=n,
                              detail=frag or "no cross-seed spread computed for overall ECE"))

    # -- SK-12: per-product ECE ----------------------------------------------- #
    per_product = m.get("per_product_auc") or {}
    if not per_product:
        results.append(Result("SK-12", status="pending", detail="metrics.per_product_auc not present"))
    else:
        cells = [dict(level=prod, value=row.get("ece"),
                      n=(row.get("auc_ci") or {}).get("n"), ci=None)
                for prod, row in per_product.items()]
        worst = max(cells, key=lambda c: c["value"])
        results.append(Result("SK-12", value=worst["value"], n=worst["n"], breakdown=cells,
                              detail=f"binding (worst) product: {worst['level']}; no CI computed "
                                     "for ECE by src/model/metrics.py"))

    by_id = {r.criterion_id: r for r in results}
    try:
        fig1 = _reliability_figure(ctx, m)
        if fig1 and "SK-11" in by_id:
            by_id["SK-11"].figures.append(fig1)
    except Exception:
        pass
    try:
        fig2 = _ece_by_product_figure(ctx, m)
        if fig2 and "SK-12" in by_id:
            by_id["SK-12"].figures.append(fig2)
    except Exception:
        pass

    return results


def _reliability_figure(ctx: RunnerContext, m: dict) -> str | None:
    calib = m.get("calibration") or []
    if not calib:
        return None
    preds = [b["pred"] for b in calib]
    obs = [b["obs"] for b in calib]
    fig, ax = plt.subplots(figsize=(4.2, 4.0))
    lim = max(max(preds, default=0), max(obs, default=0)) * 1.15 or 1.0
    ax.plot([0, lim], [0, lim], linestyle="--", color="#94A3B8", label="perfect calibration")
    ax.scatter(preds, obs, s=[max(20, b["n"] / 50) for b in calib], color="#2563EB",
              label="decile bin (size ~ n)")
    ax.set_xlabel("mean predicted probability")
    ax.set_ylabel("observed disbursement rate")
    ax.set_title(f"Reliability — overall ECE {m.get('ece')}")
    ax.legend(fontsize=7)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    return sh.savefig(fig, ctx, "reliability_overall.png")


def _ece_by_product_figure(ctx: RunnerContext, m: dict) -> str | None:
    per_product = m.get("per_product_auc") or {}
    if not per_product:
        return None
    prods = list(per_product.keys())
    eces = [per_product[p]["ece"] for p in prods]
    order = sorted(range(len(prods)), key=lambda i: eces[i], reverse=True)
    prods, eces = [prods[i] for i in order], [eces[i] for i in order]
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    colors = ["#DC2626" if e > 0.03 else "#2563EB" for e in eces]
    ax.bar(prods, eces, color=colors)
    sh.band_line(ax, 0.03, "SK-12 ceiling 0.03")
    ax.set_ylabel("ECE")
    ax.set_title("Per-product ECE")
    ax.legend(fontsize=8)
    plt.xticks(rotation=20)
    return sh.savefig(fig, ctx, "ece_by_product.png")
