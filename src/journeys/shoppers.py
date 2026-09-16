"""SD-S3 — the window shopper as a *causal negative*, not a label.

The mentors described the window shopper behaviourally: vague answers, refusal
to share details, balking at the Rs 1,000 processing fee, refusing documents,
revisiting several products without committing.  Those are five symptoms of one
underlying disposition, so that is how they are generated here: a single latent
``shopper_propensity`` per customer that raises the probability of each symptom
**and** independently drags on every funnel gate.

Informative, not deterministic
------------------------------
This is the design rule the plan sets and the one that keeps the validation band
(SK-05, ``shopper AUC >= 0.70`` — a deliberately modest floor) honest:

* a genuine buyer can balk at the fee once, sit on it for a week, and then pay;
* a shopper can, occasionally, disburse.  Nothing here forbids it.

Consistency with the book
-------------------------
The book already carries a ``window_shopper`` archetype (9% of non-converters:
heavy dwell, no financial movement, never buys).  ``shopper_propensity`` loads
heavily on it, so the two never contradict each other — the journey layer makes
the archetype *behave* rather than replacing it.  It also loads **negatively on
``is_converter``**, which is what gives the four signals a genuine negative
marginal effect on disbursement in the generated data.

Deliberately absent: an occupation term
---------------------------------------
An explicit ``+ gig`` term in the shopper logit would manufacture the fairness
problem the model is then measured on (SK-23/SK-24).  There is none.  Gig
workers do end up marginally shoppier, but only through the book's own
``fee_sensitivity`` (which already carries ``+0.25 * gig``), and that inheritance
is written down in ``DATA_CARD.md`` §11.6 rather than hidden here.

Every coefficient below is ``assumed``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .bookview import BookView

# --------------------------------------------------------------------------- #
# parameters — all ``assumed``
# --------------------------------------------------------------------------- #

#: Loadings on the base-free shopper logit.
W_BOOK_WINDOW_SHOPPER = 4.30   # the book's own archetype: browses hard, never buys
W_NEAR_MISS = 0.90             # full textbook run-up, then no purchase
W_RED_HERRING = 0.40           # a real financial event, no purchase intent
W_CURIOSITY = 0.70
W_PRICE_SENSITIVITY = 0.35
W_DOC_RELUCTANCE = 0.18
W_CONVERTER = -1.60            # the term that makes the four signals negative
W_PEAK_INTENT = -1.10

#: Curiosity: breadth of product browsing, distinct from intent depth.
CURIOSITY_BETA = (2.0, 3.0)
CURIOSITY_BROWSES_BONUS = 0.20
CURIOSITY_WS_BONUS = 0.15

#: Commitment: how far along the road to actually borrowing this customer is.
#: One latent, read four times through four independent, noisy channels — the
#: blank form, the refusal to state an income, the fee balk and the document
#: refusal.  Each channel carries information the other three do not, which is
#: the whole reason a bank collects four signals instead of one, and the reason
#: each of the four survives as an independently negative predictor of
#: disbursement (mentor mandate; ``tests/test_journeys_shoppers.py``).
COMMITMENT_CONVERTER = 1.10
COMMITMENT_INTENT = 0.55
COMMITMENT_NOISE = 0.60
#: Per-channel measurement noise.  Without it the four signals are one signal.
COMMITMENT_CHANNEL_NOISE = 0.90

#: Return propensity: having abandoned, how likely the customer comes back at
#: all.  Genuine buyers return; shoppers move on.  This is the quantity the
#: contact effect theta (SD-S4) will multiply.
RETURN_BASE = 0.55
RETURN_SHOPPER_DRAG = -0.85
RETURN_INTENT_GAIN = 0.45

#: Search bracket for the solved intercept.
_BASE_BRACKET = (-12.0, 12.0)


@dataclass
class ShopperLatents:
    """All ``(N,)``.  Never a feature; :mod:`journeys.build` writes them to the
    journey truth file and nowhere else."""

    partial_logit: np.ndarray     # the logit without its solved intercept
    tilt: np.ndarray              # sigmoid(partial_logit) — base-free, acyclic
    commitment: np.ndarray        # how close this customer is to actually borrowing
    curiosity: np.ndarray
    price_sensitivity: np.ndarray
    return_propensity: np.ndarray
    base: float = 0.0             # solved in :func:`solve_base`
    propensity: np.ndarray | None = None
    truth: np.ndarray | None = None


def _z(x: np.ndarray) -> np.ndarray:
    sd = float(np.std(x))
    return (x - float(np.mean(x))) / (sd if sd > 1e-12 else 1.0)


def sigmoid(x: np.ndarray | float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float64)))


def build_latents(view: BookView, rng: np.random.Generator) -> ShopperLatents:
    """Draw curiosity and assemble the base-free shopper logit."""
    b = view.book
    n = view.n
    browses = b["browses"].to_numpy().astype(bool)
    ws = b["window_shopper"].to_numpy().astype(float)
    near_miss = b["near_miss"].to_numpy().astype(float)
    red_herring = b["red_herring"].to_numpy().astype(float)
    doc_rel = b["doc_reluctance"].to_numpy(dtype=np.float64)
    #: price sensitivity IS the book's ``fee_sensitivity`` latent — reused rather
    #: than re-invented, so the fee balk cannot contradict the book.
    price_sens = b["fee_sensitivity"].to_numpy(dtype=np.float64)

    curiosity = np.clip(
        rng.beta(*CURIOSITY_BETA, n)
        + CURIOSITY_BROWSES_BONUS * browses
        + CURIOSITY_WS_BONUS * ws, 0.0, 1.0)

    peak_intent = view.intent.max(axis=(1, 2)).astype(np.float64)

    partial = (W_BOOK_WINDOW_SHOPPER * ws
               + W_NEAR_MISS * near_miss
               + W_RED_HERRING * red_herring
               + W_CURIOSITY * _z(curiosity)
               + W_PRICE_SENSITIVITY * _z(price_sens)
               + W_DOC_RELUCTANCE * _z(doc_rel)
               + W_CONVERTER * view.is_converter.astype(float)
               + W_PEAK_INTENT * _z(peak_intent))

    commitment = (COMMITMENT_CONVERTER * view.is_converter.astype(float)
                  + COMMITMENT_INTENT * _z(peak_intent)
                  + rng.normal(0.0, COMMITMENT_NOISE, n))
    commitment = _z(commitment)

    tilt = sigmoid(partial)
    ret = np.clip(RETURN_BASE + RETURN_SHOPPER_DRAG * tilt
                  + RETURN_INTENT_GAIN * _z(peak_intent) * 0.25, 0.02, 0.95)

    return ShopperLatents(partial_logit=partial, tilt=tilt, commitment=commitment,
                          curiosity=curiosity, price_sensitivity=price_sens,
                          return_propensity=ret)


def read_commitment(lat: ShopperLatents, rows: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One noisy reading of :attr:`ShopperLatents.commitment`, per attempt.

    Called once per signal, so the four window-shopper signals each see the same
    underlying commitment through their own independent measurement error.
    """
    return lat.commitment[rows] + rng.normal(0.0, COMMITMENT_CHANNEL_NOISE, len(rows))


def solve_base(lat: ShopperLatents, abandoner_rows: np.ndarray, target: float) -> float:
    """Solve the intercept so ``mean(propensity)`` over abandoning *attempts*
    equals ``target``.

    ``abandoner_rows`` indexes customers, once per abandoned attempt, so a
    customer who abandons twice counts twice — the share the plan pre-registers
    ("~30% of drop-offs are shoppers") is read off attempts, which is also what
    ``tests/test_journeys_shoppers.py`` measures.
    """
    p = lat.partial_logit[abandoner_rows]
    lo, hi = _BASE_BRACKET
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if float(np.mean(sigmoid(p + mid))) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def realise(lat: ShopperLatents, base: float, rng: np.random.Generator) -> ShopperLatents:
    """Fix the intercept, form the propensity and draw ``shopper_truth``."""
    lat.base = float(base)
    lat.propensity = sigmoid(lat.partial_logit + base)
    lat.truth = rng.random(len(lat.propensity)) < lat.propensity
    return lat
