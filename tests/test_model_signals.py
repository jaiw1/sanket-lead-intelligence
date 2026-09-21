"""SM-1/SM-3 — the four window-shopper signals, the menu of four, and the windows.

The mentors named four behaviours that mean "this one is not really buying":
vague or blank answers, refusing to share income, balking at the ₹1,000 fee, and
refusing documents. Three things have to be true about them, and each is a test
here:

* they must push the disbursement probability **down** (SK-15, and gate G3 reads
  it as "4 signals negative");
* the RM has to be *told*, which is what the negative chips are for — and a chip
  must never fire on a customer who did not do the thing;
* the direction must survive being measured on the model rather than asserted in
  a slide, which is why the effect is a SHAP difference on held-out rows.

The menu of four and the per-product windows are here for the same reason: they
are mandates, so they are assertions.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from model import PRODUCTS, WINDOW_DAYS
from model.copy import ALWAYS_SHOW, NEGATIVE, PITCH_EN, PITCH_HI, negative_chips
from model.frame import MENTOR_SIGNALS
from model.metrics import menu, menu_metrics
from model.pack import signal_effects


# --------------------------------------------------------------------------- #
# direction of effect  (SK-15)
# --------------------------------------------------------------------------- #

def test_all_four_signals_push_the_probability_down(model_run: SimpleNamespace) -> None:
    """The shipped model. Monotone constraints make this structural — see below."""
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    eff = signal_effects(model_run.ranker, model_run.stacked, h, model_run.cfg)
    assert eff["n_negative"] == 4, eff["constrained"]
    for s in MENTOR_SIGNALS:
        v = eff["constrained"][s]
        if v.get("status") == "skipped_low_n":
            continue
        assert v["effect"] < 0, (s, v)


def test_the_unconstrained_twin_is_reported_too(model_run: SimpleNamespace) -> None:
    """A constraint that forbids the wrong answer is not evidence the data agrees.

    So the same fit is repeated without the constraints and reported beside it.
    This test does **not** assert that all four come out negative unconstrained —
    that would be asserting a property of the generator, and if one of them is
    genuinely null on this label the honest thing is to publish the number, not
    to fail the build. It asserts only that the number exists to be read.
    """
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    eff = signal_effects(model_run.ranker, model_run.stacked, h, model_run.cfg)
    assert set(eff["unconstrained"]) == set(MENTOR_SIGNALS)
    assert 0 <= eff["n_negative_unconstrained"] <= 4


def test_the_effect_is_a_difference_not_a_level(model_run: SimpleNamespace) -> None:
    """``effect = mean SHAP where on - mean SHAP where off``.

    A level would let a feature with a constant negative offset look like a
    working signal; a difference cannot.
    """
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    eff = signal_effects(model_run.ranker, model_run.stacked, h, model_run.cfg)
    for s, v in eff["constrained"].items():
        if v.get("status") == "skipped_low_n":
            continue
        assert v["effect"] == v["mean_shap_on"] - v["mean_shap_off"], s


# --------------------------------------------------------------------------- #
# negative chips  (SM-3)
# --------------------------------------------------------------------------- #

def test_a_chip_never_fires_on_a_customer_who_did_not_do_it() -> None:
    clean = pd.Series(dict(journey_blank_field_ratio=0.0, journey_refused_income=0,
                           journey_fee_balk=0, journey_doc_refusal=0,
                           journey_multi_product_revisits=0, journey_docs_shortfall=0,
                           journey_stated_income_ratio=1.0, contacts_30d=0,
                           journey_open_now=0))
    assert negative_chips(clean, {k: -1.0 for k in NEGATIVE}) == []


def test_every_mentor_signal_has_a_chip_and_it_fires() -> None:
    row = pd.Series(dict(journey_blank_field_ratio=0.62, journey_refused_income=1,
                         journey_fee_balk=1, journey_doc_refusal=1,
                         journey_multi_product_revisits=0, journey_docs_shortfall=0,
                         journey_stated_income_ratio=1.0, contacts_30d=0,
                         journey_open_now=0))
    chips = negative_chips(row, {k: -0.2 for k in NEGATIVE}, k=4)
    assert {c["signal"] for c in chips} == set(MENTOR_SIGNALS)
    assert all(c["mentor_signal"] for c in chips)
    assert "62%" in next(c["text"] for c in chips
                         if c["signal"] == "journey_blank_field_ratio")


def test_the_four_mentor_chips_show_even_when_the_model_liked_them() -> None:
    """An RM must be told about the four, whichever way the model leaned.

    Everything else in the chip list is suppressed when the model's contribution
    was positive, so the chips stay a statement about the *score*, not a catalogue
    of every fact on file.
    """
    row = pd.Series(dict(journey_blank_field_ratio=0.0, journey_refused_income=1,
                         journey_fee_balk=0, journey_doc_refusal=0,
                         journey_multi_product_revisits=3, journey_docs_shortfall=0,
                         journey_stated_income_ratio=1.0, contacts_30d=0,
                         journey_open_now=0))
    chips = negative_chips(row, {k: +0.4 for k in NEGATIVE}, k=6)
    kinds = {c["signal"] for c in chips}
    assert "journey_refused_income" in kinds
    assert "journey_multi_product_revisits" not in kinds
    assert set(ALWAYS_SHOW) == set(MENTOR_SIGNALS)


def test_a_chip_carries_the_score_it_cost() -> None:
    row = pd.Series(dict(journey_blank_field_ratio=0.4, journey_refused_income=0,
                         journey_fee_balk=0, journey_doc_refusal=0,
                         journey_multi_product_revisits=0, journey_docs_shortfall=0,
                         journey_stated_income_ratio=1.0, contacts_30d=0,
                         journey_open_now=0))
    chips = negative_chips(row, dict.fromkeys(NEGATIVE, 0.0)
                           | {"journey_blank_field_ratio": -0.37})
    assert chips[0]["impact"] == -0.37


# --------------------------------------------------------------------------- #
# the menu of four  (SK-13 / SK-14)
# --------------------------------------------------------------------------- #

def test_the_menu_is_four_distinct_products_best_first(model_run: SimpleNamespace) -> None:
    m = menu(model_run.P, 4)
    assert m.shape == (len(model_run.base), 4)
    assert all(len(set(r.tolist())) == 4 for r in m[:200])
    P = model_run.P
    for i in range(200):
        vals = P[i, m[i]]
        assert list(vals) == sorted(vals, reverse=True)


def test_menu_hit_rate_is_computed_on_positives_only(model_run: SimpleNamespace) -> None:
    """SK-13's registered reading: among held-out customers who *do* disburse."""
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    hb = model_run.base[h].reset_index(drop=True)
    mm = menu_metrics(model_run.P[h], hb, 4)
    assert mm["n_positives"] == int(hb["t_label"].sum())
    assert 0.0 <= mm["menu_of_4_hit_rate"] <= 1.0
    assert mm["menu_of_4_hit_rate"] >= mm["top_1_product_accuracy"]
    lo, hi = mm["menu_of_4_hit_rate_ci"]
    assert lo <= mm["menu_of_4_hit_rate"] <= hi


