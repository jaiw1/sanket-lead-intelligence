"""
Shared small-book refit machinery — for runners 07 (leakage cross-check), 08
(ablation) and 10 (stress), the three SK-17..SK-25 runners that genuinely need
a fresh model fit rather than an adapter over ``data/model_metrics.json``.

A leading underscore excludes this module from `validation/runners/__init__.py`
`discover()`'s `NN_slug.py` pattern, exactly like `_shared.py` — it is never
invoked as a runner and never appears in a criterion's `runner:` field.

Why a refit at all
-------------------
`validation/runners/_shared.py` explains why runners 01-06 never refit: the
one full `python3 src/score_and_pack.py` run is itself this lane's ~10-minute
budget, already spent. But SK-19 (ablation — "what would we lose without this
feature family") and SK-22 (stress — reweighted-positives / channel-missing)
ask questions that one run's `data/model_metrics.json` has no answer for: it
was never asked to drop a family or reweight a label. Answering them needs a
second fit, in each direction tested — which the L9 brief explicitly carves
out of the "no second full run" rule: *"Where a criterion genuinely needs a
refit ... do it with the model's own training function on the 8,000-row small
book (`realism.generate_book_and_journeys` as L9 did) and say so."*

Why the SMALL book (n=8,000), never the 60,000-row production book
---------------------------------------------------------------------
`validation/tests/conftest.py`'s `small_metrics_root` fixture already
established n=8,000 / 30 months / seed=7 as "the smallest size that clears
every existing generator band reliably" (SD-S7's own finding — n=3,000 was
tried first and rejected). This module reuses that exact convention via
`realism.generate_book_and_journeys` rather than inventing a second "small"
size, and a single quick LightGBM config (150 trees, one seed) rather than
refitting at production scale, which would turn one ablation family into
another ~90s-minimum run and blow this lane's remaining budget across ten
families plus two stress scenarios plus a leakage cross-check.

What a small-book delta buys, and what it does not
----------------------------------------------------
A small-book delta is a smaller-book, lower-precision, single-seed estimate of
the *direction and rough size* of an effect — useful for "does dropping this
family help or hurt, roughly how much", not a re-creation of the production
run's own AUC/precision numbers (those stay sourced from
`data/model_metrics.json`, computed on the full 60,000-row book across 5
seeds). Every `Result` built from this module says so in `detail`.

Design: generate once, fit many
---------------------------------
`harness(ctx)` builds the small book, the point-in-time frame and the
customer-grouped split exactly once per process (cached, like
`_shared.py load_metrics_doc`, keyed on `str(ctx.repo_root)` even though the
generated book itself does not depend on repo content — only `<repo_root>/src`
needs to be on `sys.path`). `python3 -m validation.run` runs runners 07, 08,
09, 10, 11, 12 in that order inside one process, so by the time 08_ablation or
10_stress calls `harness()`, 07_leakage (if it ran first) has already paid the
~5s generation + ~1.4s frame-assembly cost; each runner then only pays for its
own `fit_ranker` calls (~1-1.5s each on this book). The full sequence — one
generation, one baseline fit, ten family-drop fits (08), one reweighted fit
(10), one permutation-retrain fit (07's cross-check) — measured at ~25s total,
independently timed before this module was written.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from validation.criteria import RunnerContext

#: Matches `validation/tests/conftest.py` SMALL_N / SMALL_MONTHS / SMALL_SEED
#: exactly — see the module docstring for why this is not a second convention.
SMALL_N = 8_000
SMALL_MONTHS = 30
SMALL_SEED = 7

#: A model small enough to fit in ~1-1.5s per call: 150 trees, one seed.
#: Mirrors `validation/tests/conftest.py MODEL_KW`'s lgbm block.
LGBM_KW: dict[str, Any] = dict(
    n_estimators=150, learning_rate=0.06, num_leaves=31, min_child_samples=40,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=-1, verbose=-1,
)

_CACHE: dict[str, Any] = {}


def reset_cache() -> None:
    """Test hook: clear the process-local cache between independent test fixtures."""
    _CACHE.clear()


def _ensure_src_on_path(repo_root: Path) -> None:
    src = str(repo_root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def harness(ctx: RunnerContext) -> dict[str, Any]:
    """A fresh, process-cached small book + frame + split, ready to refit.

    Returns a dict with keys ``base``, ``stacked``, ``split``, ``cfg``, plus
    the imported modules a caller needs (``F`` = `model.frame`, ``M`` =
    `model.metrics`, ``PK`` = `model.pack`, ``fit_ranker``, ``roc_auc_score``)
    so callers never need their own `sys.path` dance. On any failure (src not
    importable, generator raised, ...) returns ``{"error": <message>}`` instead
    of raising, so a runner turns that into a `pending` result rather than a
    crash the harness would report as `error` on every criterion.
    """
    key = str(ctx.repo_root)
    if key in _CACHE:
        return _CACHE[key]
    try:
        _ensure_src_on_path(ctx.repo_root)
        import realism
        from model import ModelConfig
        from model import frame as F
        from model import metrics as M
        from model import pack as PK
        from model.train import fit_ranker, split_customers
        from sklearn.metrics import roc_auc_score

        root = Path(tempfile.mkdtemp(prefix="sanket_validation_refit_"))
        data_dir = root / "data"
        realism.generate_book_and_journeys(
            n=SMALL_N, months=SMALL_MONTHS, seed=SMALL_SEED, out_dir=data_dir)

        cfg = ModelConfig(root=root, seed=SMALL_SEED, seeds=(SMALL_SEED,),
                          quick=True, lgbm=dict(LGBM_KW))
        t = F.load_tables(data_dir)
        base = F.as_categorical(F.customer_month_frame(t))
        stacked = F.as_categorical(F.stack(base))
        sp = split_customers(base["cust_id"].unique(), cfg, SMALL_SEED)

        out: dict[str, Any] = dict(
            root=root, base=base, stacked=stacked, split=sp, cfg=cfg,
            F=F, M=M, PK=PK, fit_ranker=fit_ranker, roc_auc_score=roc_auc_score,
            n_base=int(len(base)), n_customers=int(base["cust_id"].nunique()),
        )
    except Exception as exc:  # pragma: no cover - defensive; turned into `pending`
        out = dict(error=f"{type(exc).__name__}: {exc}")
    _CACHE[key] = out
    return out


def _held_mask(h: dict) -> np.ndarray:
    base, sp = h["base"], h["split"]
    return sp.mask(base["cust_id"], "held") & (base["eligible_for_contact"].to_numpy() == 1)


def _score(h: dict, rk, extra: dict | None = None, frame=None) -> dict:
    """Held-set precision@budget (Wilson CI, from `model.metrics.precision_at`)
    and row-level AUC (Hanley-McNeil CI) for an already-fitted `Ranker`, scored
    against `frame` (default: the harness's own unduplicated, block-ordered
    `stacked` frame — pass an explicit `frame` only when the caller needs to
    score against a modified copy, e.g. `blanked_score`'s NaN'd columns; it
    must still be the same block-ordered shape `Ranker.matrix()` asserts)."""
    base, stacked, cfg, M = h["base"], h["stacked"], h["cfg"], h["M"]
    held = _held_mask(h)
    P = rk.matrix(stacked if frame is None else frame)
    hb = base[held]
    Ph = P[held]
    y = hb["t_label"].to_numpy().astype(int)
    p_top = Ph.max(axis=1)
    at = M.precision_at(y, p_top, cfg.budget)
    a, lo, hi = M.auc_ci(y, p_top)
    out = dict(precision=round(float(at["precision"]), 4), ci_low=round(float(at["ci_low"]), 4),
              ci_high=round(float(at["ci_high"]), 4), n=int(at["k"]),
              auc=(round(float(a), 4) if np.isfinite(a) else None),
              auc_ci=([round(float(lo), 4), round(float(hi), 4)] if np.isfinite(a) else None),
              baseline=round(float(y.mean()), 4), n_held=int(len(y)))
    if extra:
        out.update(extra)
    return out


def fit_and_score(h: dict, features: tuple[str, ...]) -> dict:
    """Fit `fit_ranker` with `features` on the harness's split; score the held
    slice with `model.metrics.precision_at` / `auc_ci`. The fitted `Ranker` is
    included under `"ranker"` so a caller (e.g. the stress runner's
    channel-missing scenario) can re-score it against a modified frame without
    a second fit."""
    stacked, sp, cfg = h["stacked"], h["split"], h["cfg"]
    rk = h["fit_ranker"](stacked, sp, cfg, features=tuple(features))
    out = _score(h, rk, extra=dict(n_features=len(features)))
    out["ranker"] = rk
    return out


def baseline(h: dict) -> dict:
    """The full-feature small-book fit, cached on `h` itself (the harness dict
    IS the cached object `_CACHE` holds, so this persists across every runner
    that calls `harness(ctx)` for the same `ctx.repo_root` within one process —
    07, 08 and 10 share exactly one baseline fit rather than three)."""
    if "baseline" not in h:
        h["baseline"] = fit_and_score(h, h["F"].FEATURES)
    return h["baseline"]


def reweighted_fit_and_score(h: dict, multiplier: int = 2) -> dict:
    """Duplicate eligible, training-split POSITIVE rows `multiplier`-1 extra
    times before fitting (a training-time reweight, not a resample of the
    held-out population), then score against the harness's own unduplicated
    `stacked` frame. This is SK-22's "2x base rate" scenario: it stresses what
    the ranker learns without ever touching what it is measured against.

    Duplicating rows rather than passing `sample_weight` is deliberate:
    `model.train.fit_ranker` has no `sample_weight` parameter, and row
    duplication is the more transparent choice to read back later — a
    `journal_ever_disbursed` fan-out row-count is auditable where a weight
    array bolted onto the fit call is not.
    """
    import pandas as pd

    base, stacked, sp, cfg, F = h["base"], h["stacked"], h["split"], h["cfg"], h["F"]
    cust = stacked["cust_id"]
    fit_pos = (sp.mask(cust, "fit")
              & (stacked["eligible_for_contact"].to_numpy() == 1)
              & (stacked["y"].to_numpy() == 1))
    extra_frames = [stacked[fit_pos]] * (multiplier - 1)
    boosted = pd.concat([stacked, *extra_frames], ignore_index=True) if extra_frames else stacked
    rk = h["fit_ranker"](boosted, sp, cfg, features=tuple(F.FEATURES))
    # score against the ORIGINAL frame: `Ranker.matrix()` asserts a contiguous
    # product-block row order that the duplicated `boosted` frame no longer has,
    # and scoring must only ever see the real held population once each.
    return _score(h, rk, extra=dict(multiplier=multiplier,
                                    n_fit_positives_added=int(fit_pos.sum()) * (multiplier - 1)))


def blanked_score(h: dict, rk, family: str) -> dict:
    """Re-score an ALREADY-FITTED ranker after blanking one feature family's
    columns to NaN in a copy of the harness's `stacked` frame — a channel
    going dark in production, not a retrain that never knew the channel
    existed. LightGBM routes NaN through its learned missing-value branch, so
    this measures the trained model's live robustness to the channel's loss,
    which `fit_and_score` on a family-dropped feature list (08_ablation's
    question) does not."""
    F = h["F"]
    stacked = h["stacked"]
    cols = [c for c in F.FEATURE_FAMILIES[family] if c in stacked.columns]
    blanked = stacked.copy()
    for c in cols:
        blanked[c] = np.nan
    return _score(h, rk, extra=dict(blanked_family=family, blanked_columns=cols))
