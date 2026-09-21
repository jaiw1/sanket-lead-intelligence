# -*- coding: utf-8 -*-
"""One calling policy, used by the evaluator and by the packer.

Why this module exists
----------------------
Until 2026-09-21 the two halves of the claim disagreed.  ``model.pack`` measured
precision@budget by ranking held-out rows on ``max(product probabilities)``,
while the queue an RM actually receives was ranked on
``0.65 x intent-percentile + 0.35 x capacity`` and then truncated.  The headline
therefore described a list nobody was ever handed.

Everything about *which rows get called, in what order* now lives here, once:

    suppression  ->  eligibility  ->  ranking  ->  truncation  ->  tie-break

:func:`score_pool` turns a scored pool into the policy's own quantities.
:func:`rank_order` puts the eligible rows in calling order.  :func:`select`
truncates.  The evaluator and the packer both call them, so the number that is
measured and the list that is delivered cannot drift apart again.

The default ranking
-------------------
:data:`DEFAULT_RANKING` is set by measurement, not by preference — see
``MODEL_CARD.md`` §8, "The delivered queue, and why it ranks on probability".
Both rankings are measured on the same held-out rows under the same budget every
run and both land in ``data/model_metrics.json`` -> ``metrics.ranking_comparison``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import PRODUCTS
from . import emi as EMI

#: Rank on the blend of intent percentile and repayment capacity.
RANKING_BLEND = "blend"
#: Rank on the calibrated probability of the best product alone.
RANKING_PROBABILITY = "probability"
RANKINGS = (RANKING_BLEND, RANKING_PROBABILITY)

#: The blend's weights.  One place, so a screen, the export and the evaluator
#: cannot quote three different mixes.
INTENT_WEIGHT = 0.65
CAPACITY_WEIGHT = 0.35

#: ``safe_emi / REFERENCE_EMI`` is clipped here before being scaled to [0, 1]:
#: twice the reference EMI of headroom is already "comfortably affordable" and
#: more headroom past that should not out-rank intent.
CAPACITY_CAP = 2.0

#: Which ranking the delivered queue uses.  Chosen on 2026-09-21 by the
#: pre-agreed rule: keep the blend if its held-out precision@10% is within
#: 2 percentage points of probability-only ranking, otherwise rank on
#: probability and keep capacity as a displayed secondary signal.
#:
#: Measured on the registered seeds 7-11: blend 21.92% (seed 7) / 20.52%
#: (5-seed mean) against probability 29.06% / 28.11%.  The blend costs **7.1
#: percentage points** of precision at the 10% budget — three and a half times
#: the tolerance — so the queue ranks on probability.  ``capacity`` and
#: ``blend`` are still computed and exported: an RM sees whether the customer
#: can afford the product, it just no longer decides who gets called.
DEFAULT_RANKING = RANKING_PROBABILITY


@dataclass(frozen=True)
class PolicyScores:
    """Everything the policy derives from one scored pool.

    Arrays are row-aligned with the pool that was passed in, *including* the
    suppressed rows — a suppressed row is scored and shown, never queued, so it
    keeps its position rather than being dropped on the floor.
    """

    cust_id: np.ndarray
    eligible: np.ndarray
    p_top: np.ndarray
    top_index: np.ndarray
    nbp: np.ndarray
    intent: np.ndarray
    capacity: np.ndarray
    blend: np.ndarray
    rank_score: np.ndarray
    ranking: str

    @property
    def n_eligible(self) -> int:
        return int(self.eligible.sum())


def any_product_probability(P: np.ndarray) -> np.ndarray:
    """P(this customer disburses *something* in window), for MUTUALLY EXCLUSIVE labels.

    The six product labels partition the disbursement outcome (``model.frame``):
    a row is at most one of them.  The union of mutually exclusive events is
    their **sum**, not ``1 - prod(1 - p)`` — that formula assumes independence,
    and until 2026-09-21 both ``evaluate_seed`` and ``build_queue`` used it.

    The clip at 1 is load-bearing, not cosmetic: the six isotonic calibrators
    are fitted independently, so nothing constrains their outputs to sum to at
    most one.  A sum above one is a coherence failure of the calibration, and
    ``MODEL_CARD.md`` §4 ("Any-product probability") says so rather than letting
    the clip hide it.
    """
    return np.minimum(1.0, np.asarray(P, dtype=float).sum(axis=1))


def product_choice(P: np.ndarray) -> np.ndarray:
    """Column index of the pitched product — stable argmax, ties to the lower index."""
    return np.argsort(-P, axis=1, kind="stable")[:, 0]


def capacity_score(safe_emi: np.ndarray, products: np.ndarray) -> np.ndarray:
    """Repayment headroom against the bank-rate reference EMI of the pitched product."""
    ref = np.array([EMI.REFERENCE_EMI[p] for p in products], dtype=float)
    return np.clip(np.asarray(safe_emi, dtype=float) / ref, 0.0, CAPACITY_CAP) / CAPACITY_CAP


def intent_percentile(p_top: np.ndarray, eligible: np.ndarray) -> np.ndarray:
    """Percentile rank of ``p_top`` **within the eligible pool**; 0 for the rest.

    The denominator is the pool the policy is actually choosing from.  Ranking a
    customer against rows the policy has already suppressed would make the blend
    depend on how many people the bank happened not to be allowed to call.
    """
    out = np.zeros(len(p_top), dtype=float)
    idx = np.flatnonzero(eligible)
    if len(idx):
        out[idx] = pd.Series(np.asarray(p_top, dtype=float)[idx]).rank(pct=True).to_numpy()
    return out


def score_pool(cust_id, safe_emi, P: np.ndarray, eligible: np.ndarray,
               ranking: str = DEFAULT_RANKING) -> PolicyScores:
    """Suppression and eligibility in, the policy's ranking quantities out."""
    if ranking not in RANKINGS:
        raise ValueError(f"unknown ranking {ranking!r}; expected one of {RANKINGS}")
    P = np.asarray(P, dtype=float)
    eligible = np.asarray(eligible).astype(bool)
    top_index = product_choice(P)
    p_top = P[np.arange(len(P)), top_index]
    nbp = np.array([PRODUCTS[int(i)] for i in top_index], dtype=object)
    cap = capacity_score(safe_emi, nbp)
    intent = intent_percentile(p_top, eligible)
    blend = INTENT_WEIGHT * intent + CAPACITY_WEIGHT * cap
    rank_score = blend if ranking == RANKING_BLEND else p_top
    return PolicyScores(
        cust_id=np.asarray(cust_id, dtype=str), eligible=eligible, p_top=p_top,
        top_index=top_index, nbp=nbp, intent=intent, capacity=cap, blend=blend,
        rank_score=np.asarray(rank_score, dtype=float), ranking=ranking,
    )


