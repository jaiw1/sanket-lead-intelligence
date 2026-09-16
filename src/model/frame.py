"""Point-in-time feature assembly and the stacked (customer, month, product) frame.

The training frame
------------------
``data/labels.csv`` filtered to ``eligible_for_contact = 1`` — one row per
(customer, month) of the drop-off population that the bank is allowed to call.
Each such row is expanded into **six** rows, one per candidate product, and the
per-product label ``label_product_<p>`` becomes ``y``.  The six per-product
labels partition the row label (``labels.check()`` asserts it), so:

* ``P(row disburses) = sum_p P(product p disburses)`` — mutually exclusive, and
* one LightGBM with ``product`` as a categorical learns all six at once.

Three feature sources, all point-in-time safe, none of them re-derived here:

===================  ==========================================================
source               what it contributes
===================  ==========================================================
``customer_panel``   trailing behavioural aggregates over months <= m only
``journeys.features``the application-journey block, computed by the lane that
                     owns the timestamps (SK-17 is a zero-tolerance band, so the
                     safe aggregation lives there, not here)
``labels.csv``       the bank's own contact history and the suppression decision,
                     computed once in ``journeys.labels`` and read back verbatim
===================  ==========================================================

Two rules inherited from DATA_CARD 12.5 and honoured here:

* **a contact counter of 0 is a genuine zero**, so ``contacts_30d`` and friends
  are used as they come;
* **an absent journey row is not a zero** — it means no application history.
  Every row of the drop-off population has one by construction (a customer is in
  the pool *because* they abandoned something), which the loader asserts, but the
  ``has_journey`` flag is emitted anyway so the same builder can score a
  whole-book frame without silently teaching the model that never-applied looks
  like clean-applied.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from journeys.features import journey_features_as_at

from . import BOOK_ANCHOR, FORBIDDEN_INPUTS, PRODUCTS, TRUTH_PREFIX, TYPICAL_EMI, WINDOW_DAYS

# --------------------------------------------------------------------------- #
# feature families  (also the ablation map runner 08 / SK-19 needs)
# --------------------------------------------------------------------------- #

#: family -> feature names.  Every model input belongs to exactly one family;
#: ``FEATURES`` is derived from this dict so the two cannot drift apart.
FEATURE_FAMILIES: dict[str, tuple[str, ...]] = {
    # --- what the CASA book says about income and its rhythm --------------- #
    "income": (
        "credits_med_6m", "credits_cv_6m", "credits_gr_6m", "bonus_share_3m",
        "salary_source_count", "salary_day_drift",
    ),
    # --- balances, buffers and the monthly squeeze ------------------------- #
    "balance": (
        "bal_avg", "bal_gr_6m", "minbal_ratio", "fd_ratio", "fd_drop",
        "minbal_charge_6m",
    ),
    # --- committed and discretionary outflow ------------------------------- #
    "outflow": (
        "rent_share", "rent_ratio_6m", "fuel_ratio_3m", "fuel_share",
        "school_share", "ecom_share", "card_share", "insurance_share",
        "upi_share", "upi_count_3m",
    ),
    # --- existing debt, incl. the cross-bank block APIs 595/739 would fill -- #
    "debt": (
        "emi_share", "emi_gr_6m", "has_auto_emi", "external_emi_count",
        "other_bank_emi_share", "mandate_fail_6m",
    ),
    # --- KYC / life-event tells -------------------------------------------- #
    "life_event": ("kyc_event_6m",),
    # --- who they are (no protected attribute; see EXCLUDED_FEATURES) ------ #
    "profile": ("age", "segment", "city_tier", "tenure_m"),
    # --- the application journey (SM-3's reason the drop-off list is a list) #
    "journey": (
        "journey_stage_idx", "journey_attempts", "journey_open_now",
        "journey_ever_abandoned", "journey_ever_disbursed", "journey_fee_paid",
        "journey_docs_shortfall", "journey_rm_contacted",
        "journey_amount_requested", "journey_stated_income_ratio",
        "journey_days_since_last_event", "journey_days_since_first_start",
        "journey_last_channel", "has_journey", "days_since_abandon",
        "dropoff_attempts", "dropoff_product",
    ),
    # --- the four the mentors named, plus the browsing tell ---------------- #
    "shopper": (
        "journey_blank_field_ratio", "journey_refused_income",
        "journey_fee_balk", "journey_doc_refusal",
        "journey_multi_product_revisits", "journey_revisits_30d",
        "journey_products_viewed_30d",
    ),
    # --- what the bank has already done to this customer ------------------- #
    "contact": (
        "contacts_30d", "contacts_90d", "campaign_contacts_6m",
        "last_contact_days", "last_campaign_matches_product",
    ),
    # --- the candidate product, and how it relates to this customer -------- #
    "product": (
        "product", "is_dropoff_product", "product_window_days",
        "dwell_product_3m", "dwell_product_share", "emi_headroom_ratio",
        "journey_last_product_matches",
    ),
}

FEATURES: tuple[str, ...] = tuple(f for fam in FEATURE_FAMILIES.values() for f in fam)

#: LightGBM categoricals.  ``product`` and ``dropoff_product`` together let one
#: model learn the substitution structure (gold <-> personal, home <-> lap)
#: from the data rather than importing the generator's affinity matrix.
CATEGORICAL: tuple[str, ...] = ("product", "dropoff_product", "segment", "journey_last_channel")

#: The four window-shopper signals the mentors named.  Each is constrained to
#: push the disbursement probability DOWN (``monotone_constraints`` = -1), and
#: :func:`model.metrics.signal_effects` measures the realised direction both with
#: and without that constraint so the constraint is never the only evidence.
MENTOR_SIGNALS: tuple[str, ...] = (
    "journey_blank_field_ratio", "journey_refused_income",
    "journey_fee_balk", "journey_doc_refusal",
)

#: Features that live at the (customer, month) grain — everything except the
#: per-product block.  Used by the two models that do not need a candidate
#: product: the auxiliary window-shopper detector and the uplift pair.
CUSTOMER_FEATURES: tuple[str, ...] = tuple(
    [f for fam, fs in FEATURE_FAMILIES.items() if fam != "product" for f in fs]
    + ["dwell_total_3m"]
)

#: The auxiliary window-shopper detector.  It is a *separate* model with a
#: separate target (``t_shopper_truth``) and never feeds the main one; its output
#: drives the negative chips and is measured against SK-05.
SHOPPER_FEATURES: tuple[str, ...] = CUSTOMER_FEATURES

#: Measurement-only columns, all loaded with :data:`model.TRUTH_PREFIX`.
TRUTH_COLUMNS: tuple[str, ...] = (
    "t_true_income", "t_inc_drift", "t_shopper_truth", "t_persuadable",
    "t_consent", "t_dnd", "t_label", "t_label_product", "t_label_no_contact",
    "t_days_to_disbursement", "t_window_days", "t_suppressed",
    "t_suppression_reason",
)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def month_start(month: int, anchor: tuple[int, int] = BOOK_ANCHOR) -> pd.Timestamp:
    """First instant of panel month ``month`` — when an RM picks the list up.

    The drop-off population's membership is decided at exactly this instant
    (DATA_CARD 12.1), so every feature is computed here too: nothing that
    happens *inside* month m can reach a row that is scored for month m.
    """
    return pd.Timestamp(year=anchor[0], month=anchor[1], day=1) + pd.DateOffset(months=month)


def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the five tables the model needs, and nothing else."""
    d = Path(data_dir)
    labels = pd.read_csv(d / "labels.csv")
    keep = set(labels.cust_id.unique())
    # the whole-book counts the cockpit header quotes, read before the filter
    allbook = pd.read_csv(d / "customer_book.csv", usecols=["cust_id", "consent"])
    book_meta = dict(n_customers=int(len(allbook)),
                     n_consented=int((allbook.consent == 1).sum()))
    del allbook
    journeys = pd.read_csv(d / "journeys.csv")
    events = pd.read_csv(d / "journey_events.csv")
    book = pd.read_csv(d / "customer_book.csv")
    panel = pd.read_csv(d / "customer_panel.csv")
    truth = pd.read_csv(d / "label_truth.csv", usecols=["cust_id", "month", "shopper_truth"])
    book = book[book.cust_id.isin(keep)].reset_index(drop=True)
    panel = panel[panel.cust_id.isin(keep)].reset_index(drop=True)
    journeys = journeys[journeys.customer_id.isin(keep)].reset_index(drop=True)
    events = events[events.customer_id.isin(keep)].reset_index(drop=True)
    return dict(labels=labels, journeys=journeys, events=events, book=book,
                panel=panel, label_truth=truth, book_meta=book_meta)


