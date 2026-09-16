"""SD-S4 — the drop-off population, the contact effect theta, and the labels.

What this table is
------------------
One row per **(customer, month)** of the *drop-off population*, per the
architect's ruling of 2026-09-16, recorded as the dated entry under
``amendments:`` at the foot of ``validation/criteria.yaml``:

    the scoring unit is a (customer, month) row for customers in the drop-off
    population — consented, contactable customers with at least one abandoned
    application attempt in the trailing 12 months and no disbursement in flight
    — and the label is disbursement of any product within that product's
    decision window after an RM contact.

The label is therefore a **potential outcome under contact**, ``Y(1)``: *if an
RM called this customer this month, would a disbursement follow inside the
product's window?*  Both pre-registered bands are statements about that
quantity — SK-01 contacts a uniformly random 10% of the population, SK-02
contacts the model's top 10% of the same population — so the generator has to
supply ``Y(1)`` for every row, or neither band is gradeable.  ``Y(0)`` (the
no-contact counterfactual) is emitted beside it as ``label_no_contact``, which
is what makes the uplift exhibit and the SK-25 baseline ladder possible.

How this stays tied to the observed world
-----------------------------------------
``journeys.csv`` is the **observed** world: almost nobody in it was called, and
the book's converters are the only customers who ever disburse.  ``labels.csv``
is the world *under an intervention*.  Three constructions keep them honest
about each other:

1. **Every observed recovery is a forced positive.**  A drop-off who really did
   come back, was really contacted, and really disbursed inside the window
   carries ``label_disbursed_in_window = 1`` at the month of that contact, for
   the product the book says they took (``realised_recovery = 1``).  If the
   realised disbursement missed its window it is a forced *negative* — an
   observed disbursement that the pre-registered label does not count, which is
   where ``window_respected`` gets its honest sub-100%.
2. **``Y(0)`` is calibrated to the observed recovery frequency.**
   :data:`SPONTANEOUS_RETURN` is solved so that the mean no-contact label rate
   equals the per-row rate at which drop-offs really did come back on their own
   in ``journeys.csv``.  The contact lift ``theta / SPONTANEOUS_RETURN`` is then
   a derived number, not an assumption.
3. **The latents are the same latents.**  ``return_propensity``, ``commitment``,
   the shopper tilt and the book's own intent and capacity tensors drive both
   layers, so "who is ready" never disagrees between them.

The two solved knobs
--------------------
``theta`` — the **contact effect**.  Contact multiplies the customer's
``return_propensity`` (the hook SD-S2 left): ``P(returns | contacted) =
clip(theta * return_propensity * fatigue, 0, 1)``.  Solved numerically so the
random-contact disbursement rate lands in **[0.08, 0.10]** (SK-01).

:data:`LABEL_SIGNAL_TO_NOISE` — **the one S/N knob**, and the only one.  It
governs how much latent structure survives into the label, against unit-variance
idiosyncratic noise, and it is applied to **every** latent channel::

    P(completes | returned) = sigmoid(LABEL_SIGNAL_TO_NOISE * signal_z + N(0, 1))
    return_propensity_eff   = mean * (return_propensity / mean) ** min(S/N, 1)

Both, not just the first.  A knob that scaled only the completion logit has a
floor it cannot go below: ``return_propensity`` is itself a latent, it is
correlated with the index (window shoppers neither return nor complete), and at
S/N = 0 ranking on the index alone still reached 35% precision — outside the
registered band, with the knob at the bottom of its bracket.  Shrinking the
return propensity toward its own mean by the same exponent closes that floor, so
the single number really does sweep the population from "unrankable" to
"perfectly separable".  Raising it makes the drop-off population more separable
and raises the precision any ranker can reach; lowering it buries the signal.  It is solved so
that an **oracle** ranker — one that sees ``signal_z`` itself, which no model
ever can — reaches a precision@10% of :data:`ORACLE_PRECISION_TARGET`.  That
figure is a *ceiling*: L7's model reads the latents only through noisy
observables and will land below it, which is why the target sits in the upper
half of the registered 25-35% band rather than at its midpoint.  Putting the
ceiling at 30% would make SK-02 unreachable by construction.

The frozen scorer (``src/score_and_pack.py``) is **not** used for this tuning.
It is a three-product, whole-book, 3-month-horizon model; it answers a different
question and would calibrate the knob against the wrong target.

Every parameter below is ``assumed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from book.products import DECISION_WINDOW_DAYS, PRODUCTS, SUBSTITUTION

from . import STAGES
from .bookview import BookView
from .campaigns import ContactState, contact_features_for_rows, reason_names, suppression_for_rows
from .shoppers import ShopperLatents, sigmoid

# --------------------------------------------------------------------------- #
# population
# --------------------------------------------------------------------------- #

#: How far back an abandonment stays a live lead.  The architect's ruling names
#: twelve months; a stale list is still a list.
DROPOFF_LOOKBACK_DAYS = 365.0
#: Earliest panel month a population row may exist.  Applications start at month
#: 6 (``JourneyConfig.first_attempt_month``), so nothing can have abandoned
#: before month 6 and the first contactable month is 7.
FIRST_LABEL_MONTH = 7

# --------------------------------------------------------------------------- #
# the latent index behind the label
# --------------------------------------------------------------------------- #

#: Weights on the standardised components of the latent index.  Commitment
#: dominates (it is what the four window-shopper signals measure), then how much
#: the customer actually wants something this month, then how far they got
#: before walking, then how fresh the drop-off is.
W_COMMITMENT = 1.00
W_INTENT = 0.70
W_CAPACITY = 0.35
W_STAGE = 0.45
W_RECENCY = 0.40
W_SHOPPER = -0.55

#: **THE SIGNAL-TO-NOISE KNOB.**  Solved by :func:`solve`; this is the starting
#: point of the search and the value recorded in ``journey_params.json``.
LABEL_SIGNAL_TO_NOISE = 1.0
#: Where the oracle ceiling is aimed.  Registered band (SK-02) is [0.25, 0.35];
#: see the module docstring for why the target sits above the midpoint.
ORACLE_PRECISION_TARGET = 0.32
#: The contact budget both pre-registered bands are priced at.
CONTACT_BUDGET = 0.10

#: Search brackets for the two numerical solves.
THETA_BRACKET = (0.005, 40.0)
SNR_BRACKET = (0.02, 8.0)
SOLVE_ITERS = 48

#: Target for the contact effect solve: the middle of the registered 8-10% band.
RANDOM_CONTACT_TARGET = 0.09

#: Multiplier on ``return_propensity`` in the **no-contact** arm.  Solved (not
#: assumed) so ``Y(0)`` reproduces the per-row rate at which drop-offs really
#: did come back on their own in ``journeys.csv``.
SPONTANEOUS_RETURN = 0.05

# --------------------------------------------------------------------------- #
# the clock from contact to disbursement
# --------------------------------------------------------------------------- #

#: Contact-to-disbursement lag as a fraction of the product's decision window,
#: shaped like the journey layer's own clock (DATA_CARD §11.5): a Gamma for the
#: ordinary path, plus a stall tail for the customer who has to find a document
#: or sits on the Rs 1,000 fee for a week.  The stall tail is the *only* reason
#: a completed return can miss its window, which is what SK-04 measures.
LAG_MEAN_FRAC = 0.44
LAG_SHAPE = 2.6
LAG_STALL_P = 0.050
LAG_STALL_FRAC = 0.85

#: How sharply the realised product concentrates on eligibility-weighted intent.
PRODUCT_SHARPNESS = 1.6
#: ...and how strongly it is anchored on the product they walked away from,
#: through SD-S1's cross-product substitution matrix.  Without this term a
#: customer who abandoned a home loan took an unrelated product 69% of the time,
#: which is not what the menu of four is for: the menu exists because a drop-off
#: takes the *neighbouring* product (gold <-> personal, home <-> lap), not a
#: random one.  Exponent 2 on the affinity leaves the diagonal at 1.0, the close
#: pairs near 0.5 and the distant ones below 0.05.
SUBSTITUTION_SHARPNESS = 2.0
#: Size of the menu the mentors asked for.
MENU_K = 4

LABEL_COLUMNS = [
    "cust_id", "month", "as_at",
    "in_dropoff_pool", "eligible_for_contact", "suppressed", "suppression_reason",
    "consent_marketing", "dnd",
    "dropoff_stage_reached", "dropoff_product", "dropoff_attempts", "days_since_abandon",
    "contacts_30d", "contacts_90d", "campaign_contacts_6m",
    "last_contact_days", "last_contact_date", "last_campaign_product",
    "contacted", "contacted_at", "contact_channel",
    "label_disbursed_in_window", "label_product", "window_days", "contact_window_days",
    "window_respected", "days_to_disbursement", "label_disbursed_at",
    "label_no_contact", "label_observed", "realised_recovery",
] + [f"label_product_{p}" for p in PRODUCTS]

TRUTH_COLUMNS = [
    "cust_id", "month", "latent_signal", "oracle_score",
    "oracle_menu_hit", "menu_hit_with_dropoff_anchor",
    "p_disburse_if_contacted", "p_disburse_no_contact", "returns_and_completes",
    "fatigue", "return_propensity", "shopper_truth", "commitment",
]


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

@dataclass
class Population:
    """The drop-off population, flat.  Every array is ``(R,)`` over rows."""

    cust_row: np.ndarray
    month: np.ndarray
    as_at_day: np.ndarray
    days_since_abandon: np.ndarray
    stage_idx: np.ndarray          # furthest stage of the most recent abandonment
    dropoff_product: np.ndarray    # product index of that abandonment
    dropoff_attempts: np.ndarray   # attempts visible at as_at
    suppressed: np.ndarray
    reason: np.ndarray
    contact: dict[str, np.ndarray] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.cust_row)


def _month_starts(view: BookView) -> np.ndarray:
    first = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    starts = pd.date_range(first, periods=view.months + 1, freq="MS")
    return (starts - first).days.to_numpy().astype(np.float64)


def build_population(view: BookView, journeys: pd.DataFrame, st: ContactState) -> Population:
    """Every ``(customer, month)`` with a live abandoned application behind it.

    Membership is decided **as at the first instant of the month** — the moment
    an RM would pick the list up — so nothing that happens inside the month can
    put a row into the population it is then scored in.
    """
    n, m = view.n, view.months
    edges = _month_starts(view)                       # (M + 1,)
    as_at = edges[:m]

    row_of = {c: i for i, c in enumerate(view.book["cust_id"].to_numpy(dtype=object))}
    j_row = journeys.customer_id.map(row_of).to_numpy(dtype=np.int64)
    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)

    def days(col: pd.Series) -> np.ndarray:
        t = pd.to_datetime(col.replace("", None), format="mixed")
        return ((t - base).dt.total_seconds() / 86400.0).to_numpy(dtype=np.float64)

    abandon_day = days(journeys.abandoned_at)
    started_day = days(journeys.started_at)
    has_ab = np.isfinite(abandon_day)

    # ---- live-lead window: months whose start falls in (abandon, abandon+365] #
    live = np.zeros((n, m + 1), dtype=np.int32)
    lo = np.searchsorted(as_at, abandon_day[has_ab], side="left")
    hi = np.searchsorted(as_at, abandon_day[has_ab] + DROPOFF_LOOKBACK_DAYS, side="left")
    np.add.at(live, (j_row[has_ab], np.minimum(lo, m)), 1)
    np.add.at(live, (j_row[has_ab], np.minimum(hi, m)), -1)
    in_pool = np.cumsum(live[:, :m], axis=1) > 0
    in_pool[:, :FIRST_LABEL_MONTH] = False

    cust_row, month = np.nonzero(in_pool)
    as_at_day = as_at[month]

    # ---- the most recent abandonment visible at as_at ----------------------- #
    order = np.lexsort((abandon_day[has_ab], j_row[has_ab]))
    src = np.flatnonzero(has_ab)[order]
    key = j_row[src] * 1_000_000.0 + abandon_day[src]
    pos = np.searchsorted(key, cust_row * 1_000_000.0 + as_at_day, side="right") - 1
    last = src[np.maximum(pos, 0)]
    days_since = as_at_day - abandon_day[last]

    stage_idx = journeys.last_stage_idx.to_numpy(dtype=np.int64)[last]
    pidx = {p: i for i, p in enumerate(PRODUCTS)}
    prod_idx = journeys["product"].map(pidx).to_numpy(dtype=np.int64)[last]

    # attempts of this customer that had started by as_at
    skey = np.sort(j_row * 1_000_000.0 + started_day)
    n_att = (np.searchsorted(skey, cust_row * 1_000_000.0 + as_at_day, side="right")
             - np.searchsorted(skey, cust_row * 1_000_000.0, side="left"))

    suppressed, reason = suppression_for_rows(st, cust_row, as_at_day, month)
    contact = contact_features_for_rows(st, cust_row, as_at_day)

    return Population(cust_row=cust_row, month=month, as_at_day=as_at_day,
                      days_since_abandon=days_since, stage_idx=stage_idx,
                      dropoff_product=prod_idx, dropoff_attempts=n_att.astype(np.int16),
                      suppressed=suppressed, reason=reason, contact=contact)


# --------------------------------------------------------------------------- #
# the latent index
# --------------------------------------------------------------------------- #

def _z(x: np.ndarray) -> np.ndarray:
    sd = float(np.std(x))
    return (x - float(np.mean(x))) / (sd if sd > 1e-12 else 1.0)


def latent_signal(view: BookView, lat: ShopperLatents, pop: Population,
                  pitch: np.ndarray) -> np.ndarray:
    """The standardised latent index that decides whether a return completes."""
    r, mth = pop.cust_row, pop.month
    best_intent = pitch[r, :, mth].max(axis=1).astype(np.float64)
    cap = view.capacity_ratio[r, mth].astype(np.float64)
    raw = (W_COMMITMENT * _z(lat.commitment[r])
           + W_INTENT * _z(np.log1p(np.maximum(best_intent, 0.0)))
           + W_CAPACITY * _z(np.clip(cap, -5.0, 5.0))
           + W_STAGE * _z(pop.stage_idx.astype(np.float64))
           + W_RECENCY * _z(-np.log1p(pop.days_since_abandon))
           + W_SHOPPER * _z(lat.tilt[r]))
    return _z(raw)


def draw_clock(pop: Population, product: np.ndarray,
               rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(window_days, lag_days, respected)`` — the contact-to-disbursement clock.

    Drawn once, independently of the two solved knobs, so re-solving theta or the
    S/N never re-rolls the clock underneath it.
    """
    k = len(pop)
    w = np.array([DECISION_WINDOW_DAYS[p] for p in PRODUCTS], dtype=np.float64)[product]
    lag = w * LAG_MEAN_FRAC * rng.gamma(LAG_SHAPE, 1.0 / LAG_SHAPE, k)
    stall = rng.random(k) < LAG_STALL_P
    lag = lag + np.where(stall, w * rng.exponential(LAG_STALL_FRAC, k), 0.0)
    return w, lag, lag <= w


