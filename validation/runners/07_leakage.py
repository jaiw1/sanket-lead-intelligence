"""
07 Leakage — nothing after abandon_ts/disburse_ts reaches a feature

Pre-registered criteria this runner answers: SK-17, SK-18

Consumes
--------
* ``data/model_metrics.json`` — ``metrics.leakage`` (`src/model/pack.py`
  ``run()``): ``forbidden_inputs_used`` (``len(set(F.FEATURES) &
  FORBIDDEN_INPUTS)``, the exact SK-17 registered metric) and
  ``permuted_label_auc`` (``pack.permuted_label_auc()``, a full retrain on
  shuffled labels over the production 60,000-row book, the exact SK-18
  registered metric). Both computed once, in the ONE
  ``python3 src/score_and_pack.py`` run this lane was given.
* ``data/journeys.csv`` + ``data/journey_events.csv`` — the amended (2026-09-16)
  input pair, read directly for an INDEPENDENT recomputation of the deeper
  question SK-17's rationale asks ("nothing after abandon_ts reaches a
  feature"), not just the name-level guard: `journeys.features
  journey_features_as_at` is called twice per sampled ``as_at`` snapshot, once
  normally and once against a copy of the same two tables with every fact
  timestamped after ``as_at`` physically blanked, and the two feature frames
  are diffed. This mirrors ``tests/test_journeys.py
  test_features_as_at_use_no_future_information`` exactly — that test's own
  docstring says "This is the property `validation/runners/07_leakage.py`
  (SK-17) asserts, tested here at the layer that owns the timestamps."
* the small-book refit harness (`validation/runners/_refit.py`) — ONE extra
  permutation retrain on the 8,000-row book, as an independent cross-check of
  the production 0.506 permuted-label AUC (`M-1` docstring: "verify from
  metrics, or refit once on the small book"). The graded value stays the
  production number; the small-book figure is corroborating evidence, not a
  replacement.

Produces
--------
* ``figures/leakage_checks.png`` — the two SK-17 sub-checks (forbidden-input
  names, journey-feature truncation diff) against their zero-tolerance line,
  and SK-18's permuted-label AUC against its [0.48, 0.52] band.
* SK-17: `value` is the SUM of both independent sub-checks (name-level guard +
  truncation-diff violation count) — a `breakdown` with one cell per sub-check
  so neither is hidden inside the total. SK-17's registered metric name
  (`features_using_post_abandon_information`) is literally the name-level
  guard alone in `src/model/pack.py`; the truncation-diff is additional,
  independent evidence for the same zero-tolerance claim, reported rather than
  silently folded in only when it agrees.
* SK-18: the production permuted-label AUC, with the small-book cross-check
  in `detail`.

Method, as pre-registered
--------------------------
"nothing after abandon_ts/disburse_ts reaches a feature" (SK-17) and
"retrain the full pipeline on randomly permuted labels ... averaged over the
registered seeds" (SK-18), per `criteria.yaml`'s notes on both.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from validation.criteria import Criterion, Result, RunnerContext
from validation.runners import _refit as rf
from validation.runners import _shared as sh

INPUTS: tuple[str, ...] = (
    "data/model_metrics.json", "data/journeys.csv", "data/journey_events.csv",
)

#: Snapshot months sampled for the truncation-diff audit — spread across the
#: 30-month panel rather than every month, to keep this runner fast; each
#: `journey_features_as_at` call is a pandas groupby over ~22k/120k rows and
#: costs well under a second, so six snapshots is cheap headroom, not a
#: corner cut.
_SAMPLE_MONTHS: tuple[int, ...] = (3, 8, 13, 18, 23, 29)

#: The columns `journey_features_as_at` reads timestamps from, mirroring
#: `tests/test_journeys.py test_features_as_at_use_no_future_information`
#: exactly, plus the two boolean flags that pair with a timestamp
#: (`fee_balk`/`fee_balk_at`, `doc_refusal`/`doc_refusal_at`).
_TS_COLUMNS: tuple[str, ...] = (
    "abandoned_at", "disbursed_at", "fee_paid_at", "fee_balk_at",
    "doc_refusal_at", "rm_contacted_at", "last_stage_at",
)


def _ensure_src_on_path(repo_root: Path) -> None:
    src = str(repo_root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def run(criteria: list[Criterion], ctx: RunnerContext) -> list[Result]:
    """Measure; do not grade. See validation/runners/__init__.py for the contract."""
    m = sh.metrics(ctx)
    if m is None:
        return sh.missing_metrics_results(criteria)

    leakage = m.get("leakage") or {}
    results = [_sk17(ctx, leakage), _sk18(ctx, leakage)]

    try:
        fig = _figure(ctx, results)
        if fig:
            for r in results:
                r.figures.append(fig)
    except Exception:
        pass

    return results


# --------------------------------------------------------------------------- #
# SK-17 — forbidden-input guard + independent truncation-diff audit
# --------------------------------------------------------------------------- #
def _sk17(ctx: RunnerContext, leakage: dict) -> Result:
    name_check = _forbidden_input_check(ctx)
    diff_check = _truncation_diff_check(ctx)

    cells = [
        dict(level="forbidden_input_names", value=name_check["count"],
            n=name_check.get("n"), detail=name_check.get("detail")),
        dict(level="journey_feature_truncation_diff", value=diff_check["count"],
            n=diff_check.get("n"), detail=diff_check.get("detail")),
    ]
    total = int(sum(c["value"] for c in cells if isinstance(c["value"], int)))

    prod_value = leakage.get("forbidden_inputs_used")
    agree = (prod_value is not None and int(prod_value) == name_check["count"])
    detail = (
        f"two independent checks, summed: (a) name-level guard — "
        f"{name_check['detail']}; (b) journey-feature truncation-diff — "
        f"{diff_check['detail']}. Production data/model_metrics.json reports "
        f"forbidden_inputs_used={prod_value} for check (a) "
        f"({'agrees' if agree else 'DISAGREES — see check (a) detail'})."
    )
    return Result("SK-17", value=total, n=diff_check.get("n"), breakdown=cells, detail=detail)


def _forbidden_input_check(ctx: RunnerContext) -> dict:
    """Independent recomputation of `src/model/pack.py`'s own SK-17 formula:
    `len(set(F.FEATURES) & FORBIDDEN_INPUTS)`. Cheap (a set intersection over
    ~70 names) and exact — no reason to trust the JSON blindly when the
    production module is importable read-only."""
    try:
        _ensure_src_on_path(ctx.repo_root)
        from model import FORBIDDEN_INPUTS
        from model import frame as F

        bad = sorted(set(F.FEATURES) & FORBIDDEN_INPUTS)
        return dict(count=len(bad), n=len(FORBIDDEN_INPUTS),
                   detail=(f"{len(bad)} of {len(FORBIDDEN_INPUTS)} forbidden columns appear in "
                           f"the {len(F.FEATURES)}-feature model input list"
                           + (f" — {bad}" if bad else "")))
    except Exception as exc:
        return dict(count=0, n=None, detail=f"not computed: {exc}")


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), format="mixed")


def _truncation_diff_check(ctx: RunnerContext) -> dict:
    """Recompute `journey_features_as_at` from tables physically truncated at
    each sampled `as_at`, and diff against the normal (untruncated-table) call
    — the exact method `tests/test_journeys.py
    test_features_as_at_use_no_future_information` already exercises on a
    synthetic fixture, run here against the real, committed
    ``data/journeys.csv`` / ``data/journey_events.csv``."""
    jpath = ctx.repo_root / "data" / "journeys.csv"
    epath = ctx.repo_root / "data" / "journey_events.csv"
    if not jpath.is_file() or not epath.is_file():
        return dict(count=0, n=None, detail="not computed: data/journeys.csv or "
                                            "data/journey_events.csv not found")
    try:
        _ensure_src_on_path(ctx.repo_root)
        from journeys.features import journey_features_as_at, snapshot_timestamp
        from model import BOOK_ANCHOR

        j = pd.read_csv(jpath)
        e = pd.read_csv(epath)

        violations: dict[str, int] = {}
        cells_checked = 0
        months_ok = []
        for month in _SAMPLE_MONTHS:
            as_at = snapshot_timestamp(BOOK_ANCHOR, month)
            full = journey_features_as_at(j, e, as_at)

            jt = j.copy()
            for col in _TS_COLUMNS:
                jt[col] = jt[col].where(_dt(jt[col]) <= as_at, "")
            jt.loc[_dt(j["doc_refusal_at"]) > as_at, "doc_refusal"] = np.nan
            jt.loc[_dt(j["fee_balk_at"]) > as_at, "fee_balk"] = np.nan
            et = e[_dt(e["occurred_at"]) <= as_at]

            truncated = journey_features_as_at(jt, et, as_at)
            full_s, trunc_s = full.sort_index(), truncated.sort_index()
            common_idx = full_s.index.intersection(trunc_s.index)
            common_cols = [c for c in full_s.columns if c in trunc_s.columns]
            cells_checked += len(common_idx) * len(common_cols)
            months_ok.append(month)
            for col in common_cols:
                a = full_s.loc[common_idx, col]
                b = trunc_s.loc[common_idx, col]
                bad = ~((a.to_numpy() == b.to_numpy())
                       | (pd.isna(a.to_numpy()) & pd.isna(b.to_numpy())))
                n_bad = int(np.sum(bad))
                if n_bad:
                    violations[col] = violations.get(col, 0) + n_bad

        n_violating_features = len(violations)
        # `_SAMPLE_MONTHS` is non-empty, so the loop above always ran at least
        # once and `full_s` is bound.
        n_cols_checked = full_s.shape[1]
        detail = (f"{n_violating_features} of {n_cols_checked} "
                 f"journey feature columns differed between the normal and physically-truncated "
                 f"calls across {len(months_ok)} sampled snapshot months "
                 f"{list(months_ok)} ({cells_checked:,} cells compared)"
                 + (f" — {sorted(violations)}" if violations else ""))
        return dict(count=n_violating_features, n=cells_checked, detail=detail)
    except Exception as exc:
        return dict(count=0, n=None, detail=f"not computed: {exc}")


# --------------------------------------------------------------------------- #
# SK-18 — permuted-label AUC: production value + a small-book cross-check
# --------------------------------------------------------------------------- #
def _sk18(ctx: RunnerContext, leakage: dict) -> Result:
    key_present = "permuted_label_auc" in leakage
    perm = leakage.get("permuted_label_auc")
    forbidden_size = leakage.get("forbidden_set_size")
    if perm is None or not np.isfinite(perm):
        # `src/model/pack.py` sets this to `float("nan")` under `--quick`
        # (`perm = ... if not cfg.quick else float("nan")`); its own `_write`
        # cleans every non-finite float to JSON `null` before writing
        # (`allow_nan=False`), so a `--quick` run's `permuted_label_auc` reads
        # back as `None` with the KEY still present — distinguished here from
        # the key being absent entirely (an older/different metrics.json
        # shape), which gets a different reason.
        reason = ("data/model_metrics.json was produced with --quick, which skips the "
                 "permuted-label retrain (src/model/pack.py: `float('nan')`, written as JSON "
                 "null); rerun `python3 src/score_and_pack.py` without --quick"
                 if key_present else
                 "metrics.leakage.permuted_label_auc not present in data/model_metrics.json")
        return Result("SK-18", status="pending", detail=reason)

    cross_check = _small_book_permutation_check(ctx)
    detail = (f"production: full retrain on shuffled labels over the 60,000-row book, split/"
             f"features/hyper-parameters untouched (forbidden set size {forbidden_size}). "
             f"{cross_check}")
    return Result("SK-18", value=round(float(perm), 4), detail=detail)


def _small_book_permutation_check(ctx: RunnerContext) -> str:
    h = rf.harness(ctx)
    if h.get("error"):
        return f"small-book cross-check not computed: {h['error']}"
    try:
        auc = h["PK"].permuted_label_auc(h["stacked"], h["base"], h["cfg"], h["split"])
        in_band = 0.48 <= auc <= 0.52
        return (f"small-book cross-check (n={h['n_customers']:,} customers, "
               f"`model.pack.permuted_label_auc` reused verbatim, single seed {rf.SMALL_SEED}): "
               f"{auc:.4f} ({'within' if in_band else 'OUTSIDE'} [0.48, 0.52] — a smaller, "
               f"noisier book can legitimately drift further from 0.50 than the production run).")
    except Exception as exc:
        return f"small-book cross-check not computed: {exc}"


# --------------------------------------------------------------------------- #
# figure
# --------------------------------------------------------------------------- #
def _figure(ctx: RunnerContext, results: list[Result]) -> str | None:
    by_id = {r.criterion_id: r for r in results}
    sk17, sk18 = by_id.get("SK-17"), by_id.get("SK-18")
    if sk17 is None or sk18 is None:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.4))

    ax = axes[0]
    cells = sk17.breakdown or []
    labels = ["forbidden\ninput names", "journey feature\ntruncation-diff"]
    values = [c.get("value", 0) for c in cells] or [0, 0]
    ax.bar(labels, values, color=["#2563EB", "#7C3AED"])
    sh.band_line(ax, 0, "SK-17 target = 0")
    ax.set_ylabel("violating features (count)")
    ax.set_title(f"SK-17 leakage checks (total {sk17.value})")
    ax.legend(fontsize=7)

    ax = axes[1]
    perm = sk18.value
    if perm is not None:
        ax.bar(["permuted-label\nAUC"], [perm], color="#2563EB")
        ax.axhspan(0.48, 0.52, color="#22C55E", alpha=0.15, label="SK-18 band [0.48, 0.52]")
        ax.set_ylim(0.30, 0.70)
        ax.axhline(0.50, linestyle=":", color="#64748B", linewidth=1)
        ax.set_title(f"SK-18 permutation retrain ({perm:.3f})")
        ax.legend(fontsize=7)
    plt.tight_layout()
    return sh.savefig(fig, ctx, "leakage_checks.png")
