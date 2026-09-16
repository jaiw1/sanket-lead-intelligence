"""
02 Out-of-time — does the queue go stale

Pre-registered criteria this runner answers: SK-07

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.oot`` (`src/model/pack.py`'s
  ``out_of_time()``): trained on months before the cut, measured on the last
  ``ModelConfig.oot_months`` (6) months, with the 14-day embargo satisfied
  structurally (every product's window resolves inside its own snapshot
  month, so a month-boundary cut leaves no training label unresolved — see
  that function's docstring). Requires a run of ``python3
  src/score_and_pack.py`` **without** ``--quick``: the quick path skips this
  exhibit entirely (``metrics.oot.status == "skipped_quick"``), which this
  runner reports as `pending`, not as a pass.

Produces
--------
* ``figures/oot_precision.png`` — in-time vs out-of-time precision@10%, with
  CIs, against the SK-07 degradation ceiling.
* One `Result` for SK-07: degradation in percentage points (holdout
  precision@10% minus OOT precision@10%; negative means it improved).

Method
------
`src/model/pack.py out_of_time()` already computes `degradation_pp` exactly as
`criteria.yaml`'s note prescribes. This runner reads it and lets
`validation.run.grade()` compare it to the registered <= 5.0 pp band — the
model's own `metrics.bands["SK-07"]["verdict"]` is not read.
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

    oot = m.get("oot") or {}
    status = oot.get("status")

    if status != "ok":
        reason = {
            "skipped_quick": "data/model_metrics.json was produced with --quick, which "
                             "skips the out-of-time exhibit; rerun `python3 "
                             "src/score_and_pack.py` without --quick",
            "skipped_low_n": f"fewer than 50 positives in the early-months training window "
                             f"(n={oot.get('n')})",
        }.get(status, f"metrics.oot.status = {status!r}")
        return [Result("SK-07", status="pending", detail=reason)]

    degradation = round(float(oot["degradation_pp"]), 4)
    n = oot.get("n")
    oot_ci_raw = oot.get("oot_ci") or [None, None]
    oot_ci = sh.wilson_ci({"ci_low": oot_ci_raw[0], "ci_high": oot_ci_raw[1]})
    detail = (f"cut month {oot.get('cut_month')}; in-time precision@10% "
              f"{oot.get('in_time_precision'):.4f} vs OOT {oot.get('oot_precision_at_budget'):.4f} "
              f"(OOT 95% CI {oot_ci}); OOT baseline {oot.get('oot_baseline')}, OOT row AUC "
              f"{oot.get('oot_row_auc')}. Negative degradation means the OOT window did better "
              f"than in-time.")
    result = Result("SK-07", value=degradation, n=n, detail=detail)

    try:
        result.figures.append(_figure(ctx, oot))
    except Exception:
        pass

    return [result]


def _figure(ctx: RunnerContext, oot: dict) -> str | None:
    in_time = oot.get("in_time_precision")
    oot_p = oot.get("oot_precision_at_budget")
    oot_ci = oot.get("oot_ci") or [None, None]
    if in_time is None or oot_p is None:
        return None

    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    xs = ["in-time\n(holdout)", f"out-of-time\n(last {oot.get('cut_month') and 6} mo)"]
    ys = [in_time, oot_p]
    err_lo = [0, (oot_p - oot_ci[0]) if oot_ci[0] is not None else 0]
    err_hi = [0, (oot_ci[1] - oot_p) if oot_ci[1] is not None else 0]
    ax.bar(xs, ys, color=["#2563EB", "#F59E0B"], yerr=[err_lo, err_hi], capsize=6)
    ax.set_ylabel("precision @ 10% budget")
    deg = oot.get("degradation_pp")
    ax.set_title(f"Out-of-time degradation: {deg:+.2f} pp (band <= 5.0 pp)")
    ax.set_ylim(0, max(ys) * 1.3)
    ax.grid(axis="y", alpha=0.25)
    return sh.savefig(fig, ctx, "oot_precision.png")
