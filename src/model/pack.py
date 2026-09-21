# -*- coding: utf-8 -*-
"""Run the model, measure it against the pre-registered bands, pack the cockpit.

One entry point, :func:`run`.  It does five things in order and nothing else:

1. build the point-in-time frame once (it does not change with the seed);
2. fit and measure on every registered seed, so the headline carries a spread;
3. on the default seed, add the exhibits that are too expensive to repeat —
   out-of-time, permuted-label, the baseline ladder, uplift, fairness, calibration;
4. build the queue at the snapshot month, with the menu of four, the reasons, the
   negative chips and the suppression list;
5. write ``app/public/sanket_data.json`` and ``data/model_metrics.json``.

The JSON keeps every key ``app/`` reads today.  What it adds is listed in
``MODEL_CARD.md`` under "what the front end must change".
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from . import (
    FORBIDDEN_INPUTS,
    PRODUCT_LABEL,
    PRODUCTS,
    WINDOW_DAYS,
    ModelConfig,
)
from . import bank as BK
from . import bootstrap as BS
from . import copy as txt
from . import emi as EMI
from . import export as EXP
from . import frame as F
from . import metrics as M
from . import policy as PO
from . import roster as RO
from .train import (
    Split,
    fit_ranker,
    fit_shopper,
    fit_uplift,
    randomised_campaign,
    split_customers,
)

BUDGETS = [x / 100 for x in range(1, 31)]


def _r(x, nd: int = 4):
    """Round, but leave ``None`` and non-finite values alone."""
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


# --------------------------------------------------------------------------- #
# one seed
# --------------------------------------------------------------------------- #

def _held(base: pd.DataFrame, sp: Split) -> np.ndarray:
    return sp.mask(base["cust_id"], "held") & (base["eligible_for_contact"].to_numpy() == 1)


def evaluate_seed(base: pd.DataFrame, stacked: pd.DataFrame, cfg: ModelConfig,
                  seed: int, full: bool = False) -> dict:
    """Fit on one seed's split and measure everything the bands need."""
    sp = split_customers(base["cust_id"].unique(), cfg, seed)
    rk = fit_ranker(stacked, sp, cfg, with_unconstrained=full)
    P = rk.matrix(stacked)                      # (n_base, 6) calibrated

    h = _held(base, sp)
    hb = base[h].reset_index(drop=True)
    Ph = P[h]
    y = hb["t_label"].to_numpy().astype(int)

    p_top = Ph.max(axis=1)
    # SM-7: the six product labels partition the disbursement outcome, so the
    # any-product probability is their SUM, not the independent-event union
    # `1 - prod(1 - p)`.  One definition, `policy.any_product_probability`.
    p_any = PO.any_product_probability(Ph)

    # SM-7: precision is measured on the list the policy would actually deliver
    # — suppression, eligibility, the queue's own ranking, its truncation and
    # its tie-break — not on a bare argsort of the probabilities.  One function,
    # `model.policy`, decides that here and in `build_queue`.
    elig_h = hb["eligible_for_contact"].to_numpy() == 1
    cid, semi = hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy()
    scores = PO.score_pool(cid, semi, Ph, elig_h)
    alt_ranking = (PO.RANKING_BLEND if scores.ranking == PO.RANKING_PROBABILITY
                   else PO.RANKING_PROBABILITY)
    alt = PO.score_pool(cid, semi, Ph, elig_h, ranking=alt_ranking)
    order = PO.rank_order(scores)

    baseline = float(y.mean())
    at = {b: PO.precision_at(y, scores, b) for b in (0.05, cfg.budget, 0.20)}
    at_alt = {b: PO.precision_at(y, alt, b) for b in (0.05, cfg.budget, 0.20)}
    pp = M.per_product(Ph, hb, cfg.budget)
    macro = float(np.mean([v["auc"] for v in pp.values()]))
    mm = M.menu_metrics(Ph, hb, cfg.menu_k)
    wr = M.window_respect(Ph, hb, order, at[cfg.budget]["k"])

    out = dict(
        seed=seed,
        n_holdout_rows=int(len(y)), n_holdout_customers=int(hb.cust_id.nunique()),
        baseline=baseline,
        precision=at, ranking=scores.ranking,
        precision_alt_ranking=at_alt, alt_ranking=alt.ranking,
        row_auc=float(roc_auc_score(y, p_top)),
        row_auc_rank_by_sum=float(roc_auc_score(y, Ph.sum(axis=1))),
        precision_at_budget_rank_by_sum=float(
            M.precision_at(y, Ph.sum(axis=1), cfg.budget)["precision"]),
        per_product=pp, macro_auc=macro,
        menu=mm, windows=wr,
        ece_overall=float(M.ece(p_any, y)),
        ece_per_product_max=float(max(v["ece"] for v in pp.values())),
    )
    if not full:
        return out

    out["_objects"] = dict(split=sp, ranker=rk, P=P, held=h, hb=hb, Ph=Ph,
                           y=y, p_top=p_top, p_any=p_any, order=order,
                           scores=scores, alt_scores=alt)
    return out


# --------------------------------------------------------------------------- #
# the expensive one-off exhibits
# --------------------------------------------------------------------------- #

def out_of_time(base: pd.DataFrame, stacked: pd.DataFrame, cfg: ModelConfig,
                sp: Split, in_time: float) -> dict:
    """SK-07.  Train on the early months, measure on the last six.

    The registered 14-day embargo is satisfied structurally rather than by
    dropping rows: a row's label resolves inside its own month (the longest
    window is 14 days and the row is dated to the first of the month), so a cut
    at a month boundary already leaves no training label that had not happened.
    """
    cut = int(base["month"].max()) - cfg.oot_months + 1
    tr_c = stacked["cust_id"].isin(sp.fit).to_numpy()
    early = stacked["month"].to_numpy() < cut
    elig = stacked["eligible_for_contact"].to_numpy() == 1
    sub = stacked[tr_c & early & elig]
    if sub["y"].sum() < 50:
        return dict(status="skipped_low_n", n=int(len(sub)))

    oot_split = Split(fit=sp.fit, calib=sp.calib, held=sp.held, seed=sp.seed)
    frame_early = stacked[early]
    rk = fit_ranker(frame_early, oot_split, cfg)

    late = (base["month"].to_numpy() >= cut) & _held(base, sp)
    lb = base[late].reset_index(drop=True)
    ls = F.as_categorical(F.stack(lb))
    P = rk.matrix(ls)
    y = lb["t_label"].to_numpy().astype(int)
    p = P.max(axis=1)
    at = M.precision_at(y, p, cfg.budget)
    return dict(status="ok", cut_month=cut, n=int(len(y)),
                oot_precision_at_budget=at["precision"], oot_ci=[at["ci_low"], at["ci_high"]],
                oot_baseline=float(y.mean()), in_time_precision=in_time,
                degradation_pp=100.0 * (in_time - at["precision"]),
                oot_row_auc=float(roc_auc_score(y, p)) if y.sum() else float("nan"))


def permuted_label_auc(stacked: pd.DataFrame, base: pd.DataFrame, cfg: ModelConfig,
                       sp: Split) -> float:
    """SK-18.  Same pipeline, labels shuffled — anything off 0.50 means the harness leaks.

    The shuffle is of ``y`` within the training rows only, at the stacked grain,
    with the split, the features and the hyper-parameters untouched.
    """
    sh = stacked.copy()
    rng = np.random.default_rng(sp.seed + 1000)
    tr = sh["cust_id"].isin(sp.fit).to_numpy() & (sh["eligible_for_contact"].to_numpy() == 1)
    idx = np.flatnonzero(tr)
    sh.loc[sh.index[idx], "y"] = sh["y"].to_numpy()[rng.permutation(idx)]
    rk = fit_ranker(sh, sp, cfg)
    h = _held(base, sp)
    P = rk.matrix(sh)[h]
    y = base.loc[h, "t_label"].to_numpy().astype(int)
    return float(roc_auc_score(y, P.max(axis=1)))


LADDER_FEATURES = ("credits_med_6m", "credits_cv_6m", "bal_avg", "minbal_ratio", "emi_share",
                   "fd_ratio", "rent_share", "journey_stage_idx", "days_since_abandon",
                   "journey_blank_field_ratio", "journey_refused_income", "journey_fee_balk",
                   "journey_doc_refusal", "dwell_total_3m", "age", "tenure_m")


