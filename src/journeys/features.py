"""Point-in-time-safe journey features, for L7 / SM-3.

The application-journey layer is the single biggest leakage hazard in SANKET:
every journey column is a fact about a timeline that ends in the outcome being
predicted.  ``validation/criteria.yaml`` SK-17 registers a **zero-tolerance**
band for it ("nothing after ``abandon_ts``"), so the safe aggregation lives
here, in the lane that owns the timestamps, rather than being re-derived by
every consumer.

The rule
--------
A feature computed *as at* instant ``T`` may use a fact only if that fact was on
the bank's screen at ``T``.  Concretely:

=========================  ==========================================================
fact                       knowable from
=========================  ==========================================================
the attempt exists         ``started_at``
product, channel, ask      ``started_at``
blank-answer ratio         ``started_at`` (it is the form they submitted)
income refusal             ``started_at``
revisits / products viewed ``started_at`` (both are read from the *previous* month)
stage reached              the ``occurred_at`` of each stage transition
fee balk                   ``fee_balk_at`` — the Eligibility conversation
document refusal           ``doc_refusal_at`` — the same conversation
documents supplied         entering the Docs stage
fee paid                   ``fee_paid_at``
abandoned / disbursed      ``abandoned_at`` / ``disbursed_at``
=========================  ==========================================================

An attempt that has started but not finished at ``T`` is **in flight**: its stage
is whatever it had reached by ``T`` and its outcome is unknown.  That population
is not an edge case, it is the live queue an RM works.

Column names
------------
The six ``journey_*`` columns are spelled exactly as ``data/bank/SCHEMA.md``
specifies for ``enriched.csv`` (family ``journey``), because that is the contract
the platform, the enrichment path and the cockpit already share.  The rest are
additions this lane emits for SM-3; they carry the same prefix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import STAGES

#: The six columns ``data/bank/SCHEMA.md`` already names in the ``journey`` family.
CONTRACT_COLUMNS: tuple[str, ...] = (
    "journey_stage_reached", "journey_blank_field_ratio", "journey_refused_income",
    "journey_fee_balk", "journey_doc_refusal", "journey_multi_product_revisits",
)


def snapshot_timestamp(anchor: tuple[int, int], month: int) -> pd.Timestamp:
    """The last instant of panel month ``month`` — "now" for a snapshot at ``month``."""
    first = pd.Timestamp(year=anchor[0], month=anchor[1], day=1)
    return (first + pd.DateOffset(months=month + 1)) - pd.Timedelta(seconds=1)


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), format="mixed")


def journey_features_as_at(journeys: pd.DataFrame, events: pd.DataFrame,
                           as_at: pd.Timestamp | str,
                           campaigns: pd.DataFrame | None = None,
                           labels: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per customer with at least one attempt open or closed by ``as_at``.

    Consumers left-join this onto the book; a customer with no row simply has no
    application history at ``as_at``, which is different from having a bad one and
    should be encoded as such (a ``has_journey`` flag, not a zero).

    Pass ``campaigns`` (and optionally ``labels``) to get the SD-S6 additions —
    ``contacts_30d``, ``contacts_90d``, ``campaign_contacts_6m``,
    ``last_contact_days``, ``last_campaign_product``, ``suppressed`` and
    ``suppression_reason``.  They carry no ``journey_`` prefix because they are
    facts about the *bank's* behaviour, not the customer's application.
    ``suppressed`` / ``suppression_reason`` come from ``labels`` when a row for
    this ``as_at`` month exists there, because the suppression rule is decided
    once, in ``journeys.labels``, and never re-derived by a consumer.
    """
    as_at = pd.Timestamp(as_at)
    j = journeys.copy()
    for c in ("started_at", "last_stage_at", "abandoned_at", "disbursed_at",
              "fee_paid_at", "fee_balk_at", "doc_refusal_at", "rm_contacted_at"):
        j[c] = _dt(j[c])

    j = j[j.started_at <= as_at].copy()
    if j.empty:
        return pd.DataFrame(columns=["customer_id", *CONTRACT_COLUMNS]).set_index("customer_id")

    # ---- stage reached: the furthest transition actually timestamped by as_at - #
    ev = events[events.attempt_id.isin(j.attempt_id)].copy()
    ev["occurred_at"] = _dt(ev["occurred_at"])
    ev = ev[ev.occurred_at <= as_at]
    #: the last thing that actually happened on this attempt by ``as_at``.  NOT
    #: ``last_stage_at``: for an attempt still in flight that column holds a stage
    #: entry in the future, and using it here would leak (caught by
    #: ``tests/test_journeys.py::test_features_as_at_use_no_future_information``).
    last_event = ev.groupby("attempt_id").occurred_at.max()
    stage_idx = {s: i for i, s in enumerate(STAGES)}
    stage_ev = ev[ev.event != "abandon"]
    reached = stage_ev.assign(idx=stage_ev.to_stage.map(stage_idx)).groupby("attempt_id")["idx"].max()
    j["stage_idx_visible"] = j.attempt_id.map(reached).fillna(0).astype(int)
    j["stage_visible"] = np.array(STAGES, dtype=object)[j.stage_idx_visible.to_numpy()]

    # ---- per-attempt visibility ------------------------------------------- #
    j["abandoned_visible"] = j.abandoned_at.notna() & (j.abandoned_at <= as_at)
    j["disbursed_visible"] = j.disbursed_at.notna() & (j.disbursed_at <= as_at)
    j["open_now"] = ~(j.abandoned_visible | j.disbursed_visible)
    j["fee_balk_visible"] = (j.fee_balk == 1) & j.fee_balk_at.notna() & (j.fee_balk_at <= as_at)
    j["doc_refusal_visible"] = (j.doc_refusal == 1) & j.doc_refusal_at.notna() & (j.doc_refusal_at <= as_at)
    j["fee_paid_visible"] = j.fee_paid_at.notna() & (j.fee_paid_at <= as_at)
    docs_seen = j.stage_idx_visible >= STAGES.index("docs")
    j["docs_short_visible"] = docs_seen & (j.docs_supplied.fillna(0) < j.docs_requested.fillna(0))
    j["rm_seen"] = j.rm_contacted_at.notna() & (j.rm_contacted_at <= as_at)

    j["last_event_at"] = j.attempt_id.map(last_event).fillna(j.started_at)

    j = j.sort_values(["customer_id", "started_at"], kind="stable")
    last = j.groupby("customer_id").tail(1).set_index("customer_id")
    g = j.groupby("customer_id")

    out = pd.DataFrame(index=last.index)
    out["journey_stage_reached"] = last.stage_visible
    out["journey_blank_field_ratio"] = g.answers_blank_ratio.max()
    out["journey_refused_income"] = (1 - g.income_shared.max()).astype(np.int8)
    out["journey_fee_balk"] = g.fee_balk_visible.max().astype(np.int8)
    out["journey_doc_refusal"] = g.doc_refusal_visible.max().astype(np.int8)
    # "revisiting several products without committing" (mentor wording): the
    # wider of the two readings — how many distinct products they have applied
    # for, and how many they were browsing in the month before an application —
    # minus the one they are actually on.  0 means single-minded.
    out["journey_multi_product_revisits"] = np.maximum(
        g["product"].nunique().to_numpy(), g.products_viewed_30d.max().to_numpy()) - 1
    out["journey_multi_product_revisits"] = out["journey_multi_product_revisits"].astype(np.int16)

    # ---- additions for SM-3 ------------------------------------------------ #
    out["journey_attempts"] = g.size().astype(np.int16)
    out["journey_open_now"] = g.open_now.max().astype(np.int8)
    out["journey_ever_abandoned"] = g.abandoned_visible.max().astype(np.int8)
    out["journey_ever_disbursed"] = g.disbursed_visible.max().astype(np.int8)
    out["journey_stage_idx"] = last.stage_idx_visible.astype(np.int8)
    out["journey_last_product"] = last["product"]
    out["journey_last_channel"] = last.channel
    out["journey_fee_paid"] = g.fee_paid_visible.max().astype(np.int8)
    out["journey_docs_shortfall"] = g.docs_short_visible.max().astype(np.int8)
    out["journey_rm_contacted"] = g.rm_seen.max().astype(np.int8)
    out["journey_revisits_30d"] = g.revisits_30d.max().astype(np.int16)
    out["journey_products_viewed_30d"] = g.products_viewed_30d.max().astype(np.int16)
    out["journey_amount_requested"] = last.amount_requested
    out["journey_stated_income_ratio"] = last.stated_income_vs_book_ratio
    out["journey_days_since_last_event"] = np.round(
        (np.datetime64(as_at) - g.last_event_at.max().to_numpy()) / np.timedelta64(1, "D"), 2)
    out["journey_days_since_first_start"] = np.round(
        (np.datetime64(as_at) - g.started_at.min().to_numpy()) / np.timedelta64(1, "D"), 2)

    # ---- SD-S6 additions: what the bank has already done to this customer --- #
    if campaigns is not None:
        out = out.join(contact_features_as_at(campaigns, as_at, out.index))
    if labels is not None:
        out = out.join(suppression_as_at(labels, as_at, out.index))
    return out


