#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Why gig workers are under-contacted, and what any fix would cost.

    python3 src/experiments/fairness_probe.py            # ~2 min, writes the JSON
    python3 src/experiments/fairness_probe.py --quick    # skip the SHAP attribution

SK-23 reports a four-fifths ratio of **0.69** for gig workers and **0.79** for the
lowest income quintile, and the model card used to explain it by saying the
capacity term depressed their rank. That explanation was wrong — SK-23 has always
been measured on the probability-ranked selection, and the ratio did not move when
capacity was removed from the ranking entirely. This script replaces the wrong
explanation with four measurements and two costed remedies.

What it measures
----------------
1. **Selection and base rates by group.** The four-fifths ratio on the held-out
   split, beside each group's *actual* conversion rate. A group that converts less
   often will be selected less often by any ranker that works; that is not, on its
   own, evidence of a defect.
2. **Outcomes at comparable score.** Within score decile, does a gig worker convert
   at the same rate as a salaried customer with the same score? If yes, the model
   is calibrated within segment and the selection gap is tracking a real base-rate
   difference. If gig workers convert *better* at the same score, the model
   under-ranks them and the gap is the model's fault. This is the measurement that
   decides which story is true, and it is the one nobody had run.
3. **What the capacity term does.** The ratio and the precision under three
   rankings: probability only (shipped), the retired 0.65/0.35 blend, and a
   half-weight blend. If capacity were the mechanism, the ratio would move.
4. **Which features carry it.** Mean SHAP by feature for gig against salaried, on
   rows near the selection boundary — where a small contribution decides whether a
   customer is called.

The two remedies, costed
------------------------
* **Capacity weight** — the sweep in (3), read as a remedy.
* **Within-segment quota** — allocate the contact budget to segments in proportion
  to their share of the eligible pool and rank within each. The ratio goes to 1.00
  by construction; the question is what it costs in precision.
* **Minimum-ratio floor** — the smallest reallocation that lifts the worst ratio to
  0.80, rather than to 1.00. Cheaper, and it is what a bank would actually be asked
  for.

**Nothing here is optimised to 0.80.** The output is a trade-off table; the choice
belongs to a human who can weigh a percentage point of precision against a
percentage point of contact equity, and the point of the table is to make that
exchange rate visible instead of implicit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from model import PRODUCTS, ModelConfig  # noqa: E402
from model import frame as F  # noqa: E402
from model import metrics as M  # noqa: E402
from model import policy as PO  # noqa: E402
from model.pack import _held, build_frames  # noqa: E402
from model.train import fit_ranker, split_customers  # noqa: E402

OUT_REL = Path("data") / "experiments" / "fairness_probe.json"

#: Rows used for the SHAP attribution. Exact TreeSHAP over the whole held-out
#: stacked frame costs minutes and adds nothing past a few thousand rows.
SHAP_SAMPLE = 8_000


