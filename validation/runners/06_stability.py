"""
06 Stability — PSI on the score, CSI on a few raw feature-family proxies, and
how fragile the tier labels are

Pre-registered criteria this runner answers: SK-16. SK-26 was added after
registration (2026-09-22, `criteria.yaml amendments`) and is answered here too:
it is a stability question about the same held-out score, one step further on —
PSI asks whether the score distribution moved, SK-26 asks how much the *labels*
cut out of it would move if it did.

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.stability.psi_score_distribution``:
  `src/model/pack.py` already computes this as `model.metrics.psi(p_top[early],
  p_top[~early])` over the held-out score, where "early" is every held-out row
  before the last `ModelConfig.oot_months` (6) months and "~early" is that
  trailing window — i.e. PSI between the training-era score distribution and
  the most recent one, exactly as `criteria.yaml`'s note prescribes.
* ``data/labels.csv`` (`eligible_for_contact`, `month`, `days_since_abandon`,
  `dropoff_attempts`, `contacts_30d`) — for a **supplementary, non-gated** CSI
  read on a couple of raw feature-family proxies, split by the same early/late
  boundary (`metrics.oot.cut_month` when the one run computed it, else derived
  from `meta.snapshot_month`). This is a best-effort exhibit, not a re-creation
  of `src/model/frame.py`'s engineered features: the labels table carries only
  the `journey` and `contact` families in a form usable without re-deriving
  anything, so `income` / `balance` / `outflow` / `debt` / `life_event` /
  `profile` / `shopper` / `product` are reported as not computed here rather
  than approximated from a column that is not really them.

* ``data/model_metrics.json`` —
  ``metrics.delivered_queue.tier_plateau_sensitivity``, computed by
  `src/model/policy.py::tier_plateau_sensitivity` over the same 320 delivered
  rows `metrics.delivered_queue.tiers` counts, for SK-26.

Produces
--------
* ``figures/psi_score.png`` — the score PSI against the 0.10 ceiling.
* SK-16 (`psi_score_distribution`, `<= 0.10`); the CSI table is reported in
  `detail` for a human to read, per the README's "the per-feature CSI table is
  emitted alongside for the report even though only PSI gates."
* SK-26 (`tier_plateau_sensitivity`, reported, no target), one cell per tier
  cut. Every cell is `report`: `criteria.yaml` registers no band, on purpose —
  a threshold here would create a reason to move the cuts, which would change
  who gets called in order to improve a stability number.

Method
------
`model.metrics.psi()` (`src/model/metrics.py`) is reused for both the score
PSI already computed by the one `score_and_pack.py` run and the supplementary
CSI here — never re-implemented.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ("data/model_metrics.json", "data/labels.csv")

#: Raw `data/labels.csv` columns usable as a feature-family proxy without
#: re-deriving anything `src/model/frame.py` engineers. See module docstring.
_CSI_PROXIES: dict[str, str] = {
    "journey": "days_since_abandon",
    "contact": "contacts_30d",
}


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    stability = m.get("stability") or {}
    psi = stability.get("psi_score_distribution")
    if psi is None:
        return [Result("SK-16", status="pending",
                       detail="metrics.stability.psi_score_distribution not present"),
                *_plateau_results(criteria, m)]

    per_seed = ((m.get("seeds") or {}).get("per_seed") or [{}])[0]
    n = per_seed.get("n_holdout_rows")
    cut_month = (m.get("oot") or {}).get("cut_month")

    csi_detail, csi_rows = _csi_proxies(ctx, cut_month)
    detail = ("PSI is over the held-out score, early months vs the trailing "
              "6-month window (src/model/pack.py's own early/~early split); "
              "no cross-seed spread computed for PSI. " + csi_detail)

    result = Result("SK-16", value=round(float(psi), 5), n=n, detail=detail)
    if csi_rows:
        # informational only — SK-16 is the sole graded criterion here, so this
        # is carried as extra structure on the one Result rather than a second
        # breakdown that the harness would (wrongly) grade against the PSI band.
        result.detail = detail

    try:
        fig = _psi_figure(ctx, psi, csi_rows)
        if fig:
            result.figures.append(fig)
    except Exception:
        pass

    return [result, *_plateau_results(criteria, m)]


def _plateau_results(criteria: list[Criterion], m: dict) -> list[Result]:
    """SK-26 — how many delivered leads sit within a hair of a tier cut.

    Silent unless the criterion is registered, so this runner keeps working
    against an older `criteria.yaml` that does not carry SK-26.
    """
    if not any(c.id == "SK-26" for c in criteria):
        return []

    block = ((m.get("delivered_queue") or {}).get("tier_plateau_sensitivity")) or {}
    cuts = block.get("cuts") or {}
    if not cuts:
        return [Result("SK-26", status="pending",
                       detail="metrics.delivered_queue.tier_plateau_sensitivity not present "
                              "(re-run src/score_and_pack.py)")]

    breakdown = []
    for name, cut in cuts.items():
        near = cut.get("nearest_above") or {}
        breakdown.append(dict(
            level=f"{name} cut (p >= {cut.get('cut')})",
            value=int(cut.get("within") or 0),
            n=int(block.get("leads") or 0),
            detail=(f"nearest plateau above: {near.get('n')} lead(s) at "
                    f"{near.get('value')} (+{near.get('distance')})"),
        ))
    # Ordered by cut, descending, so `hot` reads first however the dict came.
    breakdown.sort(key=lambda cell: -float(cuts[cell["level"].split(" ")[0]]["cut"]))

    worst = max(cuts.values(), key=lambda c: (c.get("within") or 0))
    detail = (
        f"{block.get('leads')} delivered leads sit on {block.get('distinct_probabilities')} "
        f"distinct calibrated probabilities (isotonic plateaus, largest "
        f"{block.get('largest_plateau')} leads). Reported value is the worst cut's count "
        f"within +/-{block.get('window')}. A count of 0 does not mean a cut is safe: "
        + "; ".join(
            f"{name} cut {c.get('cut')} — nearest plateau above is "
            f"{(c.get('nearest_above') or {}).get('n')} lead(s) at "
            f"{(c.get('nearest_above') or {}).get('value')}"
            for name, c in cuts.items())
        + ". Reported, never gated (criteria.yaml SK-26 note): precision moves by a fraction "
          "of a point where the tier label moves by whole plateaus, and no band here could "
          "be anything but invented after the fact."
    )
    return [Result("SK-26", value=int(worst.get("within") or 0),
                   n=int(block.get("leads") or 0), breakdown=breakdown, detail=detail)]


def _csi_proxies(ctx: RunnerContext, cut_month: int | None) -> tuple[str, list[dict]]:
    """Best-effort CSI on the two families `data/labels.csv` can support
    without re-deriving engineered features. Never raises — a failure here
    must not cost SK-16 its (graded) result."""
    try:
        import pandas as pd

        M = sh.model_metrics_module(ctx)
        path = ctx.repo_root / "data" / "labels.csv"
        if not path.is_file():
            return "CSI proxies not computed: data/labels.csv not found.", []

        cols = ["month", "eligible_for_contact", *set(_CSI_PROXIES.values())]
        df = pd.read_csv(path, usecols=cols)
        df = df[df["eligible_for_contact"] == 1]
        if cut_month is None:
            meta = sh.meta(ctx) or {}
            snap = meta.get("snapshot_month")
            cut_month = (snap - 6 + 1) if snap is not None else int(df["month"].max()) - 5
        early = df["month"] < cut_month
        late = ~early
        if not early.any() or not late.any():
            return f"CSI proxies not computed: no rows on both sides of cut month {cut_month}.", []

        rows = []
        for family, col in _CSI_PROXIES.items():
            e = df.loc[early, col].dropna().to_numpy(dtype=float)
            l = df.loc[late, col].dropna().to_numpy(dtype=float)
            if len(e) == 0 or len(l) == 0:
                continue
            rows.append(dict(family=family, proxy_column=col, csi=round(float(M.psi(e, l)), 4),
                             n_early=int(len(e)), n_late=int(len(l))))
        skipped = sorted(set(("income", "balance", "outflow", "debt", "life_event",
                             "profile", "shopper", "product")))
        frag = ("CSI (cut month " + str(cut_month) + ", eligible_for_contact=1 population): "
               + "; ".join(f"{r['family']} ({r['proxy_column']})={r['csi']}" for r in rows)
               + f". Not computed (would need re-deriving engineered features, not this "
               f"runner's job): {', '.join(skipped)}.")
        return frag, rows
    except Exception as exc:
        return f"CSI proxies not computed: {exc}", []


def _psi_figure(ctx: RunnerContext, psi: float, csi_rows: list[dict]) -> str | None:
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    labels = ["score PSI"] + [f"{r['family']} CSI" for r in csi_rows]
    values = [psi] + [r["csi"] for r in csi_rows]
    colors = ["#2563EB"] + ["#94A3B8"] * len(csi_rows)
    ax.bar(labels, values, color=colors)
    sh.band_line(ax, 0.10, "SK-16 ceiling 0.10 (score only)")
    ax.set_ylabel("PSI / CSI")
    ax.set_title("Stability: score PSI (gated) + supplementary CSI (reported)")
    ax.legend(fontsize=7)
    plt.xticks(rotation=15)
    return sh.savefig(fig, ctx, "psi_score.png")