def test_the_drop_off_anchor_is_reported_beside_the_menu(model_run: SimpleNamespace) -> None:
    """Most positives take the product they abandoned, so "offer them that" is a
    strong rule on its own. The menu's value has to be reported against it."""
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    hb = model_run.base[h].reset_index(drop=True)
    mm = menu_metrics(model_run.P[h], hb, 4)
    assert 0.0 <= mm["dropoff_anchor_top_1_accuracy"] <= 1.0
    assert mm["n_switched"] >= 0
    assert "menu_hit_rate_when_product_changed" in mm


def test_a_random_menu_of_four_over_six_would_score_two_thirds(
        model_run: SimpleNamespace) -> None:
    """The bar SK-13 registers (0.80) is only meaningful against this number."""
    rng = np.random.default_rng(0)
    h = model_run.split.mask(model_run.base["cust_id"], "held") \
        & (model_run.base["eligible_for_contact"].to_numpy() == 1)
    hb = model_run.base[h].reset_index(drop=True)
    R = rng.random((len(hb), len(PRODUCTS)))
    mm = menu_metrics(R, hb, 4)
    assert 0.55 <= mm["menu_of_4_hit_rate"] <= 0.80


# --------------------------------------------------------------------------- #
# the windows
# --------------------------------------------------------------------------- #

def test_the_windows_are_the_pre_registered_ones() -> None:
    assert WINDOW_DAYS == {"personal": 1, "gold": 1, "auto": 3,
                           "education": 7, "home": 14, "lap": 14}


def test_every_menu_entry_carries_its_own_window_and_a_contact_by_date(
        packed: SimpleNamespace) -> None:
    """SM-7: `contact_by` runs from ABANDONMENT, not from the scoring snapshot.

    The label is "disbursed inside the product's window after contact" and the
    platform backend expires a lead at `journeys.abandon_ts + window`; the pack
    used to compute `snapshot + window`, so the two disagreed by however long
    the customer had been sitting in the drop-off pool. A `contact_by` earlier
    than `scored_at` is therefore expected and correct — it means the window had
    already closed by the time the monthly snapshot reached this customer.
    """
    seen_closed = False
    for lead in packed.out["leads"]:
        abandoned = pd.Timestamp(lead["abandoned_at"])
        scored = pd.Timestamp(lead["scored_at"])
        assert (scored - abandoned).days == lead["days_since_abandon"]
        for entry in lead["product_menu"]:
            assert entry["window_days"] == WINDOW_DAYS[entry["product"]]
            gap = (pd.Timestamp(entry["contact_by"]) - abandoned).days
            assert gap == entry["window_days"], entry
        if pd.Timestamp(lead["contact_by"]) < scored:
            seen_closed = True
    assert seen_closed, ("no lead's window had closed by the snapshot — the fixture no "
                         "longer exercises the case the old formula hid")


def test_the_lead_window_is_the_offered_product_s_window(packed: SimpleNamespace) -> None:
    for lead in packed.out["leads"]:
        assert lead["window_days"] == WINDOW_DAYS[lead["product"]]
        assert lead["product"] == lead["product_menu"][0]["product"]


# --------------------------------------------------------------------------- #
# six products all the way through
# --------------------------------------------------------------------------- #

def test_there_is_call_material_for_all_six_products() -> None:
    assert set(PITCH_EN) == set(PRODUCTS)
    assert set(PITCH_HI) == set(PRODUCTS)
    for p in PRODUCTS:
        for block in (PITCH_EN[p], PITCH_HI[p]):
            opener, why_now, objection, answer = block
            # the why-now always quotes the customer's own EMI headroom; the
            # objection answer quotes it only where the money *is* the objection.
            assert "{emi:,}" in why_now and "₹" in why_now, p
            assert len(opener) > 60 and len(why_now) > 60, p
            assert len(answer) > 60 and len(objection) > 15, p


def test_no_lead_carries_the_retired_three_product_spelling(packed: SimpleNamespace) -> None:
    """``pl`` died at SM-1: the canonical spelling is ``personal``."""
    for lead in packed.out["leads"]:
        assert lead["product"] in PRODUCTS
        assert lead["product"] != "pl"
        for e in lead["product_menu"]:
            assert e["product"] in PRODUCTS
    assert set(packed.out["metrics"]["per_product"]) == set(PRODUCTS)