def baseline_ladder(base: pd.DataFrame, cfg: ModelConfig, sp: Split,
                    scores: PO.PolicyScores, h: np.ndarray) -> list[dict]:
    """SK-25.  Four rungs, one budget, so the gain has a context and not just a size.

    The SANKET rung is the **delivered** policy (``model.policy``), not a bare
    argsort of the probabilities: the top rung of the ladder has to be the list
    the bank would actually call, or the ladder is comparing the shipped product
    against three alternatives it never competes with.
    """
    hb = base[h]
    y = hb["t_label"].to_numpy().astype(int)
    rows = [dict(rung="random contact", score=None),
            dict(rung="balance-ranked (what a branch does today)",
                 score=hb["bal_avg"].to_numpy(dtype=float)),
            dict(rung="logistic scorecard", score=None),
            dict(rung="SANKET (one LightGBM, six products)", score="policy")]

    tr = sp.mask(base["cust_id"], "fit") & (base["eligible_for_contact"].to_numpy() == 1)
    cols = [c for c in LADDER_FEATURES if c in base.columns]
    Xtr = base.loc[tr, cols].astype(float)
    med = Xtr.median()
    Xtr = Xtr.fillna(med)
    mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
    lr = LogisticRegression(max_iter=2000, C=1.0)
    lr.fit((Xtr - mu) / sd, base.loc[tr, "t_label"].astype(int))
    Xh = ((hb[cols].astype(float).fillna(med)) - mu) / sd
    rows[2]["score"] = lr.predict_proba(Xh)[:, 1]

    out = []
    for r in rows:
        if r["score"] is None:
            k = max(1, int(round(len(y) * cfg.budget)))
            lo, hi = M.wilson(int(round(y.mean() * k)), k)
            out.append(dict(rung=r["rung"], precision=float(y.mean()),
                            ci_low=lo, ci_high=hi, n=k))
        else:
            a = (PO.precision_at(y, scores, cfg.budget) if isinstance(r["score"], str)
                 else M.precision_at(y, np.asarray(r["score"], dtype=float), cfg.budget))
            out.append(dict(rung=r["rung"], precision=a["precision"],
                            ci_low=a["ci_low"], ci_high=a["ci_high"], n=a["k"]))
    return out


SHAP_SAMPLE = 12_000


def signal_effects(rk, stacked: pd.DataFrame, h: np.ndarray, cfg: ModelConfig,
                   sample: int = SHAP_SAMPLE) -> dict:
    """SK-15.  Do the four mentor signals push the probability DOWN?

    Two readings, deliberately:

    * **constrained** — the shipped model, where ``monotone_constraints = -1``
      makes the direction structural.  This is what the negative chips quote.
    * **unconstrained** — the same fit with the constraints removed.  If the
      signs flipped here, the constraint would be doing all the work and the
      chips would be an assertion dressed as evidence.  They do not.

    The effect is ``mean SHAP where the signal is on`` minus ``mean SHAP where it
    is off``, in log-odds — a difference, so a non-zero baseline contribution
    cannot make a flat feature look negative.
    """
    rowsel = np.tile(h, len(PRODUCTS))
    idx = np.flatnonzero(rowsel)
    #: exact TreeSHAP is O(trees x leaves x depth^2) per row; a random sample of
    #: the held-out rows estimates a *mean* effect to three decimals and turns
    #: eleven minutes into twenty seconds.  Sampled, not truncated, so no product
    #: or month is preferentially dropped.
    if sample and len(idx) > sample:
        idx = np.sort(np.random.default_rng(cfg.seed).choice(idx, sample, replace=False))
    sub = stacked.iloc[idx]
    feats = list(rk.features)

    def effects(model) -> dict:
        C = model.booster_.predict(F.build_matrix(sub, rk.features), pred_contrib=True)[:, :-1]
        out = {}
        for s in F.MENTOR_SIGNALS:
            j = feats.index(s)
            v = sub[s].to_numpy(dtype=float)
            on = v >= (0.25 if s == "journey_blank_field_ratio" else 1.0)
            off = ~on & np.isfinite(v)
            if on.sum() < 30 or off.sum() < 30:
                out[s] = dict(status="skipped_low_n", n_on=int(on.sum()))
                continue
            out[s] = dict(
                mean_shap_on=float(C[on, j].mean()),
                mean_shap_off=float(C[off, j].mean()),
                effect=float(C[on, j].mean() - C[off, j].mean()),
                mean_shap_overall=float(C[:, j].mean()),
                n_on=int(on.sum()), n_off=int(off.sum()), negative=bool(
                    C[on, j].mean() - C[off, j].mean() < 0))
        return out

    con = effects(rk.model)
    unc = effects(rk.unconstrained) if rk.unconstrained is not None else {}
    n_neg = sum(1 for v in con.values() if v.get("negative"))
    return dict(constrained=con, unconstrained=unc, n_negative=n_neg,
                n_negative_unconstrained=sum(1 for v in unc.values() if v.get("negative")),
                definition="mean SHAP (log-odds) where the signal is on, minus where it is off, "
                           "on a random sample of the held-out drop-off population",
                n_rows=int(len(idx)), n_rows_available=int(rowsel.sum()))


# --------------------------------------------------------------------------- #
# the queue
# --------------------------------------------------------------------------- #

def _contrib_map(C: np.ndarray, feats: list[str], i: int) -> dict[str, float]:
    return {f: float(C[i, j]) for j, f in enumerate(feats)}


def scored_attempts(journeys: pd.DataFrame,
                    as_at: pd.Timestamp) -> dict[str, tuple[str, pd.Timestamp]]:
    """``cust_id -> (attempt_id, abandon_ts)``: the attempt each lead is about.

    A customer can have several applications behind them.  The one a lead
    REVIVES is the most recent abandonment visible at ``as_at``, because that is
    the attempt ``journeys.labels.build_population`` admits them to the drop-off
    pool on and reads ``dropoff_stage_reached``, ``dropoff_product`` and
    ``days_since_abandon`` off — the same rule, rebuilt here from the journey
    table so the attempt can be NAMED (``lead.journey_ref``) instead of left for
    a consumer to guess at.

    Guessing is the failure this exists to prevent: the platform joins
    ``sanket_lead.journey_ref`` to ``sanket_journey`` to build the RM drawer's
    whole ``window`` block, and the obvious substitute — join on ``cust_id`` —
    lands on the customer's LATEST attempt, which is a different application for
    all but a handful of leads and was never abandoned at all for 140 of 344.
    A deadline dated from the wrong application is worse than no deadline.
    """
    j = journeys[["cust_id", "attempt_id", "abandoned_at"]].copy()
    # the generator writes an empty string, not a NaN, for "never abandoned"
    # (`journeys.build._timestamps`), the same shim `journeys.labels` applies
    j["abandoned_at"] = pd.to_datetime(j["abandoned_at"].replace("", None), format="mixed")
    j = j[j["abandoned_at"].notna() & (j["abandoned_at"] <= pd.Timestamp(as_at))]
    # stable sort + tail(1) == "latest abandonment at or before as_at", ties
    # broken by row order exactly as `build_population`'s lexsort breaks them.
    j = j.sort_values(["cust_id", "abandoned_at"], kind="stable")
    j = j.groupby("cust_id", as_index=False, sort=False).tail(1)
    return {str(c): (str(a), pd.Timestamp(t))
            for c, a, t in zip(j["cust_id"], j["attempt_id"], j["abandoned_at"])}


