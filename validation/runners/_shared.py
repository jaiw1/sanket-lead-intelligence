"""
Shared machinery for runners 01-06 — not itself a runner.

`validation/runners/__init__.py`'s `discover()` only picks up files matching
`NN_slug.py`; a leading underscore excludes this module from that pattern, so it
is never invoked as a runner and never appears in a criterion's `runner:` field.

Design, and why it differs from the DRISHTi (L8) validation pack
------------------------------------------------------------------
DRISHTi's `validation/runners/_shared.py` (a sibling lane, read for pattern only)
refits a model *inside* the validation process, because that repo's generator
and model are cheap enough to run six times over without leaving the runners'
budget. SANKET's is not: one full `score_and_pack.py` run (5 seeds, OOT,
permuted-label retrain, the baseline ladder) is itself the ~10-minute budget
this lane was given, and it has already been spent once, on
`python3 src/score_and_pack.py` (no `--quick` — SK-07 needs the out-of-time
exhibit, which `--quick` skips). Refitting again inside a runner to get raw
held-out predictions for a fresh bootstrap would be a **second** full model run,
which the budget does not allow.

So these six runners are graders, not trainers: they read `data/model_metrics.json`
— the ONE run's output, already computed with `src/model/metrics.py`'s own
`wilson`, `auc_ci`, `precision_at`, `ece`, `psi`, `menu_metrics`,
`window_respect`, `per_product`, all of them pre-registered-band-shaped — and
turn each pre-registered SK-id into a `Result` the harness grades independently.
"Independently" here means what `validation/run.py` actually enforces: a
runner sets `value`/`ci`/`n`/`breakdown` and leaves `status` alone, so it is
`validation.criteria.Criterion.check()` — reading straight from
`criteria.yaml` — that decides pass/fail, never the model's own
`metrics.bands[...]["verdict"]`. That field is deliberately never read here.

Confidence intervals, honestly
-------------------------------
`criteria.yaml confidence.method` calls for a percentile bootstrap resampled at
`cust_id`. That requires the raw (cust_id, product, y, score) rows behind each
metric, and the one script run does not persist those (only the aggregates in
`data/model_metrics.json`) — writing them out would mean editing
`src/score_and_pack.py`, which this lane may not touch. Two intervals are used
instead, in order of preference, and every `Result.detail` says which one:

1. **Cross-seed percentile spread** (`metrics.seeds.spread[...]`) — the 2.5th to
   97.5th percentile of the metric's value across the five *registered* seeds
   [7, 8, 9, 10, 11], i.e. `criteria.yaml confidence.cross_seed`'s own method,
   already computed by `model.metrics.spread`. Available for the headline
   precision/baseline numbers, macro AUC, the six per-product AUCs, menu-of-4,
   window respect and overall ECE. This is not a weaker substitute for a
   group-bootstrap — it is wider, because it carries training variance the
   bootstrap would not.
2. **The single (packed) seed's Wilson / Hanley-McNeil interval** — for
   whatever `metrics.seeds.spread` does not cover (per-product ECE, the
   window-shopper AUC, top-1 accuracy, the by-cut cells). Row-level, so
   narrower than a group bootstrap would be; documented as such.

Every criterion is graded on the **packed seed's point value** (seed 7 — "the
value already used in today's pipelines", `criteria.yaml seeds.policy`), which
is what `01_holdout` etc. being "deterministic under ctx.seed" means. Where the
cross-seed mean would flip the verdict, `detail` says so instead of hiding it
(see `seed_mean_note` below) — the SK-04 window-respect finding in
`MODEL_CARD.md` §8 is exactly this: passes on the packed seed, fails on the
5-seed mean.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set first)

from validation.criteria import Criterion, Result, RunnerContext

METRICS_REL_PATH = "data/model_metrics.json"

_CACHE: dict[str, Any] = {}


def reset_cache() -> None:
    """Test hook: clear the process-local cache between independent test fixtures."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Loading data/model_metrics.json — the one full run's output
# ---------------------------------------------------------------------------
def load_metrics_doc(ctx: RunnerContext) -> dict | None:
    """The whole `data/model_metrics.json`, cached per repo_root for this process.

    Returns None if the file is missing rather than raising, so a runner can
    turn that into `pending` results (the file is gitignored and regenerable —
    `python3 src/score_and_pack.py` — never committed, per README §11) instead
    of crashing the whole harness.
    """
    key = str(ctx.repo_root)
    if key in _CACHE:
        return _CACHE[key]
    p = ctx.repo_root / METRICS_REL_PATH
    if not p.is_file():
        _CACHE[key] = None
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    _CACHE[key] = doc
    return doc


