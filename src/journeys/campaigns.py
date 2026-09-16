"""SD-S6 — campaign and contact history, fatigue, and the suppression rule.

Why this module exists
----------------------
A prospect-assist model that ignores what the bank has *already* done to a
customer is a model that will cheerfully tell an RM to make the fourth call this
month to somebody who declined the last three.  Two mechanisms are generated
here, and both are causal, not decorative:

**Fatigue.**  Every marketing touch in the trailing 30 days multiplies the
customer's probability of responding — and, downstream in :mod:`journeys.labels`,
their probability of returning to an abandoned application — by
:data:`FATIGUE_DECAY`.  The decay is *geometric in the trailing-30-day count*::

    fatigue(k) = FATIGUE_DECAY ** k          k = contacts in the trailing 30 days

so k = 0 -> 1.00, k = 1 -> 0.72, k = 2 -> 0.52, k = 3 -> 0.37, k = 4 -> 0.27.
Nothing older than 30 days counts: the window is a hard edge, not a half-life, so
that the feature ``contacts_30d`` the model sees is exactly the quantity that
drove the behaviour.

**Suppression.**  A row of the drop-off population is *not contactable* if any of
eight conditions holds.  They are evaluated in a fixed priority order and the
first match wins, which is what makes ``suppression_reason`` a single, mutually
exclusive enum rather than a set:

==  ===========================  ===========================================
#   reason                       fires when
==  ===========================  ===========================================
1   ``deceased``                 the customer died before ``as_at``
2   ``no_marketing_consent``     ``consent_marketing = 0``, or they opted out
                                 of a campaign before ``as_at``
3   ``dnd``                      the customer is on the do-not-disturb list
4   ``account_dormant``          the CASA account went dormant before ``as_at``
5   ``application_in_flight``    an application is open with the bank right now
6   ``recent_decline``           they declined a campaign in the last
                                 :data:`DECLINE_COOLOFF_DAYS` days
7   ``recent_contact``           last touched fewer than
                                 :data:`CONTACT_COOLOFF_DAYS` days ago
8   ``already_holds_product``    the product their need points at is one they
                                 already hold, and nothing else clears the
                                 pitch floor
==  ===========================  ===========================================

Field names follow ``data/bank/SCHEMA.md``: ``consent_marketing``, ``dnd``,
``campaign_contacts_6m``, ``last_contact_date``, ``holdings`` (which is where
``already_holds_product`` comes from in the platform contract).  The reasons the
bank's own APIs would supply — arrears from 402 ``dpd`` / ``npaStatus`` — are
**not** modelled here: SANKET's book is a liability book with no loan
performance in it.  That gap is written down in ``DATA_CARD.md`` §12.6 rather
than faked.

Point-in-time safety
--------------------
Every function in this module takes an ``as_at`` (in panel days) and reads only
campaign rows with ``sent_at <= as_at``.  There is no other way to call them:
the counters are computed by ``searchsorted`` over a customer-keyed, day-sorted
array, so "everything before T" is the only query the data structure supports.

Every parameter below is ``assumed``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from book.products import PRODUCTS

from .bookview import BookView
from .shoppers import ShopperLatents, sigmoid

# --------------------------------------------------------------------------- #
# vocabulary
# --------------------------------------------------------------------------- #

#: Outbound marketing channels.  ``rm-call`` is the expensive one and the one
#: the SANKET queue is actually rationing.
CAMPAIGN_CHANNELS: tuple[str, ...] = ("sms", "email", "rm-call")

#: What came back.  ``no_response`` is by far the most common; ``opted_out`` is
#: absorbing and withdraws marketing consent from that instant on.
RESPONSES: tuple[str, ...] = ("no_response", "opened", "engaged", "declined", "opted_out")

#: The suppression enum, in priority order.  ``none`` is index 0 and means the
#: row is contactable.  Exhaustive and mutually exclusive by construction:
#: :func:`suppression_for_rows` returns the first match.
SUPPRESSION_REASONS: tuple[str, ...] = (
    "none",
    "deceased",
    "no_marketing_consent",
    "dnd",
    "account_dormant",
    "application_in_flight",
    "recent_decline",
    "recent_contact",
    "already_holds_product",
)
REASON_INDEX: dict[str, int] = {r: i for i, r in enumerate(SUPPRESSION_REASONS)}

# --------------------------------------------------------------------------- #
# parameters — all ``assumed``
# --------------------------------------------------------------------------- #

#: Monthly campaign intensity: contacts ~ Poisson(lambda_i * wave_m).  The
#: per-customer lambda is log-normal because real campaign lists are not uniform
#: — the same "hot" names get pushed month after month, which is precisely the
#: over-contacting the fatigue term exists to punish.
CAMPAIGN_LAMBDA_MEDIAN = 0.14
CAMPAIGN_LAMBDA_SIGMA = 0.90
CAMPAIGN_LAMBDA_CAP = 1.20
#: Campaigns are bursty: a product push lands on everybody in the same month.
CAMPAIGN_WAVE = (0.55, 1.85)
#: Channel mix of outbound touches.  SMS is cheap and dominates.
CHANNEL_MIX = (0.50, 0.32, 0.18)

#: **Fatigue.**  Each contact in the trailing 30 days multiplies the response
#: probability (and the return probability in :mod:`journeys.labels`) by this.
FATIGUE_DECAY = 0.72
#: Floor, so an over-contacted customer never becomes exactly unreachable.
FATIGUE_FLOOR = 0.12

#: Response logit.  Commitment raises it, window shopping lowers it, and the
#: RM call outperforms the two digital channels by a wide margin — which is the
#: reason an RM's hour is the scarce resource this whole product rations.
RESPONSE_BASE = -1.55
RESPONSE_CHANNEL = {"sms": -0.55, "email": -0.80, "rm-call": 0.95}
RESPONSE_COMMITMENT = 0.55
RESPONSE_SHOPPER = -0.70
#: Conditional on responding at all: what the response was.
RESPONSE_SPLIT = {"opened": 0.46, "engaged": 0.30, "declined": 0.22, "opted_out": 0.02}

#: Cool-offs used by the suppression rule.
CONTACT_COOLOFF_DAYS = 7.0
DECLINE_COOLOFF_DAYS = 90.0

#: Mortality and dormancy.  The book models neither, so both are drawn here and
#: declared as a known unrealism (DATA_CARD §12.6): a real bank would read them
#: off the CIF, not simulate them.
DECEASED_SHARE = 0.0015
DORMANT_SHARE = 0.012

#: How sharply the "what would we pitch this customer" ranking concentrates on
#: eligibility-weighted latent intent, and how close the runner-up has to be
#: before a held top product stops suppressing the row.
PITCH_SHARPNESS = 1.0
PITCH_FLOOR = 0.35

#: Products a customer can already hold, and the book column that says so.
HELD_COLUMN = {"home": "has_home_loan", "auto": "has_auto_emi"}

#: Multiplier used to fold a customer id into a sortable ``cust * KEY_SCALE +
#: day`` key.  Larger than any panel-day offset by three orders of magnitude.
_KEY_SCALE = 1_000_000.0

CAMPAIGN_COLUMNS = [
    "campaign_id", "cust_id", "sent_at", "sent_day", "month",
    "channel", "product", "response", "contacts_30d_before", "fatigue",
]


# --------------------------------------------------------------------------- #
# customer-level flags the book does not carry
# --------------------------------------------------------------------------- #

@dataclass
class ContactState:
    """Everything the suppression rule and the contact features need, as arrays.

    ``*_day`` fields are panel-day offsets, ``inf`` where the event never
    happens.  ``_key`` fields are ``cust_row * _KEY_SCALE + day`` sorted
    ascending, which is what makes "count the contacts before T for customer i"
    a single ``searchsorted``.
    """

    n: int
    consent: np.ndarray            # (N,) int8, the book's marketing consent
    dnd: np.ndarray                # (N,) int8
    deceased_day: np.ndarray       # (N,) float
    dormant_day: np.ndarray        # (N,) float
    opt_out_day: np.ndarray        # (N,) float
    contact_key: np.ndarray        # (C,) sorted contact keys
    contact_product: np.ndarray    # (C,) product index, aligned to contact_key
    decline_key: np.ndarray        # (D,) sorted keys of declines / opt-outs
    open_key: np.ndarray           # (A,) sorted attempt keys (cust, start day)
    open_max_term: np.ndarray      # (A,) running max terminal day within customer
    open_cust: np.ndarray          # (A,) customer row of each attempt
    held: np.ndarray               # (N, P) bool, products already on the books
    pitch_score: np.ndarray        # (N, P, M) eligibility-weighted latent intent


def draw_flags(view: BookView, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """``(deceased_day, dormant_day)`` in panel days, ``inf`` where it never happens.

    Neither is derivable from the book — every customer in it has a credit in
    every month — so both are drawn.  Declared in DATA_CARD §12.6.
    """
    n = view.n
    end = float(np.sum(_month_lengths(view)))
    dead = rng.random(n) < DECEASED_SHARE
    dormant = rng.random(n) < DORMANT_SHARE
    deceased_day = np.where(dead, rng.uniform(0.0, end, n), np.inf)
    dormant_day = np.where(dormant, rng.uniform(0.0, end, n), np.inf)
    return deceased_day, dormant_day


def _month_lengths(view: BookView) -> np.ndarray:
    first = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    starts = pd.date_range(first, periods=view.months + 1, freq="MS")
    return np.diff((starts - first).days.to_numpy().astype(np.float64))


# --------------------------------------------------------------------------- #
# the campaign history
# --------------------------------------------------------------------------- #

def build_campaigns(view: BookView, lat: ShopperLatents, deceased_day: np.ndarray,
                    pitch: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    """One row per outbound marketing touch, over the whole panel.

    Customers without marketing consent, and customers on the DND list, receive
    nothing — which is why they have no campaign history at all, and why the
    corresponding suppression reasons are read off the book rather than off this
    table.
    """
    n, m = view.n, view.months
    lengths = _month_lengths(view)
    starts = np.r_[0.0, np.cumsum(lengths)[:-1]]

    consent = view.book["consent"].to_numpy(dtype=np.int8)
    dnd = view.book["dnd"].to_numpy(dtype=np.int8)
    mailable = (consent == 1) & (dnd == 0)

    lam = np.clip(CAMPAIGN_LAMBDA_MEDIAN * np.exp(rng.normal(0.0, CAMPAIGN_LAMBDA_SIGMA, n)),
                  0.0, CAMPAIGN_LAMBDA_CAP) * mailable
    wave = rng.uniform(*CAMPAIGN_WAVE, m)
    counts = rng.poisson(lam[:, None] * wave[None, :])            # (N, M)

    # nothing is sent to a customer who has died
    month_end = starts + lengths
    counts[deceased_day[:, None] < month_end[None, :]] = 0

    total = int(counts.sum())
    cust_row = np.repeat(np.arange(n), counts.sum(axis=1))
    month = np.repeat(np.tile(np.arange(m), n), counts.reshape(-1))
    day = starts[month] + rng.random(total) * lengths[month]

    order = np.lexsort((day, cust_row))
    cust_row, month, day = cust_row[order], month[order], day[order]

    # ---- fatigue: contacts in the 30 days before *this* one ---------------- #
    key = cust_row * _KEY_SCALE + day
    lo = np.searchsorted(key, cust_row * _KEY_SCALE + (day - 30.0), side="left")
    contacts_before = np.arange(total) - lo
    fatigue = np.maximum(FATIGUE_DECAY ** contacts_before, FATIGUE_FLOOR)

    # ---- channel, product pitched, response -------------------------------- #
    ch = rng.choice(len(CAMPAIGN_CHANNELS), size=total, p=list(CHANNEL_MIX))
    prod = _sample_rows(rng, pitch[cust_row, :, month].astype(np.float64))

    ch_eff = np.array([RESPONSE_CHANNEL[c] for c in CAMPAIGN_CHANNELS])[ch]
    p_resp = sigmoid(RESPONSE_BASE + ch_eff
                     + RESPONSE_COMMITMENT * lat.commitment[cust_row]
                     + RESPONSE_SHOPPER * lat.tilt[cust_row]) * fatigue
    responded = rng.random(total) < p_resp
    kinds = list(RESPONSE_SPLIT)
    pick = rng.choice(len(kinds), size=total, p=[RESPONSE_SPLIT[k] for k in kinds])
    response = np.where(responded, np.array(kinds, dtype=object)[pick], "no_response")

    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    ts = (base + pd.to_timedelta(day, unit="D")).round("s")
    return pd.DataFrame({
        "campaign_id": [f"CM-{i:08d}" for i in range(total)],
        "cust_id": view.book["cust_id"].to_numpy(dtype=object)[cust_row],
        "sent_at": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "sent_day": np.round(day, 4),
        "month": month.astype(np.int16),
        "channel": np.array(CAMPAIGN_CHANNELS, dtype=object)[ch],
        "product": np.array(PRODUCTS, dtype=object)[prod],
        "response": response,
        "contacts_30d_before": contacts_before.astype(np.int16),
        "fatigue": np.round(fatigue, 4),
    })[CAMPAIGN_COLUMNS]


def pitch_scores(view: BookView) -> np.ndarray:
    """``(N, P, M)`` eligibility-weighted latent intent — what the bank would pitch.

    Built once per run and passed around: at 60,000 x 6 x 30 it is 43 MB in
    float32 and there is no reason to hold two of them.
    """
    s = np.power(np.maximum(view.intent, np.float32(1e-9)), PITCH_SHARPNESS)
    return (s * view.eligibility[:, :, None].astype(np.float32)).astype(np.float32)


def _sample_rows(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    c = np.cumsum(weights, axis=1)
    u = rng.random(len(weights)) * np.maximum(c[:, -1], 1e-12)
    return (c < u[:, None]).sum(axis=1).clip(0, weights.shape[1] - 1)


# --------------------------------------------------------------------------- #
# the state the suppression rule reads
# --------------------------------------------------------------------------- #

def build_state(view: BookView, campaigns: pd.DataFrame, journeys: pd.DataFrame,
                deceased_day: np.ndarray, dormant_day: np.ndarray,
                pitch: np.ndarray) -> ContactState:
    """Assemble everything :func:`suppression_for_rows` needs, once."""
    n = view.n
    row_of = {c: i for i, c in enumerate(view.book["cust_id"].to_numpy(dtype=object))}
    pidx = {p: i for i, p in enumerate(PRODUCTS)}

    c_row = campaigns.cust_id.map(row_of).to_numpy(dtype=np.int64)
    c_day = campaigns.sent_day.to_numpy(dtype=np.float64)
    contact_key = c_row * _KEY_SCALE + c_day                     # already sorted
    contact_product = campaigns["product"].map(pidx).to_numpy(dtype=np.int64)

    declined = campaigns.response.isin(("declined", "opted_out")).to_numpy()
    decline_key = contact_key[declined]

    opted = campaigns.response.to_numpy() == "opted_out"
    opt_out_day = np.full(n, np.inf)
    np.minimum.at(opt_out_day, c_row[opted], c_day[opted])

    j_row = journeys.customer_id.map(row_of).to_numpy(dtype=np.int64)
    started = _days(journeys.started_at, view)
    term = np.where(journeys.outcome.to_numpy() == "in_flight", np.inf,
                    _days(journeys.abandoned_at.where(journeys.abandoned_at != "")
                          .fillna(journeys.disbursed_at), view))
    # sorted by (customer, start) with a running max of the terminal day, so
    # "is anything of this customer's open at T" is two searchsorteds
    o = np.lexsort((started, j_row))
    j_row, started, term = j_row[o], started[o], term[o]
    open_max = _grouped_cummax(j_row, term)

    held = np.zeros((n, len(PRODUCTS)), dtype=bool)
    for p, col in HELD_COLUMN.items():
        held[:, pidx[p]] = view.book[col].to_numpy().astype(bool)

    return ContactState(
        n=n,
        consent=view.book["consent"].to_numpy(dtype=np.int8),
        dnd=view.book["dnd"].to_numpy(dtype=np.int8),
        deceased_day=deceased_day, dormant_day=dormant_day, opt_out_day=opt_out_day,
        contact_key=contact_key, contact_product=contact_product, decline_key=decline_key,
        open_key=j_row * _KEY_SCALE + started, open_max_term=open_max, open_cust=j_row,
        held=held, pitch_score=pitch,
    )


def _grouped_cummax(group: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Running maximum of ``x`` within each run of equal ``group`` values."""
    out = np.maximum.accumulate(x)
    if len(x) == 0:
        return out
    first = np.flatnonzero(np.r_[True, group[1:] != group[:-1]])
    # restart the accumulation at every group boundary
    for lo, hi in zip(first, np.r_[first[1:], len(x)]):
        out[lo:hi] = np.maximum.accumulate(x[lo:hi])
    return out