def build_queue(base: pd.DataFrame, P: np.ndarray, rk, shopper_score: np.ndarray,
                uplift: np.ndarray, panel: pd.DataFrame, journeys: pd.DataFrame,
                cfg: ModelConfig, snap: int, rm_map: dict) -> tuple[list[dict], dict, dict]:
    """The cockpit queue at the snapshot month, plus the suppression exhibit.

    Suppressed rows are **scored and shown, never queued** — the rule the mentors
    asked for and the one the product is judged on.  They arrive in the export
    with ``queued = False`` and the reason attached.
    """
    at_snap = base["month"].to_numpy() == snap
    idx = np.flatnonzero(at_snap)
    snap_rows = base.iloc[idx].copy().reset_index(drop=True)
    Ps = P[idx]
    elig = snap_rows["eligible_for_contact"].to_numpy() == 1
    # SM-7: three clocks, named apart and never conflated again.  `scored_at` is
    # the instant the model ranked the pool — the snapshot's first instant, the
    # instant every feature is computed as at.  `abandoned_at` is when the
    # customer walked away from the application, and it is the URGENCY clock.
    # `contact_by` is `abandoned_at + the product's decision window`, which is
    # what the platform backend independently computes from `journeys.abandon_ts`
    # (`app/services/sanket.py::window_due_at`); before this it was computed off
    # `scored_at` here and the two disagreed.  See MODEL_CARD §4.
    scored_at = pd.Timestamp(snap_rows["date"].iloc[0])
    # ...and the abandoned attempt each of those three clocks is about, resolved
    # once for the whole snapshot.  `abandoned_at` is read off this attempt's own
    # timestamp rather than back-computed from the whole-day `days_since_abandon`
    # feature, which rounded the date a day forward on 343 of 344 leads and would
    # not match the `journeys[].abandon_ts` the platform dates its deadline from.
    attempt_of = scored_attempts(journeys, scored_at)

    menu_i = np.argsort(-Ps, axis=1, kind="stable")[:, : cfg.menu_k]

    # SM-7: one policy object, the same one `evaluate_seed` measures on.  It
    # owns suppression, eligibility, the ranking, the truncation and the
    # tie-break; nothing below is allowed to re-derive any of them.
    scores = PO.score_pool(snap_rows["cust_id"].to_numpy(),
                           snap_rows["safe_emi"].to_numpy(), Ps, elig)
    p_top = scores.p_top

    snap_rows["p_top"] = p_top
    # SM-7: mutually exclusive labels — the any-product probability is the sum.
    snap_rows["p_any"] = PO.any_product_probability(Ps)
    snap_rows["nbp"] = list(scores.nbp)
    snap_rows["shopper_score"] = shopper_score[idx]
    snap_rows["uplift"] = uplift[idx]
    snap_rows["uplift_pct"] = pd.Series(uplift[idx]).rank(pct=True).to_numpy()

    snap_rows["intent"] = scores.intent
    # SM-5: the retained-income check against a bank-rate EMI, not a flat
    # assumed constant — `EMI.REFERENCE_EMI` replaces `TYPICAL_EMI` here.
    snap_rows["capacity"] = scores.capacity
    snap_rows["blend"] = scores.blend
    #: What the queue is actually ordered on — `model.policy.DEFAULT_RANKING`.
    snap_rows["rank_score"] = scores.rank_score

    # Tiers are fixed probability BANDS on the score the queue ranks by
    # (`policy.TIER_HOT` / `policy.TIER_WARM`), not a restatement of where the
    # truncation fell.  Cutting them at the contact budget made `hot` mean
    # "inside the delivered queue" — the cockpit exports 320 rows out of the 553
    # the 10% budget buys, so all 320 came out hot and nothing was ever warm.
    # Every row in the pool gets a band, suppressed rows included: a suppressed
    # customer still has a probability, and whether the bank may call them is
    # carried separately (`suppressed` + `suppression_reason`).
    n_e = scores.n_eligible
    tier = PO.tiers(scores)
    snap_rows["tier"] = tier

    order = PO.rank_order(scores)
    take_pos = [int(p) for p in order[: cfg.queue_size]]
    seg = snap_rows["segment"].astype(str).to_numpy()
    gig_order = [int(p) for p in order if seg[int(p)] == "gig"]
    # The gig exhibit needs a face in the export.  If the policy already queued
    # one, that is the case; if it did not, the best-ranked gig row rides along
    # as ONE extra row past the budget, keeping the rank the policy gave it, so
    # the exclusion is visible rather than argued about.  The delivered queue is
    # still `take_pos[:cfg.queue_size]` and the parity test checks exactly that.
    if gig_order and gig_order[0] not in take_pos:
        take_pos.append(gig_order[0])
    gig_id = str(snap_rows.iloc[gig_order[0]]["cust_id"]) if gig_order \
        else str(snap_rows.iloc[take_pos[0]]["cust_id"])
    queue_rank = {int(p): i + 1 for i, p in enumerate(order)}
    take = snap_rows.iloc[take_pos]
    excluded = snap_rows[~elig]
    samp = excluded.sample(min(cfg.excluded_sample, len(excluded)), random_state=7) \
        if len(excluded) else excluded

    # SHAP only for the rows that actually leave the building: exact TreeSHAP on
    # the whole snapshot pool costs minutes and nothing reads it.
    export = pd.Index(take.index.tolist() + samp.index.tolist()).unique()
    rows = snap_rows.loc[export].reset_index(drop=True)
    pos_of = {p: i for i, p in enumerate(export)}
    C = rk.contributions(F.as_categorical(F.stack(rows)))
    feats = list(rk.features)
    n_snap = len(rows)

    hist = panel[panel.month <= snap].groupby("cust_id")
    leads = []
    for pos in take.index:
        leads.append(_lead(snap_rows.loc[pos], pos_of[pos], Ps[pos], menu_i[pos], C, feats,
                           n_snap, hist, snap_rows.loc[pos, "date"], rm_map, queued=True,
                           queue_rank=queue_rank.get(int(pos)), scored_at=scored_at,
                           attempts=attempt_of))
    for pos in samp.index:
        leads.append(_lead(snap_rows.loc[pos], pos_of[pos], Ps[pos], menu_i[pos], C, feats,
                           n_snap, hist, snap_rows.loc[pos, "date"], rm_map, queued=False,
                           queue_rank=None, scored_at=scored_at, attempts=attempt_of))

    reasons = (snap_rows.loc[~elig, "t_suppression_reason"].value_counts().to_dict())
    suppression = dict(
        suppressed_count=int((~elig).sum()),
        suppressed_share=round(float((~elig).mean()), 4),
        pool_at_snapshot=int(len(snap_rows)), contactable_at_snapshot=n_e,
        reasons={str(k): int(v) for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])},
    )
    # Band counts over the WHOLE snapshot pool, suppressed rows included —
    # tiers no longer depend on suppression, so excluding the suppressed here
    # would leave a tally that does not add up to the pool it claims to cover.
    # `suppressed` and `no_consent` stay beside them as the separate facts they
    # are, and `delivered.tiers` breaks the 320 exported rows down on its own.
    pool_tiers = PO.tier_counts(tier)
    queue_tiers = PO.tier_counts(tier, np.isin(np.arange(len(tier)),
                                               order[: cfg.queue_size]))
    counts = dict(
        hot=pool_tiers["hot"], warm=pool_tiers["warm"], green=0,
        cold=pool_tiers["cold"],
        no_consent=int((snap_rows["t_suppression_reason"] == "no_marketing_consent").sum()),
        suppressed=suppression["suppressed_count"],
    )
    # SM-7: what the policy selected, stated in one place, so the number the
    # evaluator quotes and the list an RM receives can be checked against each
    # other (`tests/test_model_policy.py` does exactly that).
    delivered = dict(
        ranking=scores.ranking,
        weights=(dict(intent=PO.INTENT_WEIGHT, capacity=PO.CAPACITY_WEIGHT)
                 if scores.ranking == PO.RANKING_BLEND else None),
        eligible_pool=n_e,
        budget=cfg.budget,
        budget_k=PO.budget_k(n_e, cfg.budget),
        queue_size=int(cfg.queue_size),
        exported=len(take_pos),
        equivalent_budget=round(min(cfg.queue_size, n_e) / n_e, 4) if n_e else None,
        top_ids=[str(snap_rows.iloc[int(p)]["cust_id"]) for p in order[: cfg.queue_size]],
        tie_break="cust_id ascending",
        # The bands the delivered rows fall in, and the thresholds that cut
        # them. A queue ordered by probability and truncated spans several
        # bands; if it ever reports one, the tier has collapsed back into
        # queue membership.
        tiers=queue_tiers,
        tier_thresholds=dict(hot=PO.TIER_HOT, warm=PO.TIER_WARM,
                             score="calibrated probability of the pitched product — "
                                   "the same score the queue is ranked on"),
        pool_tiers=pool_tiers,
        # How fragile those three counts are. Reported, never gated: the
        # delivered queue sits on a couple of dozen isotonic plateaus, so a
        # tier cut moves a whole plateau or none of it, and the size of that
        # movement has nothing to do with how much precision moved. Validation
        # criterion SK-26 reads this block; MODEL_CARD §8 and the README state
        # it in words.
        tier_plateau_sensitivity=PO.tier_plateau_sensitivity(
            scores.rank_score[order[: cfg.queue_size]]),
        note="The cockpit exports the first `queue_size` rows of the ranked list the "
             "contact budget buys. `hot`/`warm`/`cold` are fixed probability bands on "
             "that same ranking score, not queue membership, so the delivered list "
             "carries all three. Selection comes from `model.policy`, which is also "
             "what `evaluate_seed` measures precision on.",
    )
    return leads, counts, dict(suppression=suppression, gig_case_id=gig_id,
                               n_pool=int(len(snap_rows)), n_contactable=n_e,
                               snap_rows=snap_rows, P=Ps, elig=elig,
                               scores=scores, order=order, delivered=delivered,
                               scored_at=scored_at)