def rank_order(scores: PolicyScores) -> np.ndarray:
    """Positional indices of the **eligible** rows, best first.

    Ties break on ``cust_id`` ascending rather than on frame order, so the same
    pool ranks the same way whichever module built the frame.
    """
    idx = np.flatnonzero(scores.eligible)
    if not len(idx):
        return idx
    return idx[np.lexsort((scores.cust_id[idx], -scores.rank_score[idx]))]


def budget_k(n_eligible: int, budget: float) -> int:
    """How many calls a contact budget buys over an eligible pool of this size."""
    return max(1, int(round(int(n_eligible) * float(budget))))


def select(scores: PolicyScores, k: int | None = None,
           budget: float | None = None) -> np.ndarray:
    """The delivered list: ordered positional indices, truncated.

    Exactly one of ``k`` (an absolute queue size) or ``budget`` (a share of the
    eligible pool) must be given.
    """
    if (k is None) == (budget is None):
        raise ValueError("select() takes exactly one of k= or budget=")
    order = rank_order(scores)
    if budget is not None:
        k = budget_k(scores.n_eligible, budget)
    return order[: max(0, int(k))]


def tiers(scores: PolicyScores, budget: float, warm_budget: float = 0.25) -> np.ndarray:
    """``hot`` / ``warm`` / ``cold`` / ``held``, cut on the **queue's own ranking**.

    ``hot`` is therefore exactly the list the contact budget buys, not a second
    opinion computed from a different score.
    """
    out = np.full(len(scores.eligible), "held", dtype=object)
    order = rank_order(scores)
    if not len(order):
        return out
    n_e = scores.n_eligible
    hot = budget_k(n_e, budget)
    warm = budget_k(n_e, warm_budget)
    out[order] = "cold"
    out[order[:warm]] = "warm"
    out[order[:hot]] = "hot"
    return out


def precision_at(y: np.ndarray, scores: PolicyScores, budget: float) -> dict:
    """Precision among the rows the policy would actually call at this budget.

    The same shape ``model.metrics.precision_at`` returns, so a caller can swap
    one for the other — but the ``k`` rows counted here are the policy's, not a
    bare ``argsort`` of the probabilities.
    """
    from .metrics import wilson

    y = np.asarray(y).astype(int)
    sel = select(scores, budget=budget)
    k = max(1, len(sel))
    hits = int(y[sel].sum())
    lo, hi = wilson(hits, k)
    return dict(budget=round(float(budget), 4), k=int(k), hits=hits,
                precision=hits / k, ci_low=lo, ci_high=hi,
                ranking=scores.ranking, n_eligible=scores.n_eligible)


__all__ = [
    "RANKING_BLEND", "RANKING_PROBABILITY", "RANKINGS", "DEFAULT_RANKING",
    "INTENT_WEIGHT", "CAPACITY_WEIGHT", "CAPACITY_CAP", "PolicyScores",
    "any_product_probability", "product_choice", "capacity_score",
    "intent_percentile", "score_pool",
    "rank_order", "budget_k", "select", "tiers", "precision_at",
]