def metrics(ctx: RunnerContext) -> dict | None:
    doc = load_metrics_doc(ctx)
    return doc["metrics"] if doc else None


def meta(ctx: RunnerContext) -> dict | None:
    doc = load_metrics_doc(ctx)
    return doc["meta"] if doc else None


def missing_metrics_results(crits: list[Criterion]) -> list[Result]:
    """Every criterion this runner owns, reported `pending` because
    data/model_metrics.json does not exist yet."""
    return [
        Result(c.id, status="pending",
               detail=f"{METRICS_REL_PATH} not found — run "
                       "`python3 src/score_and_pack.py` (add --quick for a ~90s "
                       "pass; SK-07/02_oot needs a run without --quick) before "
                       "`python3 -m validation.run`")
        for c in crits
    ]


# ---------------------------------------------------------------------------
# CI resolution: cross-seed spread first, single-seed Wilson/Hanley second
# ---------------------------------------------------------------------------
def spread_ci(m: dict, spread_key: str) -> tuple[tuple[float, float] | None, str | None]:
    """`(ci, detail_fragment)` from `metrics.seeds.spread[spread_key]`, or
    `(None, None)` if that key was not computed (fewer than 2 seeds, or this
    metric is not one of the ones `score_and_pack.py` spreads across seeds)."""
    sp = (m.get("seeds") or {}).get("spread") or {}
    row = sp.get(spread_key)
    if not row or row.get("n", 0) < 2:
        return None, None
    lo, hi = row.get("pct_low"), row.get("pct_high")
    if lo is None or hi is None:
        return None, None
    frag = (f"95% CI is the cross-seed 2.5-97.5 percentile spread over "
            f"{row['n']} registered seeds (criteria.yaml confidence.cross_seed), "
            f"mean {row.get('mean'):.4f}" if isinstance(row.get("mean"), float)
            else f"95% CI is the cross-seed percentile spread over {row['n']} seeds")
    return (round(float(lo), 4), round(float(hi), 4)), frag


def wilson_ci(block: dict | None) -> tuple[float, float] | None:
    """`(ci_low, ci_high)` from a `model.metrics.measured()`-shaped dict, or a
    `{value, ci_low, ci_high, ...}` block such as `metrics.per_product_auc[p]`."""
    if not block:
        return None
    lo, hi = block.get("ci_low"), block.get("ci_high")
    if lo is None or hi is None:
        return None
    return (round(float(lo), 4), round(float(hi), 4))


def seed_mean_note(crit: Criterion, value: float, m: dict, spread_key: str) -> str | None:
    """If the cross-seed mean would land on the other side of the band from the
    packed seed's point value, say so — never hide it (MODEL_CARD.md §8's SK-04
    finding is exactly this disagreement)."""
    sp = (m.get("seeds") or {}).get("spread") or {}
    row = sp.get(spread_key)
    if not row or row.get("n", 0) < 2 or row.get("mean") is None:
        return None
    mean = float(row["mean"])
    ok_point = crit.check(value)
    ok_mean = crit.check(mean)
    if ok_point is None or ok_mean is None or ok_point == ok_mean:
        return None
    return (f"packed seed ({value:.4f}) {'passes' if ok_point else 'fails'} this band; "
            f"the {row['n']}-seed mean ({mean:.4f}) {'passes' if ok_mean else 'fails'} it — "
            f"reported, not hidden.")


# ---------------------------------------------------------------------------
# src/model import shim — for the handful of places (06_stability's CSI
# exhibit) that reuse a `src/model/**` function directly rather than reading
# an already-computed value out of data/model_metrics.json. Never used to
# refit anything — see the module docstring's "Design" section.
# ---------------------------------------------------------------------------
def _ensure_src_on_path(repo_root: Path) -> None:
    src = str(repo_root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def model_metrics_module(ctx: RunnerContext):
    """The `src/model/metrics.py` module, importable without a subprocess."""
    _ensure_src_on_path(ctx.repo_root)
    import model.metrics as M  # noqa: F401
    return M


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def savefig(fig, ctx: RunnerContext, name: str) -> str:
    ctx.figures_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.figures_dir / name
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return name


def band_line(ax, threshold, label: str, orientation: str = "h") -> None:
    """A dashed reference line at a pre-registered threshold, so a figure
    carries its own band rather than making a reader cross-reference the table."""
    fn = ax.axhline if orientation == "h" else ax.axvline
    fn(threshold, linestyle="--", linewidth=1, color="#B00020", alpha=0.8, label=label)
