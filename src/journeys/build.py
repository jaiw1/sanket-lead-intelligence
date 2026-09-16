"""CLI entry point: assemble and write the SANKET application-journey layer.

    python3 src/make_journeys.py                      # reads data/, writes data/
    python3 src/make_journeys.py --seed 8
    python3 src/make_journeys.py --book-dir /tmp/b --out /tmp/b
    python3 src/make_journeys.py --seeds 7,8,9,10,11   # re-solve on 5 seeds, write nothing

Outputs (into ``--out``, default ``data/``)

``journeys.csv``        one row per application attempt
``journey_events.csv``  one row per stage transition, with its timestamp
``journey_truth.csv``   one row per attempt of latent drivers — **never a feature**
``campaigns.csv``       one row per outbound marketing touch (SD-S6)
``labels.csv``          one row per (customer, month) of the drop-off population,
                        with the pre-registered label (SD-S4)
``label_truth.csv``     the label layer's latents — **never a feature**
``journey_params.json`` the solved intercepts, the solved contact effect theta and
                        S/N knob, and every realised headline number

The book must already exist (``python3 src/make_book.py``): the journey layer
reads it, never regenerates it, and never contradicts it.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from book.products import DECISION_WINDOW_DAYS, PRODUCTS

from . import CHANNELS, N_GATES, ROOT, STAGES, JourneyConfig, substream
from . import attempts as at
from . import bookview, campaigns as cp, funnel as fn, labels as lb, shoppers as sh
from .attempts import Attempts

#: Where inside the Eligibility conversation the fee is quoted and the document
#: checklist is read out.  Both refusals are recorded then — which is what makes
#: them observable four stages before the fee is actually due, and what stops the
#: two signals being a pure survivorship artefact of reaching the Fee stage.
DISCLOSURE_POINT = 0.5

#: Tolerance on the per-stage abandonment shares, in share points.
STAGE_SHARE_TOL = 0.06

JOURNEY_COLUMNS = [
    "customer_id", "attempt_id", "attempt_seq", "product", "channel",
    "started_at", "start_month", "last_stage", "last_stage_idx", "last_stage_at",
    "abandoned_at", "disbursed_at", "outcome", "journey_days", "decision_window_days",
    "amount_requested", "amount_offered",
    "fee_amount", "fee_paid", "fee_paid_at", "fee_balk", "fee_balk_at",
    "docs_requested", "docs_supplied", "doc_refusal", "doc_refusal_at",
    "answers_blank_ratio", "income_shared", "stated_income_vs_book_ratio",
    "revisits_30d", "products_viewed_30d",
    "rm_contacted", "rm_contacted_at", "rm_id",
] + [f"time_in_stage_{s}" for s in STAGES[:N_GATES]]

#: Column-name shim for ``validation/runners/07_leakage.py``, whose ``INPUTS``
#: were written down (pre-registered, ahead of this generator) as ``cust_id,
#: stage_reached, start_ts, abandon_ts, disburse_ts, blank_ratio,
#: income_refused, revisit_count``.  Same values, the spelling that runner
#: expects.  Delete both these columns and this comment when runner 07 lands.
ALIAS_COLUMNS = {
    "cust_id": "customer_id", "stage_reached": "last_stage", "start_ts": "started_at",
    "abandon_ts": "abandoned_at", "disburse_ts": "disbursed_at",
    "blank_ratio": "answers_blank_ratio", "revisit_count": "revisits_30d",
}


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def _timestamps(days: np.ndarray, base: pd.Timestamp) -> pd.Series:
    """Day offsets from the panel start -> second-resolution ISO strings."""
    ts = base + pd.to_timedelta(np.asarray(days, dtype=np.float64), unit="D")
    return pd.Series(ts).dt.round("s").dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")


def generate(cfg: JourneyConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Build ``(journeys, events, truth, params)``."""
    _view, _lat, j, e, t, p = _core(cfg)
    return j, e, t, p


