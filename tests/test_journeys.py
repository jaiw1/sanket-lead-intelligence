"""SD-S2 — the application-journey layer must be coherent, in order, and honest.

Four families of test:

**Structure** — an attempt walks the eight stages in order, stops exactly once,
and a disbursement implies every earlier stage was actually passed (including
the Rs 1,000 fee).

**Time** — nothing is recorded after ``abandoned_at`` or ``disbursed_at``; two
attempts by the same customer never overlap; the panel's monthly grain is
respected.  This is the family ``validation/runners/07_leakage.py`` will lean on
(criterion SK-17, zero tolerance).

**Consistency with the book** — the book is read-only truth.  Exactly the
customers it says convert disburse, for the product it names, in the month it
names, and (bar a documented noise share) nobody applies for a product their
eligibility latent rules out.

**Calibration** — the volumes and the funnel shape the plan pre-registers:
25-35% of the book attempts an application, the drop-off recovery rate sits in
the bank-stated 8-10% band, and abandonments land at each stage in the
documented proportions.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from journeys import N_GATES, STAGES, JourneyConfig
from journeys.build import STAGE_SHARE_TOL, generate
from journeys.bookview import eligibility_from_book
from journeys.features import journey_features_as_at, snapshot_timestamp
from journeys.funnel import ABANDON_SHARE

STAGE_IDX = {s: i for i, s in enumerate(STAGES)}


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), format="mixed")


# --------------------------------------------------------------------------- #
# structure
# --------------------------------------------------------------------------- #

def test_every_attempt_appears_once_per_table(journeys: SimpleNamespace) -> None:
    j, e, t = journeys.journeys, journeys.events, journeys.truth
    assert j.attempt_id.is_unique
    assert t.attempt_id.is_unique
    assert set(e.attempt_id) == set(j.attempt_id)
    assert list(t.attempt_id) == list(j.attempt_id), "truth and journeys are not row-aligned"


def test_stage_order_is_monotone_within_an_attempt(journeys: SimpleNamespace) -> None:
    """Start -> Eligibility -> ... -> Disburse, one step at a time, no skips."""
    e = journeys.events.sort_values(["attempt_id", "seq"], kind="stable")
    idx = e.to_stage.map(STAGE_IDX).to_numpy()
    same = e.attempt_id.to_numpy()[1:] == e.attempt_id.to_numpy()[:-1]
    step = idx[1:] - idx[:-1]
    advance = (e.event.to_numpy()[1:] != "abandon") & same
    assert (step[advance] == 1).all(), "a journey skipped or repeated a stage"
    assert (step[same & ~advance] == 0).all(), "the terminal event moved the stage"
    first = e.groupby("attempt_id").head(1)
    assert (first.to_stage == "start").all() and (first.event == "start").all()


def test_last_stage_matches_the_events(journeys: SimpleNamespace) -> None:
    j, e = journeys.journeys, journeys.events
    reached = e[e.event != "abandon"].groupby("attempt_id").to_stage.last()
    assert (j.set_index("attempt_id").last_stage == reached.reindex(j.attempt_id.values)).all()
    assert (j.last_stage.map(STAGE_IDX) == j.last_stage_idx).all()


def test_disbursement_implies_every_earlier_stage_passed(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    d = j[j.outcome == "disbursed"]
    assert (d.last_stage == "disburse").all()
    assert (d.fee_paid == 1).all(), "a disbursement that never paid the fee"
    assert d.fee_paid_at.ne("").all(), "fee paid without a timestamp"
    assert (d.docs_supplied == d.docs_requested).all(), "disbursed on an incomplete file"
    assert d.amount_offered.notna().all(), "disbursed without an offer"
    assert d.disbursed_at.ne("").all() and d.abandoned_at.eq("").all()
    per_attempt = journeys.events[journeys.events.attempt_id.isin(d.attempt_id)] \
        .groupby("attempt_id").to_stage.nunique()
    assert (per_attempt == len(STAGES)).all(), "a disbursement is missing a stage event"


def test_an_attempt_stops_exactly_once(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    assert set(j.outcome) <= {"disbursed", "abandoned", "in_flight"}
    assert (j.loc[j.outcome == "abandoned", "abandoned_at"] != "").all()
    assert (j.loc[j.outcome == "abandoned", "disbursed_at"] == "").all()
    inflight = j[j.outcome == "in_flight"]
    assert (inflight.abandoned_at == "").all() and (inflight.disbursed_at == "").all(), \
        "an attempt still open carries a terminal timestamp"
    assert len(inflight) > 0, "no attempt is open at the panel end — there is no live queue"


def test_information_is_withheld_until_the_stage_is_reached(journeys: SimpleNamespace) -> None:
    """A customer who never saw the fee page cannot have balked at it."""
    j = journeys.journeys
    before_elig = j.last_stage_idx < STAGE_IDX["eligibility"]
    assert j.loc[before_elig, "fee_balk"].isna().all()
    assert j.loc[before_elig, "doc_refusal"].isna().all()
    before_docs = j.last_stage_idx < STAGE_IDX["docs"]
    assert j.loc[before_docs, ["docs_requested", "docs_supplied"]].isna().all().all()
    before_fee = j.last_stage_idx < STAGE_IDX["fee"]
    assert j.loc[before_fee, ["fee_amount", "fee_paid"]].isna().all().all()
    before_offer = j.last_stage_idx < STAGE_IDX["offer"]
    assert j.loc[before_offer, "amount_offered"].isna().all()
    assert j.loc[~before_offer, "amount_offered"].notna().all()
    assert j.loc[j.income_shared == 0, "stated_income_vs_book_ratio"].isna().all()


def test_time_in_stage_is_recorded_for_exactly_the_stages_entered(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    cols = [f"time_in_stage_{s}" for s in STAGES[:N_GATES]]
    present = j[cols].notna().to_numpy()
    last = j.last_stage_idx.to_numpy()[:, None]
    entered = np.arange(N_GATES)[None, :] < last
    stopped_here = (np.arange(N_GATES)[None, :] == last) & (j.outcome.to_numpy() != "disbursed")[:, None]
    assert (present == (entered | stopped_here)).all(), \
        "time-in-stage is recorded for a stage the attempt never entered (or missing for one it did)"
    assert (j[cols].to_numpy()[present] >= 0).all()


# --------------------------------------------------------------------------- #
# time
# --------------------------------------------------------------------------- #

def test_no_event_lands_after_the_terminal_instant(journeys: SimpleNamespace) -> None:
    """SK-17's core claim: nothing after ``abandon_ts``."""
    j, e = journeys.journeys, journeys.events
    end = _dt(j.abandoned_at).fillna(_dt(j.disbursed_at))
    end.index = j.attempt_id
    latest = _dt(e.occurred_at).groupby(e.attempt_id).max()
    closed = end.dropna()
    assert (latest.reindex(closed.index) <= closed + pd.Timedelta(seconds=1)).all()
    for col in ("fee_paid_at", "fee_balk_at", "doc_refusal_at", "last_stage_at"):
        v = _dt(j[col]); v.index = j.attempt_id
        both = v.reindex(closed.index).dropna()
        assert (both <= closed.reindex(both.index) + pd.Timedelta(seconds=1)).all(), \
            f"{col} lands after the attempt closed"


