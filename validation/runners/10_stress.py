"""
10 Stress — the book under two pre-registered shifts

Pre-registered criteria this runner answers: SK-22

Consumes
--------
* the small-book refit harness (`validation/runners/_refit.py`) — same book,
  frame and split `08_ablation` uses, and (when both runners execute in the
  same `python3 -m validation.run` process) the SAME cached full-feature
  baseline fit, so this runner's own cost is one extra refit plus one
  zero-refit re-score.

Produces
--------
* ``figures/stress_precision.png`` — precision@10% under each scenario
  against the small-book baseline, with CIs.
* One `Result` for SK-22: `value` is `{scenario: delta_precision_pp}`;
  `breakdown` carries one cell per scenario.

Method, as pre-registered
--------------------------
`criteria.yaml` SK-22's rationale names four scenarios (consent withdrawal at
scale, a suppression-rule sweep, cross-bank transaction data unavailable, a
doubled window-shopper share) and registers no band ("no threshold was
invented"). This lane's brief narrows execution to the two that are tractable
as a refit/re-score on the small book within the remaining budget, and says
so rather than silently substituting:

1. **2x base rate** — eligible, training-split POSITIVE rows are duplicated
   before fitting (`_refit.reweighted_fit_and_score`), then scored against the
   unduplicated held population. A refit, because a base-rate shift changes
   what the ranker learns, not just what it is fed at inference.
2. **channel-missing** — the `contact` family (`contacts_30d`, `contacts_90d`,
   `campaign_contacts_6m`, `last_contact_days`,
   `last_campaign_matches_product` — the bank's own contact-history channel)
   is blanked to NaN in a COPY of the frame and re-scored through the
   ALREADY-FITTED baseline ranker (`_refit.blanked_score`, zero extra fits) —
   deliberately an inference-time channel outage, not a retrain that never
   knew the channel existed, which is the more realistic production failure
   mode and also the cheaper one to run.

The other two registered scenarios (consent withdrawal at scale, a
suppression-rule sweep) are reported `not computed this pass`, with the
reason, rather than approximated: both are about which rows enter the
*population* the labels/suppression layer (`journeys.labels`) builds, which
this runner cannot alter without re-running `journeys.build` under different
generator parameters — a second full generator run, which this lane's refit
budget does not cover twice over.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _refit as rf
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = ()  # generates its own small book; see module docstring

_BLANKED_FAMILY = "contact"

_NOT_COMPUTED = (
    "consent withdrawal at scale",
    "suppression-rule sweep (plan §B L6 SD-S6)",
)


#: `src/experiments/challenge_regimes.py`'s output. SK-22 registers no band, so
#: this can only ever be reported — but the registered scenarios this runner said
#: it could not afford ("each needs a second generator run under altered
#: parameters") are exactly what that script does, at full book size, against a
#: model that is frozen rather than refitted.
_CHALLENGE_REL = "data/experiments/challenge_regimes.json"


def _challenge_note(ctx: RunnerContext) -> str:
    import json

    path = ctx.repo_root / _CHALLENGE_REL
    if not path.is_file():
        return (f"FULL-SIZE CHALLENGE REGIMES: not run. "
                f"`python3 src/experiments/challenge_regimes.py` writes "
                f"{_CHALLENGE_REL} — a frozen development generator config, one model "
                f"fitted on it and never refitted, and seven named departures scored "
                f"with that frozen model at a generator seed it never saw.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"FULL-SIZE CHALLENGE REGIMES: {_CHALLENGE_REL} is unreadable ({exc})."

    rows = "; ".join(
        f"{r['regime']} {r.get('precision_at_budget')} "
        f"(lift {r.get('lift')}, {r.get('degradation_vs_comparator_pp'):+.2f} pp vs "
        f"{r.get('comparator')})"
        for r in doc.get("regimes", [])
        if r.get("precision_at_budget") is not None and r.get("kind") != "baseline")
    lift = doc.get("lift_stability") or {}
    return (
        f"FULL-SIZE CHALLENGE REGIMES (reported, no band; `{_CHALLENGE_REL}`). The "
        f"development generator config is frozen to "
        f"`{doc.get('frozen_config_file')}` BEFORE any regime runs, one model is "
        f"fitted on the development world at model seed {doc.get('model_seed')} and "
        f"NEVER refitted, and every challenge world uses generator seed "
        f"{doc.get('challenge_generator_seed')}, which the development world never "
        f"used — so a degradation cannot be a training-split accident. Development "
        f"world precision@10% = "
        f"{next((r.get('precision_at_budget') for r in doc.get('regimes', []) if r.get('kind') == 'baseline'), None)}. "
        f"Regimes: {rows}. Read each against its own control: a regenerated world is "
        f"compared with `fresh_world` (same frozen config, new seed) because it has "
        f"already paid the cost of being a new world. LIFT STABILITY: "
        f"precision/baseline stays in [{lift.get('min')}, {lift.get('max')}] across "
        f"every regime — absolute precision tracks whatever base rate a world has, and "
        f"the ratio is the part that belongs to the model. Any rupee figure derived "
        f"from these numbers is a SIMULATION RESULT and the JSON carries an assumption "
        f"range rather than a point.")


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    h = rf.harness(ctx)
    if h.get("error"):
        return [Result("SK-22", status="pending",
                       detail=f"small-book refit harness failed: {h['error']}")]

    base = rf.baseline(h)
    reweighted = rf.reweighted_fit_and_score(h, multiplier=2)
    blanked = rf.blanked_score(h, base["ranker"], _BLANKED_FAMILY)

    cells = [
        dict(level="2x_base_rate_reweight_positives",
            value=round((reweighted["precision"] - base["precision"]) * 100, 3),
            n=reweighted["n"], ci=[reweighted["ci_low"], reweighted["ci_high"]],
            precision=reweighted["precision"], auc=reweighted.get("auc"),
            n_fit_positives_added=reweighted.get("n_fit_positives_added")),
        dict(level=f"channel_missing_{_BLANKED_FAMILY}",
            value=round((blanked["precision"] - base["precision"]) * 100, 3),
            n=blanked["n"], ci=[blanked["ci_low"], blanked["ci_high"]],
            precision=blanked["precision"], auc=blanked.get("auc"),
            blanked_columns=blanked.get("blanked_columns")),
    ]

    detail = (f"small-book refit (n={h['n_customers']:,} customers, single seed {rf.SMALL_SEED} "
             f"— see validation/runners/_refit.py). Baseline: precision@10%="
             f"{base['precision']:.4f} [{base['ci_low']:.4f}, {base['ci_high']:.4f}], AUC="
             f"{base.get('auc')}. delta_pp = scenario - baseline (positive = the scenario "
             f"IMPROVED precision, negative = it degraded). 2x base rate: "
             f"{reweighted.get('n_fit_positives_added')} duplicate positive training rows added "
             f"to the fit split only, scored against the unduplicated held population — precision@10%="
             f"{reweighted['precision']:.4f}. channel-missing ({_BLANKED_FAMILY}): "
             f"{blanked.get('blanked_columns')} blanked to NaN in a copy of the SAME fitted "
             f"baseline ranker's scoring frame (no retrain) — precision@10%="
             f"{blanked['precision']:.4f}. Registered scenarios NOT computed this pass "
             f"(reason: each needs a second generator run under altered parameters, which the "
             f"refit budget does not cover twice over — not approximated, not silently dropped): "
             f"{list(_NOT_COMPUTED)}.")

    value = {c["level"]: c["value"] for c in cells}
    result = Result("SK-22", value=value, breakdown=cells,
                    detail=f"{detail} {_challenge_note(ctx)}")

    try:
        fig = _figure(ctx, base, cells)
        if fig:
            result.figures.append(fig)
    except Exception:
        pass

    return [result]


def _figure(ctx: RunnerContext, base: dict, cells: list[dict]) -> str | None:
    labels = ["baseline"] + [c["level"] for c in cells]
    ys = [base["precision"]] + [c["precision"] for c in cells]
    los = [base["ci_low"]] + [c["ci"][0] if c["ci"][0] is not None else c["precision"] for c in cells]
    his = [base["ci_high"]] + [c["ci"][1] if c["ci"][1] is not None else c["precision"] for c in cells]
    err = [np.array(ys) - np.array(los), np.array(his) - np.array(ys)]

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    xs = np.arange(len(labels))
    colors = ["#2563EB"] + ["#F59E0B"] * len(cells)
    ax.bar(xs, ys, yerr=err, capsize=4, color=colors)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("precision @ 10% budget (small-book refit)")
    ax.set_title("SK-22 stress scenarios vs small-book baseline")
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "stress_precision.png")