def _days(s: pd.Series, view: BookView) -> np.ndarray:
    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    t = pd.to_datetime(s.replace("", None), format="mixed")
    return ((t - base).dt.total_seconds() / 86400.0).to_numpy(dtype=np.float64)


# --------------------------------------------------------------------------- #
# point-in-time contact counters
# --------------------------------------------------------------------------- #

def counts_before(key: np.ndarray, cust_row: np.ndarray, as_at_day: np.ndarray,
                  window: float | None = None) -> np.ndarray:
    """How many rows of ``key`` belong to each customer strictly before ``as_at``.

    ``window`` limits the count to the trailing ``window`` days.  ``key`` must be
    ``cust_row * _KEY_SCALE + day``, sorted ascending — the only shape this
    module ever builds, and the reason a future-dated row cannot be counted.
    """
    hi = np.searchsorted(key, cust_row * _KEY_SCALE + as_at_day, side="right")
    if window is None:
        lo = np.searchsorted(key, cust_row * _KEY_SCALE, side="left")
    else:
        lo = np.searchsorted(key, cust_row * _KEY_SCALE + (as_at_day - window), side="left")
    return hi - lo


def last_before(key: np.ndarray, cust_row: np.ndarray, as_at_day: np.ndarray) -> np.ndarray:
    """Day of the most recent row of ``key`` before ``as_at``; ``-inf`` if none."""
    hi = np.searchsorted(key, cust_row * _KEY_SCALE + as_at_day, side="right")
    first = np.searchsorted(key, cust_row * _KEY_SCALE, side="left")
    ok = hi > first
    out = np.full(len(cust_row), -np.inf)
    idx = np.maximum(hi - 1, 0)
    out[ok] = key[idx[ok]] - cust_row[ok] * _KEY_SCALE
    return out


