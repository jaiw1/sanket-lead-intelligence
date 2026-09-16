"""SD-S4 — the drop-off population, the contact effect theta, and the labels.

Five families of test:

**The population** — the scoring unit is a ``(customer, month)`` row, decided at
the first instant of the month, for a customer with a live abandoned application
behind them.  The 2026-09-16 amendment at the foot of ``validation/criteria.yaml``
is the definition; these tests are that definition in code.

**The bands** — the two numbers the plan makes this lane solve for: the
random-contact disbursement rate in [8%, 10%] and the oracle precision@10% in
[25%, 35%], plus the window-respect floor of 90%.  They are asserted inside
``labels.check()`` on every run; here they are asserted again on a second,
independent draw, so a band that only holds at one seed cannot pass.

**The windows** — a positive label means a disbursement inside the offered
product's own decision window, and the windows are the pre-registered ones.

**The mechanism** — theta really is a contact effect (contact raises the rate),
the S/N knob really is monotone in separability, and the per-product menu labels
really do partition the row label.

**The anchoring** — the observed recoveries in ``journeys.csv`` come back as
positives in ``labels.csv``, which is what stops the counterfactual table
drifting away from the world it is supposed to be a counterfactual of.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from book.products import DECISION_WINDOW_DAYS, PRODUCTS
from journeys import JourneyConfig
from journeys.labels import (
    BAND_ORACLE_PRECISION, BAND_RANDOM_CONTACT, CONTACT_BUDGET, DROPOFF_LOOKBACK_DAYS,
    FIRST_LABEL_MONTH, MIN_WINDOW_RESPECT, effective_return, solve_theta,
)


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), format="mixed")


# --------------------------------------------------------------------------- #
# the population
# --------------------------------------------------------------------------- #

def test_one_row_per_customer_month(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    assert not lab.duplicated(["cust_id", "month"]).any()
    assert (lab.month >= FIRST_LABEL_MONTH).all(), "a row before any application could exist"
    assert lab.month.max() < journeys.journeys.start_month.max() + 13


def test_every_row_has_a_live_abandonment_behind_it(journeys: SimpleNamespace) -> None:
    """Membership is exactly "abandoned in the trailing 12 months", as at month start."""
    lab, j = journeys.labels, journeys.journeys
    ab = j[j.abandoned_at != ""][["customer_id", "abandoned_at"]].copy()
    ab["abandoned_at"] = _dt(ab.abandoned_at)
    as_at = _dt(lab.as_at)
    first_ab = ab.groupby("customer_id").abandoned_at.min()
    last_ab = ab.groupby("customer_id").abandoned_at.max()

    assert lab.cust_id.isin(first_ab.index).all(), \
        "a population row for a customer who never abandoned anything"
    age_of_newest = (as_at - lab.cust_id.map(last_ab).to_numpy()).dt.days
    age_of_oldest = (as_at - lab.cust_id.map(first_ab).to_numpy()).dt.days
    assert (age_of_oldest >= 0).all(), "a row predates the abandonment that created it"
    assert (age_of_newest <= DROPOFF_LOOKBACK_DAYS).all(), \
        "a row survives past the 12-month look-back of its most recent abandonment"


def test_the_population_is_the_drop_offs_not_the_book(journeys: SimpleNamespace) -> None:
    book = pd.read_csv(journeys.book_dir / "customer_book.csv", usecols=["cust_id"])
    share = journeys.labels.cust_id.nunique() / len(book)
    assert 0.10 < share < 0.35, (
        f"{share:.1%} of the book is in the drop-off population — that is the whole "
        "book, or none of it")


def test_days_since_abandon_is_consistent_with_as_at(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    assert (lab.days_since_abandon >= 0).all()
    assert (lab.days_since_abandon <= DROPOFF_LOOKBACK_DAYS + 0.01).all()


# --------------------------------------------------------------------------- #
# the pre-registered bands
# --------------------------------------------------------------------------- #

def test_random_contact_disbursement_is_in_band(journeys: SimpleNamespace) -> None:
    """SK-01 as amended: a uniformly random 10% contact sample of the population."""
    lab = journeys.labels
    e = lab.eligible_for_contact.to_numpy().astype(bool)
    y = lab.label_disbursed_in_window.to_numpy()[e]
    rate = float(np.mean(y))
    lo, hi = BAND_RANDOM_CONTACT
    assert lo <= rate <= hi, f"random-contact rate {rate:.2%} outside [{lo:.0%}, {hi:.0%}]"

    # ...and a single 10% draw, the estimator itself, sits within 3 standard
    # errors of it.  On the test book that is a wide interval; on the 60k book
    # the two agree to a tenth of a point.
    rng = np.random.default_rng(4242)
    k = int(round(CONTACT_BUDGET * len(y)))
    drawn = float(np.mean(y[rng.permutation(len(y))[:k]]))
    se = float(np.sqrt(rate * (1 - rate) / k))
    assert abs(drawn - rate) <= 3 * se, f"a uniform 10% sample gave {drawn:.2%} against {rate:.2%}"


def test_oracle_precision_is_in_band(journeys: SimpleNamespace) -> None:
    """SK-02's ceiling: what a ranker that saw the latent index itself could reach."""
    lab, truth = journeys.labels, journeys.label_truth
    e = lab.eligible_for_contact.to_numpy().astype(bool)
    y = lab.label_disbursed_in_window.to_numpy()[e]
    score = truth.oracle_score.to_numpy()[e]
    k = int(round(CONTACT_BUDGET * len(y)))
    top = np.argpartition(-score, k - 1)[:k]
    lo, hi = BAND_ORACLE_PRECISION
    assert lo <= float(np.mean(y[top])) <= hi


