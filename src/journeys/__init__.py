"""SANKET application-journey layer — the drop-off population.

Why this package exists
-----------------------
The mentors' mandate is blunt: **conversion means disbursement, not lead
creation**, and *the population that matters is the drop-offs* — customers who
started an application and did not finish it.  The liability book
(:mod:`book`) knows only *who* eventually disburses and *when*; it has no
application, no stages, no fee, no document request and therefore no drop-off.
This package adds that layer.

Grain
-----
``data/journeys.csv``
    one row per **application attempt**.  A customer may have several over the
    panel: they abandon, they come back, and (a minority) they finish.
``data/journey_events.csv``
    one row per **stage transition**, with a timestamp.  This is the table the
    point-in-time feature builder reads, because it is the only place that says
    *when* each thing became knowable.
``data/journey_truth.csv``
    one row per attempt of **latent** drivers — window-shopper truth, the
    hazard's own predicted completion, the intent and capacity the attempt was
    launched on.  Never a feature.  Graded against, never trained on.

The funnel
----------
Eight stages, seven gates between them::

    start -> eligibility -> kyc -> docs -> fee (Rs 1,000) -> offer -> accept -> disburse
          g0            g1     g2      g3            g4         g5        g6

At each gate the attempt advances with probability

    P(advance) = sigmoid(alpha_stage + beta*intent + gamma*capacity
                         + delta*friction_stage + product_effect + channel_effect)

and otherwise **times out** at that stage: it sits there for a per-stage number
of days and the file is closed.  ``last_stage`` is where it stopped, which is
exactly the ``stage_reached`` cut the validation lane pre-registered.

Consistency with the book is a hard constraint
----------------------------------------------
The book is read-only ground truth.  A customer the book says converts at month
``e`` with product ``p`` **must** have an attempt for ``p`` that disburses in
month ``e``; a customer the book says never converts **must never** disburse.
So the journey layer does not re-decide the outcome — it samples a *path*
consistent with it.  For an attempt that is going to abandon, the abandonment
stage is drawn from the hazard model conditioned on not disbursing,

    P(abandon at s | attempt does not disburse)
        = [prod_{j<s} p_j * (1 - p_s)] / (1 - prod_j p_j)

which is the honest Bayes conditioning, not a re-roll.  The stage intercepts
``alpha_s`` are then *solved* (not hand-set) so the realised abandonment shares
match the funnel shape documented in ``DATA_CARD.md`` §11.

Modules
-------
``bookview``   read-only view of the book, the truth file and panel dwell
``shoppers``   the window-shopper latent (SD-S3)
``attempts``   who applies, when, for what, through which channel, saying what
``funnel``     the hazard, the sampled path, durations, timestamps, events
``features``   point-in-time-safe per-customer aggregation for L7 / SM-3
``build``      CLI entry point, assembly and the in-script assertions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import numpy as np

__all__ = [
    "STAGES", "STAGE_INDEX", "STAGE_LABEL", "N_GATES", "CHANNELS",
    "JourneyConfig", "substream", "ROOT",
]

ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The eight funnel stages, lowercase on disk.  The spelling matches
#: ``data/bank/fixture.json`` (``journey_stage_reached``), which is the platform
#: contract; ``validation/criteria.yaml`` writes the same eight capitalised for
#: display.  :data:`STAGE_LABEL` is that mapping.
STAGES: Final[tuple[str, ...]] = (
    "start", "eligibility", "kyc", "docs", "fee", "offer", "accept", "disburse",
)
STAGE_INDEX: Final[dict[str, int]] = {s: i for i, s in enumerate(STAGES)}
STAGE_LABEL: Final[dict[str, str]] = {
    "start": "Start", "eligibility": "Eligibility", "kyc": "KYC", "docs": "Docs",
    "fee": "Fee", "offer": "Offer", "accept": "Accept", "disburse": "Disburse",
}
#: Seven gates: gate ``s`` is the transition out of ``STAGES[s]``.
N_GATES: Final[int] = len(STAGES) - 1

#: Acquisition channels.  ``dsa`` = direct selling agent.
CHANNELS: Final[tuple[str, ...]] = ("branch-walk-in", "rm-call", "app", "web", "dsa")

#: Named RNG substreams.  Offset from the book's ids (1-6) so a journey stream
#: can never collide with a book stream at the same seed.
_STREAM_ID: Final[dict[str, int]] = {
    "shoppers": 101,
    "applicants": 102,
    "attempts": 103,
    "signals": 104,
    "funnel": 105,
    "timing": 106,
}


def substream(seed: int, name: str) -> np.random.Generator:
    """Return the independent generator for named block ``name``."""
    if name not in _STREAM_ID:
        raise KeyError(f"unknown RNG substream {name!r}; known: {sorted(_STREAM_ID)}")
    return np.random.default_rng([seed, _STREAM_ID[name]])


@dataclass(frozen=True)
class JourneyConfig:
    """Everything the journey generator needs, and every tuning target it hits.

    The three ``target_*`` fields are not descriptions of the output — they are
    *solved for*.  ``build.check()`` re-measures each of them on the realised
    data and fails the run if the solver drifted.
    """

    #: where ``customer_book.csv`` / ``liability_book_truth.csv`` /
    #: ``customer_panel.csv`` are read from
    book_dir: Path = field(default_factory=lambda: ROOT / "data")
    #: where the three journey CSVs are written
    out_dir: Path = field(default_factory=lambda: ROOT / "data")
    seed: int = 20260709

    # ---- volume targets --------------------------------------------------- #
    #: share of book customers with at least one application attempt over the
    #: panel.  Plan §B/L6 SD-S2: 25-35%.  ``assumed``.
    target_attempt_share: float = 0.30
    #: **The 8-10% baseline.**  Share of customers who abandoned an application
    #: and later disbursed anyway — i.e. of 100 drop-offs an RM works at random,
    #: how many end in a disbursement.  Mentor-stated; see DATA_CARD §11.3 for
    #: why this, and not the whole-book contact rate, is the right denominator.
    target_recovery_rate: float = 0.09
    #: share of *abandoned attempts* whose customer is a true window-shopper.
    #: Plan §B/L6 SD-S3: ~30%.  ``assumed``.
    target_shopper_share_of_dropoffs: float = 0.30

    #: earliest panel month an application may start (needs a prior month of
    #: browsing history in front of it for the 30-day look-back).  ``assumed``.
    first_attempt_month: int = 6
    #: share of attempts launched for a product the customer's eligibility
    #: latent rules out entirely (no property -> LAP, no gold -> gold loan).
    #: Real banks receive these; they die at the Eligibility stage.  ``assumed``.
    ineligible_noise_share: float = 0.02

    def __post_init__(self) -> None:
        if not 0.10 <= self.target_attempt_share <= 0.60:
            raise ValueError("target_attempt_share outside a sane range")
        if not 0.0 < self.target_recovery_rate < 0.5:
            raise ValueError("target_recovery_rate outside a sane range")
        if not 0.0 <= self.ineligible_noise_share < 0.2:
            raise ValueError("ineligible_noise_share outside a sane range")
