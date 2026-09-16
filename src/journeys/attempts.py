"""Who applies, when, for what, through which channel — and what they say.

This module builds the attempt table *before* any funnel outcome is known.  It
decides five things, in this order, and nothing here may look at the outcome:

1. **Who applies.**  Every customer the book says converts applies (they have to
   — they disburse).  Non-converting applicants are drawn by weighted sampling
   without replacement, heavily favouring the book's hard-negative archetypes:
   a *near-miss* is a drop-off by definition, a *window shopper* browses and
   never buys, a *red herring* has a real financial run-up and no purchase.
2. **How many attempts.**  Converters may carry one earlier, abandoned attempt
   (they balked once and came back — this is the "recovery" population the
   8-10% baseline is measured on).  Non-converters may try two or three times;
   shoppers do it more.
3. **Which product, and in which month.**  Sampled *jointly* from the book's own
   latent intent tensor, weighted by eligibility, so an attempt lands where the
   customer's need actually was.  A small share is deliberately launched for a
   product the customer is ineligible for; those die at the Eligibility stage.
4. **Which channel.**
5. **What the customer tells the bank** — the four mentor-named window-shopper
   signals plus the amount asked for and the amount the bank can offer.

Every parameter is ``assumed``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from book.products import PRODUCTS

from . import CHANNELS, JourneyConfig
from .bookview import BookView
from . import shoppers as sh
from .shoppers import ShopperLatents, sigmoid

# --------------------------------------------------------------------------- #
# 1. who applies
# --------------------------------------------------------------------------- #

#: Relative propensity to *start* an application, by book archetype.  A plain
#: non-converter is 1.0.  These set the composition of the drop-off population,
#: which is the population the whole product is about.
APPLY_WEIGHT = {
    "plain": 1.0,
    "dormant_rich": 0.45,     # capacity, no intent — rarely even starts
    "red_herring": 3.0,       # real financial event, no purchase
    "window_shopper": 6.0,    # browses hard; starting a form is free
    "near_miss": 12.0,        # the full run-up, then life happens
}
#: Extra weight per unit of peak latent intent.
APPLY_INTENT_GAIN = 2.6

# --------------------------------------------------------------------------- #
# 2. how many attempts
# --------------------------------------------------------------------------- #

#: Converters: probability of one earlier, abandoned attempt.  Scaled at runtime
#: so the realised recovery rate hits ``cfg.target_recovery_rate``; the shape
#: (shoppers and fee-sensitive customers balk first and come back) is fixed here.
PRIOR_ATTEMPT_TILT = 1.35        # multiplier per unit of shopper tilt
PRIOR_ATTEMPT_FEE_TILT = 0.55    # multiplier per unit of centred fee sensitivity
#: Non-converters: probability of a second and a third attempt.
SECOND_ATTEMPT_BASE = 0.085
SECOND_ATTEMPT_SHOPPER = 0.16
THIRD_ATTEMPT_BASE = 0.020
THIRD_ATTEMPT_SHOPPER = 0.070
#: Minimum whole months between two attempts by the same customer.  A per-stage
#: timeout can run to 45 days, so two months of separation keeps the overlap
#: clamp in :mod:`journeys.funnel` a rare correction rather than the norm.
MIN_MONTHS_BETWEEN_ATTEMPTS = 2

# --------------------------------------------------------------------------- #
# 3. product and month
# --------------------------------------------------------------------------- #

#: How sharply the joint (product, month) draw concentrates on high intent.
INTENT_SHARPNESS = 2.5
#: Floor so a customer with no modelled intent can still apply for something.
INTENT_FLOOR = 0.004
#: Probability a converter's earlier abandoned attempt was for the *same*
#: product they eventually take.  The rest shopped around first.
PRIOR_SAME_PRODUCT_P = 0.75

# --------------------------------------------------------------------------- #
# 4. channel
# --------------------------------------------------------------------------- #

#: Channel mix by segment (rows: salaried / self-employed / gig), columns in
#: :data:`journeys.CHANNELS` order.
CHANNEL_MIX = {
    "salaried":      (0.16, 0.18, 0.34, 0.22, 0.10),
    "self-employed": (0.24, 0.18, 0.22, 0.16, 0.20),
    "gig":           (0.14, 0.12, 0.40, 0.18, 0.16),
}
#: Multiplicative tilt by city tier — tier-3 walks into a branch, tier-1 taps.
CHANNEL_TIER_TILT = {
    1: (0.80, 1.00, 1.25, 1.15, 0.90),
    2: (1.00, 1.00, 1.00, 1.00, 1.00),
    3: (1.45, 1.05, 0.65, 0.70, 1.20),
}
#: Channel is an *outcome* of commitment, not an exogenous assignment: a customer
#: who means it walks into a branch or takes the RM's call, a tyre-kicker taps the
#: app at midnight.  Log-tilt on one noisy reading of the commitment latent.  This
#: is the (confounded, deliberately) reason the by-channel cut the validation lane
#: pre-registered has anything in it.
CHANNEL_COMMITMENT = {"branch-walk-in": 0.35, "rm-call": 0.30, "app": -0.10,
                      "web": -0.25, "dsa": -0.20}

#: Probability an RM *reaches* an attempt that did not arrive through ``rm-call``.
RM_TOUCH_P = {"branch-walk-in": 0.30, "rm-call": 1.0, "app": 0.18, "web": 0.16, "dsa": 0.25}
#: ...reduced by window-shopper non-response, the fifth mentor-named symptom: the
#: RM rings, the tyre-kicker does not pick up.  An ``rm-call`` application is
#: exempt by definition — that one started *because* the customer answered.
RM_NONRESPONSE_SHOPPER = 0.55

# --------------------------------------------------------------------------- #
# 5. what the customer says, and what the bank can offer
# --------------------------------------------------------------------------- #

#: Blank / vague answers on the application form.  Base Beta(2, 9) has mean 0.18.
BLANK_BETA = (1.9, 5.8)
BLANK_SHOPPER_GAIN = 0.20
#: ...and one noisy reading of the customer's commitment (see shoppers.py).
BLANK_COMMITMENT = -0.040
BLANK_CHANNEL = {"branch-walk-in": -0.06, "rm-call": -0.04, "app": 0.03, "web": 0.06, "dsa": 0.01}
BLANK_CAP = 0.92

#: Willingness to state an income at all.
INCOME_SHARE_BASE = 1.75
INCOME_SHARE_SHOPPER = -2.00
INCOME_SHARE_BLANK = -0.70
INCOME_SHARE_COMMITMENT = 0.75
INCOME_SHARE_CHANNEL = {"branch-walk-in": 0.35, "rm-call": 0.25, "app": 0.0, "web": -0.20, "dsa": -0.10}

#: Stated income vs the book's true income.  Self-employed and gig customers
#: round up; shoppers inflate hardest because nothing is being verified yet.
STATED_INCOME_SD = 0.12
STATED_INCOME_BASE = 0.015
STATED_INCOME_SELF_EMPLOYED = 0.10
STATED_INCOME_GIG = 0.15
STATED_INCOME_SHOPPER = 0.13

#: Documents the bank asks for, by product.
DOCS_BASE = {"home": 8, "lap": 8, "education": 6, "auto": 5, "personal": 4, "gold": 3}
#: **Stated** document refusal — "I'm not giving you my ITR" — recorded when the
#: checklist is read out at the Eligibility conversation, which is why it is
#: observable long before the Docs stage.  See DATA_CARD §11.7.
DOC_REFUSE_BASE = -1.25
DOC_REFUSE_SHOPPER = 1.60
DOC_REFUSE_RELUCTANCE = 2.60
DOC_REFUSE_COMMITMENT = -0.85
DOC_REFUSE_CHANNEL = {"branch-walk-in": -0.35, "rm-call": -0.15, "app": 0.10, "web": 0.20, "dsa": 0.05}
#: ...and the measured consequence: how much of the checklist actually arrives.
DOC_SUPPLY_BASE = 1.85
DOC_SUPPLY_REFUSAL = -2.10
DOC_SUPPLY_SHOPPER = -1.20
DOC_SUPPLY_RELUCTANCE = -1.00
DOC_SUPPLY_CHANNEL = {"branch-walk-in": 0.45, "rm-call": 0.20, "app": -0.05, "web": -0.15, "dsa": 0.10}

#: The Rs 1,000 processing fee, and who balks at it.  Mentor-named, flat across
#: products (a real schedule of charges varies; see DATA_CARD §11.8).  The fee is
#: *quoted* at the Eligibility conversation and *paid* four stages later, so the
#: balk is on the bank's screen well before the payment is due.
FEE_AMOUNT = 1_000
FEE_BALK_BASE = -0.85
FEE_BALK_SHOPPER = 1.60
FEE_BALK_SENSITIVITY = 2.30
FEE_BALK_BURDEN = 0.55
FEE_BALK_COMMITMENT = -0.85

#: Ticket size as a multiple of monthly income, before the bank's underwriting.
REQUEST_MULT = {"home": 58.0, "lap": 34.0, "auto": 11.0, "education": 14.0,
                "gold": 3.5, "personal": 6.5}
REQUEST_SD = 0.35
REQUEST_BOUNDS = {
    "home": (500_000, 15_000_000), "lap": (300_000, 10_000_000),
    "auto": (150_000, 2_500_000), "education": (100_000, 4_000_000),
    "gold": (20_000, 1_500_000), "personal": (50_000, 2_000_000),
}
#: EMI per Rs 1 lakh borrowed, at indicative retail tenors and rates.
#: ``assumed``; SM-5 replaces this with API 433 rates + API 473 schedules.
EMI_PER_LAKH = {"home": 870.0, "lap": 1_000.0, "auto": 2_075.0,
                "education": 1_200.0, "gold": 4_500.0, "personal": 2_540.0}
#: Share of measured monthly headroom the bank will commit to a new EMI.
CAPACITY_TO_EMI = 0.55
#: Underwriting haircut applied on top of the capacity cap.
HAIRCUT_BETA = (1.5, 12.0)
OFFER_FLOOR_FRAC = 0.25

#: Browsing in the 30 days before the attempt starts, read off the *previous*
#: panel month so it is strictly prior to ``started_at``.
REVISIT_BASE = 0.6
REVISIT_DWELL_GAIN = 0.05
REVISIT_SHOPPER_GAIN = 5.0
REVISIT_CAP = 25
VIEWED_DWELL_MIN = 0.5
VIEWED_SHOPPER_GAIN = 3.2


@dataclass
class Attempts:
    """The attempt table before the funnel runs.  Every array is ``(A,)``."""

    cust_row: np.ndarray          # index into the book
    slot: np.ndarray              # 0-based order within the customer
    n_attempts: np.ndarray        # that customer's total attempt count
    designated_disburse: np.ndarray   # the book says this attempt disburses
    product_idx: np.ndarray
    channel_idx: np.ndarray
    ref_month: np.ndarray         # panel month the attempt is launched in
    ineligible: np.ndarray        # launched for a product the customer cannot take

    # signals, filled by :func:`build_signals`
    blank_ratio: np.ndarray | None = None
    income_shared: np.ndarray | None = None
    stated_income_ratio: np.ndarray | None = None
    docs_requested: np.ndarray | None = None
    docs_supplied_first: np.ndarray | None = None
    doc_shortfall: np.ndarray | None = None
    doc_refusal: np.ndarray | None = None
    fee_balk: np.ndarray | None = None
    amount_requested: np.ndarray | None = None
    amount_offered: np.ndarray | None = None
    offer_shortfall: np.ndarray | None = None
    revisits_30d: np.ndarray | None = None
    products_viewed_30d: np.ndarray | None = None
    rm_contacted: np.ndarray | None = None
    intent_at_start: np.ndarray | None = None
    capacity_at_start: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.cust_row)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _sample_rows(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    """Vectorised categorical sampling with a different weight row per item."""
    c = np.cumsum(weights, axis=1)
    u = rng.random(len(weights)) * c[:, -1]
    return (c < u[:, None]).sum(axis=1).clip(0, weights.shape[1] - 1)


def _gumbel_top_k(rng: np.random.Generator, weight: np.ndarray, k: int) -> np.ndarray:
    """Indices of ``k`` items drawn without replacement with probability
    proportional to ``weight`` (the Gumbel top-k trick)."""
    if k <= 0:
        return np.empty(0, dtype=np.int64)
    key = np.log(np.maximum(weight, 1e-12)) + rng.gumbel(size=len(weight))
    return np.argpartition(-key, k - 1)[:k]


def _channel_weights(view: BookView) -> np.ndarray:
    """``(N, C)`` channel probabilities per customer."""
    seg = view.book["segment"].to_numpy(dtype=object)
    tier = view.book["city_tier"].to_numpy()
    base = np.array([CHANNEL_MIX[s] for s in ("salaried", "self-employed", "gig")])
    seg_idx = np.select([seg == "salaried", seg == "self-employed"], [0, 1], default=2)
    tilt = np.array([CHANNEL_TIER_TILT[t] for t in (1, 2, 3)])
    w = base[seg_idx] * tilt[np.clip(tier, 1, 3) - 1]
    return w / w.sum(axis=1, keepdims=True)


# --------------------------------------------------------------------------- #
# 1-2. applicant selection and attempt slots
# --------------------------------------------------------------------------- #

def select(cfg: JourneyConfig, view: BookView, lat: ShopperLatents,
           rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(cust_row, slot, n_attempts)`` for every attempt, unordered.

    The converter's **last** slot is the attempt that disburses; everything else
    abandons.
    """
    n = view.n
    conv = view.is_converter
    b = view.book

    target_customers = int(round(cfg.target_attempt_share * n))
    n_conv = int(conv.sum())
    n_extra = target_customers - n_conv
    if n_extra <= 0:
        raise ValueError(
            f"the book already converts {n_conv / n:.1%} of customers, which is above the "
            f"{cfg.target_attempt_share:.0%} attempt-share target; raise target_attempt_share")

    peak_intent = view.intent.max(axis=(1, 2)).astype(np.float64)
    w = np.full(n, APPLY_WEIGHT["plain"])
    w = np.where(b["dormant_rich"].to_numpy() == 1, APPLY_WEIGHT["dormant_rich"], w)
    w = np.where(b["red_herring"].to_numpy() == 1, APPLY_WEIGHT["red_herring"], w)
    w = np.where(b["window_shopper"].to_numpy() == 1, APPLY_WEIGHT["window_shopper"], w)
    w = np.where(b["near_miss"].to_numpy() == 1, APPLY_WEIGHT["near_miss"], w)
    w = w * (1.0 + APPLY_INTENT_GAIN * peak_intent)
    w = np.where(conv, 0.0, w)                      # converters are already in

    extra = _gumbel_top_k(rng, w, n_extra)
    applicant = conv.copy()
    applicant[extra] = True

    # ---- attempt counts ---------------------------------------------------- #
    n_att = np.zeros(n, dtype=np.int64)

    # converters: one final attempt, plus (solved share) one earlier abandoned one
    fee_c = b["fee_sensitivity"].to_numpy(dtype=np.float64) - 0.42
    prior_shape = np.clip(1.0 + PRIOR_ATTEMPT_TILT * lat.tilt + PRIOR_ATTEMPT_FEE_TILT * fee_c,
                          0.05, None)
    prior_shape = np.where(conv, prior_shape, 0.0)

    # Solve the scale so the realised recovery rate hits the target.  A "drop-off"
    # is a customer with at least one abandoned attempt, so the denominator is
    # (non-converting applicants) + (converters carrying a prior attempt):
    #     recovery = S / (n_extra + S)  ->  S = target * n_extra / (1 - target)
    tgt = cfg.target_recovery_rate
    wanted = tgt * n_extra / (1.0 - tgt)
    scale = wanted / max(prior_shape.sum(), 1e-9)
    prior_p = np.clip(prior_shape * scale, 0.0, 0.95)
    has_prior = conv & (rng.random(n) < prior_p)
    n_att[conv] = 1
    n_att[has_prior] += 1

    # non-converting applicants: one attempt, sometimes two, rarely three
    nc = applicant & ~conv
    p2 = SECOND_ATTEMPT_BASE + SECOND_ATTEMPT_SHOPPER * lat.tilt
    p3 = THIRD_ATTEMPT_BASE + THIRD_ATTEMPT_SHOPPER * lat.tilt
    second = nc & (rng.random(n) < p2)
    third = second & (rng.random(n) < p3)
    n_att[nc] = 1
    n_att[second] += 1
    n_att[third] += 1

    cust_row = np.repeat(np.arange(n), n_att)
    counts = n_att[cust_row]
    starts = np.repeat(np.cumsum(n_att) - n_att, n_att)
    slot = np.arange(len(cust_row)) - starts
    return cust_row, slot, counts


