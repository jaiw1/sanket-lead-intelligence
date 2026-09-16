"""SD-S6 — campaign history, fatigue and the suppression rule.

Four families of test:

**The enum** — ``suppression_reason`` is exhaustive (nothing outside the declared
vocabulary ever appears), consistent with the ``suppressed`` flag, and *mutually
exclusive by priority*: a row carrying reason `r` really does satisfy `r`, and
really does not satisfy anything ranked above it.

**Fatigue** — monotone, geometric, floored.  Both as a pure function of the
trailing-30-day contact count and as a realised effect: the response rate and the
label rate both fall as the customer is contacted more.

**Suppression bites** — a row the bank may not call never carries a positive
contact label.  That is the property the cockpit's suppressed-count KPI and the
SK-22 suppression sweep both rest on.

**Point in time** — the contact counters recomputed from a campaign table
physically truncated at ``as_at`` are identical to the ones computed from the
full table.  Same test SD-S2 applies to the journey features, for the same
reason: every one of these columns is a fact about a timeline that ends in the
outcome being predicted.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from journeys.campaigns import (
    CAMPAIGN_CHANNELS, CONTACT_COOLOFF_DAYS, DECLINE_COOLOFF_DAYS, FATIGUE_DECAY,
    FATIGUE_FLOOR, RESPONSES, SUPPRESSION_REASONS,
)
from journeys.features import contact_features_as_at, journey_features_as_at, snapshot_timestamp


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), format="mixed")


# --------------------------------------------------------------------------- #
# the campaign table itself
# --------------------------------------------------------------------------- #

def test_campaign_vocabulary_is_closed(journeys: SimpleNamespace) -> None:
    c = journeys.campaigns
    assert set(c.channel) <= set(CAMPAIGN_CHANNELS)
    assert set(c.response) <= set(RESPONSES)
    assert c.campaign_id.is_unique
    assert (c.sent_day >= 0).all()


def test_no_campaign_reaches_a_customer_who_said_no(journeys: SimpleNamespace) -> None:
    """Marketing consent and DND are enforced at send time, not after the fact."""
    book = pd.read_csv(journeys.book_dir / "customer_book.csv",
                       usecols=["cust_id", "consent", "dnd"]).set_index("cust_id")
    touched = journeys.campaigns.cust_id.unique()
    assert (book.loc[touched, "consent"] == 1).all(), "a campaign went to a non-consented customer"
    assert (book.loc[touched, "dnd"] == 0).all(), "a campaign went to a DND customer"


def test_campaigns_are_sorted_within_a_customer(journeys: SimpleNamespace) -> None:
    c = journeys.campaigns
    step = c.groupby("cust_id", sort=False).sent_day.diff().dropna()
    assert (step >= 0).all(), "a customer's touches are not in time order"


# --------------------------------------------------------------------------- #
# fatigue
# --------------------------------------------------------------------------- #

def test_fatigue_is_geometric_monotone_and_floored(journeys: SimpleNamespace) -> None:
    c = journeys.campaigns
    got = c.groupby("contacts_30d_before").fatigue.agg(["mean", "min", "max"])
    for k, row in got.iterrows():
        want = max(FATIGUE_DECAY ** int(k), FATIGUE_FLOOR)
        assert row["min"] == pytest.approx(want, abs=1e-4)
        assert row["max"] == pytest.approx(want, abs=1e-4)
    ks = sorted(got.index)
    means = [got.loc[k, "mean"] for k in ks]
    assert all(a >= b for a, b in zip(means, means[1:])), "fatigue is not monotone"
    assert means[0] > means[-1], "fatigue never actually bites"


def test_fatigue_lowers_the_realised_response_rate(journeys: SimpleNamespace) -> None:
    """Not just the multiplier — the behaviour it drives."""
    c = journeys.campaigns
    resp = (c.response != "no_response").groupby(
        np.minimum(c.contacts_30d_before, 2)).mean()
    assert resp.loc[0] > resp.loc[1], "a second touch in 30 days does not cost anything"
    if 2 in resp.index and (c.contacts_30d_before >= 2).sum() > 200:
        assert resp.loc[1] >= resp.loc[2] - 0.05


def test_fatigue_lowers_the_label_rate(journeys: SimpleNamespace) -> None:
    """The same decay reaches the drop-off population's contact outcome."""
    lab = journeys.labels
    e = lab.eligible_for_contact == 1
    rate = lab[e].groupby(np.minimum(lab.loc[e, "contacts_30d"], 1)
                          ).label_disbursed_in_window.mean()
    assert rate.loc[0] > rate.loc[1], "being contacted last month costs nothing"


# --------------------------------------------------------------------------- #
# the suppression enum
# --------------------------------------------------------------------------- #