def contact_features_for_rows(st: ContactState, cust_row: np.ndarray,
                              as_at_day: np.ndarray) -> dict[str, np.ndarray]:
    """``contacts_30d`` / ``contacts_90d`` / ``campaign_contacts_6m`` /
    ``last_contact_days`` / ``last_campaign_product`` / ``fatigue``, as at each row."""
    last_day = last_before(st.contact_key, cust_row, as_at_day)
    hi = np.searchsorted(st.contact_key, cust_row * _KEY_SCALE + as_at_day, side="right")
    first = np.searchsorted(st.contact_key, cust_row * _KEY_SCALE, side="left")
    prod = np.where(hi > first, st.contact_product[np.maximum(hi - 1, 0)], -1)
    c30 = counts_before(st.contact_key, cust_row, as_at_day, 30.0)
    return {
        "contacts_30d": c30.astype(np.int16),
        "contacts_90d": counts_before(st.contact_key, cust_row, as_at_day, 90.0).astype(np.int16),
        "campaign_contacts_6m": counts_before(
            st.contact_key, cust_row, as_at_day, 183.0).astype(np.int16),
        "last_contact_days": np.where(np.isfinite(last_day), as_at_day - last_day, np.nan),
        "last_campaign_product": np.where(
            prod >= 0, np.array(PRODUCTS + ("",), dtype=object)[prod], ""),
        "fatigue": np.maximum(FATIGUE_DECAY ** c30, FATIGUE_FLOOR),
    }


