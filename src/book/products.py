"""Product vocabulary, per-product behaviour parameters and the cross-product
substitution / affinity matrix for the SANKET synthetic liability book.

Vocabulary
----------
The canonical six-product vocabulary is ``home, lap, gold, auto, education,
personal``.  The pre-SD-S1 book carried three products ``home, auto, pl``;
``pl`` is an alias of ``personal`` and nothing else changed.

``score_and_pack.py`` is frozen until SM-1 and still reads the three-product
spelling, so the generator writes *both* vocabularies to disk:

* ``product``            — compat spelling (``personal`` written as ``pl``)
* ``product_canonical``  — the six-product canonical spelling
* ``dwell_pl``           — compat duplicate of ``dwell_personal``

:data:`COMPAT_SPELLING` / :data:`CANONICAL_SPELLING` are that alias map.  Both
the extra column and the duplicate dwell series disappear at SM-1.

Every numeric parameter in this module is ``assumed`` unless its docstring
names a source; see ``DATA_CARD.md`` for the sourced-vs-assumed table.
"""

from __future__ import annotations

from typing import Final

import numpy as np

# --------------------------------------------------------------------------- #
# vocabulary
# --------------------------------------------------------------------------- #

PRODUCTS: Final[tuple[str, ...]] = ("home", "lap", "gold", "auto", "education", "personal")
LEGACY_PRODUCTS: Final[tuple[str, ...]] = ("home", "auto", "personal")

#: canonical name -> spelling written to the CSVs for the frozen scorer
COMPAT_SPELLING: Final[dict[str, str]] = {"personal": "pl"}
#: on-disk spelling -> canonical name
CANONICAL_SPELLING: Final[dict[str, str]] = {"pl": "personal"}

PRODUCT_INDEX: Final[dict[str, int]] = {p: i for i, p in enumerate(PRODUCTS)}

PRODUCT_LABEL: Final[dict[str, str]] = {
    "home": "Home loan",
    "lap": "Loan against property",
    "gold": "Gold loan",
    "auto": "Auto loan",
    "education": "Education loan",
    "personal": "Personal loan",
}


def to_compat(name: str) -> str:
    """Canonical product name -> the spelling written to the CSVs."""
    return COMPAT_SPELLING.get(name, name)


def to_canonical(name: str) -> str:
    """On-disk product spelling -> the canonical product name."""
    return CANONICAL_SPELLING.get(name, name)


# --------------------------------------------------------------------------- #
# per-product parameters
# --------------------------------------------------------------------------- #

#: Months of observable run-up before the disbursement event, (low, high_exclusive).
#: Short-fuse products (gold, personal) decide in weeks; property-backed ones
#: take a season.  Ordering mirrors the SD-S4 decision windows below. ``assumed``.
RAMP_MONTHS: Final[dict[str, tuple[int, int]]] = {
    "home": (5, 10),
    "lap": (4, 9),
    "gold": (1, 4),
    "auto": (3, 7),
    "education": (3, 7),
    "personal": (2, 6),
}

#: Contact-to-disbursement decision window in days (plan §B/L6 SD-S4).  Carried
#: here so SD-S2/SD-S4 read one table; unused by the generator today.
DECISION_WINDOW_DAYS: Final[dict[str, int]] = {
    "personal": 1, "gold": 1, "auto": 3, "education": 7, "home": 14, "lap": 14,
}

#: Indicative EMI on a typical ticket, used only for documentation and for the
#: capacity narrative.  ``assumed`` (anchored on prevailing retail rates).
TYPICAL_EMI: Final[dict[str, int]] = {
    "home": 26_000, "lap": 19_000, "gold": 6_500,
    "auto": 12_500, "education": 9_500, "personal": 8_500,
}

