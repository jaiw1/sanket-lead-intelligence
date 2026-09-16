"""SM-1 — what the model is allowed to see, and what it must never see.

The forbidden-input guard is the test this repo would be most embarrassed to
fail, because every headline number is worthless if one outcome column leaked
into the features. It is enforced in three places, and all three are checked
here from the outside:

1. ``model.FORBIDDEN_INPUTS`` names the columns — outcomes, generator latents and
   policy flags — that may never be inputs;
2. ``model.frame.build_matrix`` **raises** rather than let one through, so the
   guard sits in the code path and not only in this file;
3. the measurement-only columns are all loaded under a ``t_`` prefix, so a
   rename cannot smuggle one past the name check.

SK-17 registers a **zero-tolerance** band for this ("nothing after
``abandon_ts``"), which is why the count, not a share, is what gets reported.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from model import FORBIDDEN_INPUTS, PRODUCTS, TRUTH_PREFIX
from model.frame import (
    CUSTOMER_FEATURES,
    FEATURE_FAMILIES,
    FEATURES,
    LABEL_KEEP,
    MENTOR_SIGNALS,
    build_matrix,
    monotone_constraints,
)


# --------------------------------------------------------------------------- #
# the forbidden set
# --------------------------------------------------------------------------- #

def test_no_feature_is_a_forbidden_input() -> None:
    assert not set(FEATURES) & FORBIDDEN_INPUTS
    assert not set(CUSTOMER_FEATURES) & FORBIDDEN_INPUTS


def test_the_label_and_its_parts_are_forbidden() -> None:
    """Every column the label is made of, and the treatment that produced it."""
    for c in ("label_disbursed_in_window", "label_product", "label_no_contact",
              "label_observed", "window_respected", "days_to_disbursement",
              "realised_recovery", *(f"label_product_{p}" for p in PRODUCTS)):
        assert c in FORBIDDEN_INPUTS, c
    # `contacted` is timestamped at or after as_at (DATA_CARD 12.5): a treatment,
    # never a feature.
    for c in ("contacted", "contacted_at", "contact_channel"):
        assert c in FORBIDDEN_INPUTS, c


def test_the_generator_latents_are_forbidden() -> None:
    for c in ("shopper_truth", "latent_signal", "oracle_score", "return_propensity",
              "commitment", "p_disburse_if_contacted", "p_disburse_no_contact",
              "window_shopper", "persuadable", "true_income", "inc_drift",
              "event_month", "product_canonical", "driver_product"):
        assert c in FORBIDDEN_INPUTS, c


def test_the_policy_flags_are_forbidden() -> None:
    """Who may be called is decided before scoring, not learned from."""
    for c in ("consent", "consent_marketing", "dnd", "suppressed",
              "suppression_reason", "eligible_for_contact"):
        assert c in FORBIDDEN_INPUTS, c


def test_build_matrix_raises_on_a_forbidden_input(model_run: SimpleNamespace) -> None:
    """The guard is in the code path, not only in this file."""
    with pytest.raises(ValueError, match="forbidden model inputs"):
        build_matrix(model_run.stacked, (*FEATURES, "label_disbursed_in_window"))


def test_build_matrix_raises_on_a_measurement_column(model_run: SimpleNamespace) -> None:
    with pytest.raises(ValueError, match="measurement-only"):
        build_matrix(model_run.stacked, (*FEATURES, "t_shopper_truth"))


def test_measurement_columns_are_all_prefixed(model_run: SimpleNamespace) -> None:
    """A rename cannot defeat the name check, because the prefix is the check."""
    truth = [c for c in model_run.base.columns if c.startswith(TRUTH_PREFIX)]
    assert len(truth) >= 8
    assert not set(truth) & set(FEATURES)


def test_the_design_matrix_holds_exactly_the_features(model_run: SimpleNamespace) -> None:
    X = build_matrix(model_run.stacked)
    assert list(X.columns) == list(FEATURES)
    assert len(X) == len(model_run.stacked)


def test_the_model_was_fitted_on_exactly_those_columns(model_run: SimpleNamespace) -> None:
    assert list(model_run.ranker.model.feature_name_) == list(FEATURES)


def test_families_partition_the_feature_list() -> None:
    flat = [f for fam in FEATURE_FAMILIES.values() for f in fam]
    assert sorted(flat) == sorted(set(flat)), "a feature is in two families"
    assert sorted(flat) == sorted(FEATURES)


# --------------------------------------------------------------------------- #
# point-in-time
# --------------------------------------------------------------------------- #

def test_features_are_computed_at_the_month_start(model_run: SimpleNamespace) -> None:
    """The frame's ``as_at`` is the first instant of the month, not the last.

    Membership in the drop-off pool is decided at the moment an RM picks the list
    up (DATA_CARD 12.1); computing a feature at the *end* of the month would let
    the row see the month it is being scored in.
    """
    as_at = pd.to_datetime(model_run.base["as_at"])
    assert (as_at.dt.day == 1).all()
    assert (as_at.dt.hour == 0).all()


def test_no_feature_column_is_perfectly_correlated_with_the_label(
        model_run: SimpleNamespace) -> None:
    """A crude leak detector: a feature that *is* the answer would show up here."""
    base = model_run.base
    y = base["t_label"].to_numpy(dtype=float)
    numeric = [f for f in CUSTOMER_FEATURES
               if f in base.columns and pd.api.types.is_numeric_dtype(base[f])]
    for f in numeric:
        v = base[f].to_numpy(dtype=float)
        ok = np.isfinite(v)
        if ok.sum() < 100 or np.std(v[ok]) == 0:
            continue
        r = abs(float(np.corrcoef(v[ok], y[ok])[0, 1]))
        assert r < 0.60, f"{f} correlates {r:.2f} with the label"


def test_label_columns_are_carried_but_renamed_out_of_the_feature_space(
        model_run: SimpleNamespace) -> None:
    """The label is loaded (we have to grade something) — under ``t_``, not its own name."""
    assert "label_disbursed_in_window" in LABEL_KEEP
    assert "label_disbursed_in_window" not in model_run.base.columns
    assert "t_label" in model_run.base.columns


# --------------------------------------------------------------------------- #
# monotone constraints
# --------------------------------------------------------------------------- #

def test_the_four_mentor_signals_are_the_constrained_ones() -> None:
    assert MENTOR_SIGNALS == ("journey_blank_field_ratio", "journey_refused_income",
                              "journey_fee_balk", "journey_doc_refusal")


def test_constraints_are_minus_one_on_those_four_and_zero_elsewhere() -> None:
    c = monotone_constraints()
    assert len(c) == len(FEATURES)
    for f, v in zip(FEATURES, c):
        assert v == (-1 if f in MENTOR_SIGNALS else 0), f


def test_no_categorical_carries_a_constraint() -> None:
    """LightGBM rejects a constraint on a categorical; none of the four is one."""
    from model.frame import CATEGORICAL

    assert not set(CATEGORICAL) & set(MENTOR_SIGNALS)