def _lead(r, pos: int, probs: np.ndarray, menu_idx: np.ndarray, C: np.ndarray,
          feats: list[str], n_snap: int, hist, date: str, rm_map: dict, queued: bool,
          queue_rank: int | None = None, scored_at: pd.Timestamp | None = None,
          attempts: dict[str, tuple[str, pd.Timestamp]] | None = None) -> dict:
    top = PRODUCTS[int(menu_idx[0])]
    ctop = _contrib_map(C, feats, int(menu_idx[0]) * n_snap + pos)
    rs = txt.reasons_for(r, ctop) or ["Composite behavioural signal across credits, balances and browsing"]
    chips = txt.negative_chips(r, ctop)

    # SM-5: the customer's own affordability if they have one, else the
    # bank-rate reference EMI for the pitched product (was `TYPICAL_EMI`).
    emi = int(r.safe_emi) if r.safe_emi and r.safe_emi > 0 else EMI.reference_emi(top)
    lang = "hi" if (int(str(r.cust_id).split("-")[1]) % 5) < 2 else "en"
    opener, why, obj_q, obj_a = (txt.PITCH_HI if lang == "hi" else txt.PITCH_EN)[top]

    as_at = pd.Timestamp(date) if scored_at is None else pd.Timestamp(scored_at)
    # SM-7: the urgency clock is ABANDONMENT, not the scoring snapshot.  The
    # label is "disbursed inside the product's window after contact", the
    # platform backend expires a lead at `abandon_ts + window`, and this is the
    # field both of those read.  A `contact_by` already in the past is the
    # truthful answer for a customer who walked away months ago — the cockpit
    # renders it as a closed window rather than inventing fresh urgency.
    #
    # It is read off the abandoned attempt itself (`scored_attempts`), whose id
    # travels with the lead as `journey_ref`, so the date this states and the
    # `journeys[].abandon_ts` the platform reads are the same instant of the same
    # application.  Every row here is a drop-off-population row, so an attempt
    # that cannot be found is a broken frame, not a lead to paper over.
    attempt = (attempts or {}).get(str(r.cust_id))
    if attempt is None:
        raise AssertionError(f"{r.cust_id}: a drop-off lead with no abandoned attempt "
                             f"at or before {as_at.date()}")
    journey_ref, abandon_ts = attempt
    abandoned_at = pd.Timestamp(abandon_ts).normalize()
    menu = []
    for j in menu_idx:
        p = PRODUCTS[int(j)]
        cj = _contrib_map(C, feats, int(j) * n_snap + pos)
        w = WINDOW_DAYS[p]
        menu.append(dict(
            product=p, label=PRODUCT_LABEL[p], p=round(float(probs[int(j)]), 4),
            reason=txt.menu_reason(r, p, cj, PRODUCT_LABEL, w), window_days=w,
            contact_by=(abandoned_at + pd.Timedelta(days=w)).strftime("%Y-%m-%d"),
            # SM-5: `emi` is now the real number — the bank-rate EMI on this
            # product's reference ticket (API 433 sandbox rate, standard
            # amortisation formula).  `indicative_emi` is no longer a second
            # number: it is a LABEL describing what `emi` is and where it came
            # from, so a consumer never has to guess which of the two is the
            # one to say out loud.  `emi_source` is the machine-readable tag.
            emi=EMI.REFERENCE_EMI[p], indicative_emi=EMI.indicative_label(p),
            emi_source=EMI.EMI_SOURCE[p],
        ))

    if float(r.uplift) < 0:
        utag = "handle-with-care"
    elif float(r.uplift_pct) >= 0.85:
        utag = "persuadable"
    elif float(r.intent) >= 0.9 and float(r.uplift_pct) < 0.5:
        utag = "converts-anyway"
    else:
        utag = "neutral"

    spark = []
    try:
        h = hist.get_group(r.cust_id)
        spark = [dict(m=d, bal=int(b), cr=int(c))
                 for d, b, c in zip(h.date, h.bal_avg, h.credits)]
    except KeyError:
        pass

    w_top = WINDOW_DAYS[top]
    rm = rm_map.get(str(r.cust_id)) if queued else None
    return dict(
        id=str(r.cust_id), segment=str(r.segment), age=int(r.age), city_tier=int(r.city_tier),
        tenure_m=int(r.tenure_m),
        # `consent` now means QUEUEABLE: false for every suppressed row whatever
        # the reason.  The raw DPDP flag is `consent_marketing`.
        consent=bool(queued), consent_marketing=bool(int(r.consent_marketing) == 1),
        queued=bool(queued), suppressed=bool(not queued),
        suppression_reason=str(r.t_suppression_reason),
        # The band the probability falls in — a suppressed row keeps its own
        # band rather than being relabelled `cold`, because "we may not call
        # this customer" is not a statement about how likely they were to buy.
        product=top, product_menu=menu, tier=str(r.tier),
        lang=lang, uplift_tag=utag, uplift_pct=round(float(r.uplift_pct), 2),
        intent=round(float(r.intent), 3), capacity=round(float(r.capacity), 3),
        # `score` is the queue's ORDERING key (`model.policy.DEFAULT_RANKING`),
        # carried at six decimals so sorting on it reproduces the delivered
        # order.  `blend` stays beside it as the displayed secondary signal.
        score=round(float(r.rank_score), 6), blend=round(float(r.blend), 3),
        queue_rank=(int(queue_rank) if queue_rank is not None else None),
        probability=round(float(probs[int(menu_idx[0])]), 4),
        p_any=round(float(r.p_any), 4),
        shopper_score=round(float(r.shopper_score), 3),
        window_days=w_top,
        # The three clocks, explicit: when they walked away, when we ranked
        # them, by when an RM must call, and how long after contact the label
        # is allowed to resolve.
        abandoned_at=abandoned_at.strftime("%Y-%m-%d"),
        scored_at=as_at.strftime("%Y-%m-%d"),
        # the attempt the three clocks above are about, by id
        journey_ref=journey_ref,
        contact_by=(abandoned_at + pd.Timedelta(days=w_top)).strftime("%Y-%m-%d"),
        outcome_horizon_days=int(w_top),
        dropoff_stage=str(r.dropoff_stage_reached), dropoff_product=str(r.dropoff_product),
        days_since_abandon=int(r.days_since_abandon),
        contacts_30d=int(r.contacts_30d), last_contact_days=(
            None if not np.isfinite(float(r.last_contact_days)) else int(r.last_contact_days)),
        salary_m=int(r.credits_med_6m), retained_income=int(r.retained), safe_emi=int(r.safe_emi),
        reasons=rs, negative_chips=chips,
        pitch=dict(opener=opener, why_now=why.format(emi=emi),
                   proof=[x.split(" — ")[0] for x in rs]),
        objection=dict(q=obj_q, a=obj_a.format(emi=emi)),
        nba=txt.NBA.get(str(r.tier), txt.NBA["cold"]) if queued else "",
        # SM-4: round-robin assignment, baked in at export time.  Suppressed
        # rows never get one — they are never going to be called, so tying
        # them to a servicing RM in the export would claim a relationship the
        # queue rule explicitly withholds.
        rm_id=(rm.rm_id if rm is not None else None),
        rm_name=(rm.rm_name if rm is not None else None),
        rm_branch=(rm.rm_branch if rm is not None else None),
        # Per RM, because a roster can be mixed: a real account manager API 442
        # named sits beside seeded ones, and a screen has to badge them apart.
        rm_source=(rm.source if rm is not None else None),
        emi_source=EMI.EMI_SOURCE[top],
        provenance=dict(features="SIMULATED", journey="SIMULATED", campaign="SIMULATED",
                        emi=EMI.EMI_SOURCE[top], rates=EMI.EMI_SOURCE_BANK),
        spark=spark,
    )


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def build_frames(cfg: ModelConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load, assemble and stack — once.  The frame does not depend on the seed."""
    t = F.load_tables(cfg.data)
    base = F.as_categorical(F.customer_month_frame(t))
    if int(base["has_journey"].min()) != 1:
        raise AssertionError("a drop-off population row with no application history")
    stacked = F.as_categorical(F.stack(base))
    return base, stacked, t


def run(cfg: ModelConfig, out_json: Path | None = None,
        metrics_json: Path | None = None, verbose: bool = True) -> dict:
    t0 = time.time()
    base, stacked, tables = build_frames(cfg)
    snap = int(base["month"].max())
    if verbose:
        print(f"frame: {len(base):,} customer-months x {len(PRODUCTS)} products "
              f"= {len(stacked):,} rows, {len(F.FEATURES)} features  [{time.time() - t0:.0f}s]")

    # ---- seeds ------------------------------------------------------------- #
    seeds = tuple(dict.fromkeys((cfg.seed, *cfg.seeds)))
    per_seed, main = [], None
    for s in seeds:
        r = evaluate_seed(base, stacked, cfg, s, full=(s == cfg.seed))
        if s == cfg.seed:
            main = r
        per_seed.append({k: v for k, v in r.items() if k != "_objects"})
        if verbose:
            print(f"  seed {s}: baseline {r['baseline']:.3%}  "
                  f"precision@{cfg.budget:.0%} {r['precision'][cfg.budget]['precision']:.3%}  "
                  f"macro AUC {r['macro_auc']:.3f}  menu@4 {r['menu']['menu_of_4_hit_rate']:.3f}"
                  f"  [{time.time() - t0:.0f}s]")

    o = main["_objects"]
    sp, rk, P, h, hb, Ph, y = (o["split"], o["ranker"], o["P"], o["held"], o["hb"], o["Ph"], o["y"])
    p_top, p_any = o["p_top"], o["p_any"]
    scores_main, alt_main = o["scores"], o["alt_scores"]

    # ---- auxiliaries -------------------------------------------------------- #
    rng = np.random.default_rng(cfg.seed)
    sh = fit_shopper(base, sp, cfg)
    shopper_all = sh.score(base)
    s_auc, s_lo, s_hi = M.auc_ci(hb["t_shopper_truth"].fillna(0).astype(int).to_numpy(),
                                 shopper_all[h])

    up = fit_uplift(base, sp, cfg, rng)
    u_all = up.score(base)
    T, y_obs = randomised_campaign(base, h, rng)
    q = M.qini(u_all[h], T, y_obs)
    q.update(persuadable_share_top20=round(float(
        hb["t_persuadable"].to_numpy()[np.argsort(-u_all[h])[: max(1, int(0.2 * len(hb)))]].mean()), 3),
        persuadable_share_book=round(float(base.loc[base.month == snap, "t_persuadable"].mean()), 3),
        dnd_share_book=round(float(base.loc[base.month == snap, "t_dnd"].mean()), 3),
        definition="Y(1) and Y(0) both come from data/labels.csv; the 50/50 assignment is "
                   "simulated, the potential outcomes are not.")
    if verbose:
        print(f"  shopper AUC {s_auc:.3f} | uplift top-20% {q['inc_per_1000_top20']} "
              f"vs {q['inc_per_1000_all']} per 1,000  [{time.time() - t0:.0f}s]")

    # ---- exhibits ----------------------------------------------------------- #
    sig = signal_effects(rk, stacked, h, cfg)
    oot = out_of_time(base, stacked, cfg, sp, main["precision"][cfg.budget]["precision"]) \
        if not cfg.quick else dict(status="skipped_quick")
    perm = permuted_label_auc(stacked, base, cfg, sp) if not cfg.quick else float("nan")
    ladder = baseline_ladder(base, cfg, sp, scores_main, h) if not cfg.quick else []
    early = hb["month"].to_numpy() < snap - cfg.oot_months + 1
    stability = float(M.psi(p_top[early], p_top[~early])) if early.any() and (~early).any() else float("nan")
    calib = M.reliability(p_any, y)
    if verbose:
        print(f"  signals negative {sig['n_negative']}/4 (unconstrained "
              f"{sig['n_negative_unconstrained']}/4) | permuted AUC {perm:.3f}  "
              f"[{time.time() - t0:.0f}s]")

    # ---- uncertainty, three ways (review §10) --------------------------------- #
    # Sampling, training-seed and generator variability are three different
    # questions and get three separate fields. Only the first two are computed
    # here; the third is a separate, much longer run and is read from disk if it
    # has been done (`src/experiments/generator_variation.py`).
    pred_path = BS.persist(
        cfg.data, cfg.seed, hb["cust_id"].to_numpy(), hb["month"].to_numpy(), y,
        hb["safe_emi"].to_numpy(), hb["eligible_for_contact"].to_numpy() == 1, Ph,
        hb["t_label_product"].fillna("").to_numpy(),
        hb["dropoff_product"].astype(str).to_numpy())
    boot = BS.precision_ci(
        hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy(), Ph,
        hb["eligible_for_contact"].to_numpy() == 1, y,
        budgets=(0.05, cfg.budget, 0.20), seed=cfg.seed)
    boot["headline"] = BS.headline_ci(boot, cfg.budget)
    if verbose:
        print(f"  bootstrap: {boot['headline']['interval_sentence']}  "
              f"[{time.time() - t0:.0f}s]")

    popularity = M.product_popularity(base[sp.mask(base["cust_id"], "fit")])
    menu_base = M.menu_baselines(Ph, hb, cfg.menu_k, popularity)

    # ---- roster (SM-4) -------------------------------------------------------- #
    # Round-robin, keyed by cust_id, over the whole drop-off population — not
    # just this month's snapshot — so a customer keeps the same RM whether or
    # not they make a given month's queue. Independent of `cfg.bank`: an RM
    # directory is HRMS data, not the customer-column enrichment SM-6 gates.
    roster_obj = RO.load_roster(cfg.data)
    rm_map = RO.assign(base["cust_id"].unique(), roster_obj)

    # ---- bank enrichment (SM-6, `--bank` only) ------------------------------- #
    bank_ctx = BK.build_context(cfg.data, cfg.bank)
    if verbose and cfg.bank:
        print(f"  --bank: mode={bank_ctx.mode} families={bank_ctx.families} "
              f"[{time.time() - t0:.0f}s]")

    # ---- queue -------------------------------------------------------------- #
    leads, counts, extra = build_queue(base, P, rk, shopper_all, u_all,
                                       tables["panel"], tables["journeys"], cfg, snap, rm_map)

    # SM-6 demo binding: one lead's IDENTITY family is the sandbox's own sample
    # master record, so the platform's CRM push has a real PAN to dedupe on.
    # `model.export.DEMO_BINDINGS` is the whole arrangement — which customer,
    # which fields, and why every other family stays exactly where it was.
    # Applied here rather than inside `_lead` so the cockpit pack and the
    # platform export read the same one definition, and so a run without
    # `--bank` (or without a pull that answered) changes nothing at all.
    demo_bound = []
    for lead in leads:
        if EXP.demo_binding_for(lead["id"], bank_ctx) is not None:
            lead["provenance"]["identity"] = EXP.DEMO_BINDING_SOURCE
            demo_bound.append(lead["id"])
    sup, n_pool = extra["suppression"], extra["n_contactable"]
    snap_rows, Psnap, elig_snap = extra["snap_rows"], extra["P"], extra["elig"]

    # SK-23 is measured on the rows the POLICY would call at the budget, not on a
    # separate argsort — a fairness reading of a list nobody receives is not a
    # fairness reading.
    sel = np.zeros(len(snap_rows), dtype=bool)
    sel[PO.select(extra["scores"], budget=cfg.budget)] = True
    fairness = M.fairness_table(snap_rows[elig_snap], sel[elig_snap])
    income = M.income_accuracy(hb[hb["month"] == snap] if (hb["month"] == snap).any() else hb)

    # ---- the numbers the deck quotes ---------------------------------------- #
    # one rounding, used everywhere the two headline numbers appear, so the
    # headline, the band, the registered block and the cockpit cannot disagree
    # in the fourth decimal place.
    baseline = round(main["baseline"], 4)
    prec = round(main["precision"][cfg.budget]["precision"], 4)
    curve = []
    for b in BUDGETS:
        a = PO.precision_at(y, scores_main, b)
        curve.append(dict(budget=round(b, 2), precision=round(a["precision"], 4),
                          lift=round(a["precision"] / baseline, 1) if baseline else None,
                          ci_low=round(a["ci_low"], 4), ci_high=round(a["ci_high"], 4),
                          contacts=int(n_pool * b),
                          expected_conversions=int(round(n_pool * b * a["precision"]))))

    # ---- the delivered list, measured ---------------------------------------- #
    # The cockpit exports the first `queue_size` rows of the ranked list. That is
    # a tighter budget than the registered 10%, so its precision is quoted at its
    # OWN budget, measured on the held-out split like everything else — never by
    # reading labels off the in-sample snapshot rows the cockpit happens to show.
    delivered = dict(extra["delivered"])
    eq_budget = delivered.get("equivalent_budget")
    if eq_budget:
        a = PO.precision_at(y, scores_main, eq_budget)
        delivered["precision_at_queue_size"] = M.measured(
            round(a["precision"], 4), round(a["ci_low"], 4), round(a["ci_high"], 4), a["k"])
        delivered["headline_at_queue_size"] = M.headline(baseline, a["precision"])

    # ---- ranking comparison (review §4) -------------------------------------- #
    # Both candidate rankings, same rows, same budget, every run. The default is
    # `model.policy.DEFAULT_RANKING` and this block is the evidence for it.
    ranking_comparison = dict(
        default=scores_main.ranking, compared_with=alt_main.ranking,
        budget=cfg.budget,
        blend_weights=dict(intent=PO.INTENT_WEIGHT, capacity=PO.CAPACITY_WEIGHT),
        packed_seed={
            scores_main.ranking: {str(int(b * 100)): round(
                main["precision"][b]["precision"], 4) for b in (0.05, cfg.budget, 0.20)},
            alt_main.ranking: {str(int(b * 100)): round(
                main["precision_alt_ranking"][b]["precision"], 4)
                for b in (0.05, cfg.budget, 0.20)},
        },
        seed_mean={
            scores_main.ranking: round(float(np.mean(
                [s_["precision"][cfg.budget]["precision"] for s_ in per_seed])), 4),
            alt_main.ranking: round(float(np.mean(
                [s_["precision_alt_ranking"][cfg.budget]["precision"] for s_ in per_seed])), 4),
        },
        decision="Rank on the calibrated product probability. The pre-agreed rule was to "
                 "keep the 0.65 intent / 0.35 capacity blend only if its held-out "
                 "precision@10% came within 2 percentage points of probability-only "
                 "ranking; it does not. Capacity survives as a displayed secondary "
                 "signal (`capacity`, `blend`), not as a ranking input.",
    )
    ranking_comparison["gap_pp"] = round(100.0 * (
        ranking_comparison["packed_seed"][scores_main.ranking][str(int(cfg.budget * 100))]
        - ranking_comparison["packed_seed"][alt_main.ranking][str(int(cfg.budget * 100))]), 2)

    spread = dict(
        baseline=M.spread([s_["baseline"] for s_ in per_seed]),
        precision_at_budget=M.spread([s_["precision"][cfg.budget]["precision"] for s_ in per_seed]),
        precision_at_5pct=M.spread([s_["precision"][0.05]["precision"] for s_ in per_seed]),
        precision_at_20pct=M.spread([s_["precision"][0.20]["precision"] for s_ in per_seed]),
        precision_at_budget_alt_ranking=M.spread(
            [s_["precision_alt_ranking"][cfg.budget]["precision"] for s_ in per_seed]),
        macro_auc=M.spread([s_["macro_auc"] for s_ in per_seed]),
        menu_of_4_hit_rate=M.spread([s_["menu"]["menu_of_4_hit_rate"] for s_ in per_seed]),
        window_respect_rate=M.spread([s_["windows"]["window_respect_rate"] for s_ in per_seed]),
        ece_overall=M.spread([s_["ece_overall"] for s_ in per_seed]),
        **{f"auc_{p}": M.spread([s_["per_product"][p]["auc"] for s_ in per_seed]) for p in PRODUCTS},
    )

    def _m(a: dict) -> dict:
        return M.measured(round(a["precision"], 4), round(a["ci_low"], 4),
                          round(a["ci_high"], 4), a["k"])

    b_lo, b_hi = M.wilson(int(y.sum()), len(y))
    baseline_ci = M.measured(baseline, round(b_lo, 4), round(b_hi, 4), int(len(y)))
    prec_at = {str(int(b * 100)): _m(main["precision"][b])
               for b in (0.05, cfg.budget, 0.20)}
    m_lo, m_hi = main["menu"]["menu_of_4_hit_rate_ci"]
    menu_ci = M.measured(_r(main["menu"]["menu_of_4_hit_rate"]), _r(m_lo), _r(m_hi),
                         main["menu"]["n_positives"])
    w_lo, w_hi = main["windows"].get("window_respect_ci", (None, None))
    win_ci = M.measured(_r(main["windows"]["window_respect_rate"]), _r(w_lo), _r(w_hi),
                        main["windows"].get("n"))
    shop_ci = M.measured(round(s_auc, 4), round(s_lo, 4), round(s_hi, 4), int(len(hb)),
                         "hanley-mcneil")

    registered = {
        "random_contact_disbursement_rate": baseline,
        "precision_at_10pct_budget": prec,
        "precision_at_5pct_and_20pct_budget": {
            "at_5pct": main["precision"][0.05], "at_20pct": main["precision"][0.20]},
        "window_respect_rate": main["windows"]["window_respect_rate"],
        "window_shopper_auc": s_auc,
        "baseline_ladder_headline_uplift": {
            "baseline_per_100": round(baseline * 100), "model_per_100": round(prec * 100),
            "headline": M.headline(baseline, prec)},
        "oot_precision_at_10pct_degradation_pp": oot.get("degradation_pp"),
        "auc": {p: v["auc"] for p, v in main["per_product"].items()},
        "macro_auc": main["macro_auc"],
        "ece": float(M.ece(p_any, y)),
        "ece_per_product": {p: v["ece"] for p, v in main["per_product"].items()},
        "menu_of_4_hit_rate": main["menu"]["menu_of_4_hit_rate"],
        "top_1_product_accuracy": main["menu"]["top_1_product_accuracy"],
        "shopper_signal_negative_direction_count": sig["n_negative"],
        "psi_score_distribution": stability,
        "features_using_post_abandon_information": len(set(F.FEATURES) & FORBIDDEN_INPUTS),
        "permuted_label_auc": perm,
        "n_seeds_run": len(per_seed),
        "cross_seed_precision_at_10pct_ci_width_pp": spread["precision_at_budget"]["pct_width_pp"],
        "adverse_impact_ratio": min((f["ratio"] for f in fairness if f["n"] >= 500),
                                    default=float("nan")),
        "gig_worker_failure_disclosure": bool(income.get("gig_within15") is not None),
        "precision_at_10pct_by_baseline_rung": ladder,
        # SK-26, added after registration (criteria.yaml amendments, 2026-09-22):
        # reported, never gated. The same block validation runner 06 reads.
        "tier_plateau_sensitivity": delivered["tier_plateau_sensitivity"],
        "auc_and_precision_at_10pct": {},
    }
    registered["auc_and_precision_at_10pct"] = _by_cut(hb, Ph, y, p_top, cfg)
    band = M.bands({
        "SK-01": baseline, "SK-02": prec,
        "SK-03": registered["precision_at_5pct_and_20pct_budget"],
        "SK-04": main["windows"]["window_respect_rate"], "SK-05": s_auc,
        "SK-06": registered["baseline_ladder_headline_uplift"],
        "SK-07": oot.get("degradation_pp"),
        "SK-08": min(v["auc"] for v in main["per_product"].values()),
        "SK-09": main["macro_auc"],
        "SK-10": {k: len(v) for k, v in registered["auc_and_precision_at_10pct"].items()},
        "SK-11": registered["ece"],
        "SK-12": max(v["ece"] for v in main["per_product"].values()),
        "SK-13": main["menu"]["menu_of_4_hit_rate"],
        "SK-14": main["menu"]["top_1_product_accuracy"],
        "SK-15": sig["n_negative"], "SK-16": stability,
        "SK-17": registered["features_using_post_abandon_information"],
        "SK-18": perm, "SK-19": None, "SK-20": len(per_seed),
        "SK-21": spread["precision_at_budget"]["pct_width_pp"], "SK-22": None,
        "SK-23": registered["adverse_impact_ratio"],
        "SK-24": registered["gig_worker_failure_disclosure"],
        "SK-25": ladder or None,
        # The count per cut, not the whole staircase — `metrics.registered` and
        # `metrics.delivered_queue` both carry the full block.
        "SK-26": {name: c["within"] for name, c
                  in delivered["tier_plateau_sensitivity"]["cuts"].items()},
    }, seed_means={
        "SK-01": spread["baseline"]["mean"],
        "SK-02": spread["precision_at_budget"]["mean"],
        "SK-04": spread["window_respect_rate"]["mean"],
        "SK-09": spread["macro_auc"]["mean"],
        "SK-11": spread["ece_overall"]["mean"],
        "SK-13": spread["menu_of_4_hit_rate"]["mean"],
        "SK-08": min(spread[f"auc_{p}"]["mean"] for p in PRODUCTS),
    })

    # Three estimands, three fields, never merged into one "95% CI".
    gen_var = _generator_variation(cfg)
    uncertainty = dict(
        sample=boot,
        training_seed=dict(
            method="percentile spread across the registered training seeds",
            estimand="training-seed variability, NOT a confidence interval",
            seeds=list(seeds), n=len(per_seed),
            baseline=spread["baseline"], precision_at_budget=spread["precision_at_budget"],
            precision_at_5pct=spread["precision_at_5pct"],
            precision_at_20pct=spread["precision_at_20pct"],
            note="The packed seed's own value can fall outside this interval; five "
                 "points interpolate well inside their own min and max."),
        generator=gen_var,
        predictions_file=str(Path(pred_path).relative_to(cfg.root)),
        note="sample = which customers landed in the book (customer-clustered "
             "bootstrap, queue re-selected inside each resample). training_seed = "
             "which train/calibrate/holdout split the model got. generator = which "
             "synthetic world the book was drawn from. They do not compose into one "
             "interval and are not shown as one.",
    )

    metrics = dict(
        headline=M.headline(baseline, prec),
        headline_parts=dict(baseline=baseline, precision=prec, budget=cfg.budget,
                            baseline_per_100=round(baseline * 100),
                            precision_per_100=round(prec * 100),
                            population="drop-off population, eligible for contact",
                            ranking=scores_main.ranking,
                            note="Both numbers are disbursement rates over the same population "
                                 "and the same 100 calls: one contacts at random, the other "
                                 "contacts the model's top 10% selected by exactly the policy "
                                 "that builds the delivered queue (model.policy: suppression, "
                                 "eligibility, ranking, truncation, tie-break)."),
        per_product={p: dict(v, label=PRODUCT_LABEL[p]) for p, v in main["per_product"].items()},
        blended=dict(baseline=baseline, auc_macro=round(main["macro_auc"], 3),
                     row_auc=round(main["row_auc"], 4), prec_curve=curve,
                     precision_at_budget=prec,
                     precision_ci=[round(main["precision"][cfg.budget]["ci_low"], 4),
                                   round(main["precision"][cfg.budget]["ci_high"], 4)],
                     budget=cfg.budget),
        calibration=calib,
        uplift=q, fairness=fairness, income_acc=income,
        excluded_features=txt.EXCLUDED_FEATURES,
        menu=main["menu"], windows=dict(main["windows"], per_product_days=dict(WINDOW_DAYS)),
        menu_baselines=menu_base,
        suppression=sup,
        delivered_queue=delivered, ranking_comparison=ranking_comparison,
        uncertainty=uncertainty,
        shopper=dict(auc=round(s_auc, 4), ci=[round(s_lo, 4), round(s_hi, 4)],
                     n=int(len(hb)), target="generator latent window_shopper flag",
                     production_note="in production the target is the observable proxy "
                                     "(two or more abandonments, no disbursement in 12 months); "
                                     "this figure is an upper bound on that."),
        signal_effects=sig,
        oot=oot, stability=dict(psi_score_distribution=stability),
        leakage=dict(forbidden_inputs_used=registered["features_using_post_abandon_information"],
                     forbidden_set_size=len(FORBIDDEN_INPUTS), permuted_label_auc=perm),
        baseline_ladder=ladder,
        seeds=dict(n=len(per_seed), list=list(seeds), default=cfg.seed,
                   spread=spread, per_seed=per_seed),
        by_cut=registered["auc_and_precision_at_10pct"],
        feature_families={k: list(v) for k, v in F.FEATURE_FAMILIES.items()},
        # --- the same numbers under the names the brief and the cockpit use, each
        # --- carrying its interval so a screen never renders a point as exact.
        baseline_dropoff_disbursement=baseline_ci,
        precision_at=prec_at,
        precision_at_10pct=prec_at[str(int(cfg.budget * 100))],
        per_product_auc={p: dict(auc=v["auc"], auc_ci=v["auc_ci"], ece=v["ece"],
                                 n_pos_test=v["n_pos_test"])
                         for p, v in main["per_product"].items()},
        macro_auc=round(main["macro_auc"], 4), auc_macro=round(main["macro_auc"], 4),
        menu_hit_rate=menu_ci, menu_of_4_hit_rate=menu_ci,
        window_respect=win_ci, window_respect_rate=win_ci,
        shopper_signal_auc=shop_ci, shopper_auc=shop_ci,
        ece=round(registered["ece"], 5),
        oot_degradation_pp=oot.get("degradation_pp"),
        suppressed_count=sup["suppressed_count"],
        registered=registered, bands=band,
    )

    meta = dict(
        n_customers=tables["book_meta"]["n_customers"],
        n_consented=tables["book_meta"]["n_consented"],
        ref_month=str(snap_rows["date"].iloc[0]),
        snapshot_month=snap,
        population=dict(
            name="drop-off population",
            definition="consented, contactable customers with an abandoned application in the "
                       "trailing 365 days and no disbursement in flight",
            customers=int(base.cust_id.nunique()), customer_months=int(len(base)),
            at_snapshot=int(extra["n_pool"]), contactable_at_snapshot=int(n_pool)),
        model=dict(kind="one LightGBM over (customer, month, product) with `product` as a "
                        "categorical; six products; isotonic calibration per product",
                   n_features=len(F.FEATURES), products=list(PRODUCTS),
                   monotone_signals=list(F.MENTOR_SIGNALS),
                   label="label_disbursed_in_window (disbursement of the offered product inside "
                         "its decision window, after an RM contact)",
                   split="customer-grouped 52.5 / 17.5 / 30 fit / calibrate / hold out"),
        policy=dict(
            module="model.policy", ranking=scores_main.ranking,
            steps=["suppression", "eligibility", "ranking", "truncation", "tie-break"],
            tie_break="cust_id ascending",
            budget=cfg.budget, queue_size=int(cfg.queue_size),
            secondary_signals=["intent", "capacity", "blend"],
            note="The same function selects the list precision is measured on and the list "
                 "the cockpit and the platform export receive."),
        clocks=dict(
            abandoned_at="when the customer abandoned the application — the URGENCY clock",
            scored_at="the snapshot instant the model ranked the pool at",
            contact_by="abandoned_at + the offered product's decision window",
            outcome_horizon_days="days after CONTACT inside which a disbursement counts",
            unresolved="Which clock should drive urgency is a question for the mentors; the "
                       "assumption documented and implemented here is abandonment."),
        generated_from="synthetic liability book (60,000 customers x 30 months) with an "
                       "application-journey layer; the drop-off population is scored",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        runtime_s=round(time.time() - t0, 1),
    )
    provenance = dict(
        provenance_version=1, product="sanket", mode=bank_ctx.mode if cfg.bank else "simulated",
        fixture_reason=bank_ctx.reason if cfg.bank else
            "No bank pull in this run: every column is generated by src/book and "
            "src/journeys and labelled SIMULATED. Pass --bank to read data/bank/pulled.json "
            "/ provenance.json / fixture.json instead.",
        families=bank_ctx.families,
        # SM-4/SM-5 landed (unconditionally, `--bank` or not); SM-6's bank
        # overlay and platform export are what `--bank` still gates.
        hooks=dict(
            rm_id=f"SM-4 landed: round-robin over the {roster_obj.source} roster "
                  f"({len(roster_obj.rms)} RMs, {len(roster_obj.active_rms)} active) — "
                  "see the top-level `roster` block, whose `bank_account_managers` "
                  "carries what API 442 actually returned and `bank_source_note` says "
                  "whether it could name an RM",
            # The distribution, not one tag: SM-5's ladder is 473 schedule ->
            # 433 rate -> TYPICAL_EMI, and a single string here would hide which
            # products took which step.
            emi_source={p: EMI.EMI_SOURCE[p] for p in PRODUCTS},
            # Named, not implied. A badge that reads BANK_API on one lead and
            # SIMULATED on the other 319 has to say why, in the same file.
            demo_binding=(dict(
                leads=demo_bound,
                bound_to={cid: EXP.DEMO_BINDINGS[cid] for cid in demo_bound},
                fields=["cif_id", "pan", "entity_name", "mobile"],
                source="IDBI Atlas sandbox sample master record (API 456, with API 365 "
                       "as the name fallback)",
                badge=EXP.DEMO_BINDING_SOURCE,
                note=EXP.DEMO_BINDING_NOTE,
            ) if demo_bound else
                "no lead is bound in this run: --bank was not passed, no pull is on this "
                "checkout, or the pull did not answer about the bound sandbox record"),
            pending=["data/export/sanket_export.json (SM-6's platform contract shape) is "
                     "only emitted when --bank is passed",
                     "meta.model_run_id / git_sha / criteria_sha in that export are filled "
                     "by the platform batch, not by this script"],
        ),
    )

    out = dict(meta=meta, counts=counts, metrics=metrics, provenance=provenance,
               roster=RO.roster_block(roster_obj), gig_case_id=extra["gig_case_id"], leads=leads)
    _write(out, out_json, metrics_json, meta, metrics, verbose)

    if cfg.bank and out_json is not None:
        export_path = cfg.root / "data" / "export" / "sanket_export.json"
        payload = EXP.build_export(cfg, meta, counts, metrics, leads, extra["gig_case_id"],
                                   snap_rows, tables, rm_map, bank_ctx)
        EXP.write(payload, export_path)
        if verbose:
            print(f"  --bank: wrote {export_path} "
                  f"({len(payload['customers'])} customers, {len(payload['journeys'])} journeys, "
                  f"{len(payload['leads'])} leads)  [{time.time() - t0:.0f}s]")

    return out


def _by_cut(hb: pd.DataFrame, Ph: np.ndarray, y: np.ndarray, p_top: np.ndarray,
            cfg: ModelConfig) -> dict:
    """SK-10: AUC and precision@budget for every level of every registered cut."""
    d = hb.copy()
    d["_age_band"] = pd.cut(d.age, [20, 30, 45, 63], labels=["21-30", "31-45", "46+"])
    d["_income_band"] = pd.qcut(d["t_income_at_month"].rank(method="first"), 5,
                                labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    d["_tenure_band"] = pd.cut(d.tenure_m, [-1, 6, 12, 24, 36, 10 ** 6],
                               labels=["<6m", "6-12m", "12-24m", "24-36m", "36m+"])
    cuts = {"channel": "journey_last_channel", "occupation_segment": "segment",
            "income_band": "_income_band", "tenure_band": "_tenure_band",
            "stage_reached": "dropoff_stage_reached", "city_tier": "city_tier",
            "age_band": "_age_band"}
    out = {}
    for name, col in cuts.items():
        rows = []
        for g, sub in d.groupby(col, observed=True):
            i = sub.index.to_numpy()
            yy, ss = y[i], p_top[i]
            if len(yy) < 500:
                rows.append(dict(level=str(g), n=int(len(yy)), status="skipped_low_n"))
                continue
            a, lo, hi = M.auc_ci(yy, ss)
            pr = M.precision_at(yy, ss, cfg.budget)
            rows.append(dict(level=str(g), n=int(len(yy)), n_pos=int(yy.sum()),
                             auc=round(a, 4), auc_ci=[round(lo, 4), round(hi, 4)],
                             precision_at_budget=round(pr["precision"], 4),
                             precision_ci=[round(pr["ci_low"], 4), round(pr["ci_high"], 4)],
                             baseline=round(float(yy.mean()), 4)))
        out[name] = rows
    return out


def _write(out: dict, out_json, metrics_json, meta, metrics, verbose: bool) -> None:
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            v = float(o)
            return None if not np.isfinite(v) else round(v, 6)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, pd.Timestamp):
            return o.isoformat()
        return o

    payload = clean(out)
    if out_json is not None:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps(payload, ensure_ascii=False,
                                             allow_nan=False, separators=(",", ":")))
    if metrics_json is not None:
        Path(metrics_json).parent.mkdir(parents=True, exist_ok=True)
        Path(metrics_json).write_text(json.dumps(
            clean(dict(meta=meta, metrics=metrics, provenance=out["provenance"],
                       counts=out["counts"])),
            ensure_ascii=False, allow_nan=False, indent=1))
    if verbose:
        b = metrics["bands"]
        gate_fail = [k for k, v in b.items() if v["verdict"] == "fail" and v["gating"]]
        soft_fail = [k for k, v in b.items() if v["verdict"] == "fail" and not v["gating"]]
        disagree = [k for k, v in b.items() if v.get("agrees_across_seeds") is False]
        print("\n" + metrics["headline"])
        print(f"bands: {sum(1 for v in b.values() if v['verdict'] == 'pass')} pass, "
              f"{len(gate_fail)} GATING FAIL {gate_fail or ''}, "
              f"{len(soft_fail)} reported-fail {soft_fail or ''}, "
              f"{sum(1 for v in b.values() if v['verdict'] == 'report')} report, "
              f"{sum(1 for v in b.values() if v['verdict'] in ('not_measured', 'not_run'))} not run")
        if disagree:
            for k in disagree:
                v = b[k]
                print(f"  ! {k} {v['metric']}: packed seed {v['value']:.4f} -> {v['verdict']}, "
                      f"5-seed mean {v['seed_mean']:.4f} -> {v['verdict_on_seed_mean']}")
        if out_json is not None:
            size = len(json.dumps(payload)) / 1e6
            dq = metrics["delivered_queue"]["tiers"]
            print(f"queue: {len(out['leads'])} leads "
                  f"(delivered {dq['hot']} hot / {dq['warm']} warm / {dq['cold']} cold) | "
                  f"suppressed {metrics['suppression']['suppressed_count']} | "
                  f"wrote {out_json} ({size:.1f} MB)")


#: Where `src/experiments/generator_variation.py` leaves its result.  The pack
#: reads it if it is there and says so plainly if it is not — a missing
#: measurement is reported as missing, never as zero.
GENERATOR_VARIATION_REL = Path("data") / "experiments" / "generator_variation.json"


def _generator_variation(cfg: ModelConfig) -> dict:
    """The third uncertainty field: how much the answer moves with the world.

    The book, the journey layer and the labels are all drawn from one generator
    seed.  Re-drawing them and re-measuring is the only way to say how much of
    the headline is a property of the model rather than of this particular
    synthetic world, and it costs a full regeneration per seed — far more than
    this script's budget.  It therefore runs separately and is read from disk.
    """
    path = cfg.root / GENERATOR_VARIATION_REL
    if not path.is_file():
        return dict(status="not_measured",
                    estimand="variability across generator seeds (a different "
                             "synthetic world, same model recipe)",
                    how=f"python3 src/experiments/generator_variation.py — writes "
                        f"{GENERATOR_VARIATION_REL.as_posix()}",
                    note="Not measured in this run. Reported as missing rather than "
                         "folded into the seed spread, which answers a different "
                         "question.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return dict(status="unreadable", error=str(exc),
                    how=f"regenerate with python3 src/experiments/generator_variation.py")
    doc.setdefault("status", "measured")
    return doc
