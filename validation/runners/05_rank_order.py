"""
05 Menu of four, top-1, and the direction of the shopper signals

Pre-registered criteria this runner answers: SK-13, SK-14, SK-15

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.menu`` (`src/model/metrics.py
  menu_metrics()`: menu-of-4 hit rate + CI, top-1 accuracy + CI, the
  drop-off-anchor and product-switcher sub-readings, `n_positives`) and
  ``metrics.signal_effects`` (mean SHAP on-minus-off for the four mentor
  signals, both the shipped **constrained** model and an **unconstrained**
  twin, per `src/model/train.py`'s docstring on why both are measured).

Produces
--------
* ``figures/menu_hit_rate.png`` — menu-of-4 vs top-1 vs the drop-off-anchor
  rule, against the SK-13 floor.
* ``figures/shopper_signal_directions.png`` — the four signals' constrained
  and unconstrained effect, signed, against zero.
* SK-13 (menu-of-4 hit rate, `>= 0.80`), SK-14 (top-1 accuracy, reported, no
  target — see criteria.yaml's note on why one was deliberately not set),
  SK-15 (count of the four mentor signals whose constrained effect is
  negative, `>= 4`).

Method
------
`menu_metrics()` and `signal_effects()` are `src/model/metrics.py` /
`src/model/pack.py`'s own computations from the one `score_and_pack.py` run.
This runner reads them and lets `validation.run.grade()` — not
`metrics.bands` — decide pass/fail against `criteria.yaml`.
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
    menu = m.get("menu") or {}

    # -- SK-13: menu-of-4 hit rate --------------------------------------------- #
    if menu.get("menu_of_4_hit_rate") is None:
        results.append(Result("SK-13", status="pending", detail="metrics.menu not present"))
    else:
        ci, frag = sh.spread_ci(m, "menu_of_4_hit_rate",
                                round(float(menu["menu_of_4_hit_rate"]), 4))
        if ci is None:
            raw_ci = menu.get("menu_of_4_hit_rate_ci")
            ci = tuple(round(x, 4) for x in raw_ci) if raw_ci else None
            frag = "Interval is the packed seed's own 95% Wilson confidence interval"
        results.append(Result(
            "SK-13", value=round(float(menu["menu_of_4_hit_rate"]), 4), ci=ci,
            n=menu.get("n_positives"), detail=frag))

    # -- SK-14: top-1 accuracy, reported, deliberately no target --------------- #
    if menu.get("top_1_product_accuracy") is None:
        results.append(Result("SK-14", status="pending", detail="metrics.menu not present"))
    else:
        raw_ci = menu.get("top_1_product_accuracy_ci")
        ci = tuple(round(x, 4) for x in raw_ci) if raw_ci else None
        results.append(Result(
            "SK-14", value=round(float(menu["top_1_product_accuracy"]), 4), ci=ci,
            n=menu.get("n_positives"),
            detail=(f"drop-off-anchor rule (offer what they abandoned) scores "
                    f"{menu.get('dropoff_anchor_top_1_accuracy')} on the same population — "
                    f"the anchor does most of top-1's work; among the "
                    f"{menu.get('n_switched')} positives who switched product, top-1 scores "
                    f"{menu.get('top_1_accuracy_when_product_changed')} and the menu-of-4 scores "
                    f"{menu.get('menu_hit_rate_when_product_changed')} — that gap is the menu's "
                    f"real value. No target is registered by design (criteria.yaml SK-14 note)."),
        ))

    # -- SK-15: direction of the four mentor signals --------------------------- #
    sig = m.get("signal_effects") or {}
    constrained = sig.get("constrained") or {}
    if not constrained:
        results.append(Result("SK-15", status="pending", detail="metrics.signal_effects not present"))
    else:
        n_negative = sum(1 for row in constrained.values() if row.get("negative"))
        lines = [f"{name}: {row.get('effect')} ({'negative' if row.get('negative') else 'POSITIVE'})"
                for name, row in constrained.items()]
        unconstrained = sig.get("unconstrained") or {}
        n_neg_unconstrained = sum(1 for row in unconstrained.values() if row.get("negative"))
        results.append(Result(
            "SK-15", value=n_negative, n=sig.get("n_rows"),
            detail=("shipped (constrained) model: " + "; ".join(lines) +
                    f" | unconstrained twin: {n_neg_unconstrained}/4 negative "
                    "(the constraint's job is separating a real signal from an enforced sign — "
                    "see MODEL_CARD.md's income-refusal discussion)"),
        ))

    by_id = {r.criterion_id: r for r in results}
    try:
        fig1 = _menu_figure(ctx, menu)
        if fig1:
            if "SK-13" in by_id:
                by_id["SK-13"].figures.append(fig1)
            if "SK-14" in by_id:
                by_id["SK-14"].figures.append(fig1)
    except Exception:
        pass
    try:
        fig2 = _signal_figure(ctx, sig)
        if fig2 and "SK-15" in by_id:
            by_id["SK-15"].figures.append(fig2)
    except Exception:
        pass

    return results


def _menu_figure(ctx: RunnerContext, menu: dict) -> str | None:
    if not menu:
        return None
    labels = ["menu-of-4", "top-1", "drop-off anchor\n(no model)"]
    values = [menu.get("menu_of_4_hit_rate"), menu.get("top_1_product_accuracy"),
             menu.get("dropoff_anchor_top_1_accuracy")]
    if any(v is None for v in values):
        return None
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    ax.bar(labels, values, color=["#2563EB", "#94A3B8", "#94A3B8"])
    sh.band_line(ax, 0.80, "SK-13 floor 0.80")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("hit rate")
    ax.set_title(f"Menu of 4 vs top-1 (n={menu.get('n_positives')})")
    ax.legend(fontsize=8)
    return sh.savefig(fig, ctx, "menu_hit_rate.png")


def _signal_figure(ctx: RunnerContext, sig: dict) -> str | None:
    constrained = sig.get("constrained") or {}
    unconstrained = sig.get("unconstrained") or {}
    if not constrained:
        return None
    names = list(constrained.keys())
    short = [n.replace("journey_", "") for n in names]
    c_vals = [constrained[n]["effect"] for n in names]
    u_vals = [unconstrained.get(n, {}).get("effect", 0) for n in names]

    import numpy as np
    x = np.arange(len(names))
    width = 0.35
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.bar(x - width / 2, c_vals, width, label="shipped (constrained)", color="#2563EB")
    ax.bar(x + width / 2, u_vals, width, label="unconstrained twin",
          color=["#DC2626" if v > 0 else "#94A3B8" for v in u_vals])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(short, rotation=15, fontsize=8)
    ax.set_ylabel("mean SHAP, on - off")
    ax.set_title("The four mentor signals — SK-15")
    ax.legend(fontsize=8)
    return sh.savefig(fig, ctx, "shopper_signal_directions.png")
