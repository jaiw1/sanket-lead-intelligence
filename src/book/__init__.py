"""SANKET synthetic liability-book generator — vectorised.

The generator produces three artefacts:

``data/customer_panel.csv``
    one row per customer-month; the observable channels a bank actually sees.
``data/customer_book.csv``
    one row per customer; static attributes plus the archetype / uplift ground
    truth that ``score_and_pack.py`` already consumes for measurement.
``data/liability_book_truth.csv``
    one row per customer-month; the **latent** intent and capacity processes.
    Never shipped to the app and never a model feature — it exists so SD-S2
    (journeys) and the validation lane can grade against the generative truth.

Modules
-------
``products``        vocabulary, per-product parameters, substitution matrix
``population``      static per-customer attributes
``hard_negatives``  archetypes (window-shopper / red-herring / near-miss /
                    dormant-rich / silent converter) and the uplift truth
``latent``          latent intent ``(N, P, M)`` and the ramp windows
``channels``        monthly observation channels ``(N, M)`` + the capacity process
``build``           CLI entry point; assembles and writes the CSVs

Design note — why this is fast
------------------------------
Everything is vectorised **across customers**.  The only loop is over months
(30 iterations), which is unavoidable because the balance path is a recursive
state machine: this month's closing balance is next month's opening balance.
Each iteration is a handful of ``(N,)`` numpy ops, so 60,000 x 30 costs about a
second instead of the ten minutes a per-row loop would take.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import numpy as np

from .products import LEGACY_PRODUCTS, PRODUCTS

__all__ = ["BookConfig", "BaseRates", "substream", "month_label", "SEGMENTS", "SEGMENT_P"]

SEGMENTS: Final[tuple[str, ...]] = ("salaried", "self-employed", "gig")

#: Share of the liability book by employment segment.  PLFS 2023-24 puts regular
#: wage/salaried employment near 21% of all workers nationally, but a *bank
#: savings-account* book skews heavily salaried because that is who gets a salary
#: account opened for them.  The 60/25/15 split is ``assumed``.
SEGMENT_P: Final[tuple[float, ...]] = (0.60, 0.25, 0.15)

#: Named RNG substreams.  Each block of the generator draws from its own stream
#: so that adding a channel never shifts the numbers produced by another block.
_STREAM_ID: Final[dict[str, int]] = {
    "population": 1,
    "archetypes": 2,
    "products": 3,
    "latent": 4,
    "channels": 5,
    "market": 6,
}


def substream(seed: int, name: str) -> np.random.Generator:
    """Return the independent generator for named block ``name``.

    Streams are derived from ``(seed, stream_id)`` rather than consumed in
    sequence, so a change in one module cannot perturb another module's draws.
    """
    if name not in _STREAM_ID:
        raise KeyError(f"unknown RNG substream {name!r}; known: {sorted(_STREAM_ID)}")
    return np.random.default_rng([seed, _STREAM_ID[name]])


@dataclass(frozen=True)
class BaseRates:
    """Hooks SD-S4 will solve against when it fits the contact effect theta.

    ``target_contact_conversion_3m`` is today's semantics: the share of the book
    that disburses within three months of a *random* contact at the snapshot
    month.  The generator back-solves :meth:`converter_share` from it rather than
    hard-coding 8.5%, so changing the target moves the whole book coherently.
    """

    #: bank-stated cold-calling baseline, reproduced by the monthly label
    target_contact_conversion_3m: float = 0.0135
    #: first month an event may land (a run-up needs history in front of it)
    first_event_month: int = 9
    #: label horizon in months; ``score_and_pack`` uses (m, m+3]
    label_horizon_months: int = 3
    #: contact effect. ``None`` = not yet solved; SD-S4 fills this in.
    theta_contact_effect: float | None = None

    def converter_share(self, months: int) -> float:
        """Share of the book that eventually converts, for a book of ``months``.

        Events are uniform over ``[first_event_month, months)``, so the share of
        customers whose event falls in a given three-month window is
        ``converter_share * horizon / n_event_months``.  Invert that.
        """
        n_event_months = months - self.first_event_month
        if n_event_months < self.label_horizon_months:
            raise ValueError(f"need at least {self.first_event_month + self.label_horizon_months} months")
        share = self.target_contact_conversion_3m * n_event_months / self.label_horizon_months
        return float(np.clip(share, 0.0, 0.5))


@dataclass(frozen=True)
class BookConfig:
    """Everything the generator needs to produce a reproducible book."""

    n: int = 60_000
    months: int = 30
    seed: int = 20260709
    #: ``"modern"`` = six products + seasonality + the richer channels.
    #: ``"legacy"`` = the pre-SD-S1 world (three products, no seasonality, no new
    #: channel feeding the balance path) used for equivalence testing.
    preset: str = "modern"
    out_dir: Path = field(default_factory=lambda: Path("data"))
    #: calendar (year, month) of panel month 0
    anchor: tuple[int, int] = (2024, 4)
    base_rates: BaseRates = field(default_factory=BaseRates)
    #: marketing-consent share.  ``assumed``; DPDP makes this a live join in prod.
    consent_share: float = 0.85

    # ---------------------------------------------------------------- presets #
    @classmethod
    def legacy(cls, seed: int = 20260709, out_dir: Path | None = None) -> "BookConfig":
        """The pre-SD-S1 book: 15,000 customers x 27 months, three products."""
        return cls(
            n=15_000, months=27, seed=seed, preset="legacy",
            out_dir=out_dir if out_dir is not None else Path("data"),
            anchor=(2023, 5),
            base_rates=BaseRates(target_contact_conversion_3m=0.0135),
        )

    # ------------------------------------------------------------- properties #
    @property
    def products(self) -> tuple[str, ...]:
        return LEGACY_PRODUCTS if self.preset == "legacy" else PRODUCTS

    @property
    def n_products(self) -> int:
        return len(self.products)

    @property
    def snapshot_month(self) -> int:
        """"Today" in the cockpit; the trailing months are the measured future."""
        return self.months - self.base_rates.label_horizon_months - 1

    @property
    def seasonality(self) -> bool:
        """Fee season / festive / FY-end effects (modern preset only)."""
        return self.preset != "legacy"

    @property
    def new_channels_move_balance(self) -> bool:
        """Whether insurance, min-balance charges and bonus credits hit the
        balance recursion.  Off in the legacy preset so the legacy balance path
        stays distributionally identical to the pre-SD-S1 loop."""
        return self.preset != "legacy"

    def __post_init__(self) -> None:
        if self.preset not in ("modern", "legacy"):
            raise ValueError(f"unknown preset {self.preset!r}")
        if self.months < self.base_rates.first_event_month + self.base_rates.label_horizon_months + 1:
            raise ValueError(f"months={self.months} is too short for the label horizon")
        if self.n < 100:
            raise ValueError("n must be at least 100")

    def calendar_months(self) -> np.ndarray:
        """``(M,)`` calendar month-of-year (1..12) for each panel month."""
        y0, m0 = self.anchor
        return ((m0 - 1 + np.arange(self.months)) % 12) + 1

    def month_labels(self) -> list[str]:
        return [month_label(i, self.anchor) for i in range(self.months)]


def month_label(i: int, anchor: tuple[int, int] = (2023, 5)) -> str:
    """``YYYY-MM`` label for panel month ``i``."""
    y0, m0 = anchor
    y, m = divmod(m0 - 1 + i, 12)
    return f"{y0 + y}-{m + 1:02d}"
