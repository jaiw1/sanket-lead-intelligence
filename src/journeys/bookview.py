"""Read-only view of the liability book, its latent truth and its browsing panel.

Nothing in this module writes to ``data/`` and nothing in it re-decides anything
the book already decided.  It loads three artefacts produced by
``src/make_book.py`` and reshapes them into the ``(N,)`` / ``(N, M)`` /
``(N, P, M)`` arrays the journey generator needs:

``customer_book.csv``        static attributes + the archetype / conversion truth
``liability_book_truth.csv`` latent intent ``(N, P, M)`` and capacity ``(N, M)``
``customer_panel.csv``       product-page dwell ``(N, P, M)`` (that column family only)

The eligibility rule is re-derived here rather than imported, because
``book.latent.eligibility`` takes a freshly-drawn ``Population`` object and we
only have the written CSV.  ``tests/test_journeys.py::test_eligibility_matches_book``
asserts the two derivations agree exactly, so the duplication cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from book.products import PRODUCTS

#: Columns read from ``customer_book.csv``.  Everything else is ignored.
BOOK_COLUMNS: tuple[str, ...] = (
    "cust_id", "segment", "age", "city_tier", "tenure_m", "consent",
    "product_canonical", "event_month", "true_income", "inc_drift",
    "window_shopper", "dormant_rich", "red_herring", "near_miss",
    "silent_converter", "browses", "dnd", "persuadable",
    "ramp_start", "ramp_end", "sig_strength",
    "has_auto_emi", "owns_property", "gold_holding_g", "dependants",
    "salary_regular", "fee_sensitivity", "doc_reluctance",
)


@dataclass
class BookView:
    """The book as the journey layer sees it.  Everything here is read-only."""

    n: int
    months: int
    products: tuple[str, ...]
    anchor: tuple[int, int]

    book: pd.DataFrame                # (N,) one row per customer, BOOK_COLUMNS
    intent: np.ndarray                # (N, P, M) float32 latent intent
    capacity_abs: np.ndarray          # (N, M) float32 rupees of monthly headroom
    capacity_ratio: np.ndarray        # (N, M) float32 headroom / median credits
    dwell: np.ndarray                 # (N, P, M) float32 product-page minutes
    eligibility: np.ndarray           # (N, P) float64 multiplicative weights

    # convenience views, all (N,)
    event_month: np.ndarray
    product_idx: np.ndarray           # manifest product index, -1 for non-converters
    is_converter: np.ndarray

    @property
    def n_products(self) -> int:
        return len(self.products)


def _infer_anchor(dates: pd.Series) -> tuple[int, int]:
    """Calendar ``(year, month)`` of panel month 0, read off the panel labels."""
    first = str(dates.iloc[0])
    y, m = first.split("-")[:2]
    return int(y), int(m)


def _reshape(df: pd.DataFrame, cust_id: np.ndarray, months: int, cols: list[str]) -> np.ndarray:
    """``(len(cols), N, M)`` from a long customer-month frame, order-checked.

    ``book.build`` writes the long frames as ``repeat(cust_id) x tile(month)``, so
    a reshape is correct *and* two orders of magnitude cheaper than a pivot — but
    only if that layout really holds, which is asserted rather than assumed.
    """
    n = len(cust_id)
    if len(df) != n * months:
        raise ValueError(f"expected {n * months} rows, got {len(df)}")
    m_col = df["month"].to_numpy()
    if not np.array_equal(m_col[: 2 * months], np.tile(np.arange(months), 2)):
        raise ValueError("long frame is not laid out as repeat(cust_id) x tile(month)")
    ids = df["cust_id"].to_numpy(dtype=object)[::months]
    if not np.array_equal(ids, cust_id):
        raise ValueError("long frame customer order does not match customer_book.csv")
    return np.stack([df[c].to_numpy(dtype=np.float32).reshape(n, months) for c in cols])


def eligibility_from_book(book: pd.DataFrame, products: tuple[str, ...] = PRODUCTS) -> np.ndarray:
    """``(N, P)`` eligibility weights, re-derived from the written book.

    Mirrors ``book.latent.eligibility`` for the modern preset exactly.  A weight
    of 0.0 is an *impossible state*: no property means no loan against property,
    no gold means no gold loan.
    """
    idx = {p: i for i, p in enumerate(products)}
    n = len(book)
    w = np.ones((n, len(products)), dtype=np.float64)
    age = book["age"].to_numpy()
    owns = book["owns_property"].to_numpy().astype(bool)
    gold = book["gold_holding_g"].to_numpy()
    auto_emi = book["has_auto_emi"].to_numpy().astype(bool)
    deps = book["dependants"].to_numpy()

    w[:, idx["home"]] *= np.where(owns, 0.25, 1.0)
    w[:, idx["home"]] *= np.where((age >= 24) & (age <= 48), 1.0, 0.35)
    w[:, idx["lap"]] *= owns.astype(float)
    w[:, idx["gold"]] *= (gold > 0).astype(float)
    w[:, idx["auto"]] *= np.where(auto_emi, 0.30, 1.0)
    w[:, idx["education"]] *= np.where((deps == 0) & (age > 35), 0.15, 1.0)
    return w


def load(book_dir: Path, products: tuple[str, ...] = PRODUCTS) -> BookView:
    """Load the book, the latent truth and the dwell panel into one view."""
    book_dir = Path(book_dir)
    book = pd.read_csv(book_dir / "customer_book.csv", engine="pyarrow",
                       usecols=list(BOOK_COLUMNS))[list(BOOK_COLUMNS)]
    missing = [p for p in products if f"intent_{p}" not in
               pd.read_csv(book_dir / "liability_book_truth.csv", nrows=0).columns]
    if missing:
        raise ValueError(
            f"liability_book_truth.csv has no intent columns for {missing}. "
            "Regenerate the book with `python3 src/make_book.py` (the modern "
            "preset); the journey layer cannot run on the legacy three-product book.")

    cust_id = book["cust_id"].to_numpy(dtype=object)
    n = len(cust_id)

    truth = pd.read_csv(book_dir / "liability_book_truth.csv", engine="pyarrow")
    months = int(truth["month"].max()) + 1
    stacked = _reshape(truth, cust_id, months,
                       [f"intent_{p}" for p in products] + ["capacity_abs", "capacity_ratio"])
    intent = stacked[: len(products)]                       # (P, N, M)
    capacity_abs, capacity_ratio = stacked[-2], stacked[-1]
    del truth, stacked

    dwell_cols = [f"dwell_{p}" for p in products]
    panel = pd.read_csv(book_dir / "customer_panel.csv", engine="pyarrow",
                        usecols=["cust_id", "month", "date", *dwell_cols])
    anchor = _infer_anchor(panel["date"])
    dwell = _reshape(panel, cust_id, months, dwell_cols)     # (P, N, M)
    del panel

    prod = book["product_canonical"].fillna("").to_numpy(dtype=object)
    pidx = {p: i for i, p in enumerate(products)}
    product_idx = np.array([pidx.get(p, -1) for p in prod], dtype=np.int64)
    event_month = book["event_month"].to_numpy(dtype=np.int64)

    return BookView(
        n=n, months=months, products=tuple(products), anchor=anchor, book=book,
        intent=np.ascontiguousarray(intent.transpose(1, 0, 2)),     # (N, P, M)
        capacity_abs=capacity_abs, capacity_ratio=capacity_ratio,
        dwell=np.ascontiguousarray(dwell.transpose(1, 0, 2)),       # (N, P, M)
        eligibility=eligibility_from_book(book, products),
        event_month=event_month, product_idx=product_idx,
        is_converter=event_month >= 0,
    )