def _core(cfg: JourneyConfig) -> tuple[bookview.BookView, sh.ShopperLatents,
                                       pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """The journey layer, plus the book view and latents SD-S4/SD-S6 need."""
    view = bookview.load(cfg.book_dir)
    r_shop = substream(cfg.seed, "shoppers")
    r_app = substream(cfg.seed, "applicants")
    r_att = substream(cfg.seed, "attempts")
    r_sig = substream(cfg.seed, "signals")
    r_fun = substream(cfg.seed, "funnel")
    r_time = substream(cfg.seed, "timing")

    # ---- 1. who applies, how often ---------------------------------------- #
    lat = sh.build_latents(view, r_shop)
    cust_row, slot, n_attempts = at.select(cfg, view, lat, r_app)
    is_final = view.is_converter[cust_row] & (slot == n_attempts - 1)

    # ---- 2. the shopper latent, solved against the realised drop-off set --- #
    lat = sh.realise(lat, sh.solve_base(lat, cust_row[~is_final],
                                        cfg.target_shopper_share_of_dropoffs), r_shop)

    # ---- 3. product, channel, then the two signals that change the clock --- #
    product, ineligible = at.assign_product(cfg, view, cust_row, is_final, r_att)
    channel = at.assign_channel(view, cust_row, lat, r_att)
    att = Attempts(cust_row=cust_row, slot=slot, n_attempts=n_attempts,
                   designated_disburse=is_final, product_idx=product, channel_idx=channel,
                   ref_month=np.zeros(len(cust_row), dtype=np.int64), ineligible=ineligible)
    att = at.build_stall_signals(view, att, lat, r_sig)

    # ---- 4. the clock's raw material, then the calendar -------------------- #
    step, timeout = fn.draw_durations(att, r_time)
    final_start_day, final_disburse_day, final_month = fn.converter_start_month(
        view, cust_row, is_final, step, r_time)
    att.ref_month = at.assign_month(cfg, view, cust_row, slot, n_attempts, is_final,
                                    product, final_month, r_att)
    att = at.build_month_signals(view, att, lat, r_sig)

    # ---- 5. the hazard, its solved intercepts, and the sampled path -------- #
    z = fn.gate_logits(view, att, lat)
    alpha = fn.solve_intercepts(z, ~is_final, float(is_final.mean()))
    p = sh.sigmoid(z + alpha)
    last_stage = fn.sample_paths(p, is_final, r_fun)

    f = fn.build_clock(view, att, last_stage, step, timeout, is_final,
                       final_start_day, final_disburse_day, p, alpha, r_time)

    # ---- 6. drop anything the panel has no room for ------------------------ #
    keep = f.started_day < f.panel_end_day
    if not keep.all():
        att, f = _subset(att, f, keep)

    return (view, lat, *_frames(cfg, view, att, f, lat))


# --------------------------------------------------------------------------- #
# SD-S6 + SD-S4: campaign history, the drop-off population and its labels
# --------------------------------------------------------------------------- #

@dataclass
class Bundle:
    """Everything one run of the journey lane produces."""

    journeys: pd.DataFrame
    events: pd.DataFrame
    truth: pd.DataFrame
    campaigns: pd.DataFrame
    labels: pd.DataFrame
    label_truth: pd.DataFrame
    params: dict


def generate_all(cfg: JourneyConfig) -> Bundle:
    """The journey layer *and* the campaign / label layers on top of it."""
    view, lat, journeys, events, truth, params = _core(cfg)

    pitch = cp.pitch_scores(view)
    r_camp = substream(cfg.seed, "campaigns")
    r_lab = substream(cfg.seed, "labels")

    deceased_day, dormant_day = cp.draw_flags(view, r_camp)
    campaigns = cp.build_campaigns(view, lat, deceased_day, pitch, r_camp)
    state = cp.build_state(view, campaigns, journeys, deceased_day, dormant_day, pitch)
    labels, label_truth, lparams = lb.generate(
        view, lat, journeys, state, pitch, campaigns, r_lab)

    params["campaigns"] = {
        "contacts": int(len(campaigns)),
        "contacts_per_customer_per_month": round(len(campaigns) / (view.n * view.months), 4),
        "channel_mix": {k: round(v, 4) for k, v in
                        campaigns.channel.value_counts(normalize=True).items()},
        "response_mix": {k: round(v, 4) for k, v in
                         campaigns.response.value_counts(normalize=True).items()},
        "fatigue_decay": cp.FATIGUE_DECAY,
        "contact_cooloff_days": cp.CONTACT_COOLOFF_DAYS,
        "decline_cooloff_days": cp.DECLINE_COOLOFF_DAYS,
    }
    params["labels"] = lparams
    return Bundle(journeys=journeys, events=events, truth=truth, campaigns=campaigns,
                  labels=labels, label_truth=label_truth, params=params)


def _subset(att: Attempts, f: fn.Funnel, keep: np.ndarray) -> tuple[Attempts, fn.Funnel]:
    """Drop attempts (re-numbering the per-customer sequence)."""
    def take(x):
        return x[keep] if isinstance(x, np.ndarray) and len(x) == len(keep) else x
    att2 = Attempts(**{k: take(v) for k, v in att.__dict__.items()})
    counts = np.bincount(att2.cust_row, minlength=att2.cust_row.max() + 1)
    att2.n_attempts = counts[att2.cust_row]
    first = np.flatnonzero(np.r_[True, att2.cust_row[1:] != att2.cust_row[:-1]])
    att2.slot = np.arange(len(att2.cust_row)) - np.repeat(first, counts[att2.cust_row[first]])
    f2 = fn.Funnel(**{k: take(v) for k, v in f.__dict__.items()})
    return att2, f2


def _frames(cfg: JourneyConfig, view: bookview.BookView, att: Attempts, f: fn.Funnel,
            lat: sh.ShopperLatents) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    a = len(att)
    base = pd.Timestamp(year=view.anchor[0], month=view.anchor[1], day=1)
    row = att.cust_row
    last = f.last_stage
    docs_gate, fee_gate = STAGES.index("docs"), STAGES.index("fee")
    w = fn.window_days(att.product_idx)

    # chronological attempt ids, stable for a given seed
    order = np.argsort(f.started_day, kind="stable")
    attempt_id = np.empty(a, dtype=object)
    attempt_id[order] = [f"AP-{i:07d}" for i in range(a)]

    elig_gate = STAGES.index("eligibility")
    reached_elig = last >= elig_gate
    reached_docs = last >= docs_gate
    reached_fee = last >= fee_gate
    passed_docs = last > docs_gate
    passed_fee = last > fee_gate

    docs_supplied = np.where(passed_docs, att.docs_requested, att.docs_supplied_first)
    # the instant the fee quote and the document checklist were put to the
    # customer: part-way through the Eligibility conversation they reached
    elig_dwell = np.where(last > elig_gate, f.step_days[:, elig_gate], f.time_in_last_stage)
    disclosure = f.entry_day[:, elig_gate] + DISCLOSURE_POINT * np.nan_to_num(elig_dwell)
    balk_at = np.where(att.fee_balk & reached_elig, disclosure, np.nan)
    refusal_at = np.where(att.doc_refusal & reached_elig, disclosure, np.nan)

    nan_if = lambda mask, x: np.where(mask, x, np.nan)   # noqa: E731
    j = {
        "customer_id": view.book["cust_id"].to_numpy(dtype=object)[row],
        "attempt_id": attempt_id,
        "attempt_seq": att.slot + 1,
        "product": np.array(PRODUCTS, dtype=object)[att.product_idx],
        "channel": np.array(CHANNELS, dtype=object)[att.channel_idx],
        "started_at": _timestamps(f.started_day, base),
        # the panel month the application actually begins in.  It can be one
        # later than the month whose latents the generator drew it from, when an
        # earlier attempt of the same customer over-ran; the truth file keeps
        # that ``latent_month`` so the difference is auditable, and it is always
        # in the safe direction (older information, never newer).
        "start_month": np.clip(np.searchsorted(
            fn.month_day_offsets(view.anchor, view.months)[0], f.started_day, side="right") - 1,
            0, view.months - 1),
        "last_stage": np.array(STAGES, dtype=object)[last],
        "last_stage_idx": last,
        "last_stage_at": _timestamps(f.entry_day[np.arange(a), last], base),
        "abandoned_at": _timestamps(np.where(f.outcome == "abandoned", f.terminal_day, np.nan), base),
        "disbursed_at": _timestamps(np.where(f.outcome == "disbursed", f.terminal_day, np.nan), base),
        "outcome": f.outcome,
        "journey_days": np.round(f.terminal_day - f.started_day, 3),
        "decision_window_days": w.astype(np.int16),
        "amount_requested": att.amount_requested.astype(np.int64),
        "amount_offered": nan_if(last >= STAGES.index("offer"), att.amount_offered),
        "fee_amount": nan_if(reached_fee, np.full(a, float(at.FEE_AMOUNT))),
        "fee_paid": nan_if(reached_fee, passed_fee.astype(float)),
        "fee_paid_at": _timestamps(f.fee_paid_day, base),
        "fee_balk": nan_if(reached_elig, att.fee_balk.astype(float)),
        "fee_balk_at": _timestamps(balk_at, base),
        "docs_requested": nan_if(reached_docs, att.docs_requested.astype(float)),
        "docs_supplied": nan_if(reached_docs, docs_supplied.astype(float)),
        "doc_refusal": nan_if(reached_elig, att.doc_refusal.astype(float)),
        "doc_refusal_at": _timestamps(refusal_at, base),
        "answers_blank_ratio": np.round(att.blank_ratio, 4),
        "income_shared": att.income_shared.astype(np.int8),
        "stated_income_vs_book_ratio": np.round(att.stated_income_ratio, 4),
        "revisits_30d": att.revisits_30d,
        "products_viewed_30d": att.products_viewed_30d,
        "rm_contacted": att.rm_contacted.astype(np.int8),
        "rm_contacted_at": _timestamps(f.rm_contact_day, base),
        "rm_id": np.full(a, "", dtype=object),          # SM-4 fills this from the roster
    }
    for s in range(N_GATES):
        t = np.where(s < last, f.step_days[:, s], np.where(s == last, f.time_in_last_stage, np.nan))
        j[f"time_in_stage_{STAGES[s]}"] = np.round(t, 3)
    journeys = pd.DataFrame({c: j[c] for c in JOURNEY_COLUMNS})
    for alias, src in ALIAS_COLUMNS.items():
        journeys[alias] = journeys[src]
    journeys["income_refused"] = 1 - journeys["income_shared"]

    # ---- events -------------------------------------------------------------- #
    abandoned = f.outcome == "abandoned"
    counts = last + 1 + abandoned.astype(np.int64)
    idx = np.repeat(np.arange(a), counts)
    k = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    is_terminal = k == (last[idx] + 1)
    kk = np.minimum(k, last[idx])
    occurred = np.where(is_terminal, f.terminal_day[idx], f.entry_day[idx, kk])
    days_in = np.where(is_terminal, f.time_in_last_stage[idx],
                       np.where(k > 0, f.step_days[idx, np.maximum(kk - 1, 0)], np.nan))
    event = np.where(k == 0, "start",
                     np.where(is_terminal, "abandon",
                              np.where(kk == len(STAGES) - 1, "disburse", "advance")))
    events = pd.DataFrame({
        "attempt_id": attempt_id[idx],
        "customer_id": journeys["customer_id"].to_numpy()[idx],
        "seq": k,
        "from_stage": np.where(k == 0, "", np.array(STAGES, dtype=object)[np.maximum(kk - 1, 0)]),
        "to_stage": np.array(STAGES, dtype=object)[kk],
        "event": event,
        "occurred_at": _timestamps(occurred, base),
        "days_in_from_stage": np.round(days_in, 3),
    })
    events.loc[is_terminal, "from_stage"] = np.array(STAGES, dtype=object)[last[idx][is_terminal]]

    # ---- latent truth -------------------------------------------------------- #
    truth = pd.DataFrame({
        "attempt_id": attempt_id,
        "customer_id": j["customer_id"],
        "shopper_truth": lat.truth[row].astype(np.int8),
        "shopper_propensity": np.round(lat.propensity[row], 4),
        "curiosity": np.round(lat.curiosity[row], 4),
        "price_sensitivity": np.round(lat.price_sensitivity[row], 4),
        "return_propensity": np.round(lat.return_propensity[row], 4),
        "book_window_shopper": view.book["window_shopper"].to_numpy()[row].astype(np.int8),
        "is_converter": view.is_converter[row].astype(np.int8),
        "forced_disburse": att.designated_disburse.astype(np.int8),
        "ineligible_product": att.ineligible.astype(np.int8),
        "latent_month": att.ref_month,
        "intent_at_start": np.round(att.intent_at_start, 4),
        "capacity_at_start": np.round(att.capacity_at_start, 4),
        "p_complete": np.round(f.p_complete, 5),
        "fee_balk_latent": att.fee_balk.astype(np.int8),
        "doc_shortfall_latent": att.doc_shortfall.astype(np.int8),
    })

    params = {
        "seed": cfg.seed, "n_customers": int(view.n), "months": int(view.months),
        "stage_intercepts": {STAGES[s]: round(float(f.alpha[s]), 4) for s in range(N_GATES)},
        "shopper_intercept": round(float(lat.base), 4),
        "abandon_share_target": dict(fn.ABANDON_SHARE),
        "decision_window_days": dict(DECISION_WINDOW_DAYS),
    }
    journeys = journeys.sort_values("attempt_id", kind="stable").reset_index(drop=True)
    events = events.sort_values(["attempt_id", "seq"], kind="stable").reset_index(drop=True)
    truth = truth.sort_values("attempt_id", kind="stable").reset_index(drop=True)
    return journeys, events, truth, params


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def check(cfg: JourneyConfig, journeys: pd.DataFrame, events: pd.DataFrame,
          truth: pd.DataFrame, book_dir: Path) -> dict[str, float]:
    """Assert the journey layer is coherent *and* consistent with the book.

    Every number the plan pre-registers for this lane is re-measured here, so a
    generator change that quietly drifts one of them fails the run instead of
    flattering a downstream model.
    """
    book = pd.read_csv(book_dir / "customer_book.csv", engine="pyarrow",
                       usecols=["cust_id", "event_month", "product_canonical"])
    n_book = len(book)
    conv = book.event_month.to_numpy() >= 0

    out = journeys.outcome.to_numpy()
    cid = journeys.customer_id.to_numpy()
    disbursed = out == "disbursed"
    abandoned = out == "abandoned"
    in_flight = out == "in_flight"

    cust_with_attempt = pd.unique(cid)
    abandon_cust = set(pd.unique(cid[abandoned | in_flight]))
    disburse_cust = set(pd.unique(cid[disbursed]))
    recovered = abandon_cust & disburse_cust

    stage_counts = journeys.loc[abandoned, "last_stage"].value_counts(normalize=True)
    stage_share = {s: float(stage_counts.get(s, 0.0)) for s in STAGES[:N_GATES]}

    w = journeys.decision_window_days.to_numpy(dtype=float)
    have_both = disbursed & (journeys.rm_contacted_at.to_numpy() != "")
    dd = pd.to_datetime(journeys.disbursed_at.where(journeys.disbursed_at != ""), format="mixed")
    cc = pd.to_datetime(journeys.rm_contacted_at.where(journeys.rm_contacted_at != ""), format="mixed")
    lag = (dd - cc).dt.total_seconds().to_numpy() / 86400.0
    respect = float(np.mean(lag[have_both] <= w[have_both])) if have_both.any() else float("nan")

    stats = {
        "attempts": float(len(journeys)),
        "customers_with_attempt": float(len(cust_with_attempt) / n_book),
        "attempts_per_applicant": float(len(journeys) / max(len(cust_with_attempt), 1)),
        "multi_attempt_share": float(np.mean(journeys.groupby("customer_id").size() > 1)),
        "disbursed_share_of_attempts": float(disbursed.mean()),
        "abandoned_share_of_attempts": float(abandoned.mean()),
        "in_flight_share_of_attempts": float(in_flight.mean()),
        "recovery_rate": float(len(recovered) / max(len(abandon_cust), 1)),
        "shopper_share_of_dropoffs": float(truth.loc[~disbursed, "shopper_truth"].mean()),
        "shopper_share_of_disbursed": float(truth.loc[disbursed, "shopper_truth"].mean()),
        "ineligible_share": float(truth.ineligible_product.mean()),
        "window_respect": respect,
        "median_journey_days": float(np.nanmedian(journeys.journey_days.to_numpy(dtype=float))),
        "p_complete_disbursed": float(truth.loc[disbursed, "p_complete"].mean()),
        "p_complete_abandoned": float(truth.loc[~disbursed, "p_complete"].mean()),
    }
    stats.update({f"abandon_at_{s}": v for s, v in stage_share.items()})

    # ---- structural ------------------------------------------------------- #
    assert journeys.attempt_id.is_unique, "attempt ids are not unique"
    assert not journeys.customer_id.isna().any(), "attempt without a customer"
    assert (journeys.last_stage_idx.to_numpy() == len(STAGES) - 1).sum() == disbursed.sum(), \
        "an attempt reached Disburse without being recorded as disbursed"
    assert (journeys.loc[disbursed, "fee_paid"] == 1).all(), \
        "a disbursement that never paid the Rs 1,000 fee"
    assert journeys.loc[disbursed, "abandoned_at"].eq("").all(), "a disbursed attempt also abandoned"
    assert journeys.loc[abandoned, "disbursed_at"].eq("").all(), "an abandoned attempt also disbursed"
    assert journeys.loc[in_flight, ["abandoned_at", "disbursed_at"]].eq("").all().all(), \
        "an in-flight attempt carries a terminal timestamp"
    assert journeys.loc[~disbursed, "amount_offered"].isna().sum() > 0, "offers never withheld"

    # ---- consistency with the book ---------------------------------------- #
    conv_ids = set(book.loc[conv, "cust_id"])
    assert disburse_cust == conv_ids, (
        f"disbursing customers ({len(disburse_cust)}) are not the book's converters "
        f"({len(conv_ids)}) — the journey layer contradicted the book")
    assert int(disbursed.sum()) == int(conv.sum()), "a converter disbursed more than once"
    bp = book.set_index("cust_id").product_canonical
    got = journeys.loc[disbursed].set_index("customer_id")
    assert (got["product"] == bp.reindex(got.index)).all(), \
        "a disbursed attempt is for a different product than the book's"
    ev = book.set_index("cust_id").event_month.reindex(got.index).to_numpy()
    month_of_disburse = pd.to_datetime(got.disbursed_at, format="mixed")
    anchor = pd.read_csv(book_dir / "customer_panel.csv", usecols=["date"], nrows=1).date.iloc[0]
    y0, m0 = (int(x) for x in str(anchor).split("-")[:2])
    got_month = (month_of_disburse.dt.year - y0) * 12 + (month_of_disburse.dt.month - m0)
    assert (got_month.to_numpy() == ev).all(), \
        "a disbursement did not land in the book's event_month"

    # ---- timestamps ------------------------------------------------------- #
    ts = pd.to_datetime(events.occurred_at, format="mixed")
    step = ts.groupby(events.attempt_id).diff().dt.total_seconds()
    assert (step.dropna() >= -1e-6).all(), "an event goes backwards in time"
    term = journeys.set_index("attempt_id")
    end = pd.to_datetime(term.abandoned_at.where(term.abandoned_at != "")
                         .fillna(term.disbursed_at.where(term.disbursed_at != "")), format="mixed")
    latest = ts.groupby(events.attempt_id).max()
    both = end.dropna()
    assert (latest.reindex(both.index) <= both + pd.Timedelta(seconds=1)).all(), \
        "an event lands after abandoned_at / disbursed_at"

    # ---- the pre-registered volumes --------------------------------------- #
    assert 0.25 <= stats["customers_with_attempt"] <= 0.35, (
        f"{stats['customers_with_attempt']:.1%} of the book has an attempt; the plan says 25-35%")
    assert 0.08 <= stats["recovery_rate"] <= 0.10, (
        f"drop-off recovery rate {stats['recovery_rate']:.2%} is outside the bank-stated 8-10%")
    assert 0.25 <= stats["shopper_share_of_dropoffs"] <= 0.35, (
        f"window shoppers are {stats['shopper_share_of_dropoffs']:.1%} of drop-offs; the plan says ~30%")
    for s, target in fn.ABANDON_SHARE.items():
        assert abs(stage_share[s] - target) <= STAGE_SHARE_TOL, (
            f"abandonment at {s} is {stage_share[s]:.1%} against a {target:.0%} target")
    assert stats["ineligible_share"] <= 2.0 * cfg.ineligible_noise_share + 0.005, \
        "too many attempts for products the customer cannot take"
    assert stats["p_complete_disbursed"] > stats["p_complete_abandoned"], \
        "the hazard rates abandoning attempts above disbursing ones — the book and the model disagree"
    assert 0.0 < stats["shopper_share_of_disbursed"] < stats["shopper_share_of_dropoffs"], \
        "shoppers must sometimes disburse, but less often than they drop off"
    return stats


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> tuple[JourneyConfig, list[int] | None]:
    ap = argparse.ArgumentParser(prog="make_journeys", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20260709, help="RNG seed (default: 20260709)")
    ap.add_argument("--book-dir", type=Path, default=None, help="where the book lives (default: data/)")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default: data/)")
    ap.add_argument("--attempt-share", type=float, default=None,
                    help="share of book customers with at least one attempt (default: 0.30)")
    ap.add_argument("--recovery-rate", type=float, default=None,
                    help="share of drop-offs that later disburse (default: 0.09)")
    ap.add_argument("--seeds", type=str, default=None,
                    help="comma-separated seeds: re-solve theta and the S/N knob on each "
                         "and print the spread, writing nothing (e.g. --seeds 7,8,9,10,11)")
    a = ap.parse_args(argv)
    book_dir = a.book_dir if a.book_dir is not None else ROOT / "data"
    cfg = JourneyConfig(
        book_dir=book_dir, out_dir=a.out if a.out is not None else book_dir, seed=a.seed,
        target_attempt_share=a.attempt_share if a.attempt_share is not None else 0.30,
        target_recovery_rate=a.recovery_rate if a.recovery_rate is not None else 0.09,
    )
    return cfg, ([int(s) for s in a.seeds.split(",")] if a.seeds else None)