# --------------------------------------------------------------------------- #
# the book block
# --------------------------------------------------------------------------- #

def book_features(panel: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """Trailing behavioural features per (cust_id, month), months <= m only.

    Every aggregate is a backward-looking rolling window over the panel, so a row
    for month m can only ever see months m, m-1, ...  The static block merged in
    from ``customer_book.csv`` is limited to attributes that do not move
    (segment, age, city tier, tenure); the book's outcome columns
    (``product``, ``event_month``) and its latents are never merged at all.
    """
    df = panel.sort_values(["cust_id", "month"], kind="stable").reset_index(drop=True)
    g = df.groupby("cust_id", sort=False)

    def roll(col: str, w: int, fn: str = "mean") -> pd.Series:
        r = g[col].rolling(w, min_periods=1)
        return getattr(r, fn)().reset_index(level=0, drop=True)

    df["credits_med_6m"] = roll("credits", 6, "median")
    med = df["credits_med_6m"].clip(lower=1.0)
    df["credits_std_6m"] = roll("credits", 6, "std").fillna(0)
    df["credits_cv_6m"] = (df.credits_std_6m / med).clip(0, 2)
    df["credits_gr_6m"] = (df.credits / g["credits"].shift(6)).replace([np.inf, -np.inf], np.nan)

    df["bal_gr_6m"] = (df.bal_avg / g["bal_avg"].shift(6)).replace([np.inf, -np.inf], np.nan)
    df["minbal_ratio"] = (df.bal_min / med).clip(0, 5)

    df["rent_share"] = (df.rent / med).clip(0, 1.5)
    df["rent_ratio_6m"] = (df.rent / g["rent"].shift(6).clip(lower=1)).where(g["rent"].shift(6) > 0)

    df["fuel_3m"] = roll("fuel_cab", 3, "mean")
    df["fuel_prev3"] = g["fuel_3m"].shift(3)
    df["fuel_ratio_3m"] = (df.fuel_3m / df.fuel_prev3.clip(lower=1)).clip(0, 6)
    df["fuel_share"] = (df.fuel_cab / med).clip(0, 0.6)

    df["emi_share"] = (df.ext_emi / med).clip(0, 1)
    df["emi_gr_6m"] = (df.ext_emi - g["ext_emi"].shift(6)).fillna(0) / med
    df["school_share"] = (df.school_fees / med).clip(0, 0.5)
    df["ecom_share"] = (df.ecommerce / med).clip(0, 0.8)

    df["fd_ratio"] = (df.fd_bal / med).clip(0, 20)
    df["fd_drop"] = ((df.fd_bal < 0.6 * g["fd_bal"].shift(3)) & (g["fd_bal"].shift(3) > 0)).astype(int)

    # ---- SD-S1's new channels --------------------------------------------- #
    # `emi_outflow_to_other_bank` is a SHARE of ext_emi, not an extra outflow
    # (DATA_CARD 5.2), so it enters as a ratio and never as committed spend.
    df["other_bank_emi_share"] = (df.emi_outflow_to_other_bank / df.ext_emi.clip(lower=1)).clip(0, 1)
    df["card_share"] = (df.card_spend / med).clip(0, 1.5)
    df["insurance_share"] = (roll("insurance_premium", 12, "sum") / (12 * med)).clip(0, 0.5)
    df["upi_share"] = (df.upi_p2m_value / med).clip(0, 1.5)
    df["upi_count_3m"] = roll("upi_p2m_count", 3, "mean")
    df["bonus_share_3m"] = (roll("bonus_or_irregular_credit", 3, "sum") / (3 * med)).clip(0, 2)
    df["salary_source_count"] = df.salary_credit_source_count
    df["salary_day_drift"] = roll("salary_credit_day", 6, "std").fillna(0)
    df["mandate_fail_6m"] = roll("mandate_failure_count", 6, "sum")
    df["minbal_charge_6m"] = roll("min_balance_charge_flag", 6, "sum")
    df["kyc_event_6m"] = roll("address_change_flag", 6, "sum") + roll("nominee_change_flag", 6, "sum")
    df["external_emi_count"] = df.external_emi_count

    # ---- per-product browsing --------------------------------------------- #
    for p in PRODUCTS:
        df[f"dwell_{p}_3m"] = roll(f"dwell_{p}", 3, "sum")
    df["dwell_total_3m"] = df[[f"dwell_{p}_3m" for p in PRODUCTS]].sum(axis=1)

    # ---- behavioural retained income -> comfortable EMI headroom ---------- #
    committed = df.rent + df.ext_emi + df.school_fees + 0.38 * df.credits_med_6m
    df["retained"] = (df.credits_med_6m - committed).clip(lower=0)
    df["safe_emi"] = (0.40 * df.retained).round(-2)

    static = book[["cust_id", "segment", "age", "city_tier", "tenure_m"]]
    df = df.merge(static, on="cust_id", how="left")

    cols = ["cust_id", "month", "date", "credits_med_6m", "credits_cv_6m", "credits_gr_6m",
            "bal_avg", "bal_gr_6m", "minbal_ratio", "rent_share", "rent_ratio_6m",
            "fuel_ratio_3m", "fuel_share", "emi_share", "emi_gr_6m", "school_share",
            "ecom_share", "fd_ratio", "fd_drop", "has_auto_emi", "other_bank_emi_share",
            "card_share", "insurance_share", "upi_share", "upi_count_3m", "bonus_share_3m",
            "salary_source_count", "salary_day_drift", "mandate_fail_6m", "minbal_charge_6m",
            "kyc_event_6m", "external_emi_count", "retained", "safe_emi", "dwell_total_3m",
            "segment", "age", "city_tier", "tenure_m",
            *[f"dwell_{p}_3m" for p in PRODUCTS]]
    return df[cols]


# --------------------------------------------------------------------------- #
# the journey block
# --------------------------------------------------------------------------- #

#: Journey columns this model uses.  ``journey_stage_reached`` (a string) is
#: dropped in favour of the ordinal ``journey_stage_idx``; ``journey_last_product``
#: becomes a per-product match flag in the stacked frame.
JOURNEY_KEEP: tuple[str, ...] = (
    "journey_blank_field_ratio", "journey_refused_income", "journey_fee_balk",
    "journey_doc_refusal", "journey_multi_product_revisits", "journey_attempts",
    "journey_open_now", "journey_ever_abandoned", "journey_ever_disbursed",
    "journey_stage_idx", "journey_fee_paid", "journey_docs_shortfall",
    "journey_rm_contacted", "journey_revisits_30d", "journey_products_viewed_30d",
    "journey_amount_requested", "journey_stated_income_ratio",
    "journey_days_since_last_event", "journey_days_since_first_start",
    "journey_last_channel", "journey_last_product",
)


def journey_block(journeys: pd.DataFrame, events: pd.DataFrame,
                  months: list[int]) -> pd.DataFrame:
    """``journey_features_as_at`` for every month in ``months``, stacked.

    Not re-aggregated here: SD-S2 owns the timestamps and enforces the
    point-in-time rule with a test that recomputes the frame from *physically
    truncated* tables.  This function only chooses the instant (the first of the
    month) and stacks the results.
    """
    out = []
    for m in months:
        f = journey_features_as_at(journeys, events, month_start(m))
        if f.empty:
            continue
        f = f.reindex(columns=list(JOURNEY_KEEP))
        f = f.assign(month=m).reset_index().rename(columns={"customer_id": "cust_id"})
        out.append(f)
    if not out:
        return pd.DataFrame(columns=["cust_id", "month", *JOURNEY_KEEP])
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

#: Columns carried from ``labels.csv``: the bank's own behaviour (point-in-time
#: safe, computed in ``journeys.labels``) plus the identifiers and the targets.
LABEL_KEEP: tuple[str, ...] = (
    "cust_id", "month", "as_at", "eligible_for_contact", "suppressed",
    "suppression_reason", "consent_marketing", "dnd", "dropoff_stage_reached",
    "dropoff_product", "dropoff_attempts", "days_since_abandon", "contacts_30d",
    "contacts_90d", "campaign_contacts_6m", "last_contact_days",
    "last_campaign_product", "label_disbursed_in_window", "label_product",
    "window_days", "window_respected", "days_to_disbursement",
    "label_no_contact", *(f"label_product_{p}" for p in PRODUCTS),
)


def customer_month_frame(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per (customer, month) of the drop-off population, features attached.

    Includes suppressed rows: they are *scored* (the cockpit shows why they were
    held back) but never trained on and never queued.
    """
    labels = t["labels"][list(LABEL_KEEP)].copy()  # noqa: F841 (validated below)
    months = sorted(labels.month.unique().tolist())

    bk = book_features(t["panel"], t["book"])
    jb = journey_block(t["journeys"], t["events"], months)

    df = labels.merge(bk, on=["cust_id", "month"], how="left", validate="one_to_one")
    df = df.merge(jb, on=["cust_id", "month"], how="left", validate="one_to_one")

    # an absent journey row is NOT a zero (DATA_CARD 11.9): flag it, leave the
    # numerics NaN and let LightGBM route the missing branch itself.
    df["has_journey"] = df["journey_attempts"].notna().astype(np.int8)
    df["journey_last_channel"] = df["journey_last_channel"].fillna("none")
    df["journey_last_product"] = df["journey_last_product"].fillna("none")

    # measurement-only columns, all prefixed so they cannot be mistaken for inputs
    tr = t["label_truth"].rename(columns={"shopper_truth": "t_shopper_truth"})
    df = df.merge(tr, on=["cust_id", "month"], how="left")
    static = t["book"][["cust_id", "true_income", "inc_drift", "persuadable", "consent", "dnd"]]
    static = static.rename(columns={c: TRUTH_PREFIX + c for c in
                                    ("true_income", "inc_drift", "persuadable", "consent", "dnd")})
    df = df.merge(static, on="cust_id", how="left")
    df = df.rename(columns={
        "label_disbursed_in_window": "t_label",
        "label_product": "t_label_product",
        "label_no_contact": "t_label_no_contact",
        "days_to_disbursement": "t_days_to_disbursement",
        "window_days": "t_window_days",
        "window_respected": "t_window_respected",
        "suppressed": "t_suppressed",
        "suppression_reason": "t_suppression_reason",
    })
    df["t_income_at_month"] = df.t_true_income * (1 + df.t_inc_drift) ** df.month
    return df


def stack(base: pd.DataFrame) -> pd.DataFrame:
    """Expand each (customer, month) into six (customer, month, product) rows.

    This *is* the 3-models-to-1 collapse: instead of six frames with six labels
    and six fits, one frame in which ``product`` is a column the single model
    splits on, and ``y`` is that product's share of the row label.
    """
    n = len(base)
    carry = [c for c in base.columns if c not in
             {f"label_product_{p}" for p in PRODUCTS} | {f"dwell_{p}_3m" for p in PRODUCTS}]
    rep = pd.concat([base[carry]] * len(PRODUCTS), ignore_index=True)
    prod = np.repeat(np.array(PRODUCTS, dtype=object), n)
    rep["product"] = prod

    rep["y"] = np.concatenate([base[f"label_product_{p}"].to_numpy(dtype=np.int8) for p in PRODUCTS])
    rep["dwell_product_3m"] = np.concatenate([base[f"dwell_{p}_3m"].to_numpy(dtype=float) for p in PRODUCTS])
    rep["dwell_product_share"] = (rep.dwell_product_3m
                                  / np.tile(base.dwell_total_3m.to_numpy(dtype=float), len(PRODUCTS)).clip(min=1.0))
    rep["is_dropoff_product"] = (rep["product"].to_numpy() == rep["dropoff_product"].to_numpy()).astype(np.int8)
    rep["product_window_days"] = rep["product"].map(WINDOW_DAYS).astype(np.int16)
    rep["emi_headroom_ratio"] = (rep.safe_emi / rep["product"].map(TYPICAL_EMI)).clip(0, 4)
    rep["last_campaign_matches_product"] = (
        rep["last_campaign_product"].fillna("").to_numpy() == rep["product"].to_numpy()).astype(np.int8)
    rep["journey_last_product_matches"] = (
        rep["journey_last_product"].fillna("none").to_numpy() == rep["product"].to_numpy()).astype(np.int8)
    #: block layout: rows 0..n-1 are product 0, n..2n-1 product 1, ...  ``_row``
    #: makes that explicit so ``p.reshape(6, n).T`` can be asserted, not assumed.
    rep["_row"] = np.tile(np.arange(n, dtype=np.int32), len(PRODUCTS))
    rep["_product_idx"] = np.repeat(np.arange(len(PRODUCTS), dtype=np.int8), n)
    return rep


def as_categorical(df: pd.DataFrame) -> pd.DataFrame:
    """Pin the categorical levels so train / test / score frames agree."""
    levels = {
        "product": list(PRODUCTS),
        "dropoff_product": list(PRODUCTS),
        "journey_last_product": [*PRODUCTS, "none"],
        "segment": ["gig", "salaried", "self-employed"],
        "journey_last_channel": ["app", "branch-walk-in", "dsa", "rm-call", "web", "none"],
    }
    for c, lv in levels.items():
        if c in df.columns:
            df[c] = pd.Categorical(df[c], categories=lv)
    return df


def build_matrix(df: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> pd.DataFrame:
    """The design matrix, with the forbidden-input guard in front of it.

    The guard is deliberately *here* rather than in a test: a column that should
    never be an input must be impossible to pass, not merely detected later.
    """
    bad = sorted(set(features) & FORBIDDEN_INPUTS)
    if bad:
        raise ValueError(f"forbidden model inputs: {bad}")
    leaked = sorted(f for f in features if f.startswith(TRUTH_PREFIX))
    if leaked:
        raise ValueError(f"measurement-only columns used as inputs: {leaked}")
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise KeyError(f"features missing from the frame: {missing}")
    return df[list(features)]


def monotone_constraints(features: tuple[str, ...] = FEATURES,
                         signals: tuple[str, ...] = MENTOR_SIGNALS) -> list[int]:
    """-1 on each mentor signal, 0 elsewhere.

    LightGBM rejects a non-zero constraint on a categorical feature, and none of
    the four is categorical, so the mapping is unambiguous.
    """
    return [-1 if f in signals else 0 for f in features]
