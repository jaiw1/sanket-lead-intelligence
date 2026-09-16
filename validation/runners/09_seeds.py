"""
09 Seed sweep — is the headline a property of the model or of the seed

Pre-registered criteria this runner answers: SK-20, SK-21

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.seeds`` (`src/model/pack.py``
  ``run()``): ``n`` / ``list`` (every registered seed [7, 8, 9, 10, 11] that
  was actually fit and measured — `criteria.yaml seeds.policy` forbids
  dropping or cherry-picking any of them), ``per_seed`` (one row per seed:
  baseline, precision@5/10/20%, macro AUC, menu, window respect, ECE — the
  raw per-seed values SK-21's width is computed from), and ``spread`` (`model.
  metrics.spread()`'s cross-seed 2.5-97.5 percentile interval for each
  headline metric, per `criteria.yaml confidence.cross_seed`).

Produces
--------
* ``figures/seed_sweep_precision.png`` — precision@10% for every registered
  seed against the SK-21 CI-width ceiling.
* SK-20 (`n_seeds_run`, `>= 5`) and SK-21
  (`cross_seed_precision_at_10pct_ci_width_pp`, `<= 4.0`).

Method
------
The ONE `python3 src/score_and_pack.py` run already fits and measures every
registered seed (`evaluate_seed` per seed in `src/model/pack.py run()`) —
re-running generation/split/fit across the five registered seeds a second
time here would be exactly the second full run this lane's budget forbids.
This runner reads that already-computed sweep and lets `validation.run.grade()`
compare `n` and the width, independently, against the registered floors —
never `metrics.bands["SK-20"/"SK-21"]["verdict"]`.
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

    seeds = m.get("seeds") or {}
    seed_list = seeds.get("list") or []
    per_seed = seeds.get("per_seed") or []
    n_seeds = seeds.get("n")

    if n_seeds is None:
        return [Result("SK-20", status="pending", detail="metrics.seeds.n not present"),
                Result("SK-21", status="pending", detail="metrics.seeds.spread not present")]

    registered_seeds = tuple((ctx.doc.seeds.seed_list) or ())
    missing = [s for s in registered_seeds if s not in seed_list]
    detail_20 = (f"seeds actually fit and measured: {seed_list} (registered: "
                f"{list(registered_seeds)}); none dropped or cherry-picked"
                + (f" — MISSING from the run: {missing}" if missing else ""))
    result_20 = Result("SK-20", value=int(n_seeds), n=int(n_seeds), detail=detail_20)

    spread = ((seeds.get("spread") or {}).get("precision_at_budget")) or {}
    width_pp = spread.get("pct_width_pp")
    if width_pp is None:
        result_21 = Result("SK-21", status="pending",
                           detail="metrics.seeds.spread.precision_at_budget not present")
    else:
        detail_21 = (f"precision@10% per seed: "
                     f"{[round(s.get('precision', {}).get('0.1', {}).get('precision', float('nan')), 4) for s in per_seed]}; "
                     f"cross-seed mean {spread.get('mean')}, 2.5-97.5 percentile "
                     f"[{spread.get('pct_low')}, {spread.get('pct_high')}], width "
                     f"{round(float(width_pp), 4)} pp over {spread.get('n')} seeds "
                     f"(criteria.yaml confidence.cross_seed).")
        result_21 = Result("SK-21", value=round(float(width_pp), 4), n=spread.get("n"),
                           detail=detail_21)

    try:
        fig = _figure(ctx, per_seed, spread)
        if fig:
            result_20.figures.append(fig)
            result_21.figures.append(fig)
    except Exception:
        pass

    return [result_20, result_21]


def _figure(ctx: RunnerContext, per_seed: list[dict], spread: dict) -> str | None:
    if not per_seed:
        return None
    seeds = [s.get("seed") for s in per_seed]
    ys = [s.get("precision", {}).get("0.1", {}).get("precision") for s in per_seed]
    if any(y is None for y in ys):
        return None

    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.scatter(seeds, ys, color="#2563EB", zorder=3, s=50)
    mean = spread.get("mean")
    if mean is not None:
        ax.axhline(mean, linestyle="-", color="#2563EB", alpha=0.4, label=f"cross-seed mean {mean:.4f}")
    lo, hi = spread.get("pct_low"), spread.get("pct_high")
    if lo is not None and hi is not None:
        ax.axhspan(lo, hi, color="#2563EB", alpha=0.08,
                  label=f"2.5-97.5 pctile spread ({spread.get('pct_width_pp', 0):.2f} pp)")
    ax.set_xlabel("seed")
    ax.set_ylabel("precision @ 10% budget")
    ax.set_xticks(seeds)
    ax.set_title(f"SK-20/21: {len(seeds)} registered seeds (floor 5), "
                f"CI width ceiling 4.0 pp")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.25)
    return sh.savefig(fig, ctx, "seed_sweep_precision.png")