def contact_features_as_at(campaigns: pd.DataFrame, as_at: pd.Timestamp | str,
                           index: pd.Index) -> pd.DataFrame:
    """Trailing contact counters for ``index``, using only touches at or before ``as_at``.

    A customer with no touch is a genuine zero here (the bank really has not
    contacted them), unlike the journey block where an absent row means "no
    application history" — hence the fills.
    """
    as_at = pd.Timestamp(as_at)
    c = campaigns[_dt(campaigns.sent_at) <= as_at].copy()
    c["sent_at"] = _dt(c["sent_at"])
    age = (as_at - c.sent_at).dt.total_seconds() / 86400.0
    c = c.assign(_age=age)
    g = c.sort_values(["cust_id", "sent_at"], kind="stable").groupby("cust_id")

    def within(days: float) -> pd.Series:
        return (c[c._age < days].groupby("cust_id").size()
                .reindex(index).fillna(0).astype(np.int16))

    out = pd.DataFrame(index=index)
    out["contacts_30d"] = within(30)
    out["contacts_90d"] = within(90)
    out["campaign_contacts_6m"] = within(183)
    out["last_contact_days"] = np.round(g._age.min().reindex(index), 2)
    out["last_contact_date"] = g.sent_at.max().reindex(index).dt.strftime("%Y-%m-%d").fillna("")
    out["last_campaign_product"] = g["product"].last().reindex(index).fillna("")
    return out


def suppression_as_at(labels: pd.DataFrame, as_at: pd.Timestamp | str,
                      index: pd.Index) -> pd.DataFrame:
    """``suppressed`` / ``suppression_reason`` for the population row at ``as_at``.

    Decided once, in ``journeys.labels``, and read back here — a consumer that
    re-derived it would drift from the table the labels were built against.
    Customers with no population row at this month are not in the drop-off queue
    at all: they come back ``suppressed = 0``, reason ``not_in_population``.
    """
    as_at = pd.Timestamp(as_at)
    rows = labels[_dt(labels.as_at) <= as_at]
    if rows.empty:
        latest = rows
    else:
        latest = rows.sort_values(["cust_id", "as_at"], kind="stable").groupby("cust_id").tail(1)
    latest = latest.set_index("cust_id")
    out = pd.DataFrame(index=index)
    out["suppressed"] = latest.suppressed.reindex(index).fillna(0).astype(np.int8)
    out["suppression_reason"] = latest.suppression_reason.reindex(index).fillna("not_in_population")
    return out
