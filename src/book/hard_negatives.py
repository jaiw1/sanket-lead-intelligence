"""Archetype assignment: the hard negatives that keep the AUC honest.

A synthetic book is only useful if the *negatives* are hard.  Five archetypes do
that work, and every one of them is carried over unchanged from the pre-SD-S1
book because they are the reason the model cannot separate products trivially:

``window_shopper`` (9% of non-converters)
    Heavy product-page dwell, no financial movement, never buys.  Punishes any
    model that leans on browsing alone.
``dormant_rich`` (7%)
    Capacity without intent — a permanently fat balance and nothing else.
``red_herring`` (14%)
    A genuine financial run-up (rent hike absorbed, a new commute, an external
    EMI that simply keeps being paid) with no browsing and no purchase.  This is
    the archetype that caps precision, and it is where most of the *persuadable*
    customers hide.
``near_miss`` (3%)
    The full textbook bundle — ramp plus browsing — and then life happens.
    Indistinguishable from a converter at the snapshot by construction.
``silent_converter`` (12% of converters)
    Converts with zero signal strength: no ramp, no dwell.  Caps recall.

On top of those sit the uplift potential outcomes: ``dnd`` (a pushy call kills an
otherwise organic sale) and ``persuadable`` (converts *only* if contacted inside
an active-signal window).  ``score_and_pack.py`` reads both to build the
randomised-campaign ground truth, so the column names are load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import BookConfig, substream
from .population import Population


@dataclass
class Archetypes:
    """Archetype masks and their windows, all ``(N,)``."""

    is_converter: np.ndarray
    window_shopper: np.ndarray
    dormant_rich: np.ndarray
    red_herring: np.ndarray
    near_miss: np.ndarray
    silent_converter: np.ndarray

    browses: np.ndarray            # researches on the bank's own pages at all
    sig_strength: np.ndarray       # 0.0 for silent converters, else U(0.45, 1.0)
    expresses_primary: np.ndarray  # shows the product's primary financial tell
    expresses_secondary: np.ndarray

    ws_start: np.ndarray           # window-shopper dwell burst start month (-1 = n/a)
    ws_prod: np.ndarray            # product index the window-shopper browses
    rh_start: np.ndarray           # red-herring financial ramp start (-1 = n/a)
    rh_len: np.ndarray
    rh_prod: np.ndarray            # which product's tells the red herring mimics

    dnd: np.ndarray                # do-not-disturb: contact destroys an organic sale
    persuadable: np.ndarray        # converts only when contacted in-window


#: Archetype shares.  ``window_shopper`` 9%, ``dormant_rich`` 7%, ``red_herring``
#: 14%, ``near_miss`` 3% of the *non-converter* population, expressed as
#: cumulative cut points on one uniform draw so the groups stay disjoint.
#: All ``assumed`` — they are a modelling choice, tuned so precision@budget lands
#: in the band the plan pre-registers rather than measured from any real book.
ARCHETYPE_CUTS: dict[str, tuple[float, float]] = {
    "window_shopper": (0.00, 0.09),
    "dormant_rich": (0.09, 0.16),
    "red_herring": (0.16, 0.30),
    "near_miss": (0.30, 0.33),
}

#: Share of converters that leave no behavioural trace at all. ``assumed``.
SILENT_CONVERTER_SHARE = 0.12
#: Share of the book that researches on the bank's own product pages. ``assumed``.
BROWSER_SHARE = 0.60
#: Probability a customer expresses a given sub-signal.  Nobody shows the whole
#: textbook bundle; this is what stops the features being collinear. ``assumed``.
PRIMARY_SIGNAL_P = 0.78
SECONDARY_SIGNAL_P = 0.72
#: Share of organic converters a pushy call would lose. ``assumed``.
DND_SHARE = 0.12
#: Share of near-misses / red-herrings that a well-timed call converts. ``assumed``.
PERSUADABLE_OF_NEAR_MISS = 0.55
PERSUADABLE_OF_RED_HERRING = 0.18


def assign_archetypes(cfg: BookConfig, pop: Population) -> Archetypes:
    """Assign every customer to at most one hard-negative archetype."""
    rng = substream(cfg.seed, "archetypes")
    n, n_prod = cfg.n, cfg.n_products
    conv_share = cfg.base_rates.converter_share(cfg.months)

    is_converter = rng.random(n) < conv_share

    # one uniform draw partitions the non-converters into disjoint archetypes
    r = rng.random(n)
    non_conv = ~is_converter
    def _cut(name: str) -> np.ndarray:
        lo, hi = ARCHETYPE_CUTS[name]
        return non_conv & (r >= lo) & (r < hi)

    window_shopper = _cut("window_shopper")
    dormant_rich = _cut("dormant_rich")
    red_herring = _cut("red_herring")
    near_miss = _cut("near_miss")

    silent = rng.random(n) < SILENT_CONVERTER_SHARE
    sig_strength = np.where(silent, 0.0, rng.uniform(0.45, 1.0, n))
    silent_converter = is_converter & silent

    browses = rng.random(n) < BROWSER_SHARE
    expresses_primary = rng.random(n) < PRIMARY_SIGNAL_P
    expresses_secondary = rng.random(n) < SECONDARY_SIGNAL_P

    # burst / ramp windows: bounded so they fit inside the panel with room for a
    # trailing-window feature to see them
    hi = max(7, cfg.months - 7)
    ws_start = np.where(window_shopper, rng.integers(6, hi, n), -1)
    ws_prod = np.where(window_shopper, rng.integers(0, n_prod, n), -1)
    rh_start = np.where(red_herring, rng.integers(6, hi, n), -1)
    rh_len = np.where(red_herring, rng.integers(4, 9, n), 0)
    rh_prod = np.where(red_herring, rng.integers(0, n_prod, n), -1)

    dnd = is_converter & (rng.random(n) < DND_SHARE)
    persuadable = ((near_miss & (rng.random(n) < PERSUADABLE_OF_NEAR_MISS))
                   | (red_herring & (rng.random(n) < PERSUADABLE_OF_RED_HERRING)))

    return Archetypes(
        is_converter=is_converter, window_shopper=window_shopper, dormant_rich=dormant_rich,
        red_herring=red_herring, near_miss=near_miss, silent_converter=silent_converter,
        browses=browses, sig_strength=sig_strength, expresses_primary=expresses_primary,
        expresses_secondary=expresses_secondary, ws_start=ws_start, ws_prod=ws_prod,
        rh_start=rh_start, rh_len=rh_len, rh_prod=rh_prod, dnd=dnd, persuadable=persuadable,
    )