# --------------------------------------------------------------------------- #
# 3-4. product, month, channel
# --------------------------------------------------------------------------- #

def assign_product(cfg: JourneyConfig, view: BookView, cust_row: np.ndarray,
                   is_final: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Which product each attempt is for.

    Drawn from the customer's own latent intent, **marginalised over months** and
    weighted by eligibility, so nobody applies for a loan against a property they
    do not own — except the small ``ineligible_noise_share`` who do exactly that
    and die at the Eligibility stage, because real banks receive those too.

    The book owns the converter's product outright: the attempt that disburses is
    for the product the book says they take, and an earlier abandoned attempt is
    usually (``PRIOR_SAME_PRODUCT_P``) for the same one — they balked and came
    back — and otherwise for whatever else they were weighing up.
    """
    a = len(cust_row)
    first = cfg.first_attempt_month
    # candidate month m is weighted by the intent standing in month m-1: the need
    # builds, *then* the customer applies.  Read one month back, consistently
    # with :func:`build_month_signals`, which is also what keeps every journey
    # covariate strictly prior to ``started_at``.
    intent = view.intent[cust_row][:, :, first - 1: view.months - 1].astype(np.float64)
    w = ((np.maximum(intent, 0.0) + INTENT_FLOOR) ** INTENT_SHARPNESS).sum(axis=2)
    w *= view.eligibility[cust_row]
    prod = _sample_rows(rng, w)

    book_prod = view.product_idx[cust_row]
    is_conv = view.is_converter[cust_row]
    same = rng.random(a) < PRIOR_SAME_PRODUCT_P
    prod = np.where(is_final, book_prod, np.where(is_conv & same, book_prod, prod))

    elig = view.eligibility[cust_row]
    zero = elig <= 0.0
    can_be_wrong = zero.any(axis=1) & ~is_final
    pick_wrong = can_be_wrong & (rng.random(a) < cfg.ineligible_noise_share)
    prod = np.where(pick_wrong, _sample_rows(rng, np.where(zero, 1.0, 1e-12)), prod)
    ineligible = elig[np.arange(a), prod] <= 0.0
    return prod.astype(np.int64), ineligible


def assign_month(cfg: JourneyConfig, view: BookView, cust_row: np.ndarray, slot: np.ndarray,
                 n_attempts: np.ndarray, is_final: np.ndarray, product: np.ndarray,
                 final_start_month: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Which panel month each attempt is launched in.

    Drawn from the latent intent for *that product* over the months still
    available, so the application lands where the need actually was.  Three
    constraints narrow the window: an attempt must leave room for the ones that
    follow it, a converter's earlier attempt must finish before the pinned final
    one, and nothing may start before ``cfg.first_attempt_month`` (the 30-day
    browsing look-back needs a month of history in front of it).

    ``final_start_month`` is ``(N,)`` — the month the converter's final attempt
    begins, already read backwards from the book's ``event_month`` minus the drawn
    journey length; ``-1`` for customers who never convert.
    """
    a = len(cust_row)
    first, m_n = cfg.first_attempt_month, view.months
    w = (np.maximum(view.intent[cust_row, product][:, first - 1: m_n - 1].astype(np.float64), 0.0)
         + INTENT_FLOOR) ** INTENT_SHARPNESS

    slots_after = n_attempts - slot - 1
    latest = m_n - 1 - MIN_MONTHS_BETWEEN_ATTEMPTS * slots_after
    anchor = final_start_month[cust_row]
    latest = np.where(anchor >= 0, np.minimum(latest, anchor - MIN_MONTHS_BETWEEN_ATTEMPTS), latest)
    latest = np.maximum(latest, first)

    allowed = np.arange(first, m_n)[None, :] <= latest[:, None]
    w = np.where(allowed, w, 0.0)
    dead = w.sum(axis=1) <= 0
    if dead.any():
        w[dead] = allowed[dead].astype(np.float64)
    month = _sample_rows(rng, w) + first
    return np.where(is_final, anchor, month).astype(np.int64)


def assign_channel(view: BookView, cust_row: np.ndarray, lat: ShopperLatents,
                   rng: np.random.Generator) -> np.ndarray:
    """One channel per attempt: the customer's segment/tier mix, tilted by how
    committed they are (see :data:`CHANNEL_COMMITMENT`)."""
    w = _channel_weights(view)[cust_row]
    w = w * np.exp(np.asarray([CHANNEL_COMMITMENT[c] for c in CHANNELS])[None, :]
                   * sh.read_commitment(lat, cust_row, rng)[:, None])
    return _sample_rows(rng, w)


# --------------------------------------------------------------------------- #
# 5. what the customer says, and what the bank offers
# --------------------------------------------------------------------------- #

def build_stall_signals(view: BookView, att: Attempts, lat: ShopperLatents,
                        rng: np.random.Generator) -> Attempts:
    """The two signals that change how long a journey *takes*: document refusal
    and the Rs 1,000 fee balk.

    Drawn before the calendar, because a converter's start date is read backwards
    from the book's disbursement month and therefore needs the journey length —
    which depends on whether the customer stalled.  Neither signal depends on the
    month, so the ordering is honest rather than convenient.

    Both are drawn for **every** attempt but only *emitted* for attempts that
    actually reached the stage: a customer who never got to the fee page cannot
    have balked at it.
    """
    a = len(att)
    row, prod, ch = att.cust_row, att.product_idx, att.channel_idx
    b = view.book
    sp = lat.propensity[row]

    def by_channel(table: dict[str, float]) -> np.ndarray:
        return np.array([table[c] for c in CHANNELS])[ch]

    docs_req = np.array([DOCS_BASE[p] for p in PRODUCTS])[prod] + rng.integers(0, 3, a)
    doc_rel = b["doc_reluctance"].to_numpy(dtype=np.float64)[row]
    doc_refusal = rng.random(a) < sigmoid(DOC_REFUSE_BASE + DOC_REFUSE_SHOPPER * sp
                                          + DOC_REFUSE_RELUCTANCE * (doc_rel - 0.33)
                                          + DOC_REFUSE_COMMITMENT * sh.read_commitment(lat, row, rng)
                                          + by_channel(DOC_REFUSE_CHANNEL))
    p_supply = sigmoid(DOC_SUPPLY_BASE + DOC_SUPPLY_REFUSAL * doc_refusal
                       + DOC_SUPPLY_SHOPPER * sp
                       + DOC_SUPPLY_RELUCTANCE * (doc_rel - 0.33)
                       + by_channel(DOC_SUPPLY_CHANNEL))
    docs_first = rng.binomial(docs_req, p_supply)

    income = b["true_income"].to_numpy(dtype=np.float64)[row]
    fee_sens = b["fee_sensitivity"].to_numpy(dtype=np.float64)[row]
    burden = np.log1p(FEE_AMOUNT / np.maximum(income, 1.0))
    burden = (burden - burden.mean()) / max(burden.std(), 1e-9)
    balk = rng.random(a) < sigmoid(FEE_BALK_BASE + FEE_BALK_SHOPPER * sp
                                   + FEE_BALK_SENSITIVITY * (fee_sens - 0.42)
                                   + FEE_BALK_COMMITMENT * sh.read_commitment(lat, row, rng)
                                   + FEE_BALK_BURDEN * burden)

    att.docs_requested = docs_req.astype(np.int64)
    att.docs_supplied_first = docs_first.astype(np.int64)
    att.doc_shortfall = docs_first < docs_req
    att.doc_refusal = doc_refusal
    att.fee_balk = balk
    return att


def build_month_signals(view: BookView, att: Attempts, lat: ShopperLatents,
                        rng: np.random.Generator) -> Attempts:
    """Everything the bank learns once the application is actually open: the
    vague answers, the refusal to state an income, the ask, the offer
    underwriting can support, and the browsing that preceded it all."""
    a = len(att)
    row, prod, ch, m = att.cust_row, att.product_idx, att.channel_idx, att.ref_month
    b = view.book
    sp = lat.propensity[row]

    def by_channel(table: dict[str, float]) -> np.ndarray:
        return np.array([table[c] for c in CHANNELS])[ch]

    # ---- signal 1: vague / blank answers ----------------------------------- #
    blank = np.clip(rng.beta(*BLANK_BETA, a) + BLANK_SHOPPER_GAIN * sp
                    + BLANK_COMMITMENT * sh.read_commitment(lat, row, rng)
                    + by_channel(BLANK_CHANNEL), 0.0, BLANK_CAP)

    # ---- signal 2: refusal to share income --------------------------------- #
    share_logit = (INCOME_SHARE_BASE + INCOME_SHARE_SHOPPER * sp
                   + INCOME_SHARE_COMMITMENT * sh.read_commitment(lat, row, rng)
                   + INCOME_SHARE_BLANK * (blank - 0.20) + by_channel(INCOME_SHARE_CHANNEL))
    income_shared = rng.random(a) < sigmoid(share_logit)

    seg = b["segment"].to_numpy(dtype=object)[row]
    mu = (STATED_INCOME_BASE
          + STATED_INCOME_SELF_EMPLOYED * (seg == "self-employed")
          + STATED_INCOME_GIG * (seg == "gig")
          + STATED_INCOME_SHOPPER * sp)
    stated_ratio = np.where(income_shared, np.exp(rng.normal(mu, STATED_INCOME_SD, a)), np.nan)

    # ---- the ask, and what underwriting can actually offer ----------------- #
    income = b["true_income"].to_numpy(dtype=np.float64)[row]
    mult = np.array([REQUEST_MULT[p] for p in PRODUCTS])[prod]
    req = mult * income * np.exp(rng.normal(0.0, REQUEST_SD, a))
    lo = np.array([REQUEST_BOUNDS[p][0] for p in PRODUCTS])[prod]
    hi = np.array([REQUEST_BOUNDS[p][1] for p in PRODUCTS])[prod]
    req = np.round(np.clip(req, lo, hi), -4)

    prev0 = np.maximum(m - 1, 0)
    cap_abs = view.capacity_abs[row, prev0].astype(np.float64)
    per_lakh = np.array([EMI_PER_LAKH[p] for p in PRODUCTS])[prod]
    max_loan = np.maximum(CAPACITY_TO_EMI * cap_abs, 0.0) / per_lakh * 1e5
    offered = np.minimum(req, max_loan) * (1.0 - rng.beta(*HAIRCUT_BETA, a))
    offered = np.round(np.clip(offered, OFFER_FLOOR_FRAC * req, req), -4)
    shortfall = np.clip(1.0 - offered / np.maximum(req, 1.0), 0.0, 1.0)

    # ---- everything below is read from the month BEFORE the attempt -------- #
    # that month is entirely prior to ``started_at``, which is what makes intent,
    # capacity and browsing usable without any look-ahead.
    prev = np.maximum(m - 1, 0)
    dwell_prev = view.dwell[row, :, prev].astype(np.float64)
    total_dwell = dwell_prev.sum(axis=1)
    n_viewed = (dwell_prev > VIEWED_DWELL_MIN).sum(axis=1)
    revisits = np.minimum(rng.poisson(REVISIT_BASE + REVISIT_DWELL_GAIN * total_dwell
                                      + REVISIT_SHOPPER_GAIN * sp), REVISIT_CAP)
    viewed = np.clip(n_viewed + rng.poisson(VIEWED_SHOPPER_GAIN * sp), 1, view.n_products)

    att.blank_ratio = blank
    att.income_shared = income_shared
    att.stated_income_ratio = stated_ratio
    att.amount_requested = req
    att.amount_offered = offered
    att.offer_shortfall = shortfall
    att.revisits_30d = revisits.astype(np.int64)
    att.products_viewed_30d = viewed.astype(np.int64)
    is_rm_call = ch == CHANNELS.index("rm-call")
    p_reach = np.array([RM_TOUCH_P[c] for c in CHANNELS])[ch] * (1.0 - RM_NONRESPONSE_SHOPPER * sp)
    att.rm_contacted = is_rm_call | (rng.random(a) < p_reach)
    att.intent_at_start = view.intent[row, prod, prev].astype(np.float64)
    att.capacity_at_start = view.capacity_ratio[row, prev].astype(np.float64)
    return att
