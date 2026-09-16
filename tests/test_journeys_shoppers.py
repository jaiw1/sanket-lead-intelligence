"""SD-S3 — the window shopper as a causal negative, not a label.

The mentors named five behaviours: vague answers, refusal to share details,
balking at the Rs 1,000 processing fee, refusing documents, and revisiting
several products without committing (plus not picking up the RM's call).  This
file asserts three things about them.

**They are caused, not correlated.** One latent disposition raises all of them,
and it loads negatively on conversion, so each of the four signals the model
will use carries a genuinely negative marginal effect on disbursement — the
property ``validation/criteria.yaml`` SK-15 ("4 signals negative") will check
the *model* recovers.  The coefficients are tested here on the generated data
itself, because a model can only recover a sign that is in the data.

**They are informative, not deterministic.** Some genuine buyers balk at the fee
once and come back; some shoppers disburse anyway.  SK-05 pre-registers a
deliberately modest ``shopper AUC >= 0.70`` for exactly this reason, so a
suspiciously *high* separability is a failure here too.

**They never leak.** ``shopper_truth`` lives only in the truth file.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

#: The four signals the mentors named, as the model will see them.
SIGNALS = ("answers_blank_ratio", "income_refused", "fee_balk", "doc_refusal")
MAX_P = 0.01
#: Shopper share of the drop-off population (plan §B/L6 SD-S3: ~30%).
SHOPPER_BAND = (0.25, 0.35)


def _design(j: pd.DataFrame) -> pd.DataFrame:
    """The four signals, coded the way a model would see them at scoring time.

    A signal that was never observable (the attempt died before the bank quoted
    the fee) reads as "no balk seen", which is what the bank's screen would say —
    and is also the coding that makes this test hard, because it mixes the early
    drop-offs into the ``0`` bucket.
    """
    return sm.add_constant(pd.DataFrame({
        "answers_blank_ratio": j.answers_blank_ratio.to_numpy(),
        "income_refused": 1 - j.income_shared.to_numpy(),
        "fee_balk": j.fee_balk.fillna(0).to_numpy(),
        "doc_refusal": j.doc_refusal.fillna(0).to_numpy(),
    }))


@pytest.fixture(scope="module")
def fit(journeys: SimpleNamespace):
    j = journeys.journeys
    y = (j.outcome == "disbursed").to_numpy().astype(int)
    return sm.Logit(y, _design(j)).fit(disp=0)


# --------------------------------------------------------------------------- #
# caused, not correlated
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("signal", SIGNALS)
def test_signal_lowers_disbursement_holding_the_others_fixed(fit, signal: str) -> None:
    """All four negative, together, at p < 0.01.  Together matters: the four are
    symptoms of one disposition, so a signal that only looks bad because the
    others do would not survive here."""
    coef = float(fit.params[signal])
    p = float(fit.pvalues[signal])
    assert coef < 0, f"{signal} raises the disbursement probability (coef {coef:+.3f})"
    assert p < MAX_P, f"{signal} coefficient {coef:+.3f} is not significant (p = {p:.3g})"


@pytest.mark.parametrize("signal", SIGNALS)
def test_signal_lowers_disbursement_on_its_own(journeys: SimpleNamespace, signal: str) -> None:
    j = journeys.journeys
    y = (j.outcome == "disbursed").to_numpy().astype(int)
    x = _design(j)[["const", signal]]
    r = sm.Logit(y, x).fit(disp=0)
    assert float(r.params[signal]) < 0
    assert float(r.pvalues[signal]) < MAX_P


def test_shoppers_show_every_symptom_more_often(journeys: SimpleNamespace) -> None:
    """Vague answers, withheld income, fee balk, document refusal, multi-product
    browsing — and not answering the RM."""
    j = journeys.journeys.merge(journeys.truth[["attempt_id", "shopper_truth"]], on="attempt_id")
    s, g = j[j.shopper_truth == 1], j[j.shopper_truth == 0]
    assert s.answers_blank_ratio.mean() > g.answers_blank_ratio.mean() + 0.05
    assert (1 - s.income_shared).mean() > (1 - g.income_shared).mean() + 0.05
    assert s.fee_balk.mean() > g.fee_balk.mean() + 0.10
    assert s.doc_refusal.mean() > g.doc_refusal.mean() + 0.10
    assert s.products_viewed_30d.mean() > g.products_viewed_30d.mean() + 0.5
    assert s.revisits_30d.mean() > g.revisits_30d.mean() + 0.5
    cold = j[j.channel != "rm-call"]                       # an rm-call answered itself
    cs, cg = cold[cold.shopper_truth == 1], cold[cold.shopper_truth == 0]
    assert cs.rm_contacted.mean() < cg.rm_contacted.mean(), "shoppers answer the RM as often as buyers"


def test_shoppers_abandon_earlier_and_at_the_mentors_stages(journeys: SimpleNamespace) -> None:
    j = journeys.journeys.merge(journeys.truth[["attempt_id", "shopper_truth"]], on="attempt_id")
    ab = j[j.outcome == "abandoned"]
    at_fee_or_docs = ab.last_stage.isin(["fee", "docs"])
    rate = at_fee_or_docs.groupby(ab.shopper_truth).mean()
    assert rate[1] > rate[0], "shoppers are no more likely than others to die at Fee or Docs"


# --------------------------------------------------------------------------- #
# informative, not deterministic
# --------------------------------------------------------------------------- #

def test_shopper_share_of_drop_offs(journeys: SimpleNamespace) -> None:
    lo, hi = SHOPPER_BAND
    assert lo <= journeys.stats["shopper_share_of_dropoffs"] <= hi


def test_some_shoppers_disburse_anyway(journeys: SimpleNamespace) -> None:
    share = journeys.stats["shopper_share_of_disbursed"]
    assert share > 0.0, "no shopper ever buys — the signal is deterministic"
    assert share < 0.5 * journeys.stats["shopper_share_of_dropoffs"], \
        "shoppers buy nearly as often as everyone else — the signal carries nothing"


def test_genuine_buyers_balk_at_the_fee_and_come_back(journeys: SimpleNamespace) -> None:
    """The plan's own wording: 'some genuine buyers balk at the fee once'."""
    j = journeys.journeys.merge(journeys.truth[["attempt_id", "shopper_truth"]], on="attempt_id")
    balked_and_paid = j[(j.fee_balk == 1) & (j.fee_paid == 1)]
    assert len(balked_and_paid) > 0.02 * len(j), "nobody who balked at the fee ever paid it"
    assert (balked_and_paid.shopper_truth == 0).mean() > 0.5, \
        "only shoppers ever balk — the fee balk has become a label"
    # ...and some of them go on to a disbursement
    assert (balked_and_paid.outcome == "disbursed").mean() > 0.30