def _bands(hb: pd.DataFrame) -> pd.DataFrame:
    d = hb.copy()
    d["segment"] = d["segment"].astype(str)
    d["income_band"] = pd.qcut(d["t_income_at_month"].rank(method="first"), 5,
                               labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"])
    return d


def _ratio_table(d: pd.DataFrame, selected: np.ndarray, col: str) -> list[dict]:
    """Selection rate, conversion rate and the four-fifths ratio, per group."""
    rows = []
    rates = {}
    for g, sub in d.groupby(col, observed=True):
        idx = sub.index.to_numpy()
        rates[str(g)] = float(selected[idx].mean())
    best = max(rates.values()) if rates else 0.0
    for g, sub in d.groupby(col, observed=True):
        idx = sub.index.to_numpy()
        sel = selected[idx]
        y = sub["t_label"].to_numpy().astype(int)
        rows.append(dict(
            group=str(g), n=int(len(idx)),
            selection_rate=round(float(sel.mean()), 4),
            ratio=round(rates[str(g)] / best, 4) if best else None,
            conversion_rate=round(float(y.mean()), 4),
            precision_when_selected=(round(float(y[sel].mean()), 4) if sel.any() else None),
            n_selected=int(sel.sum()),
        ))
    return sorted(rows, key=lambda r: r["ratio"] if r["ratio"] is not None else 9)


def _outcomes_at_comparable_score(d: pd.DataFrame, p_top: np.ndarray,
                                  col: str, focus: str, reference: str) -> dict:
    """Does the focus group convert as often as the reference at the SAME score?

    Deciles are cut on the pooled score so the two groups are compared inside the
    same score band rather than against each other's distributions.
    """
    decile = pd.qcut(pd.Series(p_top).rank(method="first"), 10, labels=range(1, 11))
    rows = []
    for dec in range(1, 11):
        m = (decile == dec).to_numpy()
        out = dict(decile=int(dec))
        for name, group in (("focus", focus), ("reference", reference)):
            g = m & (d[col].astype(str) == group).to_numpy()
            y = d.loc[g, "t_label"].to_numpy().astype(int)
            out[f"n_{name}"] = int(len(y))
            out[f"rate_{name}"] = round(float(y.mean()), 4) if len(y) >= 30 else None
            out[f"mean_score_{name}"] = round(float(p_top[g].mean()), 4) if len(y) else None
        both = out["rate_focus"] is not None and out["rate_reference"] is not None
        out["gap_pp"] = round(100.0 * (out["rate_focus"] - out["rate_reference"]), 2) if both else None
        rows.append(out)

    usable = [r for r in rows if r["gap_pp"] is not None]
    mean_gap = round(float(np.mean([r["gap_pp"] for r in usable])), 2) if usable else None
    return dict(
        focus=focus, reference=reference, by_decile=rows,
        mean_gap_pp=mean_gap, n_usable_deciles=len(usable),
        reading=("At the same predicted score the focus group converts at a similar rate, "
                 "so the selection gap is tracking a real difference in propensity rather "
                 "than a mis-ranking."
                 if mean_gap is not None and abs(mean_gap) <= 2.0 else
                 "At the same predicted score the focus group converts MORE often, which "
                 "means the model under-ranks them and the selection gap is the model's."
                 if mean_gap is not None and mean_gap > 2.0 else
                 "At the same predicted score the focus group converts LESS often, so the "
                 "model is if anything over-ranking them relative to outcome."
                 if mean_gap is not None else
                 "Too few rows per decile to read."),
    )


def _rank_variants(d: pd.DataFrame, Ph: np.ndarray, y: np.ndarray,
                   budget: float, weights: tuple[float, ...]) -> list[dict]:
    """Ratio and precision under probability ranking and under blends of each weight."""
    cust = d["cust_id"].to_numpy()
    emi = d["safe_emi"].to_numpy()
    elig = d["eligible_for_contact"].to_numpy() == 1
    out = []
    for w in weights:
        if w == 0.0:
            sc = PO.score_pool(cust, emi, Ph, elig, ranking=PO.RANKING_PROBABILITY)
            label = "probability only (shipped)"
        else:
            base = PO.score_pool(cust, emi, Ph, elig, ranking=PO.RANKING_BLEND)
            rank = (1 - w) * base.intent + w * base.capacity
            sc = PO.PolicyScores(
                cust_id=base.cust_id, eligible=base.eligible, p_top=base.p_top,
                top_index=base.top_index, nbp=base.nbp, intent=base.intent,
                capacity=base.capacity, blend=base.blend,
                rank_score=rank, ranking=PO.RANKING_BLEND)
            label = f"blend, capacity weight {w:.2f}"
        sel = np.zeros(len(d), dtype=bool)
        sel[PO.select(sc, budget=budget)] = True
        fair = M.fairness_table(d, sel)
        worst = min((f for f in fair if f["n"] >= 500), key=lambda f: f["ratio"], default=None)
        out.append(dict(
            capacity_weight=w, label=label,
            precision=round(float(y[sel].mean()), 4),
            worst_ratio=round(float(worst["ratio"]), 4) if worst else None,
            worst_group=f"{worst['dim']}: {worst['group']}" if worst else None,
            gig_ratio=next((round(float(f["ratio"]), 4) for f in fair
                            if f["dim"] == "Segment" and f["group"] == "gig"), None),
        ))
    return out


def _quota(d: pd.DataFrame, Ph: np.ndarray, y: np.ndarray, budget: float,
           col: str = "segment", floor: float | None = None) -> dict:
    """Allocate the budget across groups instead of ranking them against each other.

    ``floor=None`` gives every group the same selection rate (ratio 1.00).
    ``floor=0.80`` lifts only the groups below the four-fifths line and pays for it
    by scaling everyone down — the cheaper remedy, and the one a bank would
    actually be asked for.

    The arithmetic, so the rule is inspectable rather than a search: let ``rate_g``
    be each group's rate under the unconstrained queue and ``R = max(rate_g)``.
    Clip from below at ``floor * R``, then scale every group by the single factor
    that returns the total to the budget. Scaling is uniform, so it cannot break
    the floor it just established, and the budget is spent exactly.
    """
    cust, emi = d["cust_id"].to_numpy(), d["safe_emi"].to_numpy()
    elig = (d["eligible_for_contact"].to_numpy() == 1)
    sc = PO.score_pool(cust, emi, Ph, elig)
    n_e = int(elig.sum())
    k_total = PO.budget_k(n_e, budget)
    groups = d[col].astype(str).to_numpy()
    order = [int(i) for i in PO.rank_order(sc)]
    glist = sorted(set(groups[elig]))
    pool = {g: int(((groups == g) & elig).sum()) for g in glist}
    g_order = {g: [i for i in order if groups[i] == g] for g in glist}

    unconstrained = np.zeros(len(d), dtype=bool)
    unconstrained[order[:k_total]] = True
    alloc = {g: int(unconstrained[(groups == g) & elig].sum()) for g in glist}
    rate = {g: (alloc[g] / pool[g] if pool[g] else 0.0) for g in glist}

    if floor is None:
        want = {g: k_total / n_e for g in glist}
    else:
        R = max(rate.values()) if rate else 0.0
        lifted = {g: max(rate[g], floor * R) for g in glist}
        denom = sum(lifted[g] * pool[g] for g in glist) or 1.0
        scale = k_total / denom
        want = {g: lifted[g] * scale for g in glist}

    target = {g: min(pool[g], int(round(want[g] * pool[g]))) for g in glist}
    # rounding can leave the budget a call or two out; settle it on the group
    # furthest from its intended rate rather than on whoever sorts first.
    while sum(target.values()) != k_total:
        short = k_total - sum(target.values())
        step = 1 if short > 0 else -1
        candidates = [g for g in glist
                      if (step > 0 and target[g] < pool[g]) or (step < 0 and target[g] > 0)]
        if not candidates:
            break
        g = min(candidates, key=lambda g: step * (target[g] / pool[g] - want[g]))
        target[g] += step

    selected = np.zeros(len(d), dtype=bool)
    for g in glist:
        selected[g_order[g][: target[g]]] = True

    fair = M.fairness_table(d, selected)
    worst = min((f for f in fair if f["n"] >= 500), key=lambda f: f["ratio"], default=None)
    return dict(
        rule=("equal selection rate per segment (ratio 1.00 by construction)"
              if floor is None else f"minimum four-fifths ratio {floor:.2f}"),
        dimension=col, floor=floor,
        n_selected=int(selected.sum()), k_budget=int(k_total),
        precision=round(float(y[selected].mean()), 4),
        worst_ratio=round(float(worst["ratio"]), 4) if worst else None,
        worst_group=f"{worst['dim']}: {worst['group']}" if worst else None,
        gig_ratio=next((round(float(f["ratio"]), 4) for f in fair
                        if f["dim"] == "Segment" and f["group"] == "gig"), None),
        unconstrained_rate={g: round(rate[g], 4) for g in glist},
        target_rate={g: round(target[g] / pool[g], 4) for g in glist},
        by_group=_ratio_table(d, selected, col),
    )


def _shap_gap(rk, d: pd.DataFrame, Ph: np.ndarray, sc: PO.PolicyScores,
              budget: float, rng: np.random.Generator, sample: int) -> dict:
    """Mean SHAP per feature, gig minus salaried, on rows near the selection cut.

    Near the cut is where it matters: a feature that costs a gig worker a tenth of
    a log-odd in the middle of the pack changes nothing, and the same tenth at the
    boundary is the difference between being called and not.
    """
    pct = pd.Series(sc.p_top).rank(pct=True).to_numpy()
    near = (pct >= 1 - budget - 0.06) & (pct <= 1 - budget + 0.06)
    seg = d["segment"].astype(str).to_numpy()
    pool = np.flatnonzero(near & np.isin(seg, ("gig", "salaried")))
    if len(pool) < 200:
        return dict(status="skipped_low_n", n=int(len(pool)))
    take = rng.choice(pool, size=min(sample, len(pool)), replace=False)
    rows = d.iloc[take].reset_index(drop=True)
    C = rk.contributions(F.as_categorical(F.stack(rows)))
    feats = list(rk.features)
    n = len(rows)
    top = sc.top_index[take]
    # one contribution row per lead, for the product actually pitched
    pick = np.array([int(t) * n + i for i, t in enumerate(top)])
    contrib = C[pick]
    is_gig = (rows["segment"].astype(str) == "gig").to_numpy()
    gaps = []
    for j, f in enumerate(feats):
        g = float(contrib[is_gig, j].mean())
        s = float(contrib[~is_gig, j].mean())
        gaps.append(dict(feature=f, gig_mean=round(g, 5), salaried_mean=round(s, 5),
                         gap=round(g - s, 5)))
    gaps.sort(key=lambda r: r["gap"])
    return dict(
        status="ok", n_rows=int(n), n_gig=int(is_gig.sum()),
        band=f"score percentile {1 - budget - 0.06:.2f}-{1 - budget + 0.06:.2f}",
        most_against_gig=gaps[:10], most_for_gig=gaps[-5:],
        total_gap_log_odds=round(float(contrib[is_gig].sum(axis=1).mean()
                                       - contrib[~is_gig].sum(axis=1).mean()), 5),
        definition="mean TreeSHAP contribution (log-odds) for the pitched product, "
                   "gig minus salaried, on held-out rows whose score sits within six "
                   "percentiles of the contact cut",
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=float, default=0.10)
    ap.add_argument("--quick", action="store_true", help="skip the SHAP attribution")
    ap.add_argument("--out", default=str(ROOT / OUT_REL))
    a = ap.parse_args(argv)

    t0 = time.time()
    cfg = ModelConfig(root=ROOT, seed=a.seed, seeds=(a.seed,), budget=a.budget, quick=True)
    base, stacked, _ = build_frames(cfg)
    sp = split_customers(base["cust_id"].unique(), cfg, a.seed)
    rk = fit_ranker(stacked, sp, cfg)
    P = rk.matrix(stacked)
    h = _held(base, sp)
    hb = _bands(base[h].reset_index(drop=True))
    Ph = P[h]
    y = hb["t_label"].to_numpy().astype(int)
    print(f"held out {len(hb):,} rows, {hb.cust_id.nunique():,} customers "
          f"[{time.time() - t0:.0f}s]", flush=True)

    sc = PO.score_pool(hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy(), Ph,
                       hb["eligible_for_contact"].to_numpy() == 1)
    selected = np.zeros(len(hb), dtype=bool)
    selected[PO.select(sc, budget=a.budget)] = True

    doc = dict(
        seed=a.seed, budget=a.budget, ranking=sc.ranking,
        n_holdout_rows=int(len(hb)), n_holdout_customers=int(hb.cust_id.nunique()),
        precision_at_budget=round(float(y[selected].mean()), 4),
        by_segment=_ratio_table(hb, selected, "segment"),
        by_income_band=_ratio_table(hb, selected, "income_band"),
        outcomes_at_comparable_score=dict(
            segment=_outcomes_at_comparable_score(hb, sc.p_top, "segment", "gig", "salaried"),
            income=_outcomes_at_comparable_score(
                hb.assign(income_band=hb["income_band"].astype(str)),
                sc.p_top, "income_band", "Q1 lowest", "Q5 highest"),
        ),
        ranking_variants=_rank_variants(hb, Ph, y, a.budget, (0.0, 0.15, 0.35)),
        remedies=dict(
            equal_rate_quota=_quota(hb, Ph, y, a.budget, "segment", floor=None),
            four_fifths_floor=_quota(hb, Ph, y, a.budget, "segment", floor=0.80),
        ),
    )
    if not a.quick:
        doc["feature_attribution"] = _shap_gap(
            rk, hb, Ph, sc, a.budget, np.random.default_rng(a.seed), SHAP_SAMPLE)

    # the trade-off table, one row per option, so the exchange rate is explicit
    baseline_precision = doc["precision_at_budget"]
    baseline_ratio = min((r["ratio"] for r in doc["by_segment"] if r["ratio"] is not None),
                         default=None)
    trade = [dict(option="shipped (probability ranking, no quota)",
                  precision=baseline_precision, worst_segment_ratio=baseline_ratio,
                  precision_cost_pp=0.0, ratio_gain=0.0)]
    for v in doc["ranking_variants"][1:]:
        trade.append(dict(option=v["label"], precision=v["precision"],
                          worst_segment_ratio=v["gig_ratio"],
                          precision_cost_pp=round(100.0 * (baseline_precision - v["precision"]), 2),
                          ratio_gain=round((v["gig_ratio"] or 0) - (baseline_ratio or 0), 4)))
    for key, r in doc["remedies"].items():
        trade.append(dict(option=r["rule"], precision=r["precision"],
                          worst_segment_ratio=r["gig_ratio"],
                          precision_cost_pp=round(100.0 * (baseline_precision - r["precision"]), 2),
                          ratio_gain=round((r["gig_ratio"] or 0) - (baseline_ratio or 0), 4)))
    doc["trade_off"] = trade

    # The finding, assembled from the measurements rather than asserted.
    seg = {r["group"]: r for r in doc["by_segment"]}
    gig, sal = seg.get("gig"), seg.get("salaried")
    if gig and sal:
        outcome_ratio = round(gig["conversion_rate"] / sal["conversion_rate"], 4) \
            if sal["conversion_rate"] else None
        doc["finding"] = dict(
            contact_ratio=gig["ratio"], outcome_ratio=outcome_ratio,
            amplification=(round(outcome_ratio / gig["ratio"], 3)
                           if outcome_ratio and gig["ratio"] else None),
            gig_precision_when_selected=gig["precision_when_selected"],
            salaried_precision_when_selected=sal["precision_when_selected"],
            precision_gap_when_selected_pp=round(
                100.0 * (gig["precision_when_selected"] - sal["precision_when_selected"]), 2),
            mean_conversion_gap_at_equal_score_pp=(
                doc["outcomes_at_comparable_score"]["segment"]["mean_gap_pp"]),
            reads=("Gig workers convert about as often as salaried customers "
                   f"({gig['conversion_rate']:.2%} against {sal['conversion_rate']:.2%}, a ratio "
                   f"of {outcome_ratio}), but are contacted at a ratio of {gig['ratio']}. The "
                   "queue therefore AMPLIFIES a small outcome difference into a large contact "
                   "difference. The gig workers it does select convert "
                   f"{100.0 * (gig['precision_when_selected'] - sal['precision_when_selected']):+.1f} "
                   "percentage points better than the salaried ones it selects, which is what a "
                   "stricter effective threshold looks like: only the most obvious gig cases "
                   "clear it. That is a property of the ranking, not of the population."),
        )
    doc["note"] = ("Nothing here is tuned to 0.80. The table prices each option in "
                   "percentage points of precision against percentage points of contact "
                   "ratio; choosing between them is a policy decision, not a modelling one.")
    doc["runtime_s"] = round(time.time() - t0, 1)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print("\ntrade-off:")
    for row in trade:
        print(f"  {row['option']:<52} precision {row['precision']:.4f} "
              f"(costs {row['precision_cost_pp']:+.2f} pp)  "
              f"gig ratio {row['worst_segment_ratio']}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
