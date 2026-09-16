"""The discrete-time hazard, the sampled path, and the clock.

The gate
--------
At each of the seven gates the attempt advances with

    P(advance) = sigmoid(alpha_s + beta*intent + gamma*capacity
                         + delta_s . friction_s + product_s + channel)

and otherwise **times out**: it sits at that stage for a per-stage number of days
and the file is closed.  ``intent`` and ``capacity`` are the book's own latents
read at the month the attempt was launched in; ``friction_s`` is stage-specific
and is where the four window-shopper signals bite.

Why the intercepts are solved, not written down
-----------------------------------------------
A hand-set ``alpha_s`` makes the funnel's *shape* an accident of whatever the
covariate coefficients happen to be, which is exactly the kind of thing that
drifts silently when someone later changes ``delta``.  Instead the funnel shape
is the declared parameter (:data:`ABANDON_SHARE`, ``assumed``) and the
intercepts are solved to hit it — so a change to ``beta``, ``gamma`` or
``delta`` changes *who* drops out at each stage without changing *how many*.

Conditioning on the book
------------------------
The book decides the outcome.  An attempt the book says disburses walks every
stage; an attempt the book says abandons draws its stopping stage from

    P(abandon at s | does not disburse) = [prod_{j<s} p_j (1 - p_s)] / (1 - prod_j p_j)

Every parameter in this module is ``assumed``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from book.products import DECISION_WINDOW_DAYS, PRODUCTS

from . import CHANNELS, N_GATES, STAGES
from .attempts import Attempts
from .bookview import BookView
from .shoppers import ShopperLatents, sigmoid

# --------------------------------------------------------------------------- #
# the funnel shape — the one declared parameter the intercepts are solved to
# --------------------------------------------------------------------------- #

#: Share of **abandonments** that happen at each stage.  Documents are the
#: classic killer and the Rs 1,000 fee is the mentors' signature drop; the tail
#: after Offer is thin because a customer who has paid a fee and seen a number
#: usually finishes.  ``assumed`` — shaped like a retail-lending funnel for an
#: existing bank customer, not measured from one.
ABANDON_SHARE: dict[str, float] = {
    "start": 0.18, "eligibility": 0.14, "kyc": 0.10, "docs": 0.22,
    "fee": 0.20, "offer": 0.09, "accept": 0.07,
}
#: Fixed-point iterations used to make the realised conditional shares match.
_SHAPE_ITERATIONS = 12
_ALPHA_BRACKET = (-14.0, 14.0)

# --------------------------------------------------------------------------- #
# hazard coefficients
# --------------------------------------------------------------------------- #

#: Latent intent and capacity, read from the book's truth file at the attempt's
#: launch month and centred so the solved intercepts stay interpretable.
BETA_INTENT = 2.20
GAMMA_CAPACITY = 1.60

#: The window-shopper drag, **per gate** and deliberately not uniform.  Window
#: shopping is free: a shopper is perfectly happy to fill in a form and hear
#: whether they qualify — that is what they came for.  They stop when the bank
#: asks for something: documents, and then a Rs 1,000 cheque.  So the drag is
#: slightly *positive* early and heavily negative at Docs and Fee, which is what
#: puts shoppers where the mentors said they die.
SHOPPER_DRAG = (0.15, 0.10, 0.0, -0.85, -1.05, -0.25, -0.30)

#: Channel effect on every gate: somebody is holding your hand in a branch;
#: a DSA-sourced file is worked hardest and converts worst.
CHANNEL_EFFECT = {"branch-walk-in": 0.35, "rm-call": 0.25, "app": 0.0,
                  "web": -0.15, "dsa": -0.25}

#: Per-product effect per gate.  A gold loan is an appraisal and a counter; a
#: home loan is a legal and technical valuation.  Rows are products, columns the
#: seven gates (start, eligibility, kyc, docs, fee, offer, accept).
PRODUCT_EFFECT: dict[str, tuple[float, ...]] = {
    "home":      (-0.10, -0.25, -0.05, -0.55, -0.15, -0.30, -0.20),
    "lap":       (-0.10, -0.30, -0.05, -0.50, -0.15, -0.35, -0.25),
    "gold":      (0.35, 0.55, 0.20, 0.70, 0.25, 0.35, 0.30),
    "auto":      (0.05, 0.05, 0.05, 0.05, 0.00, -0.05, 0.00),
    "education": (-0.05, -0.10, 0.00, -0.25, 0.10, 0.05, 0.10),
    "personal":  (0.20, 0.15, 0.15, 0.30, -0.10, 0.10, 0.05),
}

#: Stage-specific friction weights.  Index = gate.
D_BLANK = (-0.70, -0.80, -0.50, -0.30, -0.35, -0.30, -0.15)
D_INCOME_REFUSED = (-0.45, -1.15, -0.70, -0.50, -0.35, -0.65, -0.40)
D_INELIGIBLE = (-0.30, -2.60, -0.40, -0.30, -0.20, -0.30, -0.20)
#: Stated document refusal, known from the Eligibility conversation onwards.
D_DOC_REFUSAL = (0.0, -0.50, -0.70, -1.45, -0.55, -0.45, -0.35)
#: ...and the measured shortfall, which can only bite once documents are due.
D_DOC_SHORTFALL = (0.0, 0.0, -0.25, -1.30, -0.40, -0.25, -0.20)
D_DOC_RELUCTANCE = (0.0, 0.0, -0.20, -0.60, -0.15, -0.10, -0.10)
#: The fee balk, likewise quoted at Eligibility and only paid for at the Fee gate.
D_FEE_BALK = (0.0, -0.55, -0.60, -0.70, -2.10, -0.65, -0.50)
D_FEE_SENSITIVITY = (0.0, 0.0, 0.0, -0.15, -1.30, -0.20, -0.15)
D_OFFER_SHORTFALL = (0.0, 0.0, 0.0, 0.0, -0.20, -2.00, -1.60)
#: Short relationships are harder to KYC.
D_THIN_TENURE = (-0.10, -0.25, -0.45, -0.15, -0.05, -0.05, -0.05)
THIN_TENURE_MONTHS = 12

# --------------------------------------------------------------------------- #
# the clock
# --------------------------------------------------------------------------- #

#: A journey's total *advance* time as a fraction of the product's decision
#: window, and how that total splits across the seven gates.
TOTAL_DURATION_FRAC = 0.42
ADVANCE_SPLIT = (0.05, 0.08, 0.12, 0.30, 0.12, 0.18, 0.15)
ADVANCE_SHAPE = 2.0
MIN_STEP_DAYS = 0.01

#: Stalls.  These are the realistic reason a disbursement misses its window: a
#: customer who balks at the fee for a week, or has to go and find a document.
DOC_STALL_FRAC = 0.24
FEE_STALL_FRAC = 0.26
STALL_SHAPE = 2.0

#: Timeout before the bank closes a stalled file, in days at a 7-day product;
#: scaled by the product's own speed and capped.
TIMEOUT_MEAN_DAYS = (2.5, 4.0, 6.0, 11.0, 8.0, 9.0, 12.0)
TIMEOUT_SHAPE = 1.6
TIMEOUT_CAP_DAYS = 45.0
PRODUCT_SPEED_BOUNDS = (0.45, 2.0)

#: An RM contact that *precedes* the application, as a fraction of the window.
CONTACT_LEAD_FRAC = 0.12
#: Hour of day the anchoring event lands on, by channel (fraction of the day).
START_HOUR_FRAC = {"branch-walk-in": 0.52, "rm-call": 0.58, "app": 0.75,
                   "web": 0.72, "dsa": 0.55}
START_HOUR_SD = 0.11

#: Days between abandoning one application and starting the next.
RETURN_GAP_MEAN_DAYS = 26.0
RETURN_GAP_SHAPE = 2.0
RETURN_GAP_MIN_DAYS = 3.0
#: Clearance a converter's earlier attempt must leave before the final one.
PRIOR_CLEARANCE_DAYS = 2.0


@dataclass
class Funnel:
    """The realised path and clock of every attempt.  Arrays are ``(A,)`` unless noted."""

    p_gate: np.ndarray            # (A, 7) advance probability at each gate
    p_complete: np.ndarray        # (A,)   product of the seven, the latent completion odds
    alpha: np.ndarray             # (7,)   solved intercepts
    last_stage: np.ndarray        # (A,)   0..7 index into STAGES
    last_stage_raw: np.ndarray    # (A,)   before the panel-end truncation
    entry_day: np.ndarray         # (A, 8) days since panel start, valid up to last_stage
    step_days: np.ndarray         # (A, 7) advance + stall spent in each stage passed
    time_in_last_stage: np.ndarray  # (A,) days at the stage it stopped at (NaN if disbursed)
    started_day: np.ndarray
    terminal_day: np.ndarray      # abandon or disburse instant; NaN while in flight
    outcome: np.ndarray           # 'disbursed' | 'abandoned' | 'in_flight'
    rm_contact_day: np.ndarray    # NaN where no RM touched the attempt
    fee_paid_day: np.ndarray      # NaN unless the fee gate was passed
    panel_end_day: float = 0.0


# --------------------------------------------------------------------------- #
# durations
# --------------------------------------------------------------------------- #

def _speed(product_idx: np.ndarray) -> np.ndarray:
    w = np.array([DECISION_WINDOW_DAYS[p] for p in PRODUCTS], dtype=np.float64)[product_idx]
    return np.clip(w / 7.0, *PRODUCT_SPEED_BOUNDS)


def window_days(product_idx: np.ndarray) -> np.ndarray:
    """The pre-registered decision window, in days, per attempt."""
    return np.array([DECISION_WINDOW_DAYS[p] for p in PRODUCTS], dtype=np.float64)[product_idx]


def draw_durations(att: Attempts, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """``(step_days (A,7), timeout_days (A,7))``.

    ``step_days`` is the time an attempt spends in a stage it goes on to leave —
    the base advance plus, where the customer balked or under-supplied documents,
    a stall.  ``timeout_days`` is how long it sits there if it never leaves.
    """
    a = len(att)
    w = window_days(att.product_idx)
    mean = np.asarray(ADVANCE_SPLIT)[None, :] * TOTAL_DURATION_FRAC * w[:, None]
    step = rng.gamma(ADVANCE_SHAPE, mean / ADVANCE_SHAPE, size=(a, N_GATES))
    step = np.maximum(step, MIN_STEP_DAYS)

    doc_gate, fee_gate = STAGES.index("docs"), STAGES.index("fee")
    step[:, doc_gate] += np.where(
        att.doc_shortfall, rng.gamma(STALL_SHAPE, DOC_STALL_FRAC * w / STALL_SHAPE), 0.0)
    step[:, fee_gate] += np.where(
        att.fee_balk, rng.gamma(STALL_SHAPE, FEE_STALL_FRAC * w / STALL_SHAPE), 0.0)

    t_mean = np.asarray(TIMEOUT_MEAN_DAYS)[None, :] * _speed(att.product_idx)[:, None]
    timeout = np.minimum(rng.gamma(TIMEOUT_SHAPE, t_mean / TIMEOUT_SHAPE), TIMEOUT_CAP_DAYS)
    return step, timeout


# --------------------------------------------------------------------------- #
# hazard
# --------------------------------------------------------------------------- #

def gate_logits(view: BookView, att: Attempts, lat: ShopperLatents) -> np.ndarray:
    """``(A, 7)`` linear predictor at every gate, **without** the intercepts."""
    a = len(att)
    row = att.cust_row
    b = view.book
    shopper = lat.truth[row].astype(np.float64)

    intent = att.intent_at_start
    capacity = att.capacity_at_start
    z = np.zeros((a, N_GATES), dtype=np.float64)
    z += (BETA_INTENT * (intent - intent.mean()))[:, None]
    z += (GAMMA_CAPACITY * (capacity - capacity.mean()))[:, None]
    z += np.asarray(SHOPPER_DRAG)[None, :] * shopper[:, None]
    z += np.array([CHANNEL_EFFECT[c] for c in CHANNELS])[att.channel_idx][:, None]
    z += np.array([PRODUCT_EFFECT[p] for p in PRODUCTS])[att.product_idx]

    blank = att.blank_ratio - 0.20
    refused = (~att.income_shared).astype(np.float64)
    inelig = att.ineligible.astype(np.float64)
    shortfall_docs = np.where(att.docs_requested > 0,
                              1.0 - att.docs_supplied_first / np.maximum(att.docs_requested, 1), 0.0)
    doc_rel = b["doc_reluctance"].to_numpy(dtype=np.float64)[row] - 0.33
    balk = att.fee_balk.astype(np.float64)
    fee_sens = b["fee_sensitivity"].to_numpy(dtype=np.float64)[row] - 0.42
    thin = (b["tenure_m"].to_numpy()[row] < THIN_TENURE_MONTHS).astype(np.float64)

    for weights, x in (
        (D_BLANK, blank), (D_INCOME_REFUSED, refused), (D_INELIGIBLE, inelig),
        (D_DOC_REFUSAL, att.doc_refusal.astype(np.float64)),
        (D_DOC_SHORTFALL, shortfall_docs), (D_DOC_RELUCTANCE, doc_rel),
        (D_FEE_BALK, balk), (D_FEE_SENSITIVITY, fee_sens),
        (D_OFFER_SHORTFALL, att.offer_shortfall), (D_THIN_TENURE, thin),
    ):
        z += np.asarray(weights)[None, :] * x[:, None]
    return z


def _conditional_shares(p: np.ndarray) -> np.ndarray:
    """``(A, 7)`` P(abandon at stage s | this attempt does not disburse)."""
    reach = np.concatenate([np.ones((len(p), 1)), np.cumprod(p, axis=1)], axis=1)  # (A, 8)
    fail = reach[:, :N_GATES] * (1.0 - p)
    denom = np.maximum(1.0 - reach[:, -1], 1e-12)
    return fail / denom[:, None]


def solve_intercepts(z: np.ndarray, abandons: np.ndarray, completion: float,
                     shares: tuple[float, ...] | None = None) -> np.ndarray:
    """Solve the seven intercepts against two things at once.

    1. **Shape.** The realised distribution of *where* attempts abandon matches
       :data:`ABANDON_SHARE`, measured on the attempts that abandon.
    2. **Level.** The hazard's own completion probability, averaged over every
       attempt, equals the completion rate the book implies (``completion`` =
       disbursements / attempts).

    The level constraint is what keeps the conditioning honest.  Without it the
    shape alone is satisfied by any funnel — including a degenerate one where the
    model thinks nobody could ever finish and the 26% who do are a miracle.  With
    it, the model free-runs to the same completion rate the book produces, and
    the attempts that do disburse come out with visibly better odds than the ones
    that do not (asserted in ``build.check``).

    Seven intercepts, seven constraints: six independent shape shares plus the
    level.  Solved as a damped fixed point on the per-gate marginal failure
    rates, with a forward bisection per gate so gate ``s`` is fitted on exactly
    the attempts that reached it.
    """
    target = np.asarray(shares if shares is not None
                        else [ABANDON_SHARE[s] for s in STAGES[:N_GATES]], dtype=np.float64)
    target = target / target.sum()
    if not abandons.any():
        raise ValueError("no abandoning attempts to solve the funnel shape against")
    completion = float(np.clip(completion, 0.01, 0.90))

    def hazards(shape: np.ndarray, level: float) -> np.ndarray:
        """Marginal per-gate failure rates implied by a shape and a completion."""
        f = 1.0 - level
        cum = np.concatenate([[0.0], np.cumsum(shape)[:-1]])
        return np.clip(shape * f / np.maximum(1.0 - f * cum, 1e-6), 1e-4, 0.97)

    shape, level = target.copy(), completion
    alpha = np.zeros(N_GATES)
    for _ in range(_SHAPE_ITERATIONS):
        q = hazards(shape, level)
        reach = np.ones(len(z))
        for s in range(N_GATES):
            lo, hi = _ALPHA_BRACKET
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                fail = float(np.sum(reach * (1.0 - sigmoid(z[:, s] + mid))) / max(reach.sum(), 1e-12))
                if fail > q[s]:
                    lo = mid                       # too many failures -> raise alpha
                else:
                    hi = mid
            alpha[s] = 0.5 * (lo + hi)
            reach = reach * sigmoid(z[:, s] + alpha[s])

        p = sigmoid(z + alpha)
        realised_shape = _conditional_shares(p[abandons]).mean(axis=0)
        realised_level = float(np.mean(np.prod(p, axis=1)))
        if (np.max(np.abs(realised_shape - target)) < 2e-4
                and abs(realised_level - completion) < 2e-4):
            break
        shape = shape * (target / np.maximum(realised_shape, 1e-9)) ** 0.6
        shape = shape / shape.sum()
        level = float(np.clip(level * (completion / max(realised_level, 1e-6)) ** 0.7, 0.005, 0.95))
    return alpha


def sample_paths(p: np.ndarray, disburses: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """``(A,)`` last stage index: 7 for a disbursement, otherwise the stage the
    attempt timed out at, drawn from the hazard conditioned on not disbursing."""
    g = _conditional_shares(p)
    c = np.cumsum(g, axis=1)
    u = rng.random(len(p)) * c[:, -1]
    stage = (c < u[:, None]).sum(axis=1).clip(0, N_GATES - 1)
    return np.where(disburses, len(STAGES) - 1, stage).astype(np.int64)


# --------------------------------------------------------------------------- #
# the clock
# --------------------------------------------------------------------------- #

def month_day_offsets(anchor: tuple[int, int], months: int) -> tuple[np.ndarray, np.ndarray]:
    """``(start_day, length_days)`` per panel month, as days from panel start."""
    first = pd.Timestamp(year=anchor[0], month=anchor[1], day=1)
    starts = pd.date_range(first, periods=months + 1, freq="MS")
    day = (starts - first).days.to_numpy().astype(np.float64)
    return day[:-1], np.diff(day)


def journey_length(step: np.ndarray, timeout: np.ndarray, last_stage: np.ndarray) -> np.ndarray:
    """Days from ``started_at`` to the terminal instant."""
    idx = np.arange(N_GATES)[None, :]
    advanced = idx < last_stage[:, None]
    walked = (step * advanced).sum(axis=1)
    stalled = np.where(last_stage < N_GATES,
                       timeout[np.arange(len(timeout)), np.minimum(last_stage, N_GATES - 1)], 0.0)
    return walked + stalled


def converter_start_month(view: BookView, cust_row: np.ndarray, is_final: np.ndarray,
                          step: np.ndarray, rng: np.random.Generator,
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pin every converter's final attempt to the book's ``event_month``.

    Returns ``(start_day, disburse_day, start_month_by_customer)``.  The
    disbursement lands on a day inside ``event_month``; the application therefore
    *started* however long the journey took before that, which is sometimes the
    previous month — the book's monthly grain plus a within-month day, read
    backwards from the outcome it already fixed.
    """
    n = view.n
    starts, lengths = month_day_offsets(view.anchor, view.months)
    a = len(cust_row)
    total = step.sum(axis=1)

    ev = view.event_month[cust_row]
    frac = rng.random(a)
    disb = np.where(is_final, starts[np.clip(ev, 0, None)] + frac * lengths[np.clip(ev, 0, None)], np.nan)
    start_day = disb - total
    # never begin before the panel does
    start_day = np.where(is_final, np.maximum(start_day, 0.0), np.nan)

    month = np.full(a, -1, dtype=np.int64)
    ok = is_final
    month[ok] = np.searchsorted(starts, start_day[ok], side="right") - 1

    by_cust = np.full(n, -1, dtype=np.int64)
    by_cust[cust_row[ok]] = month[ok]
    return start_day, disb, by_cust