def test_everything_observable_starts_at_or_after_the_application(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    start = _dt(j.started_at)
    for col in ("last_stage_at", "fee_paid_at", "fee_balk_at", "doc_refusal_at",
                "abandoned_at", "disbursed_at"):
        v = _dt(j[col])
        assert (v.dropna() >= start[v.notna()] - pd.Timedelta(seconds=1)).all(), f"{col} predates the application"
    # an RM call that *caused* the application is the one thing allowed to precede it
    rm = _dt(j.rm_contacted_at)
    early = rm.notna() & (rm < start)
    assert (j.loc[early, "channel"] == "rm-call").all()


def test_attempts_by_the_same_customer_never_overlap(journeys: SimpleNamespace) -> None:
    j = journeys.journeys.sort_values(["customer_id", "started_at"], kind="stable")
    end = _dt(j.abandoned_at).fillna(_dt(j.disbursed_at))
    start = _dt(j.started_at)
    same = j.customer_id.to_numpy()[1:] == j.customer_id.to_numpy()[:-1]
    gap = (start.to_numpy()[1:] - end.to_numpy()[:-1]) / np.timedelta64(1, "D")
    assert np.all(gap[same & ~np.isnan(gap)] > 0), "a customer had two applications open at once"
    seq = j.attempt_seq.to_numpy()
    assert (seq[1:][same] == seq[:-1][same] + 1).all(), "attempt_seq is not chronological"


def test_attempts_respect_the_panel_grain(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    start = _dt(j.started_at)
    y0, m0 = journeys.anchor
    month = (start.dt.year - y0) * 12 + (start.dt.month - m0)
    assert (month.to_numpy() == j.start_month.to_numpy()).all(), "start_month is not the month of started_at"
    assert j.start_month.between(0, 29).all()
    assert (j.start_month >= journeys.cfg.first_attempt_month).all()
    # ...and the drawn latent month is never *after* the application (never newer info)
    assert (journeys.truth.latent_month.to_numpy() <= j.start_month.to_numpy()).all()


def test_multi_attempt_customers_exist(journeys: SimpleNamespace) -> None:
    n = journeys.journeys.groupby("customer_id").size()
    assert (n > 1).sum() > 0.05 * len(n), "almost nobody comes back — there is no recovery population"
    assert n.max() <= 3


# --------------------------------------------------------------------------- #
# consistency with the book
# --------------------------------------------------------------------------- #

def test_exactly_the_books_converters_disburse(journeys: SimpleNamespace) -> None:
    book = pd.read_csv(journeys.book_dir / "customer_book.csv",
                       usecols=["cust_id", "event_month", "product_canonical"])
    conv = set(book.loc[book.event_month >= 0, "cust_id"])
    got = journeys.journeys[journeys.journeys.outcome == "disbursed"]
    assert set(got.customer_id) == conv
    assert len(got) == len(conv), "a converter disbursed twice"
    bp = book.set_index("cust_id").product_canonical
    assert (got.set_index("customer_id")["product"] == bp.reindex(got.customer_id)).all()


def test_disbursement_lands_in_the_books_event_month(journeys: SimpleNamespace) -> None:
    book = pd.read_csv(journeys.book_dir / "customer_book.csv", usecols=["cust_id", "event_month"])
    got = journeys.journeys[journeys.journeys.outcome == "disbursed"]
    ts = _dt(got.disbursed_at)
    y0, m0 = journeys.anchor
    month = (ts.dt.year - y0) * 12 + (ts.dt.month - m0)
    assert (month.to_numpy() == book.set_index("cust_id").event_month.reindex(got.customer_id).to_numpy()).all()


def test_eligibility_derivation_matches_the_book(small_book) -> None:
    """The journey layer re-derives the book's eligibility rule from the written
    CSV; this is the test that stops the two copies drifting apart."""
    from book import BookConfig
    from book.hard_negatives import assign_archetypes
    from book.latent import eligibility
    from book.population import build_population

    cfg = BookConfig(n=2_000, months=30)
    pop = build_population(cfg)
    assign_archetypes(cfg, pop)
    expected = eligibility(cfg, pop)
    written = pd.DataFrame({
        "age": pop.age, "owns_property": pop.owns_property.astype(int),
        "gold_holding_g": pop.gold_holding_g.round(1), "has_auto_emi": pop.has_auto_emi.astype(int),
        "dependants": pop.dependants,
    })
    np.testing.assert_allclose(eligibility_from_book(written), expected)


def test_attempts_for_impossible_products_are_rare_and_die_early(journeys: SimpleNamespace) -> None:
    j, t = journeys.journeys, journeys.truth
    share = float(t.ineligible_product.mean())
    assert share <= 2.0 * journeys.cfg.ineligible_noise_share + 0.005, \
        f"{share:.1%} of attempts are for a product the customer cannot take"
    assert share > 0.0, "no ineligible applications at all — the Eligibility stage has nothing to do"
    bad = t.ineligible_product == 1
    assert (j.loc[bad.to_numpy(), "outcome"] != "disbursed").all(), "an ineligible application disbursed"
    stage = j.loc[bad.to_numpy(), "last_stage"]
    assert (stage == "eligibility").mean() > 0.4, "ineligible applications are not dying at Eligibility"


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #

def test_attempt_volume_is_in_the_planned_band(journeys: SimpleNamespace) -> None:
    assert 0.25 <= journeys.stats["customers_with_attempt"] <= 0.35


def test_random_contact_disbursement_is_the_bank_stated_8_to_10_percent(
        journeys: SimpleNamespace) -> None:
    """Of 100 drop-offs an RM works at random, 8-10 end in a disbursement."""
    assert 0.08 <= journeys.stats["recovery_rate"] <= 0.10


@pytest.mark.parametrize("stage", list(ABANDON_SHARE))
def test_abandonment_share_per_stage(journeys: SimpleNamespace, stage: str) -> None:
    """The timeout distributions and solved intercepts reproduce the documented
    funnel shape.  Pre-registered in ``funnel.ABANDON_SHARE``, not read off the
    output."""
    got = journeys.stats[f"abandon_at_{stage}"]
    assert got == pytest.approx(ABANDON_SHARE[stage], abs=STAGE_SHARE_TOL), \
        f"abandonment at {stage} is {got:.1%} against a {ABANDON_SHARE[stage]:.0%} target"


def test_the_hazard_and_the_book_agree_about_who_finishes(journeys: SimpleNamespace) -> None:
    """The funnel model, run free, must rate the attempts that disburse above the
    ones that do not — otherwise conditioning on the book's outcome is smuggling
    in an effect the model cannot see."""
    from sklearn.metrics import roc_auc_score
    d = (journeys.journeys.outcome == "disbursed").to_numpy().astype(int)
    auc = roc_auc_score(d, journeys.truth.p_complete.to_numpy())
    assert auc > 0.65, f"hazard-vs-outcome AUC is only {auc:.3f}"
    assert journeys.stats["p_complete_disbursed"] > journeys.stats["p_complete_abandoned"]


def test_decision_windows_are_mostly_respected(journeys: SimpleNamespace) -> None:
    """A gold-loan lead is dead on day three; a home-loan lead lives a fortnight.
    Pre-registered at >= 90% (criteria.yaml SK-04)."""
    assert journeys.stats["window_respect"] >= 0.90
    assert journeys.stats["window_respect"] < 1.0, "nobody ever misses a window — too easy"


def test_journeys_are_faster_for_shorter_window_products(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    med = j[j.outcome == "disbursed"].groupby("product").journey_days.median()
    assert med["personal"] < med["auto"] < med["education"] < med["home"]
    assert med["gold"] < med["lap"]


# --------------------------------------------------------------------------- #
# point-in-time features
# --------------------------------------------------------------------------- #

def test_features_as_at_use_no_future_information(journeys: SimpleNamespace) -> None:
    """Recompute the features from tables physically truncated at ``as_at``.

    If any feature drew on a fact timestamped later, the two frames disagree.
    This is the property ``validation/runners/07_leakage.py`` (SK-17) asserts,
    tested here at the layer that owns the timestamps.
    """
    as_at = snapshot_timestamp(journeys.anchor, 20)
    j, e = journeys.journeys, journeys.events
    full = journey_features_as_at(j, e, as_at)

    jt = j.copy()
    for col in ("abandoned_at", "disbursed_at", "fee_paid_at", "fee_balk_at",
                "doc_refusal_at", "rm_contacted_at", "last_stage_at"):
        jt[col] = jt[col].where(_dt(jt[col]) <= as_at, "")
    late = _dt(j.doc_refusal_at) > as_at
    jt.loc[late, ["doc_refusal"]] = np.nan
    late = _dt(j.fee_balk_at) > as_at
    jt.loc[late, ["fee_balk"]] = np.nan
    et = e[_dt(e.occurred_at) <= as_at]
    truncated = journey_features_as_at(jt, et, as_at)
    pd.testing.assert_frame_equal(full.sort_index(), truncated.sort_index(), check_dtype=False)


def test_features_expose_the_live_drop_off_queue(journeys: SimpleNamespace) -> None:
    as_at = snapshot_timestamp(journeys.anchor, 26)
    f = journey_features_as_at(journeys.journeys, journeys.events, as_at)
    assert f.journey_open_now.sum() > 0, "no open application at the snapshot"
    assert f.journey_ever_abandoned.mean() > 0.5
    assert set(f.journey_stage_reached) <= set(STAGES)
    # a customer whose only attempt is still in flight has no outcome yet
    open_only = f[(f.journey_open_now == 1) & (f.journey_attempts == 1)]
    assert (open_only.journey_ever_disbursed == 0).all()
    assert (open_only.journey_ever_abandoned == 0).all()


# --------------------------------------------------------------------------- #
# reproducibility
# --------------------------------------------------------------------------- #

def test_same_seed_is_reproducible(small_book) -> None:
    cfg = JourneyConfig(book_dir=small_book, out_dir=small_book)
    a = generate(cfg)
    b = generate(cfg)
    for x, y in zip(a[:3], b[:3]):
        pd.testing.assert_frame_equal(x, y)
    assert a[3] == b[3]


def test_a_different_seed_changes_the_journeys(small_book) -> None:
    a, _, _, _ = generate(JourneyConfig(book_dir=small_book, out_dir=small_book, seed=1))
    b, _, _, _ = generate(JourneyConfig(book_dir=small_book, out_dir=small_book, seed=2))
    assert not a.started_at.equals(b.started_at)
    # ...but not who converts: that is the book's, and the book did not move
    assert set(a.loc[a.outcome == "disbursed", "customer_id"]) == \
           set(b.loc[b.outcome == "disbursed", "customer_id"])
