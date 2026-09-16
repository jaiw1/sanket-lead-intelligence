"""
01 Held-out queue — baseline, precision at budget, window respect, shopper detection

Pre-registered criteria this runner answers: SK-01, SK-02, SK-03, SK-04, SK-05, SK-06

Consumes
--------
* ``data/model_metrics.json`` — the ONE `python3 src/score_and_pack.py` run's
  output (see `validation/runners/_shared.py` for why this pack reads that file
  rather than refitting a model): ``meta.population`` (the amended drop-off
  population, SK-01/SK-02's scoring population per the 2026-09-16 amendment),
  ``metrics.baseline_dropoff_disbursement``, ``metrics.precision_at_10pct``,
  ``metrics.precision_at`` (5% / 20%), ``metrics.window_respect_rate``,
  ``metrics.shopper_signal_auc``, ``metrics.headline`` /
  ``metrics.headline_parts``, ``metrics.seeds.spread`` (cross-seed CIs).

Produces
--------
* ``figures/precision_curve.png`` — precision @5/10/20% with CI, the SK-02
  band [0.25, 0.35] shaded at 10%, and the SK-01 band [0.08, 0.10] on the
  baseline.
* ``figures/window_respect.png`` — observed window-respect rate against the
  SK-04 floor (0.90).
* One `Result` per criterion: SK-01, SK-02, SK-03 (report, both side budgets),
  SK-04, SK-05, SK-06 (the headline, derived — no separate band).

Method
------
Every value here is `src/model/metrics.py`'s own computation, already run once
against the amended population (``data/labels.csv``, ``eligible_for_contact =
1``, held-out 30% of customers) — this runner does not re-score anyone. What it
adds is the independent grading: `value`/`ci`/`n` are set here, `status` is left
alone, so `validation.run.grade()` — reading `criteria.yaml`, not
`model.metrics.REGISTERED_BANDS` — is what actually calls pass/fail.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json",)


def _band_result(crit_id: str, m: dict, block_key: str, spread_key: str | None,
                  crit_by_id: dict[str, Criterion], detail_prefix: str = "") -> Result:
    block = m.get(block_key)
    if not block or block.get("value") is None:
        return Result(crit_id, status="pending",
                       detail=f"metrics.{block_key} not present in data/model_metrics.json")
    value = round(float(block["value"]), 4)
    n = block.get("n")
    ci, frag = (None, None)
    if spread_key:
        ci, frag = sh.spread_ci(m, spread_key)
    if ci is None:
        ci = sh.wilson_ci(block)
        frag = (f"95% CI is the packed seed's {block.get('method', 'wilson')} interval "
                f"(row-level; no cross-seed spread computed for this metric)")
    detail = f"{detail_prefix}{frag or ''}".strip()
    note = None
    if spread_key:
        note = sh.seed_mean_note(crit_by_id[crit_id], value, m, spread_key)
    if note:
        detail = f"{detail} | {note}" if detail else note
    return Result(crit_id, value=value, ci=ci, n=n, detail=detail or None)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    crit_by_id = {c.id: c for c in criteria}
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    results: list[Result] = []

    pop = (sh.meta(ctx) or {}).get("population", {})
    pop_note = (f"population: {pop.get('name', 'drop-off population')} "
                f"({pop.get('definition', '')}), amended 2026-09-16")

    # -- SK-01: random-contact disbursement rate ---------------------------- #
    results.append(_band_result("SK-01", m, "baseline_dropoff_disbursement", "baseline",
                                 crit_by_id, detail_prefix=f"{pop_note}. "))

    # -- SK-02: precision at the 10% contact budget -------------------------- #
    results.append(_band_result("SK-02", m, "precision_at_10pct", "precision_at_budget",
                                 crit_by_id, detail_prefix=f"{pop_note}. "))

    # -- SK-03: precision at 5% and 20%, reported ---------------------------- #
    pa = m.get("precision_at") or {}
    b5, b20 = pa.get("5"), pa.get("20")
    if b5 and b20:
        cells = []
        for budget_pct, block, spread_key in (("5pct", b5, "precision_at_5pct"),
                                              ("20pct", b20, "precision_at_20pct")):
            ci, _ = sh.spread_ci(m, spread_key)
            if ci is None:
                ci = sh.wilson_ci(block)
            cells.append(dict(level=f"precision_at_{budget_pct}",
                              value=round(float(block["value"]), 4), ci=ci, n=block.get("n")))
        results.append(Result("SK-03",
                              value={c["level"]: c["value"] for c in cells},
                              breakdown=cells,
                              detail="side budgets either side of the 10% operating point"))
    else:
        results.append(Result("SK-03", status="pending", detail="metrics.precision_at incomplete"))

    # -- SK-04: window respect rate ------------------------------------------ #
    results.append(_band_result("SK-04", m, "window_respect_rate", "window_respect_rate",
                                 crit_by_id))

    # -- SK-05: window-shopper detector AUC ----------------------------------- #
    shopper = m.get("shopper") or {}
    shopper_block = dict(value=shopper.get("auc"), ci_low=(shopper.get("ci") or [None, None])[0],
                         ci_high=(shopper.get("ci") or [None, None])[1], n=shopper.get("n"),
                         method="hanley-mcneil")
    results.append(_band_result("SK-05", m, "shopper_signal_auc", None, crit_by_id)
                   if m.get("shopper_signal_auc") else
                   Result("SK-05", value=shopper_block["value"], ci=sh.wilson_ci(shopper_block),
                          n=shopper_block["n"],
                          detail="graded against the generator's latent window_shopper flag "
                                 "(production target is the observable 2+-abandonment proxy; "
                                 "see MODEL_CARD.md limit 3)"))

    # -- SK-06: the headline, derived from SK-01 + SK-02 ---------------------- #
    headline = m.get("headline")
    parts = m.get("headline_parts") or {}
    if headline:
        results.append(Result(
            "SK-06", value=headline,
            detail=(f"baseline {parts.get('baseline_per_100')}/100 -> "
                    f"precision {parts.get('precision_per_100')}/100 at a "
                    f"{parts.get('budget', 0.10):.0%} contact budget; derived from SK-01 and "
                    f"SK-02 over the same {parts.get('population', 'population')}, never typed"),
        ))
    else:
        results.append(Result("SK-06", status="pending", detail="metrics.headline not present"))

    # -- figures --------------------------------------------------------------- #
    figs = []
    try:
        figs.append(_precision_curve_figure(ctx, m))
    except Exception as exc:  # a figure failing to render must not fail grading
        pass
    try:
        figs.append(_window_respect_figure(ctx, m))
    except Exception:
        pass
    if figs:
        by_id = {r.criterion_id: r for r in results}
        for cid in ("SK-01", "SK-02", "SK-03"):
            if cid in by_id and figs and figs[0]:
                by_id[cid].figures.append(figs[0])
        if len(figs) > 1 and figs[1] and "SK-04" in by_id:
            by_id["SK-04"].figures.append(figs[1])

    return results


def _precision_curve_figure(ctx: RunnerContext, m: dict) -> str | None:
    pa = m.get("precision_at") or {}
    if not pa:
        return None
    order = ["5", "10", "20"]
    xs = [int(k) for k in order if k in pa]
    ys = [pa[k]["value"] for k in order if k in pa]
    los = [pa[k].get("ci_low", pa[k]["value"]) for k in order if k in pa]
    his = [pa[k].get("ci_high", pa[k]["value"]) for k in order if k in pa]
    err = [np.array(ys) - np.array(los), np.array(his) - np.array(ys)]

    baseline = (m.get("baseline_dropoff_disbursement") or {}).get("value")

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    ax.errorbar(xs, ys, yerr=err, fmt="o-", color="#2563EB", capsize=4,
                label="precision@budget (model)")
    ax.axhspan(0.25, 0.35, color="#22C55E", alpha=0.12, label="SK-02 band [0.25, 0.35] @10%")
    if baseline is not None:
        ax.axhspan(0.08, 0.10, xmin=0, xmax=0.04, color="#94A3B8", alpha=0.25)
        ax.scatter([0], [baseline], color="#64748B", marker="s", zorder=3,
                   label=f"random contact ({baseline:.1%})")
    ax.set_xlabel("contact budget (%)")
    ax.set_ylabel("precision")
    ax.set_ylim(0, max(0.4, max(ys) * 1.15))
    ax.set_title("Precision curve — held-out drop-off population")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.25)
    return sh.savefig(fig, ctx, "precision_curve.png")


def _window_respect_figure(ctx: RunnerContext, m: dict) -> str | None:
    block = m.get("window_respect_rate")
    if not block:
        return None
    value = block["value"]
    lo, hi = block.get("ci_low"), block.get("ci_high")
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    ax.bar(["window respect"], [value], color="#2563EB", width=0.5,
           yerr=[[value - lo], [hi - value]] if lo is not None and hi is not None else None,
           capsize=6)
    sh.band_line(ax, 0.90, "SK-04 floor 0.90")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("rate")
    ax.set_title(f"Window respect @ 10% budget (n={block.get('n')})")
    ax.legend(fontsize=8)
    return sh.savefig(fig, ctx, "window_respect.png")