def build_clock(view: BookView, att: Attempts, last_stage: np.ndarray,
                step: np.ndarray, timeout: np.ndarray, is_final: np.ndarray,
                final_start_day: np.ndarray, final_disburse_day: np.ndarray,
                p_gate: np.ndarray, alpha: np.ndarray,
                rng: np.random.Generator) -> Funnel:
    """Lay every attempt on the calendar, in chronological, non-overlapping order.

    Three rules, in priority order:

    1. a converter's final attempt is **pinned** — its disbursement instant is
       the book's ``event_month`` and nothing may move it;
    2. two attempts by the same customer never overlap: a later attempt starts
       after the earlier one closed, plus a return gap; an earlier attempt that
       would run into a pinned final one is *compressed* instead;
    3. nothing happens after the panel ends.  An attempt still open on the last
       day is ``in_flight`` — no ``abandoned_at``, no ``disbursed_at``, and only
       the stages it had actually reached are visible.  That population is real:
       it is the live drop-off queue an RM would be working today.
    """
    a = len(att)
    starts, lengths = month_day_offsets(view.anchor, view.months)
    panel_end = float(starts[-1] + lengths[-1])
    n_stages = len(STAGES)

    # ---- where each attempt would like to begin ---------------------------- #
    hour = np.clip(rng.normal(
        np.array([START_HOUR_FRAC[c] for c in CHANNELS])[att.channel_idx], START_HOUR_SD), 0.02, 0.98)
    within = rng.random(a) * np.maximum(lengths[att.ref_month] - 1.0, 0.5)
    started = starts[att.ref_month] + within + hour
    started = np.where(is_final, final_start_day, started)
    gap = np.maximum(rng.gamma(RETURN_GAP_SHAPE, RETURN_GAP_MEAN_DAYS / RETURN_GAP_SHAPE, a),
                     RETURN_GAP_MIN_DAYS)
    length = journey_length(step, timeout, last_stage)

    # ---- forward pass over slots (at most three), vectorised across customers #
    prev_end = np.full(view.n, -np.inf)
    for k in range(int(att.slot.max()) + 1):
        sel = np.flatnonzero(att.slot == k)
        rows = att.cust_row[sel]
        s = started[sel]
        if k > 0:
            s = np.maximum(s, prev_end[rows] + gap[sel])
        started[sel] = np.where(is_final[sel], started[sel], s)
        prev_end[rows] = started[sel] + length[sel]

    # ---- compress anything that would collide with the next attempt -------- #
    # the table is built as repeat(cust) x slot, so a customer's next attempt is
    # the next row whenever the customer id repeats.
    next_start = np.full(a, np.inf)
    same = np.zeros(a, dtype=bool)
    same[:-1] = att.cust_row[1:] == att.cust_row[:-1]
    next_start[:-1] = np.where(same[:-1], started[1:], np.inf)
    room = np.maximum(next_start - started - PRIOR_CLEARANCE_DAYS, 0.05)
    squeeze = np.minimum(1.0, room / np.maximum(length, 1e-9))
    step = step * squeeze[:, None]
    timeout = timeout * squeeze[:, None]
    length = journey_length(step, timeout, last_stage)

    # ---- stage entry instants ---------------------------------------------- #
    idx = np.arange(N_GATES)[None, :]
    advanced = idx < last_stage[:, None]
    entry = started[:, None] + np.concatenate(
        [np.zeros((a, 1)), np.cumsum(step * advanced, axis=1)], axis=1)
    entry[is_final, -1] = final_disburse_day[is_final]          # exactly the book's instant
    reached = np.arange(n_stages)[None, :] <= last_stage[:, None]
    entry = np.where(reached, entry, np.nan)

    terminal = started + length
    disbursed = last_stage == n_stages - 1

    # ---- truncate at the panel end ----------------------------------------- #
    visible_ok = reached & (np.nan_to_num(entry, nan=np.inf) <= panel_end)
    visible = np.clip(visible_ok.sum(axis=1) - 1, 0, last_stage)
    truncated = (~disbursed) & (terminal > panel_end)
    last_stage_raw = last_stage.copy()
    last_stage = np.where(truncated, visible, last_stage).astype(np.int64)
    reached = np.arange(n_stages)[None, :] <= last_stage[:, None]
    entry = np.where(reached, entry, np.nan)
    outcome = np.where(disbursed, "disbursed", np.where(truncated, "in_flight", "abandoned"))
    terminal = np.where(truncated, np.nan, terminal)

    # ---- time spent in the stage the attempt stopped at --------------------- #
    stop = np.minimum(last_stage, N_GATES - 1)
    stalled = timeout[np.arange(a), stop]
    censored = panel_end - entry[np.arange(a), stop]
    time_in_last = np.where(disbursed, np.nan, np.where(truncated, censored, stalled))

    # ---- RM contact and the moment the fee cleared -------------------------- #
    w = window_days(att.product_idx)
    lead = rng.random(a) * CONTACT_LEAD_FRAC * w
    end_for_contact = np.where(np.isnan(terminal), panel_end, terminal)
    mid = started + rng.random(a) * np.maximum(end_for_contact - started, 0.0)
    is_rm_call = att.channel_idx == CHANNELS.index("rm-call")
    contact = np.where(att.rm_contacted, np.where(is_rm_call, started - lead, mid), np.nan)

    fee_gate = STAGES.index("fee")
    fee_paid_day = np.where(last_stage > fee_gate, entry[:, fee_gate + 1], np.nan)

    return Funnel(
        p_gate=p_gate, p_complete=np.prod(p_gate, axis=1), alpha=alpha,
        last_stage=last_stage, last_stage_raw=last_stage_raw, entry_day=entry, step_days=step,
        time_in_last_stage=time_in_last, started_day=started, terminal_day=terminal,
        outcome=outcome, rm_contact_day=contact, fee_paid_day=fee_paid_day,
        panel_end_day=panel_end,
    )
