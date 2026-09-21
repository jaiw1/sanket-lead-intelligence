"""
03 Per-product floors, the macro average, and the full by-cut table

Pre-registered criteria this runner answers: SK-08, SK-09, SK-10

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.per_product_auc`` (six products, each
  with a Hanley-McNeil AUC CI and ``ece``: SK-08), ``metrics.macro_auc``
  (SK-09), and ``metrics.by_cut`` (channel, occupation_segment, income_band,
  tenure_band, stage_reached, city_tier — each level already gated at
  ``min_n = 500`` inside ``src/model/pack.py _by_cut()``: SK-10). The seventh
  registered cut, ``product``, is not a separate `by_cut` key — it is exactly
  ``metrics.per_product`` (AUC + precision@10% per product), so SK-10's
  breakdown folds that in as its own cut rather than duplicating SK-08's
  computation under a different name.

Produces
--------
* ``figures/auc_by_product.png`` — the six per-product AUCs against the 0.75
  floor and the 0.78 macro floor.
* ``figures/auc_by_cut_grid.png`` — AUC by level for the other six cuts.
* SK-08 (`breakdown`: one cell per product, each graded >= 0.75 individually —
  min_n is 0 by registration, so no product cell is ever exempted), SK-09
  (the unweighted macro, a single scalar — never itself broken down, so a
  large product cannot carry the average past a failing small one), SK-10
  (`breakdown`: every level of all seven cuts, `report` severity, min_n 500).

Method
------
Everything is `src/model/metrics.py`'s own `per_product()`, `auc_ci()` and the
`_by_cut()` grouping already computed in the one `score_and_pack.py` run. This
runner does not re-slice the frame; it re-grades the same cells against
`criteria.yaml`, independently of `metrics.bands`.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json",)

#: The seven registered cuts, in criteria.yaml order. "product" is sourced from
#: metrics.per_product rather than metrics.by_cut (see module docstring).
CUT_IDS: tuple[str, ...] = (
    "product", "channel", "occupation_segment", "income_band",
    "tenure_band", "stage_reached", "city_tier",
)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    results: list[Result] = []
    results.append(_sk08(m))
    results.append(_sk09(m))
    results.append(_sk10(m))

    by_id = {r.criterion_id: r for r in results}
    try:
        fig1 = _auc_by_product_figure(ctx, m)
        if fig1:
            by_id["SK-08"].figures.append(fig1)
            by_id["SK-09"].figures.append(fig1)
    except Exception:
        pass
    try:
        fig2 = _auc_by_cut_grid_figure(ctx, m)
        if fig2:
            by_id["SK-10"].figures.append(fig2)
    except Exception:
        pass

    return results


def _sk08(m: dict) -> Result:
    per_product = m.get("per_product_auc") or {}
    if not per_product:
        return Result("SK-08", status="pending", detail="metrics.per_product_auc not present")
    cells = []
    for prod, row in per_product.items():
        auc_ci = row.get("auc_ci") or {}
        spread_ci, _ = sh.spread_ci(m, f"auc_{prod}", row.get("auc"))
        ci = spread_ci or sh.wilson_ci(auc_ci)
        cells.append(dict(level=prod, value=row.get("auc"), ci=ci,
                          n=auc_ci.get("n"), n_pos=row.get("n_pos_test")))
    worst = min(cells, key=lambda c: c["value"])
    return Result("SK-08", value=worst["value"], ci=worst["ci"], n=worst["n"],
                 breakdown=cells,
                 detail=f"binding product: {worst['level']} (n_pos={worst['n_pos']}); "
                        "the interval is the 5-SEED SPREAD where available (training-seed "
                        "variability, not a confidence interval), else the packed "
                        "seed's Hanley-McNeil 95% CI")


def _sk09(m: dict) -> Result:
    macro = m.get("macro_auc")
    if macro is None:
        return Result("SK-09", status="pending", detail="metrics.macro_auc not present")
    ci, frag = sh.spread_ci(m, "macro_auc", round(float(macro), 4))
    per_product = m.get("per_product_auc") or {}
    n = None
    if per_product:
        any_row = next(iter(per_product.values()))
        n = (any_row.get("auc_ci") or {}).get("n")
    return Result("SK-09", value=round(float(macro), 4), ci=ci, n=n,
                 detail=(frag or "unweighted mean of the six per-product AUCs; "
                                "no cross-seed spread computed"))


def _sk10(m: dict) -> Result:
    cells = []

    per_product = m.get("per_product") or {}
    for prod, row in per_product.items():
        auc, prec = row.get("auc"), row.get("precision_at_budget")
        cells.append(dict(
            level=f"product:{prod}",
            value=f"AUC {auc} · precision@10% {prec}" if auc is not None else None,
            ci=None, n=(row.get("auc_ci") or {}).get("n"),
            auc=auc, precision_at_10pct=prec,
        ))

    by_cut = m.get("by_cut") or {}
    for cut_id in CUT_IDS[1:]:
        for row in by_cut.get(cut_id, []):
            level = row.get("level")
            n = row.get("n")
            if "auc" not in row:  # already flagged skipped_low_n by the model
                cells.append(dict(level=f"{cut_id}:{level}", value=None, ci=None, n=n))
                continue
            cells.append(dict(
                level=f"{cut_id}:{level}",
                value=f"AUC {row['auc']} · precision@10% {row['precision_at_budget']}",
                ci=tuple(row["auc_ci"]) if row.get("auc_ci") else None,
                n=n, auc=row["auc"], precision_at_10pct=row["precision_at_budget"],
                n_pos=row.get("n_pos"),
            ))

    if not cells:
        return Result("SK-10", status="pending", detail="metrics.by_cut / metrics.per_product not present")
    return Result("SK-10", value=f"{len(cells)} cells across {len(CUT_IDS)} registered cuts",
                 breakdown=cells,
                 detail="report only, per criteria.yaml; cells below min_n=500 are "
                        "skipped_low_n, never silently dropped")


def _auc_by_product_figure(ctx: RunnerContext, m: dict) -> str | None:
    per_product = m.get("per_product_auc") or {}
    if not per_product:
        return None
    prods = list(per_product.keys())
    aucs = [per_product[p]["auc"] for p in prods]
    order = sorted(range(len(prods)), key=lambda i: aucs[i])
    prods = [prods[i] for i in order]
    aucs = [aucs[i] for i in order]

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    colors = ["#DC2626" if a < 0.75 else "#2563EB" for a in aucs]
    ax.bar(prods, aucs, color=colors)
    sh.band_line(ax, 0.75, "SK-08 floor 0.75")
    macro = m.get("macro_auc")
    if macro is not None:
        ax.axhline(macro, linestyle=":", color="#16A34A", label=f"macro AUC {macro:.3f}")
    ax.axhline(0.78, linestyle="--", color="#16A34A", alpha=0.5, label="SK-09 floor 0.78")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("AUC")
    ax.set_title("Per-product AUC (held-out)")
    ax.legend(fontsize=7)
    plt.xticks(rotation=20)
    return sh.savefig(fig, ctx, "auc_by_product.png")


def _auc_by_cut_grid_figure(ctx: RunnerContext, m: dict) -> str | None:
    by_cut = m.get("by_cut") or {}
    cuts = [c for c in CUT_IDS[1:] if by_cut.get(c)]
    if not cuts:
        return None
    ncols = 3
    nrows = (len(cuts) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.0 * nrows))
    axes = axes.flatten() if hasattr(axes, "flatten") else [axes]
    for ax, cut_id in zip(axes, cuts):
        rows = [r for r in by_cut[cut_id] if "auc" in r]
        skipped = [r for r in by_cut[cut_id] if "auc" not in r]
        levels = [r["level"] for r in rows]
        aucs = [r["auc"] for r in rows]
        ax.bar(levels, aucs, color="#2563EB")
        sh.band_line(ax, 0.75, None)
        ax.set_title(f"{cut_id}" + (f" ({len(skipped)} skipped_low_n)" if skipped else ""),
                    fontsize=9)
        ax.set_ylim(0, 1.0)
        ax.tick_params(axis="x", labelrotation=30, labelsize=7)
    for ax in axes[len(cuts):]:
        ax.axis("off")
    fig.suptitle("AUC by cut (reported, SK-10)")
    fig.tight_layout()
    return sh.savefig(fig, ctx, "auc_by_cut_grid.png")