# --------------------------------------------------------------------------- #
# the suppression rule
# --------------------------------------------------------------------------- #

def suppression_for_rows(st: ContactState, cust_row: np.ndarray, as_at_day: np.ndarray,
                         month: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(suppressed, reason_index)`` for arbitrary ``(customer, instant)`` rows.

    Priority order is :data:`SUPPRESSION_REASONS`; the first condition that holds
    is the recorded reason, so the enum is mutually exclusive by construction and
    a row is suppressed **iff** its reason is not ``none``.
    """
    k = len(cust_row)
    reason = np.zeros(k, dtype=np.int8)

    def mark(name: str, cond: np.ndarray) -> None:
        np.copyto(reason, REASON_INDEX[name], where=(reason == 0) & cond)

    mark("deceased", st.deceased_day[cust_row] <= as_at_day)
    mark("no_marketing_consent",
         (st.consent[cust_row] == 0) | (st.opt_out_day[cust_row] <= as_at_day))
    mark("dnd", st.dnd[cust_row] == 1)
    mark("account_dormant", st.dormant_day[cust_row] <= as_at_day)

    open_now = _open_application(st, cust_row, as_at_day)
    mark("application_in_flight", open_now)

    last_decline = last_before(st.decline_key, cust_row, as_at_day)
    mark("recent_decline", (as_at_day - last_decline) < DECLINE_COOLOFF_DAYS)

    last_contact = last_before(st.contact_key, cust_row, as_at_day)
    mark("recent_contact", (as_at_day - last_contact) < CONTACT_COOLOFF_DAYS)

    mark("already_holds_product", _nothing_left_to_pitch(st, cust_row, month))
    return reason != 0, reason


def _open_application(st: ContactState, cust_row: np.ndarray, as_at_day: np.ndarray) -> np.ndarray:
    """True where the customer has an attempt open at ``as_at``.

    ``open_max_term`` is the running maximum terminal day over that customer's
    attempts in start order, so the latest attempt that had *started* by ``as_at``
    carries the furthest terminal day of all of them: the customer is mid-
    application iff that maximum is still in the future.
    """
    hi = np.searchsorted(st.open_key, cust_row * _KEY_SCALE + as_at_day, side="right")
    first = np.searchsorted(st.open_key, cust_row * _KEY_SCALE, side="left")
    started_any = hi > first
    term = np.where(started_any, st.open_max_term[np.maximum(hi - 1, 0)], -np.inf)
    return started_any & (term > as_at_day)


def _nothing_left_to_pitch(st: ContactState, cust_row: np.ndarray,
                           month: np.ndarray) -> np.ndarray:
    """The top-ranked product is already held and no runner-up clears the floor."""
    s = st.pitch_score[cust_row, :, month]                       # (k, P)
    top = s.argmax(axis=1)
    held_top = st.held[cust_row, top]
    unheld = np.where(st.held[cust_row], -np.inf, s)
    best_unheld = unheld.max(axis=1)
    top_score = s[np.arange(len(top)), top]
    return held_top & ~(best_unheld >= PITCH_FLOOR * np.maximum(top_score, 1e-12))


def reason_names(reason: np.ndarray) -> np.ndarray:
    """Enum indices -> the strings written to ``labels.csv``."""
    return np.array(SUPPRESSION_REASONS, dtype=object)[reason]