def test_suppression_reasons_are_exhaustive_and_consistent(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    seen = set(lab.suppression_reason)
    assert seen <= set(SUPPRESSION_REASONS), f"unknown reason(s): {seen - set(SUPPRESSION_REASONS)}"
    assert (lab.suppressed.to_numpy().astype(bool)
            == (lab.suppression_reason.to_numpy() != "none")).all()
    # every declared reason is reachable — a dead enum member is a rule that is
    # written down but never enforced
    missing = set(SUPPRESSION_REASONS) - seen
    assert not missing, f"suppression reasons that never fire: {sorted(missing)}"


def test_each_suppression_reason_actually_holds(journeys: SimpleNamespace) -> None:
    """Spot-check the three reasons that are checkable from the written tables."""
    lab = journeys.labels
    as_at = _dt(lab.as_at)

    no_consent = lab.suppression_reason == "no_marketing_consent"
    dnd = lab.suppression_reason == "dnd"
    assert (lab.loc[dnd, "dnd"] == 1).all(), "a dnd-suppressed row is not on the DND list"
    # no_marketing_consent is either the book flag or an in-panel opt-out
    opted = journeys.campaigns[journeys.campaigns.response == "opted_out"]
    opt_day = opted.groupby("cust_id").sent_at.min()
    rows = lab[no_consent]
    book_says_no = rows.consent_marketing == 0
    opted_before = rows.cust_id.map(opt_day).pipe(_dt) <= as_at[no_consent]
    assert (book_says_no | opted_before.fillna(False)).all(), \
        "a consent-suppressed row is neither non-consented nor an opt-out"

    recent = lab.suppression_reason == "recent_contact"
    # last_contact_days is written rounded to 2 dp, so compare with that tolerance
    assert (lab.loc[recent, "last_contact_days"] <= CONTACT_COOLOFF_DAYS + 0.005).all()
    assert (lab.loc[lab.suppression_reason == "none", "last_contact_days"]
            .fillna(np.inf) >= CONTACT_COOLOFF_DAYS - 0.005).all(), \
        "a contactable row was touched inside the cool-off"


def test_priority_order_is_respected(journeys: SimpleNamespace) -> None:
    """A lower-priority reason never masks a higher-priority one."""
    lab = journeys.labels
    # dnd outranks recent_contact / recent_decline / already_holds_product
    for lower in ("account_dormant", "application_in_flight", "recent_decline",
                  "recent_contact", "already_holds_product"):
        rows = lab[lab.suppression_reason == lower]
        assert (rows.dnd == 0).all(), f"{lower} masked a dnd row"
        assert (rows.consent_marketing == 1).all(), f"{lower} masked a no-consent row"


def test_a_suppressed_row_never_carries_a_positive_label(journeys: SimpleNamespace) -> None:
    lab = journeys.labels
    bad = lab[(lab.suppressed == 1) & (lab.label_disbursed_in_window == 1)]
    assert bad.empty, f"{len(bad)} suppressed rows carry a positive contact label"
    assert (lab.loc[lab.suppressed == 1, "contacted"] == 0).all(), \
        "the bank called a suppressed customer"


def test_decline_cooloff_is_at_least_as_long_as_the_contact_cooloff() -> None:
    assert DECLINE_COOLOFF_DAYS >= CONTACT_COOLOFF_DAYS


# --------------------------------------------------------------------------- #
# point in time
# --------------------------------------------------------------------------- #

def test_contact_features_use_no_future_information(journeys: SimpleNamespace) -> None:
    """Recompute from a campaign table physically truncated at ``as_at``."""
    as_at = snapshot_timestamp(journeys.anchor, 20)
    c = journeys.campaigns
    index = pd.Index(sorted(journeys.journeys.customer_id.unique()), name="customer_id")
    full = contact_features_as_at(c, as_at, index)
    truncated = contact_features_as_at(c[_dt(c.sent_at) <= as_at], as_at, index)
    pd.testing.assert_frame_equal(full, truncated, check_dtype=False)


def test_a_later_snapshot_never_forgets_a_contact(journeys: SimpleNamespace) -> None:
    c = journeys.campaigns
    index = pd.Index(sorted(journeys.journeys.customer_id.unique()), name="customer_id")
    early = contact_features_as_at(c, snapshot_timestamp(journeys.anchor, 14), index)
    late = contact_features_as_at(c, snapshot_timestamp(journeys.anchor, 24), index)
    assert (late.campaign_contacts_6m.sum() > 0)
    seen_early = early.last_contact_days.notna()
    assert late.last_contact_days[seen_early].notna().all(), \
        "a contact visible at month 14 had vanished by month 24"


def test_journey_features_expose_the_sds6_additions(journeys: SimpleNamespace) -> None:
    """The six columns L7 was promised, on the frame L7 already calls."""
    as_at = snapshot_timestamp(journeys.anchor, 20)
    out = journey_features_as_at(journeys.journeys, journeys.events, as_at,
                                 campaigns=journeys.campaigns, labels=journeys.labels)
    for col in ("contacts_30d", "contacts_90d", "last_contact_days",
                "last_campaign_product", "suppressed", "suppression_reason"):
        assert col in out.columns, f"{col} missing from journey_features_as_at"
    assert out.contacts_30d.notna().all()
    assert (out.contacts_90d >= out.contacts_30d).all()
    assert set(out.suppression_reason) <= set(SUPPRESSION_REASONS) | {"not_in_population"}