def test_returning_after_abandoning_is_a_real_population(journeys: SimpleNamespace) -> None:
    j = journeys.journeys
    repeat = j[j.attempt_seq > 1]
    assert len(repeat) > 0
    assert (repeat.outcome == "disbursed").mean() > 0.10, \
        "a second attempt never succeeds — there is nothing for an RM to recover"


def test_shoppers_are_detectable_but_not_trivially_so(journeys: SimpleNamespace) -> None:
    """SK-05 registers a floor of 0.70 on shopper AUC precisely because the
    generator is meant to make this hard.  Both ends are asserted."""
    j = journeys.journeys
    x = _design(j)
    x = x.assign(revisits=j.revisits_30d.to_numpy(), viewed=j.products_viewed_30d.to_numpy())
    y = journeys.truth.shopper_truth.to_numpy()
    r = sm.Logit(y, x).fit(disp=0)
    auc = roc_auc_score(y, r.predict(x))
    assert auc >= 0.70, f"window shoppers are undetectable from their own signals (AUC {auc:.3f})"
    assert auc <= 0.95, f"window shoppers are trivially separable (AUC {auc:.3f}) — too easy"


# --------------------------------------------------------------------------- #
# consistency and containment
# --------------------------------------------------------------------------- #

def test_shopper_truth_agrees_with_the_books_archetype(journeys: SimpleNamespace) -> None:
    """The book already carries a ``window_shopper`` archetype.  The journey
    layer must make it behave, not overrule it."""
    t = journeys.truth
    rate = t.groupby("book_window_shopper").shopper_truth.mean()
    assert rate[1] > 0.70, "the book's window shoppers are not shoppers in their journeys"
    assert rate[1] > 2.5 * rate[0]


def test_shoppers_are_mostly_not_converters(journeys: SimpleNamespace) -> None:
    t = journeys.truth
    assert t.groupby("is_converter").shopper_truth.mean()[0] > \
           4 * t.groupby("is_converter").shopper_truth.mean()[1]


def test_shopper_truth_never_reaches_a_feature_table(journeys: SimpleNamespace) -> None:
    from journeys.features import journey_features_as_at, snapshot_timestamp
    latent = {"shopper_truth", "shopper_propensity", "curiosity", "return_propensity",
              "p_complete", "forced_disburse", "commitment", "latent_month"}
    assert latent.isdisjoint(journeys.journeys.columns), "a latent leaked into journeys.csv"
    assert latent.isdisjoint(journeys.events.columns), "a latent leaked into journey_events.csv"
    f = journey_features_as_at(journeys.journeys, journeys.events,
                               snapshot_timestamp(journeys.anchor, 26))
    assert latent.isdisjoint(f.columns), "a latent leaked into the feature table"
    assert "shopper_truth" in journeys.truth.columns


def test_no_occupation_term_was_baked_into_the_shopper_latent(journeys: SimpleNamespace) -> None:
    """Gig workers must not be *defined* as shoppier; any gap has to come from
    the book's own fee-sensitivity inheritance, and stay small enough that the
    fairness finding (SK-23/SK-24) is a measurement, not a construction."""
    book = pd.read_csv(journeys.book_dir / "customer_book.csv", usecols=["cust_id", "segment"])
    t = journeys.truth.merge(book, left_on="customer_id", right_on="cust_id")
    rate = t.groupby("segment").shopper_truth.mean()
    assert rate.max() / rate.min() < 1.6, f"segment shopper rates differ too much: {rate.round(3).to_dict()}"
