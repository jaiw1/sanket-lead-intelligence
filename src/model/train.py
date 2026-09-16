"""The model: one LightGBM over the stacked frame, plus two auxiliaries.

Three fits, and it is worth being explicit about which is which, because the
mentors' "one model" mandate is about the *first* of them:

``fit_ranker``    **the** model — one LightGBM, ``product`` as a categorical,
                  over (customer, month, product).  It replaces the three
                  per-product models the pre-SM-1 pipeline trained.
``fit_shopper``   an auxiliary *detector* whose target is the window-shopper
                  latent, used for the negative chips and graded by SK-05.  It
                  never feeds the ranker, and the ranker's inputs never include
                  its target.
``fit_uplift``    the two-model uplift estimator the cockpit already shipped,
                  rebased onto the drop-off population's real Y(1)/Y(0) pair
                  instead of the simulated campaign it used to reconstruct.

Monotone constraints
--------------------
The four window-shopper signals the mentors named are constrained to push the
disbursement probability **down** (``monotone_constraints = -1``).  That makes
the direction a property of the model rather than a hope — but a constraint that
merely forbids the wrong answer is not evidence that the data agrees, so
:func:`fit_ranker` can be asked for an unconstrained twin and
``metrics.signal_effects`` reports both.

Calibration
-----------
Isotonic, **per product**, fitted on a customer-disjoint calibration fold.  One
global calibrator is well behaved on average and systematically over-confident on
the products it saw least, which is exactly what SK-12 exists to catch.  The
per-product maps are monotone, so they re-rank nothing *within* a product; what
they buy is comparability *across* products, which is what the menu of four needs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression

from . import PRODUCTS, ModelConfig
from .frame import (
    CATEGORICAL,
    CUSTOMER_FEATURES,
    FEATURES,
    build_matrix,
    monotone_constraints,
)


# --------------------------------------------------------------------------- #
# splits
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Split:
    """Customer-grouped split.  Every month of a customer falls on one side."""

    fit: frozenset
    calib: frozenset
    held: frozenset
    seed: int

    def mask(self, cust: pd.Series, which: str) -> np.ndarray:
        return cust.isin(getattr(self, which)).to_numpy()


def split_customers(custs, cfg: ModelConfig, seed: int | None = None) -> Split:
    """Split customers 52.5 / 17.5 / 30 into fit / calibrate / hold out.

    The holdout fraction is the 0.30 ``validation/criteria.yaml`` registers.  The
    calibration fold is carved out of the *training* side so the holdout stays
    exactly what was registered, and so no customer is ever used both to fit a
    calibrator and to measure one.
    """
    seed = cfg.seed if seed is None else seed
    c = np.array(sorted(set(custs)), dtype=object)
    perm = np.random.default_rng(seed).permutation(len(c))
    n_test = int(round(cfg.test_fraction * len(c)))
    held = c[perm[:n_test]]
    train = c[perm[n_test:]]
    n_cal = int(round(cfg.calib_fraction * len(train)))
    return Split(fit=frozenset(train[n_cal:]), calib=frozenset(train[:n_cal]),
                 held=frozenset(held), seed=seed)


# --------------------------------------------------------------------------- #
# the ranker
# --------------------------------------------------------------------------- #

@dataclass
class Ranker:
    """One LightGBM plus its six isotonic calibrators."""

    model: LGBMClassifier
    calibrators: dict[str, IsotonicRegression]
    features: tuple[str, ...]
    n_products: int = len(PRODUCTS)
    unconstrained: LGBMClassifier | None = None

    def raw(self, stacked: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(build_matrix(stacked, self.features))[:, 1]

    def calibrated(self, stacked: pd.DataFrame) -> np.ndarray:
        r = self.raw(stacked)
        out = np.empty_like(r)
        prod = stacked["product"].astype(str).to_numpy()
        for p, iso in self.calibrators.items():
            m = prod == p
            if m.any():
                out[m] = iso.predict(r[m])
        return out

    def matrix(self, stacked: pd.DataFrame) -> np.ndarray:
        """``(n_rows, 6)`` calibrated probabilities, aligned with the base frame.

        ``frame.stack`` lays the six products out as contiguous blocks; ``_row``
        records that layout and is asserted here rather than assumed.
        """
        n = len(stacked) // self.n_products
        rows = stacked["_row"].to_numpy()
        if not np.array_equal(rows, np.tile(np.arange(n), self.n_products)):
            raise ValueError("stacked frame is not in product-block order")
        return self.calibrated(stacked).reshape(self.n_products, n).T

    def contributions(self, stacked: pd.DataFrame) -> np.ndarray:
        """SHAP contributions, ``(n, n_features)`` — the log-odds decomposition."""
        return self.model.booster_.predict(
            build_matrix(stacked, self.features), pred_contrib=True)[:, :-1]


def _lgbm(cfg: ModelConfig, seed: int, monotone: bool, features: tuple[str, ...]) -> LGBMClassifier:
    kw = dict(cfg.lgbm)
    kw["random_state"] = seed
    if monotone:
        kw["monotone_constraints"] = monotone_constraints(features)
        kw["monotone_constraints_method"] = "advanced"
    return LGBMClassifier(**kw)


def fit_ranker(stacked: pd.DataFrame, split: Split, cfg: ModelConfig,
               features: tuple[str, ...] = FEATURES,
               with_unconstrained: bool = False) -> Ranker:
    """Fit the single model, then calibrate it per product on the held-out fold."""
    cust = stacked["cust_id"]
    elig = stacked["eligible_for_contact"].to_numpy() == 1
    tr = split.mask(cust, "fit") & elig
    ca = split.mask(cust, "calib") & elig

    cats = [c for c in CATEGORICAL if c in features]
    m = _lgbm(cfg, split.seed, True, features)
    m.fit(build_matrix(stacked[tr], features), stacked.loc[tr, "y"], categorical_feature=cats)

    un = None
    if with_unconstrained:
        un = _lgbm(cfg, split.seed, False, features)
        un.fit(build_matrix(stacked[tr], features), stacked.loc[tr, "y"], categorical_feature=cats)

    raw_cal = m.predict_proba(build_matrix(stacked[ca], features))[:, 1]
    prod_cal = stacked.loc[ca, "product"].astype(str).to_numpy()
    y_cal = stacked.loc[ca, "y"].to_numpy()
    calibrators = {}
    for p in PRODUCTS:
        sel = prod_cal == p
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(raw_cal[sel], y_cal[sel])
        calibrators[p] = iso
    return Ranker(model=m, calibrators=calibrators, features=tuple(features), unconstrained=un)


# --------------------------------------------------------------------------- #
# the window-shopper detector
# --------------------------------------------------------------------------- #

@dataclass
class Shopper:
    model: LGBMClassifier
    features: tuple[str, ...]

    def score(self, base: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(build_matrix(base, self.features))[:, 1]

    def contributions(self, base: pd.DataFrame) -> np.ndarray:
        return self.model.booster_.predict(
            build_matrix(base, self.features), pred_contrib=True)[:, :-1]


def fit_shopper(base: pd.DataFrame, split: Split, cfg: ModelConfig) -> Shopper:
    """Detect the window shopper from what the application actually showed.

    The target here is the generator's latent flag, which a real bank does not
    have.  In production the same detector is trained on the observable proxy —
    "two or more abandoned attempts and no disbursement in twelve months" — and
    the honest statement is that this measurement is an upper bound on how well
    that proxy would do.  Recorded in ``MODEL_CARD.md``, not buried here.
    """
    tr = split.mask(base["cust_id"], "fit") & (base["eligible_for_contact"].to_numpy() == 1)
    feats = tuple(f for f in CUSTOMER_FEATURES if f in base.columns)
    kw = dict(cfg.lgbm)
    kw.update(random_state=split.seed, n_estimators=300)
    m = LGBMClassifier(**kw)
    cats = [c for c in CATEGORICAL if c in feats]
    m.fit(build_matrix(base[tr], feats), base.loc[tr, "t_shopper_truth"].fillna(0).astype(int),
          categorical_feature=cats)
    return Shopper(model=m, features=feats)


# --------------------------------------------------------------------------- #
# uplift
# --------------------------------------------------------------------------- #

@dataclass
class Uplift:
    treated: LGBMClassifier
    control: LGBMClassifier
    features: tuple[str, ...]

    def score(self, base: pd.DataFrame) -> np.ndarray:
        X = build_matrix(base, self.features)
        return self.treated.predict_proba(X)[:, 1] - self.control.predict_proba(X)[:, 1]


def randomised_campaign(base: pd.DataFrame, mask: np.ndarray,
                        rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """A 50/50 randomised contact experiment over ``mask``.

    SD-S4 emits both potential outcomes for every row — ``label_disbursed_in_window``
    is Y(1) and ``label_no_contact`` is Y(0) — so the experiment is a coin flip
    over rows that already carry both, and the observed outcome is the one the
    flip selects.  Before SM-1 the repo reconstructed Y(1) from the book's
    ``persuadable`` window; it no longer has to guess.
    """
    n = int(mask.sum())
    T = rng.random(n) < 0.5
    y1 = base.loc[mask, "t_label"].to_numpy()
    y0 = base.loc[mask, "t_label_no_contact"].to_numpy()
    return T, np.where(T, y1, y0)


def fit_uplift(base: pd.DataFrame, split: Split, cfg: ModelConfig,
               rng: np.random.Generator) -> Uplift:
    tr = split.mask(base["cust_id"], "fit") & (base["eligible_for_contact"].to_numpy() == 1)
    T, y = randomised_campaign(base, tr, rng)
    feats = tuple(f for f in CUSTOMER_FEATURES if f in base.columns)
    X = build_matrix(base[tr], feats)
    cats = [c for c in CATEGORICAL if c in feats]
    kw = dict(cfg.lgbm)
    kw.update(random_state=split.seed, n_estimators=300)
    mt = LGBMClassifier(**kw).fit(X[T], y[T], categorical_feature=cats)
    mc = LGBMClassifier(**kw).fit(X[~T], y[~T], categorical_feature=cats)
    return Uplift(treated=mt, control=mc, features=feats)