def test_window_respect_clears_the_floor(journeys: SimpleNamespace) -> None:
    respect = journeys.label_stats["window_respect_rate"]
    assert respect >= MIN_WINDOW_RESPECT
    assert respect < 1.0, "every return landed inside its window — the stall tail is dead"


def test_the_bands_hold_on_a_second_seed(journeys: SimpleNamespace) -> None:
    """A band that only holds at the default seed is not a band."""
    from journeys import substream
    from journeys.build import generate_all
    from journeys.labels import check as label_check

    cfg = JourneyConfig(book_dir=journeys.book_dir, out_dir=journeys.book_dir, seed=11)
    b = generate_all(cfg)
    st = label_check(b.labels, b.label_truth, b.params["labels"], substream(11, "measurement"))
    lo, hi = BAND_RANDOM_CONTACT
    assert lo <= st["random_contact_disbursement_rate"] <= hi
    lo, hi = BAND_ORACLE_PRECISION
    assert lo <= st["oracle_precision_at_10pct"] <= hi
    assert st["window_respect_rate"] >= MIN_WINDOW_RESPECT


# --------------------------------------------------------------------------- #
# the windows
# --------------------------------------------------------------------------- #

def test_windows_are_the_pre_registered_ones(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    pos = lab[lab.label_disbursed_in_window == 1]
    want = pos.label_product.map(DECISION_WINDOW_DAYS)
    assert (pos.window_days.to_numpy() == want.to_numpy()).all()
    assert (lab.window_days.to_numpy() == lab.contact_window_days.to_numpy()).all()
    assert set(lab.window_days) <= set(DECISION_WINDOW_DAYS.values())


def test_a_positive_label_disbursed_inside_its_window(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    pos = lab[lab.label_disbursed_in_window == 1]
    assert (pos.days_to_disbursement <= pos.window_days + 1e-6).all()
    assert (pos.days_to_disbursement >= -1e-6).all()
    assert (pos.window_respected == 1).all()


def test_returns_outside_the_window_are_negatives(journeys: SimpleNamespace) -> None:
    """The honest cost of the per-product windows: a real disbursement that
    arrived late does not count."""
    lab = journeys.labels
    late = lab[(lab.window_respected == 0)]
    assert len(late) > 0, "nothing ever misses its window"
    assert (late.label_disbursed_in_window == 0).all()
    assert (late.days_to_disbursement > late.window_days).all()


# --------------------------------------------------------------------------- #
# the mechanism
# --------------------------------------------------------------------------- #

def test_contact_raises_the_disbursement_rate(journeys: SimpleNamespace) -> None:
    """theta is a contact *effect*: Y(1) must beat Y(0), and by a lot."""
    st = journeys.label_stats
    assert st["random_contact_disbursement_rate"] > st["no_contact_disbursement_rate"]
    assert st["contact_lift"] > 1.0


def test_solve_theta_is_monotone() -> None:
    """The quantity the solver bisects on really is increasing in theta."""
    rng = np.random.default_rng(3)
    n = 5_000
    ret = rng.uniform(0.05, 0.9, n)
    fat = np.ones(n)
    comp = rng.uniform(0.2, 0.8, n)
    resp = np.ones(n, dtype=bool)
    forced = np.zeros(n, dtype=bool)

    def rate(theta: float) -> float:
        return float(np.mean(np.clip(theta * ret * fat, 0, 1) * comp * resp))

    assert rate(0.2) < rate(0.5) < rate(1.0)
    solved = solve_theta(ret, fat, comp, resp, forced, 0.09)
    assert rate(solved) == pytest.approx(0.09, abs=1e-4)


def test_the_sn_knob_sweeps_the_return_channel_too() -> None:
    """At S/N 0 every customer's return propensity collapses onto the mean; at 1
    it is untouched.  This is what stops the knob having a floor it cannot go
    below (see journeys/labels.py module docstring)."""
    ret = np.array([0.05, 0.2, 0.5, 0.9])
    assert effective_return(ret, 0.0) == pytest.approx(np.full(4, ret.mean()))
    assert effective_return(ret, 1.0) == pytest.approx(ret)
    spread = [float(np.std(effective_return(ret, s))) for s in (0.0, 0.25, 0.5, 1.0)]
    assert spread == sorted(spread), "dispersion is not monotone in the S/N knob"


def test_per_product_labels_partition_the_row_label(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    cols = [f"label_product_{p}" for p in PRODUCTS]
    assert (lab[cols].to_numpy().sum(axis=1) == lab.label_disbursed_in_window.to_numpy()).all()
    for p in PRODUCTS:
        on = lab[f"label_product_{p}"] == 1
        assert (lab.loc[on, "label_product"] == p).all()
    assert (lab[cols].sum() > 0).all(), "a product never appears as a realised label"


def test_menu_of_four_covers_most_realised_products(journeys: SimpleNamespace) -> None:
    """SD-S5's question, measured on the population SK-13 is graded over."""
    st = journeys.label_stats
    assert st["menu_of_4_coverage"] >= 0.80
    assert st["menu_of_4_coverage_with_dropoff_anchor"] >= st["menu_of_4_coverage"]
    assert 0.10 < st["label_product_differs_from_dropoff"] < 0.60, (
        "either nobody ever substitutes a product (the menu of four is pointless) "
        "or everybody does (the drop-off tells you nothing)")


# --------------------------------------------------------------------------- #
# anchoring to the observed world
# --------------------------------------------------------------------------- #

def test_observed_recoveries_come_back_as_labels(journeys: SimpleNamespace) -> None:
    p = journeys.params["labels"]
    assert p["observed_recoveries"] > 0
    assert p["observed_recoveries_matched_to_a_row"] > 0.5 * p["observed_recoveries"], \
        "most observed recoveries could not be matched to a population row"
    kept = (p["observed_recoveries_matched_to_a_row"]
            - p["observed_recoveries_dropped_as_suppressed"])
    assert kept > 0
    lab = journeys.labels
    real = lab[(lab.realised_recovery == 1) & (lab.eligible_for_contact == 1)]
    assert real.label_disbursed_in_window.mean() > lab.label_disbursed_in_window.mean(), \
        "a customer who really did come back is no likelier to be a positive"


def test_a_realised_recovery_carries_the_book_s_product(journeys: SimpleNamespace) -> None:
    lab, j = journeys.labels, journeys.journeys
    disb = j[j.outcome == "disbursed"].set_index("customer_id")["product"]
    real = lab[(lab.realised_recovery == 1) & (lab.label_disbursed_in_window == 1)]
    assert (real.label_product.to_numpy() == real.cust_id.map(disb).to_numpy()).all(), \
        "a forced positive names a product the book does not"


def test_theta_and_the_knob_are_recorded(journeys: SimpleNamespace) -> None:
    p = journeys.params["labels"]
    for key in ("theta_contact_effect", "label_signal_to_noise", "spontaneous_return",
                "contact_lift", "observed_self_return_rate"):
        assert key in p and np.isfinite(p[key])
    assert p["decision_window_days"] == dict(DECISION_WINDOW_DAYS)


def test_the_solve_is_reproducible(journeys: SimpleNamespace) -> None:
    from journeys.build import generate_all
    cfg = JourneyConfig(book_dir=journeys.book_dir, out_dir=journeys.book_dir)
    b = generate_all(cfg)
    assert b.params["labels"]["theta_contact_effect"] == \
        journeys.params["labels"]["theta_contact_effect"]
    assert b.params["labels"]["label_signal_to_noise"] == \
        journeys.params["labels"]["label_signal_to_noise"]
    pd.testing.assert_frame_equal(b.labels, journeys.labels)


# --------------------------------------------------------------------------- #
# leakage
# --------------------------------------------------------------------------- #

def test_the_treatment_and_the_outcome_land_after_as_at(journeys: SimpleNamespace) -> None:
    """``contacted_at`` and ``label_disbursed_at`` are outcomes, never features."""
    lab = journeys.labels
    as_at = _dt(lab.as_at)
    contacted = _dt(lab.contacted_at)
    assert (contacted.dropna() >= as_at[contacted.notna()]).all(), \
        "the bank called before the month the row is scored at"
    disbursed = _dt(lab.label_disbursed_at)
    assert (disbursed.dropna() >= as_at[disbursed.notna()]).all(), \
        "a labelled disbursement predates the snapshot it is a label for"


def test_contact_counters_never_see_the_future(journeys: SimpleNamespace) -> None:
    """Every ``contacts_*`` counter is reproducible from touches at or before as_at."""
    lab, camp = journeys.labels, journeys.campaigns
    sample = lab.sample(400, random_state=7)
    sent = camp.assign(_t=_dt(camp.sent_at)).set_index("cust_id")
    for _, row in sample.iterrows():
        as_at = pd.Timestamp(row.as_at)
        if row.cust_id not in sent.index:
            assert row.contacts_30d == 0 and row.contacts_90d == 0
            continue
        mine = sent.loc[[row.cust_id]]
        age = (as_at - mine._t).dt.total_seconds() / 86400.0
        assert row.contacts_30d == int(((age >= 0) & (age < 30)).sum())
        assert row.contacts_90d == int(((age >= 0) & (age < 90)).sum())