#: Product mix among converters, by segment (count shares, not value shares).
#: Shaped by RBI *Sectoral Deployment of Bank Credit* — within personal loans,
#: housing dominates by value while gold and other-personal dominate by account
#: count — but the segment split itself is ``assumed``.
PRODUCT_MIX: Final[dict[str, dict[str, float]]] = {
    "salaried":      {"home": 0.22, "lap": 0.06, "gold": 0.08, "auto": 0.18, "education": 0.10, "personal": 0.36},
    "self-employed": {"home": 0.18, "lap": 0.14, "gold": 0.18, "auto": 0.16, "education": 0.06, "personal": 0.28},
    "gig":           {"home": 0.05, "lap": 0.03, "gold": 0.26, "auto": 0.16, "education": 0.04, "personal": 0.46},
}

#: The pre-SD-S1 three-product mix, kept verbatim so ``--legacy-size`` reproduces
#: the old book.  ``pl`` is spelled canonically here.
LEGACY_PRODUCT_MIX: Final[dict[str, dict[str, float]]] = {
    "salaried":      {"home": 0.34, "auto": 0.30, "personal": 0.36},
    "self-employed": {"home": 0.28, "auto": 0.34, "personal": 0.38},
    "gig":           {"home": 0.10, "auto": 0.28, "personal": 0.62},
}

# --------------------------------------------------------------------------- #
# cross-product substitution matrix (plan SD-S5, data structure only)
# --------------------------------------------------------------------------- #

#: Symmetric affinity between products in [0, 1].  A high value means a customer
#: whose latent need is product A frequently *takes* product B instead — the
#: reason a "next best product" menu of four beats a single recommendation.
#:
#: Every value is ``assumed``.  The ordering is the defensible part:
#:   gold <-> personal   both are short-tenor liquidity; gold wins on rate, PL on
#:                       speed and on not pledging jewellery
#:   home <-> lap        both property-backed; an owner refinances rather than buys
#:   auto <-> personal   an unsecured PL funds the down payment or the whole car
#:   education <-> pers. fees get funded by whatever disburses before the deadline
#:   gold <-> education  gold loans against jewellery are a common fee-season bridge
SUBSTITUTION_PAIRS: Final[dict[tuple[str, str], float]] = {
    ("gold", "personal"): 0.70,
    ("home", "lap"): 0.65,
    ("auto", "personal"): 0.45,
    ("education", "personal"): 0.45,
    ("gold", "education"): 0.35,
    ("lap", "personal"): 0.35,
    ("lap", "education"): 0.30,
    ("lap", "gold"): 0.25,
    ("home", "personal"): 0.20,
    ("auto", "gold"): 0.20,
    ("home", "auto"): 0.15,
    ("lap", "auto"): 0.15,
    ("home", "education"): 0.12,
    ("auto", "education"): 0.12,
    ("home", "gold"): 0.10,
}

#: How sharply the substitution matrix is peaked when sampling which product a
#: latent intent actually manifests as: weights are ``SUBSTITUTION ** SHARPNESS``.
#: 4.0 leaves ~20% of intents manifesting as a substitute. ``assumed``.
SUBSTITUTION_SHARPNESS: Final[float] = 4.0


def substitution_matrix(products: tuple[str, ...] = PRODUCTS) -> np.ndarray:
    """Return the symmetric ``len(products)`` square affinity matrix (diag 1.0)."""
    n = len(products)
    m = np.eye(n, dtype=np.float64)
    idx = {p: i for i, p in enumerate(products)}
    for (a, b), v in SUBSTITUTION_PAIRS.items():
        if a in idx and b in idx:
            m[idx[a], idx[b]] = m[idx[b], idx[a]] = v
    return m


SUBSTITUTION: Final[np.ndarray] = substitution_matrix()


def mix_matrix(segments: tuple[str, ...], products: tuple[str, ...]) -> np.ndarray:
    """``(len(segments), len(products))`` row-normalised converter product mix.

    Falls back to the three-product legacy table when ``products`` is the legacy
    triple, so ``--legacy-size`` keeps the old mix exactly.
    """
    table = LEGACY_PRODUCT_MIX if set(products) == set(LEGACY_PRODUCTS) else PRODUCT_MIX
    m = np.array([[table[s].get(p, 0.0) for p in products] for s in segments], dtype=np.float64)
    return m / m.sum(axis=1, keepdims=True)