def draw_product(pop: Population, pitch: np.ndarray,
                 rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """``(product_idx, menu_intent, menu_full)`` — the product they would take and
    two menus of :data:`MENU_K`, returned rather than reduced to a hit flag so
    they can be re-read after the observed recoveries overwrite their product.

    ``menu_intent`` ranks on eligibility-weighted latent intent **alone** — what
    a ranker that knows only what the customer wants can do.  ``menu_full`` also
    uses the substitution anchor on the product they abandoned, which is a
    feature a model really does have, and is therefore the Bayes ceiling for
    SK-13.  Both are reported; the conservative one is the headline.
    """
    intent = np.power(np.maximum(pitch[pop.cust_row, :, pop.month].astype(np.float64), 1e-12),
                      PRODUCT_SHARPNESS)
    s = intent * np.power(SUBSTITUTION[pop.dropoff_product], SUBSTITUTION_SHARPNESS)
    c = np.cumsum(s, axis=1)
    u = rng.random(len(pop)) * c[:, -1]
    prod = (c < u[:, None]).sum(axis=1).clip(0, s.shape[1] - 1)
    return (prod, np.argsort(-intent, axis=1)[:, :MENU_K],
            np.argsort(-s, axis=1)[:, :MENU_K])


# --------------------------------------------------------------------------- #
# the solves
# --------------------------------------------------------------------------- #

def _p_complete(signal: np.ndarray, snr: float, noise: np.ndarray) -> np.ndarray:
    return sigmoid(snr * signal + noise)


def effective_return(ret: np.ndarray, snr: float) -> np.ndarray:
    """``return_propensity`` with its dispersion shrunk toward its mean by the S/N.

    A power in ratio space: exponent 0 collapses every customer onto the mean,
    exponent 1 (and above) leaves the propensity exactly as SD-S2 drew it.  See
    the module docstring for why the knob has to reach this channel too.
    """
    bar = float(np.mean(ret))
    return bar * np.power(np.maximum(ret, 1e-9) / bar, min(snr, 1.0))


def _bisect(f, lo: float, hi: float, target: float, iters: int = SOLVE_ITERS) -> float:
    """Solve ``f(x) = target`` for a monotone increasing ``f``."""
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def solve_theta(ret: np.ndarray, fatigue: np.ndarray, complete: np.ndarray,
                respected: np.ndarray, forced: np.ndarray, target: float) -> float:
    """Solve the contact effect so the expected random-contact rate hits ``target``.

    ``forced`` rows are the observed recoveries: their label is already decided
    by what really happened, so they enter the mean as a constant and theta only
    has to carry the rest of the population.
    """
    free = ~forced
    n = len(ret)
    const = float(np.sum(forced))

    def rate(theta: float) -> float:
        p = np.clip(theta * ret[free] * fatigue[free], 0.0, 1.0) * complete[free]
        return (const + float(np.sum(p * respected[free]))) / n

    return _bisect(rate, *THETA_BRACKET, target=target)


@dataclass
class Solution:
    theta: float
    snr: float
    spontaneous: float
    oracle_precision: float
    expected_rate: float


def solve(signal: np.ndarray, ret: np.ndarray, fatigue: np.ndarray,
          respected: np.ndarray, forced: np.ndarray, forced_label: np.ndarray,
          eligible: np.ndarray, noise: np.ndarray, observed_self_return_rate: float,
          target_rate: float = RANDOM_CONTACT_TARGET,
          target_precision: float = ORACLE_PRECISION_TARGET) -> Solution:
    """Solve the S/N knob, then theta inside it, then the no-contact multiplier.

    The two knobs interact — raising the S/N raises the mean of
    ``sigmoid(snr * signal + noise)`` as well as its spread — so theta is
    re-solved at every step of the outer search rather than once at the end.
    Everything is evaluated on **expectations**, which makes the solve
    deterministic; the realised draw is asserted against the band afterwards by
    :func:`check`.
    """
    e = eligible
    k = max(int(round(CONTACT_BUDGET * int(e.sum()))), 1)

    def precision_at(snr: float) -> float:
        comp = _p_complete(signal, snr, noise)
        r = effective_return(ret, snr)
        theta = solve_theta(r[e], fatigue[e], comp[e], respected[e], forced[e], target_rate)
        p = np.where(forced, forced_label.astype(float),
                     np.clip(theta * r * fatigue, 0.0, 1.0) * comp * respected)
        top = np.argpartition(-signal[e], k - 1)[:k]
        return float(np.mean(p[e][top]))

    snr = _bisect(precision_at, *SNR_BRACKET, target=target_precision)
    comp = _p_complete(signal, snr, noise)
    r = effective_return(ret, snr)
    theta = solve_theta(r[e], fatigue[e], comp[e], respected[e], forced[e], target_rate)

    # the no-contact arm, calibrated to what really happened
    def rate0(s: float) -> float:
        return float(np.mean(np.clip(s * r[e], 0.0, 1.0) * comp[e]))

    spontaneous = _bisect(rate0, 1e-4, 20.0, target=max(observed_self_return_rate, 1e-6))

    p1 = np.where(forced, forced_label.astype(float),
                  np.clip(theta * r * fatigue, 0.0, 1.0) * comp * respected)
    top = np.argpartition(-signal[e], k - 1)[:k]
    return Solution(theta=float(theta), snr=float(snr), spontaneous=float(spontaneous),
                    oracle_precision=float(np.mean(p1[e][top])),
                    expected_rate=float(np.mean(p1[e])))


# --------------------------------------------------------------------------- #
# the observed recoveries, which anchor the counterfactual table
# --------------------------------------------------------------------------- #

@dataclass
class Recoveries:
    """The drop-offs who really did come back, in ``journeys.csv``."""

    cust_row: np.ndarray       # (K,) customer row
    month: np.ndarray          # (K,) panel month of the RM contact
    contacted: np.ndarray      # (K,) bool — an RM was on the returning attempt
    in_window: np.ndarray      # (K,) bool — disbursement landed inside the window
    product: np.ndarray        # (K,) product index
    lag_days: np.ndarray       # (K,) contact -> disbursement, NaN if self-returned


def find_recoveries(view: BookView, journeys: pd.DataFrame) -> Recoveries:
    """Customers with an abandoned attempt who later disbursed.

    The anchoring month is the month of the **RM contact**, not of the
    disbursement: the contact is the event the pre-registered label measures from,
    and it always precedes the returning application.
    """
    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    row_of = {c: i for i, c in enumerate(view.book["cust_id"].to_numpy(dtype=object))}
    edges = _month_starts(view)

    def days(col: pd.Series) -> np.ndarray:
        t = pd.to_datetime(col.replace("", None), format="mixed")
        return ((t - base).dt.total_seconds() / 86400.0).to_numpy(dtype=np.float64)

    j = journeys
    disb = j.outcome.to_numpy() == "disbursed"
    abandoned_cust = set(j.loc[j.outcome != "disbursed", "customer_id"])
    recovered = disb & j.customer_id.isin(abandoned_cust).to_numpy()

    d_day = days(j.disbursed_at)[recovered]
    c_day = days(j.rm_contacted_at)[recovered]
    pidx = {p: i for i, p in enumerate(PRODUCTS)}
    prod = j["product"].map(pidx).to_numpy(dtype=np.int64)[recovered]
    w = np.array([DECISION_WINDOW_DAYS[p] for p in PRODUCTS], dtype=np.float64)[prod]

    has_rm = np.isfinite(c_day)
    anchor_day = np.where(has_rm, c_day, d_day)
    month = np.clip(np.searchsorted(edges, anchor_day, side="right") - 1, 0, view.months - 1)
    lag = d_day - c_day
    return Recoveries(
        cust_row=j.customer_id.map(row_of).to_numpy(dtype=np.int64)[recovered],
        month=month, contacted=has_rm,
        in_window=has_rm & (lag <= w) & (lag >= -1e-9),
        product=prod, lag_days=lag)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def generate(view: BookView, lat: ShopperLatents, journeys: pd.DataFrame,
             st: ContactState, pitch: np.ndarray, campaigns: pd.DataFrame,
             rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build ``(labels, label_truth, params)``."""
    pop = build_population(view, journeys, st)
    r, mth = pop.cust_row, pop.month
    k = len(pop)
    eligible = ~pop.suppressed

    product, menu_intent, menu_full = draw_product(pop, pitch, rng)
    window, lag, respected = draw_clock(pop, product, rng)
    signal = latent_signal(view, lat, pop, pitch)
    noise = rng.normal(0.0, 1.0, k)
    fatigue = pop.contact["fatigue"]
    ret = lat.return_propensity[r]

    # ---- fold the observed recoveries in as forced outcomes ---------------- #
    rec = find_recoveries(view, journeys)
    row_index = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(r, mth))}
    forced = np.zeros(k, dtype=bool)
    forced_label = np.zeros(k, dtype=bool)
    realised = np.zeros(k, dtype=bool)
    rm_on_return = np.zeros(k, dtype=bool)
    matched = 0
    for c, m_, was_contacted, ok, p_, lg in zip(
            rec.cust_row, rec.month, rec.contacted, rec.in_window, rec.product, rec.lag_days):
        i = row_index.get((int(c), int(m_)))
        if i is None:
            continue
        matched += 1
        realised[i] = True
        product[i] = p_
        window[i] = DECISION_WINDOW_DAYS[PRODUCTS[p_]]
        if was_contacted:
            rm_on_return[i] = True
            forced[i] = True
            forced_label[i] = bool(ok)
            lag[i] = lg
    # a realised recovery on a row the bank may not call cannot be a contact
    # outcome: the forcing is dropped and counted (DATA_CARD §12.4).
    erased = int(np.sum(forced & ~eligible))
    forced &= eligible
    forced_label &= forced
    # the drawn lag was scaled by the product drawn before the forcing pass
    respected = np.where(forced, forced_label, lag <= window)
    in_menu = (menu_intent == product[:, None]).any(axis=1)
    in_menu_full = (menu_full == product[:, None]).any(axis=1)

    # Y(0) is anchored on the drop-offs who came back with **no** RM on the file.
    # A recovery whose RM contact fell on a row the bank may not call is not a
    # self-return; it is an observation the counterfactual table cannot carry.
    self_returns = int(np.sum(realised & ~rm_on_return & eligible))
    observed_self_rate = self_returns / max(int(eligible.sum()), 1)

    sol = solve(signal, ret, fatigue, respected, forced, forced_label, eligible,
                noise, observed_self_rate)

    complete = _p_complete(signal, sol.snr, noise)
    ret_eff = effective_return(ret, sol.snr)
    p1 = np.where(forced, forced_label.astype(float),
                  np.clip(sol.theta * ret_eff * fatigue, 0.0, 1.0) * complete)
    p0 = np.clip(sol.spontaneous * ret_eff, 0.0, 1.0) * complete

    #: a *return* is coming back and completing an application at all; the label
    #: additionally requires that it landed inside the product's window.
    returns = np.where(forced, True, rng.random(k) < p1)
    label = eligible & returns & respected
    label0 = eligible & (rng.random(k) < p0)

    # ---- the realised campaign contact (SD-S6), and the observed label ------ #
    contacted, contacted_at, channel = _realised_contacts(view, campaigns, pop)
    contacted &= eligible
    observed = np.where(contacted, label, label0)

    # ---- frames ------------------------------------------------------------ #
    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    cust_id = view.book["cust_id"].to_numpy(dtype=object)[r]
    last_days = pop.contact["last_contact_days"]
    prod_name = np.array(PRODUCTS, dtype=object)[product]

    labels = pd.DataFrame({
        "cust_id": cust_id,
        "month": mth.astype(np.int16),
        "as_at": _stamp(pop.as_at_day, base),
        "in_dropoff_pool": np.int8(1),
        "eligible_for_contact": eligible.astype(np.int8),
        "suppressed": pop.suppressed.astype(np.int8),
        "suppression_reason": reason_names(pop.reason),
        "consent_marketing": view.book["consent"].to_numpy(dtype=np.int8)[r],
        "dnd": view.book["dnd"].to_numpy(dtype=np.int8)[r],
        "dropoff_stage_reached": np.array(STAGES, dtype=object)[pop.stage_idx],
        "dropoff_product": np.array(PRODUCTS, dtype=object)[pop.dropoff_product],
        "dropoff_attempts": pop.dropoff_attempts,
        "days_since_abandon": np.round(pop.days_since_abandon, 2),
        "contacts_30d": pop.contact["contacts_30d"],
        "contacts_90d": pop.contact["contacts_90d"],
        "campaign_contacts_6m": pop.contact["campaign_contacts_6m"],
        "last_contact_days": np.round(last_days, 2),
        "last_contact_date": _stamp(pop.as_at_day - last_days, base, date_only=True),
        "last_campaign_product": pop.contact["last_campaign_product"],
        "contacted": contacted.astype(np.int8),
        "contacted_at": _stamp(contacted_at, base),
        "contact_channel": channel,
        "label_disbursed_in_window": label.astype(np.int8),
        "label_product": np.where(label, prod_name, ""),
        "window_days": window.astype(np.int16),
        "contact_window_days": window.astype(np.int16),
        "window_respected": np.where(returns & eligible, respected.astype(float), np.nan),
        "days_to_disbursement": np.where(returns & eligible, np.round(lag, 3), np.nan),
        "label_disbursed_at": _stamp(np.where(label, pop.as_at_day + lag, np.nan), base),
        "label_no_contact": label0.astype(np.int8),
        "label_observed": observed.astype(np.int8),
        "realised_recovery": realised.astype(np.int8),
    })
    for i, p in enumerate(PRODUCTS):
        labels[f"label_product_{p}"] = (label & (product == i)).astype(np.int8)
    labels = labels[LABEL_COLUMNS]

    truth = pd.DataFrame({
        "cust_id": cust_id,
        "month": mth.astype(np.int16),
        "latent_signal": np.round(signal, 5),
        "oracle_score": np.round(signal, 5),
        "oracle_menu_hit": np.where(label, in_menu.astype(float), np.nan),
        "menu_hit_with_dropoff_anchor": np.where(label, in_menu_full.astype(float), np.nan),
        "p_disburse_if_contacted": np.round(p1 * respected, 6),
        "p_disburse_no_contact": np.round(p0, 6),
        "returns_and_completes": returns.astype(np.int8),
        "fatigue": np.round(fatigue, 4),
        "return_propensity": np.round(ret, 4),
        "shopper_truth": lat.truth[r].astype(np.int8),
        "commitment": np.round(lat.commitment[r], 4),
    })[TRUTH_COLUMNS]

    params = {
        "theta_contact_effect": round(sol.theta, 6),
        "label_signal_to_noise": round(sol.snr, 6),
        "spontaneous_return": round(sol.spontaneous, 6),
        "contact_lift": round(sol.theta / max(sol.spontaneous, 1e-9), 3),
        "oracle_precision_target": ORACLE_PRECISION_TARGET,
        "random_contact_target": RANDOM_CONTACT_TARGET,
        "decision_window_days": dict(DECISION_WINDOW_DAYS),
        "dropoff_lookback_days": DROPOFF_LOOKBACK_DAYS,
        "observed_recoveries": int(len(rec.cust_row)),
        "observed_recoveries_matched_to_a_row": matched,
        "observed_recoveries_dropped_as_suppressed": erased,
        "observed_self_return_rate": round(observed_self_rate, 6),
    }
    return labels, truth, params


def _stamp(day: np.ndarray, base: pd.Timestamp, date_only: bool = False) -> pd.Series:
    t = base + pd.to_timedelta(np.asarray(day, dtype=np.float64), unit="D")
    fmt = "%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M:%S"
    return pd.Series(t).dt.round("s").dt.strftime(fmt).fillna("")


def _realised_contacts(view: BookView, campaigns: pd.DataFrame,
                       pop: Population) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The RM call the bank actually placed inside month ``m``, if any.

    This is the **treatment**, not a feature: it happens after ``as_at`` and must
    never reach a model as an input (DATA_CARD §12.5).
    """
    k = len(pop)
    row_of = {c: i for i, c in enumerate(view.book["cust_id"].to_numpy(dtype=object))}
    rm = campaigns[campaigns.channel == "rm-call"]
    c_row = rm.cust_id.map(row_of).to_numpy(dtype=np.int64)
    c_day = rm.sent_day.to_numpy(dtype=np.float64)
    key = np.sort(c_row * 1_000_000.0 + c_day)

    edges = _month_starts(view)
    end = edges[pop.month + 1]
    lo = np.searchsorted(key, pop.cust_row * 1_000_000.0 + pop.as_at_day, side="left")
    hi = np.searchsorted(key, pop.cust_row * 1_000_000.0 + end, side="left")
    hit = hi > lo
    day = np.full(k, np.nan)
    day[hit] = key[lo[hit]] - pop.cust_row[hit] * 1_000_000.0
    return hit, day, np.where(hit, "rm-call", "")


# --------------------------------------------------------------------------- #
# the in-script assertions
# --------------------------------------------------------------------------- #

#: The pre-registered bands this lane asserts against, from
#: ``validation/criteria.yaml`` (SK-01, SK-02, SK-04) as amended by AM-01.
BAND_RANDOM_CONTACT = (0.08, 0.10)
BAND_ORACLE_PRECISION = (0.25, 0.35)
MIN_WINDOW_RESPECT = 0.90


def check(labels: pd.DataFrame, truth: pd.DataFrame, params: dict,
          rng: np.random.Generator) -> dict[str, float]:
    """Re-measure every band on the realised draw and fail the run outside it."""
    e = labels.eligible_for_contact.to_numpy().astype(bool)
    y = labels.label_disbursed_in_window.to_numpy().astype(bool)
    n_e = int(e.sum())

    # SK-01 as amended: the disbursement rate among a uniformly random 10% contact
    # sample of the population.  The BAND is asserted on the estimand — the rate
    # over the whole eligible population, which is exactly what a uniform sample
    # estimates without bias — and one actual 10% draw is reported beside it with
    # its standard error.  A generator assertion that could fail on the Monte
    # Carlo noise of a single measurement sample would be a flaky gate, not a
    # gate: at the test book's size that noise is +/- 1.6 pp at 95%.
    full_rate = float(np.mean(y[e]))
    k_s = max(int(round(CONTACT_BUDGET * n_e)), 1)
    sample = rng.permutation(np.flatnonzero(e))[:k_s]
    sample_rate = float(np.mean(y[sample]))
    sample_se = float(np.sqrt(max(full_rate * (1 - full_rate), 0.0) / k_s))
    random_rate = full_rate

    # SK-02's ceiling: the oracle that sees the latent index itself
    score = truth.oracle_score.to_numpy()[e]
    k = max(int(round(CONTACT_BUDGET * n_e)), 1)
    top = np.argpartition(-score, k - 1)[:k]
    oracle = float(np.mean(y[e][top]))

    resp = labels.window_respected.to_numpy(dtype=float)
    respect = float(np.nanmean(resp))

    stats = {
        "rows": float(len(labels)),
        "customers": float(labels.cust_id.nunique()),
        "eligible_share": float(e.mean()),
        "suppressed_share": float(labels.suppressed.mean()),
        "random_contact_disbursement_rate": random_rate,
        "random_contact_sample_rate": sample_rate,
        "random_contact_sample_se": sample_se,
        "random_contact_sample_n": float(k_s),
        "oracle_precision_at_10pct": oracle,
        "no_contact_disbursement_rate": float(labels.label_no_contact.to_numpy()[e].mean()),
        "window_respect_rate": respect,
        "median_days_to_disbursement": float(
            np.nanmedian(labels.days_to_disbursement.to_numpy(dtype=float))),
        "menu_of_4_coverage": float(np.nanmean(truth.oracle_menu_hit.to_numpy(dtype=float))),
        "menu_of_4_coverage_with_dropoff_anchor": float(
            np.nanmean(truth.menu_hit_with_dropoff_anchor.to_numpy(dtype=float))),
        "label_product_differs_from_dropoff": float(np.mean(
            labels.loc[y, "label_product"].to_numpy()
            != labels.loc[y, "dropoff_product"].to_numpy())),
        "theta": float(params["theta_contact_effect"]),
        "signal_to_noise": float(params["label_signal_to_noise"]),
        "contact_lift": float(params["contact_lift"]),
    }

    # ---- structural -------------------------------------------------------- #
    assert not labels.duplicated(["cust_id", "month"]).any(), "a (customer, month) row repeats"
    assert (labels.suppressed.to_numpy() == (
        labels.suppression_reason.to_numpy() != "none")).all(), \
        "suppressed and suppression_reason disagree"
    assert not (labels.suppressed.to_numpy().astype(bool) & y).any(), \
        "a suppressed row carries a positive contact label"
    per_product = labels[[f"label_product_{p}" for p in PRODUCTS]].to_numpy().sum(axis=1)
    assert (per_product == y.astype(int)).all(), \
        "the per-product menu labels do not sum to the row label"
    assert (labels.loc[y, "label_product"] != "").all(), "a positive label names no product"
    assert labels.loc[~y, "label_product"].eq("").all(), "a negative label names a product"
    assert (labels.window_days.to_numpy() ==
            labels.contact_window_days.to_numpy()).all(), "window alias drifted"

    # ---- the pre-registered bands (amendment AM-01) ------------------------ #
    lo, hi = BAND_RANDOM_CONTACT
    assert lo <= random_rate <= hi, (
        f"random-contact disbursement {random_rate:.2%} is outside the "
        f"pre-registered [{lo:.0%}, {hi:.0%}] band (SK-01); theta solved to "
        f"{params['theta_contact_effect']}")
    lo, hi = BAND_ORACLE_PRECISION
    assert lo <= oracle <= hi, (
        f"oracle precision@10% {oracle:.2%} is outside the pre-registered "
        f"[{lo:.0%}, {hi:.0%}] band (SK-02 ceiling); S/N solved to "
        f"{params['label_signal_to_noise']}")
    assert respect >= MIN_WINDOW_RESPECT, (
        f"window respect {respect:.1%} is below the pre-registered "
        f"{MIN_WINDOW_RESPECT:.0%} floor (SK-04)")
    assert full_rate > stats["no_contact_disbursement_rate"], \
        "contact does not raise the disbursement rate — theta has the wrong sign"
    return stats
