# -*- coding: utf-8 -*-
"""Customer-clustered bootstrap over the **delivered** queue selection.

Why a bootstrap at all
----------------------
``validation/criteria.yaml`` registers ``confidence.method`` as a percentile
bootstrap resampled at ``cust_id``, and until now the pack could not honour it:
the one scoring run kept only aggregates, so the validation graders fell back on
a Wilson interval (row-level, too narrow — the same customer appears in up to 30
monthly rows) or on the five-seed percentile spread (a different estimand
entirely).  This module closes that gap.

What is resampled, and what is not
----------------------------------
**Customers**, with replacement.  Every row belonging to a drawn customer comes
with it, so the correlation between one customer's thirty monthly rows is
carried rather than assumed away.  The model is **not** refitted: these are the
packed seed's held-out predictions, so the interval is *sampling* uncertainty
over which customers happened to land in the book — not training variance
(that is the five-seed spread) and not generator variance (that is
``src/experiments/generator_variation.py``).  Three different questions, three
separate fields; ``MODEL_CARD.md`` §9 keeps them apart.

The queue is re-selected inside every resample
----------------------------------------------
This is the part that makes the interval mean anything.  ``precision@10%`` is
not a mean of independent row outcomes — it is the precision of a *list chosen
by a policy*, and the policy's intent percentiles, its eligible-pool size and
therefore its ``k`` all move when the pool moves.  Each resample calls
``model.policy.score_pool`` and ``model.policy.precision_at`` on the resampled
pool, exactly as ``build_queue`` would.  Resampling row outcomes and taking a
proportion CI would answer a question nobody asked.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import PRODUCTS
from . import policy as PO

#: Resamples.  1,000 is enough for a 2.5/97.5 percentile to be stable to about a
#: tenth of a percentage point here, and the whole thing costs ~20 s.
N_RESAMPLES = 1000

#: Where `persist` writes the packed seed's held-out predictions.  Gitignored and
#: regenerable (`python3 src/score_and_pack.py`), like `data/model_metrics.json`.
PREDICTIONS_DIR = "predictions"


def persist(data_dir: Path, seed: int, cust_id, month, y, safe_emi, eligible,
            P: np.ndarray, label_product, dropoff_product) -> Path:
    """Write one seed's held-out predictions so an experiment need not refit.

    ``.npz`` rather than CSV: 29k x 6 floats plus six string columns is 2 MB
    compressed and loads in milliseconds, and the array shapes are part of the
    file instead of being re-inferred by a parser.
    """
    out = Path(data_dir) / PREDICTIONS_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"holdout_seed{int(seed)}.npz"
    np.savez_compressed(
        path,
        cust_id=np.asarray(cust_id, dtype=str),
        month=np.asarray(month, dtype=np.int32),
        y=np.asarray(y, dtype=np.int8),
        safe_emi=np.asarray(safe_emi, dtype=np.float32),
        eligible=np.asarray(eligible, dtype=bool),
        P=np.asarray(P, dtype=np.float32),
        products=np.asarray(list(PRODUCTS), dtype=str),
        label_product=np.asarray(label_product, dtype=str),
        dropoff_product=np.asarray(dropoff_product, dtype=str),
        seed=np.asarray([int(seed)], dtype=np.int32),
    )
    return path


def load(data_dir: Path, seed: int) -> dict | None:
    path = Path(data_dir) / PREDICTIONS_DIR / f"holdout_seed{int(seed)}.npz"
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def _groups(cust_id: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """Unique customers and the row indices belonging to each."""
    order = np.argsort(cust_id, kind="stable")
    sorted_ids = cust_id[order]
    uniq, starts = np.unique(sorted_ids, return_index=True)
    rows = np.split(order, starts[1:])
    return uniq, rows


def _percentile_ci(values: np.ndarray) -> tuple[float, float]:
    return (float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5)))


def precision_ci(cust_id, safe_emi, P: np.ndarray, eligible, y,
                 budgets: tuple[float, ...], n_resamples: int = N_RESAMPLES,
                 seed: int = 7, ranking: str | None = None) -> dict:
    """Customer-clustered percentile intervals for precision@budget and the baseline.

    Returns one block per budget plus ``baseline`` and ``headline``, each with
    ``point`` (the full sample's value), ``ci_low``/``ci_high`` (2.5/97.5
    percentiles over the resamples), ``se`` and ``n_resamples``.  The headline
    block carries the per-100 counts, so the sentence the deck quotes has an
    interval of its own rather than being two rounded numbers with none.
    """
    cust_id = np.asarray(cust_id, dtype=str)
    safe_emi = np.asarray(safe_emi, dtype=float)
    P = np.asarray(P, dtype=float)
    eligible = np.asarray(eligible).astype(bool)
    y = np.asarray(y).astype(int)
    ranking = ranking or PO.DEFAULT_RANKING

    uniq, rows_by_cust = _groups(cust_id)
    n_cust = len(uniq)
    rng = np.random.default_rng(seed)

    draws = {b: np.empty(n_resamples) for b in budgets}
    base_draws = np.empty(n_resamples)
    for i in range(n_resamples):
        pick = rng.integers(0, n_cust, n_cust)
        idx = np.concatenate([rows_by_cust[j] for j in pick])
        # The resampled pool is a different pool: a customer drawn twice really
        # is two customers as far as the queue is concerned, which is the point.
        sc = PO.score_pool(cust_id[idx], safe_emi[idx], P[idx], eligible[idx],
                           ranking=ranking)
        yy = y[idx]
        base_draws[i] = float(yy.mean())
        for b in budgets:
            draws[b][i] = PO.precision_at(yy, sc, b)["precision"]

    full = PO.score_pool(cust_id, safe_emi, P, eligible, ranking=ranking)
    out = dict(method="customer-clustered percentile bootstrap",
               resampled_unit="cust_id", n_customers=int(n_cust),
               n_rows=int(len(y)), n_resamples=int(n_resamples),
               ranking=ranking, seed=int(seed),
               queue_reselected_per_resample=True,
               note="Sampling uncertainty only. Training-seed variability is "
                    "metrics.seeds.spread; generator variability is "
                    "metrics.uncertainty.generator.")

    lo, hi = _percentile_ci(base_draws)
    baseline_point = float(y.mean())
    out["baseline"] = dict(point=round(baseline_point, 4), ci_low=round(lo, 4),
                           ci_high=round(hi, 4), se=round(float(base_draws.std(ddof=1)), 5))
    for b in budgets:
        lo, hi = _percentile_ci(draws[b])
        key = str(int(round(b * 100)))
        out[key] = dict(budget=round(b, 4),
                        point=round(PO.precision_at(y, full, b)["precision"], 4),
                        ci_low=round(lo, 4), ci_high=round(hi, 4),
                        se=round(float(draws[b].std(ddof=1)), 5))
    return out


def headline_ci(block: dict, budget: float) -> dict:
    """The "N → M per 100 calls" sentence, with the bootstrap's own interval.

    Both ends are rounded the way the sentence rounds them, so the interval
    describes the number a reader actually sees rather than one behind it.
    """
    from .metrics import headline, headline_range

    key = str(int(round(budget * 100)))
    base, prec = block["baseline"], block[key]
    return dict(
        baseline_per_100=round(base["point"] * 100),
        baseline_per_100_ci=[round(base["ci_low"] * 100), round(base["ci_high"] * 100)],
        model_per_100=round(prec["point"] * 100),
        model_per_100_ci=[round(prec["ci_low"] * 100), round(prec["ci_high"] * 100)],
        # Both sentences come from `model.metrics`, which is the one place allowed
        # to assemble them — `tests/test_model_pack.py` asserts there is only one.
        sentence=headline(base["point"], prec["point"]),
        interval_sentence=headline_range((base["ci_low"], base["ci_high"]),
                                         (prec["ci_low"], prec["ci_high"])),
    )


__all__ = ["N_RESAMPLES", "PREDICTIONS_DIR", "persist", "load", "precision_ci",
           "headline_ci"]