#: The numbers a seed sweep reports, and how to format each.
SWEEP_FIELDS = (
    ("theta", "{:.4f}"), ("signal_to_noise", "{:.4f}"),
    ("random_contact_disbursement_rate", "{:.4f}"), ("oracle_precision_at_10pct", "{:.4f}"),
    ("window_respect_rate", "{:.4f}"), ("suppressed_share", "{:.4f}"),
    ("contact_lift", "{:.2f}"),
)


def seed_sweep(cfg: JourneyConfig, seeds: list[int]) -> dict[str, list[float]]:
    """Re-solve both knobs on each seed and print the spread.  Writes nothing.

    This is the re-checkability the plan asks of SD-S4: the two asserted bands
    must hold on at least five seeds, not on the one that happened to be run.
    """
    from dataclasses import replace

    out: dict[str, list[float]] = {name: [] for name, _ in SWEEP_FIELDS}
    for s in seeds:
        b = generate_all(replace(cfg, seed=s))
        st = lb.check(b.labels, b.label_truth, b.params["labels"],
                      substream(s, "measurement"))
        for name, _ in SWEEP_FIELDS:
            out[name].append(st[name])
        print(f"  seed {s:>6}: " + "  ".join(
            f"{name}={fmt.format(st[name])}" for name, fmt in SWEEP_FIELDS))
    print(f"\nspread over {len(seeds)} seeds")
    for name, fmt in SWEEP_FIELDS:
        v = np.array(out[name])
        print(f"  {name:<36} min {fmt.format(v.min())}  max {fmt.format(v.max())}  "
              f"mean {fmt.format(v.mean())}")
    return out


