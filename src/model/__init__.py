"""SANKET — **one** model across all six products, over the drop-off population.

What changed at SM-1
--------------------
The pre-SM-1 pipeline trained *three* LightGBMs — one per product, on the whole
liability book, against a three-month "did this customer take product p" label
read off the book's ``event_month``.  It scored 15,000 customers, quoted a 1.3%
random baseline and a 36% precision at a 2% budget, and called that a 28x lift.

Three things were wrong with it and the mentors said all three:

1. **Three models is not one model.**  A separate model per product cannot share
   what it learns about "this customer is ready to borrow", and it has nothing
   to say about the five products it was not trained on.  Here there is one
   LightGBM over a **stacked** frame — one row per (customer, month, candidate
   product) — with ``product`` as a categorical.  The menu of four falls out of
   ranking the six candidate rows of a customer-month against each other.
2. **The population is the drop-offs**, not the whole book.  A customer who
   never applied for anything is a lead-generation problem, and lead generation
   is out of scope.  The training frame is ``data/labels.csv`` filtered to
   ``eligible_for_contact = 1``: consented, contactable customers with a live
   abandoned application behind them.
3. **The denominator was wrong, so the headline was wrong.**  Against the
   whole-book denominator a random call converts ~1%, which made the model look
   28x better than it is.  Against the population an RM actually calls, a random
   call converts ~9% — and the honest claim is
   **"9 -> 30 disbursements per 100 RM calls"**.  ``1% -> 36%`` and ``28x`` are
   retired; nothing in this package can emit them.

Module map
----------
``frame``    point-in-time feature assembly and the stacked (customer, month, product) frame
``train``    the LightGBM, its monotone constraints, per-product calibration, the shopper detector
``metrics``  every pre-registered SK-* quantity, with confidence intervals
``copy``     reason chips, negative window-shopper chips, six-product bilingual pitch material
``pack``     the ``app/public/sanket_data.json`` export

Nothing in this package reads a column listed in :data:`FORBIDDEN_INPUTS`.
``frame.build_matrix`` raises if one ever appears, and
``tests/test_model_inputs.py`` asserts the guard from the other side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from book import products as _products

#: The canonical six-product vocabulary, re-exported so every module in this
#: package imports its product names from one place.
PRODUCTS = _products.PRODUCTS
PRODUCT_LABEL = _products.PRODUCT_LABEL
TYPICAL_EMI = _products.TYPICAL_EMI
DECISION_WINDOW_DAYS = _products.DECISION_WINDOW_DAYS

#: Where the snapshot lives, and how the panel's month index maps to dates.
BOOK_ANCHOR = (2024, 4)

#: Contact-to-disbursement window per product, in days (plan SD-S4; the same
#: table ``validation/criteria.yaml`` registers under
#: ``label_definition.conversion_windows_days``).
WINDOW_DAYS: dict[str, int] = dict(DECISION_WINDOW_DAYS)

#: The eight suppression reasons ``journeys.campaigns`` can emit, plus the
#: "no population row at this month" sentinel the feature builder adds.
SUPPRESSION_REASONS = (
    "none", "deceased", "no_marketing_consent", "dnd", "account_dormant",
    "application_in_flight", "recent_decline", "recent_contact",
    "already_holds_product", "not_in_population",
)

# --------------------------------------------------------------------------- #
# the forbidden set
# --------------------------------------------------------------------------- #

#: Columns that exist in the tables this package reads and may **never** reach
#: the model as an input.  Three families:
#:
#: * **outcomes** — everything the label is made of, and the treatment that
#:   produced it (``contacted`` happens *after* ``as_at``: DATA_CARD 12.5).
#: * **generator truth** — latents the model is supposed to infer from noisy
#:   observables.  ``shopper_truth`` is the target of the auxiliary shopper
#:   detector and is never a feature of either model.
#: * **policy flags** — consent, DND and the suppression decision.  These gate
#:   who is *scored*, before scoring; a model that learned from them would be
#:   learning the bank's own calling rule instead of the customer's readiness.
FORBIDDEN_INPUTS: frozenset[str] = frozenset({
    # --- outcomes -------------------------------------------------------- #
    "label_disbursed_in_window", "label_product", "label_no_contact",
    "label_observed", "label_disbursed_at", "realised_recovery",
    "window_respected", "days_to_disbursement",
    "contacted", "contacted_at", "contact_channel",
    *(f"label_product_{p}" for p in PRODUCTS),
    # --- generator truth ------------------------------------------------- #
    "latent_signal", "oracle_score", "oracle_menu_hit",
    "menu_hit_with_dropoff_anchor", "p_disburse_if_contacted",
    "p_disburse_no_contact", "returns_and_completes", "return_propensity",
    "commitment", "shopper_truth", "window_shopper", "persuadable",
    "p_win_start", "p_win_end", "dormant_rich", "silent_converter",
    "red_herring", "near_miss", "substituted", "driver_product",
    "sig_strength", "ramp_start", "ramp_end", "browses", "is_converter",
    "forced_disburse", "shopper_propensity", "true_income", "inc_drift",
    "event_month", "product_canonical", "p_prod", "p_prod_canonical",
    "fee_balk_latent", "doc_shortfall_latent", "p_complete",
    # --- policy flags ---------------------------------------------------- #
    "consent", "consent_marketing", "dnd", "suppressed", "suppression_reason",
    "eligible_for_contact", "in_dropoff_pool",
})

#: Every measurement-only column is loaded under this prefix, so
#: ``set(FEATURES) & set(truth_columns)`` is empty by construction and the guard
#: cannot be defeated by a rename.
TRUTH_PREFIX = "t_"


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ModelConfig:
    """Everything the run is allowed to vary, in one object."""

    root: Path
    #: The seed whose run is packed into ``sanket_data.json``.
    seed: int = 7
    #: Every seed the headline numbers are averaged over.  ``validation/criteria.yaml``
    #: registers [7, 8, 9, 10, 11] and forbids cherry-picking; SK-20 needs >= 5.
    seeds: tuple[int, ...] = (7, 8, 9, 10, 11)
    #: Customer-grouped holdout.
    test_fraction: float = 0.30
    #: Share of the *training* customers reserved to fit the isotonic calibrators.
    calib_fraction: float = 0.25
    #: Out-of-time test = the last this-many months.
    oot_months: int = 6
    #: The contact budget both pre-registered bands are priced at (SK-01/SK-02).
    budget: float = 0.10
    #: Budgets reported beside it (SK-03).
    side_budgets: tuple[float, ...] = (0.05, 0.20)
    #: Leads written to the cockpit queue.
    queue_size: int = 320
    #: Suppressed rows carried into the export so the exclusion is visible.
    excluded_sample: int = 24
    #: Size of the product menu (mentor mandate).
    menu_k: int = 4
    #: Skip the expensive one-off exhibits (permutation retrain, ablation-ready
    #: family map, baseline ladder) — used by the fast tests.
    quick: bool = False
    #: SM-6 — read ``data/bank/pulled.json`` / ``provenance.json`` / ``fixture.json``
    #: and emit ``data/export/sanket_export.json`` in the platform's contract
    #: shape.  ``False`` (the default) is the pre-SM-6 pipeline: purely
    #: synthetic, every provenance family ``SIMULATED``.  See ``model.bank``.
    bank: bool = False

    lgbm: dict = field(default_factory=lambda: dict(
        n_estimators=600, learning_rate=0.04, num_leaves=31, min_child_samples=60,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=-1, verbose=-1,
    ))

    @property
    def data(self) -> Path:
        return self.root / "data"
