"""SD-S1 equivalence: the vectorised generator must reproduce the old book.

The pre-SD-S1 generator was a ``for i in range(N)`` row loop.  Vectorising it
changes the *order* in which random numbers are drawn, so bit-for-bit equality
is impossible and meaningless.  What must hold is **distributional** equivalence
at ``--legacy-size``:

* the old schema survives — every legacy column, in its original position;
* the key behavioural columns keep their shape (quantiles and means);
* the conversion base rate the scorer measures stays within 0.2 pp;
* the hard-negative archetype shares stay within 2 pp — they are what keeps the
  AUC honest, so drifting them silently would flatter the model.

Reference fixture
-----------------
``fixtures/legacy_reference.json`` was produced by running the original row loop
(``src/book/_legacy.py``, a verbatim copy of git blob
``26454a5128aafcd8a94b43a6f1e6e3e909dca171``) and summarising its output with
:func:`summarise` below.  ``_legacy.py`` was deleted once this test passed; it
is recoverable with ``git show 26454a5128aafcd8a94b43a6f1e6e3e909dca171``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from book import BookConfig
from book.build import LEGACY_BOOK_COLUMNS, LEGACY_PANEL_COLUMNS, build_frames

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_reference.json"

#: Columns whose distribution must survive vectorisation.  These are exactly the
#: columns ``score_and_pack.build_features`` turns into model features.
KEY_COLUMNS = [
    "credits", "bal_avg", "bal_min", "rent", "fuel_cab", "school_fees",
    "ecommerce", "ext_emi", "fd_bal", "dwell_home", "dwell_auto", "dwell_pl",
]
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

#: Tolerances.  Quantiles are compared in relative terms because the columns span
#: four orders of magnitude; the ``dwell_*`` columns are mostly zero so their low
#: quantiles are compared on the mean and the non-zero share instead.
REL_TOL_QUANTILE = 0.06
REL_TOL_MEAN = 0.06
ABS_TOL_NONZERO_SHARE = 0.02
ABS_TOL_BASE_RATE = 0.002        # 0.2 pp
ABS_TOL_ARCHETYPE_SHARE = 0.02   # 2 pp


def summarise(panel: pd.DataFrame, book: pd.DataFrame, snapshot: int, horizon: int = 3) -> dict:
    """Distributional fingerprint of a book, used for both sides of the compare."""
    ev = book.event_month.values
    cols = {}
    for c in KEY_COLUMNS:
        v = panel[c].to_numpy(dtype=float)
        cols[c] = {
            "quantiles": {str(q): float(np.quantile(v, q)) for q in QUANTILES},
            "mean": float(v.mean()),
            "nonzero_share": float((v != 0).mean()),
        }
    return {
        "n": int(book.shape[0]),
        "months": int(panel.month.max()) + 1,
        "rows": int(panel.shape[0]),
        "panel_columns": list(panel.columns),
        "book_columns": list(book.columns),
        "columns": cols,
        "shares": {
            "converters": float((ev >= 0).mean()),
            "contact_conversion_3m": float(((ev > snapshot) & (ev <= snapshot + horizon)).mean()),
            "consent": float(book.consent.mean()),
            "window_shopper": float(book.window_shopper.mean()),
            "dormant_rich": float(book.dormant_rich.mean()),
            "persuadable": float(book.persuadable.mean()),
            "dnd": float(book.dnd.mean()),
        },
        "product_mix": {
            k: float(v) for k, v in
            book.loc[book["product"] != "", "product"].value_counts(normalize=True).items()
        },
    }


@pytest.fixture(scope="module")
def reference() -> dict:
    if not FIXTURE.exists():                                    # pragma: no cover
        pytest.skip(f"missing reference fixture {FIXTURE}")
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def generated() -> dict:
    cfg = BookConfig.legacy()
    panel, book, _truth = build_frames(cfg)
    return summarise(panel, book, cfg.snapshot_month)


def test_legacy_schema_is_preserved(reference: dict, generated: dict) -> None:
    """Every legacy column survives, in its original position."""
    assert generated["panel_columns"][: len(LEGACY_PANEL_COLUMNS)] == LEGACY_PANEL_COLUMNS
    assert generated["book_columns"][: len(LEGACY_BOOK_COLUMNS)] == LEGACY_BOOK_COLUMNS
    assert reference["panel_columns"] == LEGACY_PANEL_COLUMNS
    assert reference["book_columns"] == LEGACY_BOOK_COLUMNS
    # additions are allowed; removals are not
    assert set(reference["panel_columns"]) <= set(generated["panel_columns"])
    assert set(reference["book_columns"]) <= set(generated["book_columns"])


def test_panel_shape_matches(reference: dict, generated: dict) -> None:
    assert (generated["n"], generated["months"], generated["rows"]) == \
           (reference["n"], reference["months"], reference["rows"])


@pytest.mark.parametrize("col", KEY_COLUMNS)
def test_key_column_distribution(reference: dict, generated: dict, col: str) -> None:
    """Quantiles and means of the feature-bearing columns survive vectorisation."""
    ref, got = reference["columns"][col], generated["columns"][col]
    assert got["nonzero_share"] == pytest.approx(ref["nonzero_share"], abs=ABS_TOL_NONZERO_SHARE), \
        f"{col}: non-zero share moved"
    assert got["mean"] == pytest.approx(ref["mean"], rel=REL_TOL_MEAN), f"{col}: mean moved"
    for q, ref_v in ref["quantiles"].items():
        if abs(ref_v) < 1e-9:
            continue                      # a zero quantile carries no scale to compare
        assert got["quantiles"][q] == pytest.approx(ref_v, rel=REL_TOL_QUANTILE), \
            f"{col}: q{q} moved ({ref_v:.2f} -> {got['quantiles'][q]:.2f})"


def test_conversion_base_rate(reference: dict, generated: dict) -> None:
    """The label the scorer measures stays within 0.2 pp of the old book."""
    ref = reference["shares"]["contact_conversion_3m"]
    got = generated["shares"]["contact_conversion_3m"]
    assert got == pytest.approx(ref, abs=ABS_TOL_BASE_RATE), \
        f"random-contact 3-month conversion {got:.3%} vs {ref:.3%}"


@pytest.mark.parametrize("share", ["converters", "consent", "window_shopper", "dormant_rich",
                                   "persuadable", "dnd"])
def test_archetype_shares(reference: dict, generated: dict, share: str) -> None:
    """Hard negatives and uplift archetypes stay within 2 pp — they cap the AUC."""
    assert generated["shares"][share] == pytest.approx(
        reference["shares"][share], abs=ABS_TOL_ARCHETYPE_SHARE), f"{share} share drifted"


def test_product_mix(reference: dict, generated: dict) -> None:
    """The three legacy products keep their share of converters (within 4 pp)."""
    assert set(generated["product_mix"]) == set(reference["product_mix"])
    for p, ref_v in reference["product_mix"].items():
        assert generated["product_mix"][p] == pytest.approx(ref_v, abs=0.04), f"{p} mix drifted"


def test_same_seed_is_reproducible() -> None:
    """Requirement 1: identical output for the same seed."""
    cfg = BookConfig(n=800, months=16, seed=4242)
    a_panel, a_book, a_truth = build_frames(cfg)
    b_panel, b_book, b_truth = build_frames(cfg)
    pd.testing.assert_frame_equal(a_panel, b_panel)
    pd.testing.assert_frame_equal(a_book, b_book)
    pd.testing.assert_frame_equal(a_truth, b_truth)


def test_different_seed_changes_the_book() -> None:
    a_panel, _, _ = build_frames(BookConfig(n=800, months=16, seed=1))
    b_panel, _, _ = build_frames(BookConfig(n=800, months=16, seed=2))
    assert not a_panel.credits.equals(b_panel.credits)
