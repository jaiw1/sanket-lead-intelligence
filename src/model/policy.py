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

What does **not** live in that chain is the ``hot``/``warm``/``cold`` tier.  A
tier is a band on the probability (:data:`TIER_HOT`, :data:`TIER_WARM`), so a
customer carries one whether or not the bank may call them and whether or not
the truncation reached them — see :func:`tier_of`.  It was briefly defined as
"inside the delivered queue", which is why every lead on the queue screen came
out hot; the note on the constants says what that cost.

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

#: The tier bands, as ABSOLUTE probabilities on the score the queue ranks by.
#:
#: A tier is a claim about one customer — "better than a 3-in-10 chance of
#: disbursing inside the window" — not a restatement of where the truncation
#: fell.  For one day (2026-09-21) they were cut at the contact budget on the
#: queue's own ranking, which made ``hot`` a synonym for *inside the delivered
#: queue*: the cockpit exports the first 320 rows and the 10% budget buys 553,
#: so all 320 came out ``hot``, the 24 suppressed rows came out ``cold``, and
#: nothing was ever ``warm``.  A label implied by the list it labels carries no
#: information, so the bands are fixed numbers again — set once, here, and read
#: from here by the packer, the evaluator and anything that reports a tier.
#:
#: Why these two numbers.  Before 2026-09-21 the bands were percentile cuts on
#: the eligible pool (top 10% ``hot``, top 25% ``warm``) while the queue was
#: ordered on a different score, so the delivered 320 split 147 / 151 / 22.
#: Percentiles cannot survive the unification: the queue is now the top 5.8% of
#: the same score the bands would cut, so any pool percentile at or above 5.8%
#: swallows the whole queue.  The replacement is absolute and is chosen to put
#: a comparable spread back across the delivered list:
#:
#:   * ``hot`` starts just above the measured precision at the 10% contact
#:     budget (0.2906 on the packed seed) — a hot lead is one whose own
#:     calibrated probability beats the average of the list it sits in;
#:   * ``warm`` starts at a one-in-five chance, near the precision the 20%
#:     budget delivers (0.2301).
#:
#: MODEL_CARD.md §8 carries the same derivation and the counts they produce.
TIER_HOT = 0.30
TIER_WARM = 0.20
#: Best band first; ``cold`` is everything below ``TIER_WARM``.
TIERS = ("hot", "warm", "cold")


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


def tier_of(p) -> np.ndarray:
    """``hot`` / ``warm`` / ``cold`` for an array of probabilities, nothing else.

    Suppression is deliberately not an argument.  A suppressed customer still
    has a probability and still falls in a band; whether the bank is allowed to
    call them is a *different* fact, and the export carries it separately
    (``suppressed`` plus the reason).  Collapsing the two is what produced a
    queue screen on which every deliverable lead was ``hot`` and every
    suppressed one ``cold``.
    """
    p = np.asarray(p, dtype=float)
    return np.where(p >= TIER_HOT, "hot",
                    np.where(p >= TIER_WARM, "warm", "cold")).astype(object)


def tiers(scores: PolicyScores) -> np.ndarray:
    """Bands over the **whole** pool, cut on the score the queue ranks by.

    Row-aligned with the pool that was scored, suppressed rows included.  The
    delivered queue is the top of this same score, so it carries whichever
    bands its rows fall in — usually all three.
    """
    if scores.ranking != RANKING_PROBABILITY:
        raise ValueError(
            f"the tier thresholds are registered against {RANKING_PROBABILITY!r}; "
            f"they are probabilities and mean nothing on a {scores.ranking!r} score")
    return tier_of(scores.rank_score)


def tier_counts(tier: np.ndarray, mask: np.ndarray | None = None) -> dict:
    """``{hot, warm, cold}`` over a tier array, optionally over a subset of it."""
    t = np.asarray(tier, dtype=object)
    if mask is not None:
        t = t[np.asarray(mask).astype(bool)]
    return {name: int((t == name).sum()) for name in TIERS}