def main(argv: list[str] | None = None) -> None:
    cfg, seeds = parse_args(argv)
    if seeds:
        seed_sweep(cfg, seeds)
        return

    t0 = time.perf_counter()
    b = generate_all(cfg)
    t_gen = time.perf_counter() - t0
    journeys, events, truth, params = b.journeys, b.events, b.truth, b.params

    stats = check(cfg, journeys, events, truth, cfg.book_dir)
    lstats = lb.check(b.labels, b.label_truth, params["labels"],
                      substream(cfg.seed, "measurement"))
    params["realised"] = {k: round(v, 5) for k, v in stats.items()}
    params["labels"]["realised"] = {k: round(v, 5) for k, v in lstats.items()}

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    t1 = time.perf_counter()
    journeys.to_csv(cfg.out_dir / "journeys.csv", index=False)
    events.to_csv(cfg.out_dir / "journey_events.csv", index=False)
    truth.to_csv(cfg.out_dir / "journey_truth.csv", index=False)
    b.campaigns.to_csv(cfg.out_dir / "campaigns.csv", index=False)
    b.labels.to_csv(cfg.out_dir / "labels.csv", index=False)
    b.label_truth.to_csv(cfg.out_dir / "label_truth.csv", index=False)
    (cfg.out_dir / "journey_params.json").write_text(json.dumps(params, indent=2) + "\n")
    t_io = time.perf_counter() - t1

    mix = journeys["product"].value_counts().to_dict()
    print(f"{int(stats['attempts']):,} attempts by {stats['customers_with_attempt']:.1%} of the book "
          f"({stats['attempts_per_applicant']:.2f} per applicant, "
          f"{stats['multi_attempt_share']:.1%} multi-attempt) -> {len(events):,} stage events")
    print(f"outcome: disbursed {stats['disbursed_share_of_attempts']:.1%} | abandoned "
          f"{stats['abandoned_share_of_attempts']:.1%} | still open {stats['in_flight_share_of_attempts']:.1%}")
    print("drop-off stage mix: " + " | ".join(
        f"{s} {stats[f'abandon_at_{s}']:.0%}" for s in STAGES[:N_GATES]))
    print(f"observed drop-off recovery (customer level, journey layer): {stats['recovery_rate']:.2%}")
    print(f"window shoppers: {stats['shopper_share_of_dropoffs']:.1%} of drop-offs, "
          f"{stats['shopper_share_of_disbursed']:.1%} of disbursements")
    print(f"product mix: {mix}")
    print(f"\ncampaigns: {len(b.campaigns):,} touches | "
          + " ".join(f"{k} {v:.0%}" for k, v in
                     b.campaigns.channel.value_counts(normalize=True).items())
          + f" | response {1 - b.campaigns.response.eq('no_response').mean():.1%}")
    print(f"drop-off population: {len(b.labels):,} (customer, month) rows over "
          f"{int(lstats['customers']):,} customers | suppressed {lstats['suppressed_share']:.1%}")
    print(f"solved theta {lstats['theta']:.4f} (contact lift {lstats['contact_lift']:.1f}x) | "
          f"S/N {lstats['signal_to_noise']:.4f}")
    print(f"RANDOM-CONTACT DISBURSEMENT (SK-01, amended): "
          f"{lstats['random_contact_disbursement_rate']:.2%} (band 8-10%)")
    print(f"ORACLE PRECISION @10% (SK-02 ceiling): "
          f"{lstats['oracle_precision_at_10pct']:.2%} (band 25-35%)")
    print(f"window respect {lstats['window_respect_rate']:.1%} (floor 90%) | "
          f"no-contact rate {lstats['no_contact_disbursement_rate']:.2%} | "
          f"menu-of-4 coverage {lstats['menu_of_4_coverage']:.1%}")
    print(f"generated in {t_gen:.1f}s, written in {t_io:.1f}s -> {cfg.out_dir}")


if __name__ == "__main__":
    main()
