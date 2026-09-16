"""
11 Fairness — the 80% rule, including the gig-worker failure we do not hide

Pre-registered criteria this runner answers: SK-23, SK-24

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.fairness`` (`model.metrics
  fairness_table`, `src/model/pack.py` `run()`): one row per (dim, group) —
  Segment, City tier, Age band, Income band — with `sel_rate` (contact rate at
  the live 10% budget), `ratio` (four-fifths ratio to the best group in that
  dim) and `n`, over the snapshot queue's eligible population. Also
  ``metrics.registered.adverse_impact_ratio`` (the worst ratio among cells
  with n >= 500 — SK-23's min_n) and ``metrics.income_acc`` (the gig income-
  accuracy gap MODEL_CARD.md §8 quotes alongside the failure).
* the small-book refit harness (`validation/runners/_refit.py`) — reused
  (process-cached, so free if 08_ablation or 10_stress already ran) for a
  **best-effort, non-gated** true-positive-rate (equal-opportunity) exhibit
  by the same four dims, which `model.metrics.fairness_table` does not
  compute (it is a selection-rate/AIR function only) and which
  `data/model_metrics.json` therefore has no row-level data to derive without
  a refit. `criteria.yaml` registers only `adverse_impact_ratio` for SK-23 —
  no TPR-gap band exists to grade against — so this exhibit is reported in
  `detail`, the same way `06_stability`'s CSI-per-family is: informational,
  never gating.

Produces
--------
* ``figures/fairness_contact_rates.png`` — selection-rate ratio per (dim,
  group) against the 0.80 line, gig highlighted.
* ``figures/gig_gap.png`` — the gig-worker income-accuracy shortfall
  MODEL_CARD.md §8 quotes as the mechanism behind the AIR failure.
* SK-23 (`adverse_impact_ratio`, `>= 0.80`, `severity: report` — **the gig
  ratio of 0.69 is reported as a FAIL band comparison, never softened**; SK-23
  itself is `report` severity per `criteria.yaml`, so this never blocks a
  gate, but the per-cell verdict is not hidden). SK-24
  (`gig_worker_failure_disclosure`, `exists`) — the quantified gig statement.

Method, as pre-registered
--------------------------
"Contact rate and true-positive rate by group ... Report the four-fifths ratio
and the gaps. Then the quantified gig-worker statement" (runner docstring,
pre-scaffolded). The four-fifths ratio is `model.metrics.fairness_table`'s own
computation, read back, not re-derived — `validation.run.grade()` compares it
to the 0.80 band independently of `metrics.bands["SK-23"]`.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _refit as rf
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json",)

_GIG_DIM, _GIG_GROUP = "Segment", "gig"


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    fairness = m.get("fairness") or []
    if not fairness:
        return [Result("SK-23", status="pending", detail="metrics.fairness not present"),
                Result("SK-24", status="pending", detail="metrics.income_acc not present")]

    results = [_sk23(ctx, m, fairness), _sk24(m)]

    try:
        fig1 = _fairness_figure(ctx, fairness)
        fig2 = _gig_gap_figure(ctx, m.get("income_acc") or {})
        by_id = {r.criterion_id: r for r in results}
        if fig1:
            by_id["SK-23"].figures.append(fig1)
        if fig2:
            by_id["SK-24"].figures.append(fig2)
    except Exception:
        pass

    return results


def _sk23(ctx: RunnerContext, m: dict, fairness: list[dict]) -> Result:
    cells = [dict(level=f"{f['dim']}:{f['group']}", value=f["ratio"], n=f["n"],
                 sel_rate=f["sel_rate"], ci=None)
            for f in fairness]
    registered_air = ((m.get("registered") or {}).get("adverse_impact_ratio"))
    gig = next((f for f in fairness if f["dim"] == _GIG_DIM and f["group"] == _GIG_GROUP), None)

    fail_cells = [f for f in fairness if f["ratio"] < 0.80]
    fail_note = (f"BELOW the 0.80 four-fifths line (reported, not softened): "
                f"{[(f['dim'], f['group'], f['ratio']) for f in fail_cells]}."
                if fail_cells else "No cell below the 0.80 four-fifths line.")
    gig_note = (f"Occupation segment 'gig': selection rate {gig['sel_rate']:.2%} vs the best "
               f"group's rate, ratio {gig['ratio']} (n={gig['n']}) — {'FAILS' if gig['ratio'] < 0.80 else 'passes'} "
               f"the 0.80 line. This is `criteria.yaml` SK-23's documented gig failure; "
               f"severity is `report` in criteria.yaml (never gates the run), and the ratio is "
               f"carried through here exactly as measured, never rounded up or excluded."
               if gig else "No 'gig' cell found in metrics.fairness.")

    tpr_note = _tpr_gap_exhibit(ctx)
    detail = (f"four-fifths ratio = group selection rate / best group's selection rate in the "
             f"same dim, at the live 10% contact budget, over the eligible snapshot population "
             f"(`model.metrics.fairness_table`). Protected proxies evaluated: Segment "
             f"(occupation), City tier, Age band, Income band — gender/religion/caste/marital "
             f"status/pin-code are excluded outright by policy and are not in the data at all "
             f"(`model.copy.EXCLUDED_FEATURES`). {fail_note} {gig_note} {tpr_note}")

    value = registered_air if registered_air is not None else (gig["ratio"] if gig else None)
    n = gig["n"] if gig else None
    return Result("SK-23", value=value, n=n, breakdown=cells, detail=detail)


def _sk24(m: dict) -> Result:
    income = m.get("income_acc") or {}
    disclosed = ((m.get("registered") or {}).get("gig_worker_failure_disclosure"))
    gig_within15 = income.get("gig_within15")
    all_within15 = income.get("within15")
    gig_median = income.get("gig_median_err")
    all_median = income.get("median_err")

    exists = bool(disclosed) and gig_within15 is not None
    detail = (f"quantified gig-worker statement: behavioural income estimate within +-15% for "
             f"{gig_within15:.1%} of gig workers (n={income.get('n_gig')}) vs {all_within15:.1%} "
             f"overall (n={income.get('n')}); median error {gig_median:.1%} gig vs "
             f"{all_median:.1%} overall. Mechanism: irregular gig income reads as instability to "
             f"a model trained mostly on salaried credits, which depresses the behavioural "
             f"income estimate, which depresses the safe-EMI capacity score, which depresses "
             f"rank — the chain MODEL_CARD.md §8 and the README's 'What we did not build, and "
             f"why' both carry. Disclosed rather than tuned away: tuning it out on synthetic "
             f"data would be pretending to have solved it."
             if exists else
             "gig-worker income-accuracy statement not present in metrics.income_acc — "
             "SK-24 cannot confirm the disclosure exists.")
    return Result("SK-24", value=exists, detail=detail)


def _tpr_gap_exhibit(ctx: RunnerContext) -> str:
    """Best-effort, small-book, NON-GATED equal-opportunity (TPR) exhibit — see
    module docstring. Never raises; a failure here must not cost SK-23 its
    (graded) four-fifths result."""
    try:
        h = rf.harness(ctx)
        if h.get("error"):
            return f"TPR-gap exhibit not computed: {h['error']}"
        base = rf.baseline(h)
        F, M = h["F"], h["M"]
        import numpy as np
        import pandas as pd

        stacked = h["stacked"]
        snap = int(h["base"]["month"].max())
        rk = base["ranker"]
        at_snap = h["base"]["month"].to_numpy() == snap
        snap_base = h["base"][at_snap].reset_index(drop=True)
        # `Ranker.matrix()` reshapes its (n_all * n_products,) score vector back
        # to (n_products, n_all).T — reproduce that here, then subset by the
        # snapshot month's row positions, rather than rebuilding a second
        # stacked frame just for this exhibit.
        n_all = len(h["base"])
        row_pos = np.flatnonzero(at_snap)
        n_prod = len(F.PRODUCTS)
        Psnap = rk.matrix(stacked).reshape(n_prod, n_all).T[row_pos]  # (n_snap, n_prod)
        elig = snap_base["eligible_for_contact"].to_numpy() == 1
        p_top = Psnap.max(axis=1)
        k = max(1, int(round(int(elig.sum()) * h["cfg"].budget)))
        sel = np.zeros(len(snap_base), dtype=bool)
        order = np.argsort(np.where(elig, -p_top, np.inf), kind="stable")[:k]
        sel[order] = True
        y = snap_base["t_label"].to_numpy().astype(int)

        d = snap_base.copy()
        d["selected"], d["is_pos"] = sel, y.astype(bool)
        d["age_band"] = pd.cut(d["age"], [20, 30, 45, 63], labels=["21-30", "31-45", "46+"])
        d["income_band"] = pd.qcut(d["t_income_at_month"].rank(method="first"), 5,
                                   labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"])
        rows = []
        for dim, col in [("Segment", "segment"), ("City tier", "city_tier"),
                         ("Age band", "age_band"), ("Income band", "income_band")]:
            sub = d[d.is_pos & elig]
            if sub.empty:
                continue
            tpr = sub.groupby(col, observed=True).selected.mean()
            n = sub.groupby(col, observed=True).selected.size()
            for g, r in tpr.items():
                if n[g] >= 5:
                    rows.append((dim, str(g), round(float(r), 3), int(n[g])))
        if not rows:
            return "TPR-gap exhibit not computed: no positives at the small book's snapshot month."
        by_dim: dict[str, list] = {}
        for dim, g, r, n in rows:
            by_dim.setdefault(dim, []).append((g, r, n))
        gaps = {dim: round(max(r for _, r, _ in gs) - min(r for _, r, _ in gs), 3)
               for dim, gs in by_dim.items()}
        return (f"Supplementary, non-gated equal-opportunity (TPR = contact rate among true "
               f"potential-disbursers) exhibit on the SMALL book's own snapshot month "
               f"(n_positives={int((d.is_pos & elig).sum())}, single seed {rf.SMALL_SEED} — "
               f"too few positives per cell for a production-grade read, hence not registered "
               f"or gated): max-min TPR gap by dim = {gaps}. criteria.yaml SK-23 registers only "
               f"adverse_impact_ratio, not a TPR-gap band; this is reported for a human, not "
               f"graded.")
    except Exception as exc:
        return f"TPR-gap exhibit not computed: {exc}"


def _fairness_figure(ctx: RunnerContext, fairness: list[dict]) -> str | None:
    labels = [f"{f['dim']}:{f['group']}" for f in fairness]
    ys = [f["ratio"] for f in fairness]
    colors = ["#B00020" if f["ratio"] < 0.80 else "#2563EB" for f in fairness]

    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    xs = range(len(labels))
    ax.bar(xs, ys, color=colors)
    sh.band_line(ax, 0.80, "SK-23 four-fifths line 0.80")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=7)
    ax.set_ylabel("selection-rate ratio (this group / best group)")
    ax.set_title("SK-23 adverse impact ratio by protected proxy — gig FAILS at 0.69")
    ax.legend(fontsize=7)
    ax.set_ylim(0, 1.1)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "fairness_contact_rates.png")


def _gig_gap_figure(ctx: RunnerContext, income: dict) -> str | None:
    gig, allb = income.get("gig_within15"), income.get("within15")
    if gig is None or allb is None:
        return None
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    ax.bar(["all customers", "gig workers"], [allb, gig], color=["#2563EB", "#B00020"])
    ax.set_ylabel("income estimate within +-15% of true income")
    ax.set_title("SK-24: the gig-worker income-accuracy gap")
    ax.set_ylim(0, 1.0)
    return sh.savefig(fig, ctx, "gig_gap.png")