#: Half-width of the window :func:`tier_plateau_sensitivity` counts leads in,
#: on either side of each cut.  0.005 is half a percentage point of calibrated
#: probability — smaller than the gap between any two numbers a reviewer would
#: call "the same result", and far smaller than the 2.9-point width of the
#: headline's own confidence interval.
PLATEAU_WINDOW = 0.005


def _nearest_plateau(ordered: list[dict], cut: float) -> dict | None:
    """The first plateau of an already-cut-ordered list, with its distance."""
    if not ordered:
        return None
    first = ordered[0]
    return dict(value=first["value"], distance=round(abs(first["value"] - cut), 6),
                n=first["n"])


def tier_plateau_sensitivity(p, window: float = PLATEAU_WINDOW) -> dict:
    """How many delivered leads one hair's-breadth of arithmetic would re-tier.

    **Reported, never gated.**  Isotonic calibration is a step function: it maps
    whole runs of raw scores onto a single fitted value, so the delivered queue
    does not sit on 320 distinct probabilities — it sits on a couple of dozen
    *plateaus* of 15 to 60 leads each, every lead on a plateau carrying exactly
    the same number.  A tier cut is a horizontal line through that staircase.
    It therefore either misses a plateau entirely or moves the whole plateau at
    once, and "how close is the nearest plateau to a cut" is a completely
    different question from "how much would precision move", which is the
    quantity every pre-registered band is about.

    Returns, per cut:

    ``within``        leads whose probability is within ``window`` of the cut —
                      the ones a rounding difference could re-tier.
    ``nearest_above`` / ``nearest_below``
                      the closest plateau on each side, as
                      ``{value, distance, n}``.  A cut can read ``within: 0``
                      and still be one plateau away from moving twenty leads,
                      which is the case this exhibit exists to make visible, so
                      the distance is reported beside the count rather than
                      left to be inferred from a zero.

    ``leads`` is the count the ``within`` numbers are out of, and ``plateaus``
    is the whole staircase — value and size, richest first.
    """
    p = np.asarray(p, dtype=float)
    p = p[np.isfinite(p)]
    values, sizes = np.unique(np.round(p, 9), return_counts=True)
    plateaus = [dict(value=round(float(v), 6), n=int(c))
                for v, c in sorted(zip(values, sizes), key=lambda vc: -vc[0])]

    cuts: dict[str, dict] = {}
    for name, cut in (("hot", TIER_HOT), ("warm", TIER_WARM)):
        above = sorted((pl for pl in plateaus if pl["value"] >= cut), key=lambda pl: pl["value"])
        below = sorted((pl for pl in plateaus if pl["value"] < cut), key=lambda pl: -pl["value"])
        cuts[name] = dict(
            cut=round(float(cut), 6),
            within=int(((p >= cut - window) & (p <= cut + window)).sum()),
            nearest_above=_nearest_plateau(above, cut),
            nearest_below=_nearest_plateau(below, cut),
        )

    return dict(
        window=round(float(window), 6),
        leads=int(len(p)),
        distinct_probabilities=int(len(values)),
        largest_plateau=(plateaus and max(pl["n"] for pl in plateaus)) or 0,
        cuts=cuts,
        plateaus=plateaus,
        note="Reported, not gated. Isotonic calibration puts the delivered queue on a "
             "handful of plateaus, so a tier cut moves whole plateaus at once: a "
             f"difference too small to shift precision by half a point can still re-tier "
             f"every lead on a plateau. `cuts[*].within` counts leads inside +/-{window} of "
             "a cut; `nearest_above`/`nearest_below` give the distance to the next plateau "
             "on each side, because a count of zero does not mean the cut is safe.",
    )


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
    "TIER_HOT", "TIER_WARM", "TIERS", "tier_of", "tier_counts",
    "PLATEAU_WINDOW", "tier_plateau_sensitivity",
    "any_product_probability", "product_choice", "capacity_score",
    "intent_percentile", "score_pool",
    "rank_order", "budget_k", "select", "tiers", "precision_at",
]
