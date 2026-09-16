"""The latent intent and ramp structure of the book.

Generative direction
--------------------
Latent **intent** is the cause; the observable channels are its consequences.
A customer acquires a product-specific need, the need builds over a
product-specific run-up, and while it builds it *shows* — rent step-ups before a
home loan, a fuel surge before an auto loan, an EMI stack before a consolidation
personal loan.  ``channels.py`` renders those tells; this module decides who has
which need, when, and how loudly they express it.

Intent is exported to ``data/liability_book_truth.csv`` and is never a feature.

Product choice is two-stage
---------------------------
1. a **driver** product is drawn from the segment product mix, weighted by
   eligibility (you cannot take a loan against a property you do not own);
2. the need **manifests** as a possibly different product, drawn from the
   cross-product substitution matrix (``products.SUBSTITUTION``).  A gold-loan
   need that manifests as a personal loan is exactly why a menu of four beats a
   single next-best-product, and it is the data structure SD-S5 will score
   against.  Roughly a fifth of intents manifest as a substitute.

The legacy preset keeps the pre-SD-S1 behaviour: three products, no
substitution, a flat 4-8 month ramp, and the old age gate on home loans.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import BookConfig, substream
from .hard_negatives import Archetypes
from .population import Population
from .products import RAMP_MONTHS, SUBSTITUTION_SHARPNESS, mix_matrix, substitution_matrix

#: Weight multipliers applied to the segment product mix before sampling. A hard
#: 0.0 marks an impossible state (no property -> no loan against property).
#: All ``assumed``.
ELIGIBILITY_RULES = """
home       x0.25 if the customer already owns property; x0.35 outside age 24-48
lap        x0.00 unless the customer owns property
gold       x0.00 unless the customer holds gold
auto       x0.30 if an auto EMI is already running
education  x0.15 if no dependants and age > 35
personal   always eligible
"""

#: Shadow intent on a substitute product, as a fraction of the manifest ramp.
#: Keeps the truth file honest: a customer shopping for a gold loan carries real
#: (smaller) personal-loan intent at the same time. ``assumed``.
SHADOW_INTENT_WEIGHT = 0.6
#: Window shoppers are genuinely interested; they just never act. ``assumed``.
WINDOW_SHOPPER_INTENT = (0.20, 0.40)
#: Red herrings carry sub-threshold ambivalence, higher if a call would convert
#: them (that is what makes them persuadable rather than lost causes). ``assumed``.
RED_HERRING_INTENT = (0.05, 0.15)
RED_HERRING_INTENT_PERSUADABLE = (0.15, 0.32)
#: Baseline product curiosity everyone carries. ``assumed``.
BASE_PROPENSITY = 0.02


@dataclass
class Latents:
    """Latent structure; ``(N,)`` unless noted."""

    driver_prod: np.ndarray        # index of the underlying need (-1 = none)
    manifest_prod: np.ndarray      # index of the product actually taken (-1 = none)
    substituted: np.ndarray        # bool — manifest differs from driver
    event_month: np.ndarray        # disbursement month (-1 = never converts)
    ramp_start: np.ndarray         # first month of the observable run-up (-1 = none)
    ramp_end: np.ndarray           # month the run-up resolves (event, or fake event)
    ramp_prod: np.ndarray          # product whose tells are expressed during the ramp
    sig_strength: np.ndarray       # copy of the archetype signal strength

    in_ramp: np.ndarray            # (N, M) bool
    k: np.ndarray                  # (N, M) raw ramp progress, 0 -> 1
    ks: np.ndarray                 # (N, M) strength-scaled ramp progress, 0 -> s
    intent: np.ndarray             # (N, P, M) float32, latent intent per product

    pw_start: np.ndarray           # persuasion window (uplift ground truth)
    pw_end: np.ndarray
    pw_prod: np.ndarray            # product name string ('' when not persuadable)


def _sample_rows(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    """Vectorised categorical sampling with a different weight row per customer."""
    c = np.cumsum(weights, axis=1)
    u = rng.random(len(weights)) * c[:, -1]
    return (c < u[:, None]).sum(axis=1).clip(0, weights.shape[1] - 1)


def eligibility(cfg: BookConfig, pop: Population) -> np.ndarray:
    """``(N, P)`` multiplicative eligibility weights for the configured products."""
    n = cfg.n
    w = np.ones((n, cfg.n_products), dtype=np.float64)
    idx = {p: i for i, p in enumerate(cfg.products)}

    if cfg.preset == "legacy":
        # the pre-SD-S1 rule: home buyers skew 26-42 (applied post-hoc back then,
        # as a 70% re-roll; folded into the sampling weight here)
        w[:, idx["home"]] *= np.where((pop.age >= 26) & (pop.age <= 42), 1.0, 0.30)
        return w

    w[:, idx["home"]] *= np.where(pop.owns_property, 0.25, 1.0)
    w[:, idx["home"]] *= np.where((pop.age >= 24) & (pop.age <= 48), 1.0, 0.35)
    w[:, idx["lap"]] *= pop.owns_property.astype(float)
    w[:, idx["gold"]] *= (pop.gold_holding_g > 0).astype(float)
    w[:, idx["auto"]] *= np.where(pop.has_auto_emi, 0.30, 1.0)
    w[:, idx["education"]] *= np.where((pop.dependants == 0) & (pop.age > 35), 0.15, 1.0)
    return w


def _ramp_length(cfg: BookConfig, rng: np.random.Generator, prod: np.ndarray) -> np.ndarray:
    """Months of run-up before the event, per customer, by manifest product."""
    n = len(prod)
    if cfg.preset == "legacy":
        return rng.integers(4, 9, n)
    lo = np.array([RAMP_MONTHS[p][0] for p in cfg.products])
    hi = np.array([RAMP_MONTHS[p][1] for p in cfg.products])
    safe = prod.clip(0)
    span = hi[safe] - lo[safe]
    return lo[safe] + (rng.random(n) * span).astype(int)


def build_latents(cfg: BookConfig, pop: Population, arche: Archetypes) -> Latents:
    """Assign products, event months, ramps and the latent intent tensor."""
    rng = substream(cfg.seed, "latent")
    n, m_n, p_n = cfg.n, cfg.months, cfg.n_products
    months = np.arange(m_n)

    elig = eligibility(cfg, pop)
    mix = mix_matrix(("salaried", "self-employed", "gig"), cfg.products)
    base_w = mix[pop.seg_idx] * elig

    # ---- stage 1: the underlying need ------------------------------------- #
    driver_prod = np.where(arche.is_converter, _sample_rows(rng, base_w), -1)

    # ---- stage 2: which product the need manifests as ---------------------- #
    sub = substitution_matrix(cfg.products) ** SUBSTITUTION_SHARPNESS
    if cfg.preset == "legacy":
        manifest_prod = driver_prod.copy()               # no substitution pre-SD-S1
    else:
        man_w = sub[driver_prod.clip(0)] * elig
        manifest_prod = np.where(arche.is_converter, _sample_rows(rng, man_w), -1)
    substituted = (manifest_prod >= 0) & (manifest_prod != driver_prod)

    # ---- event month and run-up ------------------------------------------- #
    first = cfg.base_rates.first_event_month
    event_month = np.where(arche.is_converter, rng.integers(first, m_n, n), -1)

    # Near-misses behave exactly like ramping converters and then do not buy, so
    # they get a *fake* event whose ramp is fully expressed but never resolves.
    if cfg.preset == "legacy":
        nm_prod = rng.integers(0, p_n, n)                # uniform, as before
    else:
        nm_prod = _sample_rows(rng, base_w)
    fake_ev = rng.integers(min(12, m_n - 1), m_n, n)
    nm_strength = rng.uniform(0.4, 1.0, n)

    ramp_prod = np.where(arche.near_miss, nm_prod, manifest_prod)
    sig = np.where(arche.near_miss, nm_strength, arche.sig_strength)
    ramp_end = np.where(arche.near_miss, fake_ev, event_month)
    ramp_len = _ramp_length(cfg, rng, ramp_prod)
    has_ramp = (ramp_end >= 0) & (sig > 0)
    ramp_start = np.where(has_ramp, np.maximum(ramp_end - ramp_len, 0), -1)

    # ---- (N, M) ramp progress --------------------------------------------- #
    in_ramp = (ramp_start[:, None] >= 0) & (months[None, :] >= ramp_start[:, None]) \
              & (months[None, :] < ramp_end[:, None])
    span = np.maximum(1, ramp_end - ramp_start)[:, None]
    k = np.where(in_ramp, (months[None, :] - ramp_start[:, None]) / span, 0.0)
    ks = (k * sig[:, None]).astype(np.float64)

    # ---- latent intent tensor (N, P, M) ------------------------------------ #
    # base curiosity, scaled by eligibility so impossible products stay at zero
    intent = (BASE_PROPENSITY * elig / elig.max(axis=1, keepdims=True).clip(1e-9))
    intent = np.repeat(intent[:, :, None], m_n, axis=2).astype(np.float32)

    # the ramp itself, plus shadow intent smeared across substitutes
    shadow = sub[ramp_prod.clip(0)] * SHADOW_INTENT_WEIGHT
    shadow[np.arange(n), ramp_prod.clip(0)] = 1.0
    shadow *= (ramp_prod >= 0)[:, None]
    intent += (shadow[:, :, None] * ks[:, None, :]).astype(np.float32)

    rows = np.arange(n)[:, None]
    mcol = months[None, :]

    # window shoppers: real interest, no action
    ws_mask = (arche.ws_start[:, None] >= 0) & (mcol >= arche.ws_start[:, None]) \
              & (mcol < arche.ws_start[:, None] + 4)
    ws_amp = rng.uniform(*WINDOW_SHOPPER_INTENT, n)[:, None] * ws_mask
    np.add.at(intent, (rows, arche.ws_prod.clip(0)[:, None], mcol), ws_amp.astype(np.float32))

    # red herrings: sub-threshold ambivalence behind a real financial run-up
    rh_mask = (arche.rh_start[:, None] >= 0) & (mcol >= arche.rh_start[:, None]) \
              & (mcol < (arche.rh_start + arche.rh_len)[:, None])
    rh_lo, rh_hi = np.where(arche.persuadable, RED_HERRING_INTENT_PERSUADABLE[0], RED_HERRING_INTENT[0]), \
                   np.where(arche.persuadable, RED_HERRING_INTENT_PERSUADABLE[1], RED_HERRING_INTENT[1])
    rh_amp = (rh_lo + rng.random(n) * (rh_hi - rh_lo))[:, None] * rh_mask
    np.add.at(intent, (rows, arche.rh_prod.clip(0)[:, None], mcol), rh_amp.astype(np.float32))

    np.clip(intent, 0.0, 1.0, out=intent)

    # ---- uplift ground truth: the window in which a call converts ---------- #
    # Unchanged from the pre-SD-S1 book: near-misses are winnable throughout
    # their ramp, red herrings throughout their financial run-up.
    pw_start = np.full(n, -1)
    pw_end = np.full(n, -1)
    pw_prod_idx = np.full(n, -1)
    nm_p = arche.persuadable & arche.near_miss
    rh_p = arche.persuadable & arche.red_herring & ~arche.near_miss
    pw_start[nm_p], pw_end[nm_p], pw_prod_idx[nm_p] = ramp_start[nm_p], ramp_end[nm_p], ramp_prod[nm_p]
    pw_start[rh_p] = arche.rh_start[rh_p]
    pw_end[rh_p] = (arche.rh_start + arche.rh_len)[rh_p]
    pw_prod_idx[rh_p] = arche.rh_prod[rh_p]

    names = np.array(list(cfg.products) + [""], dtype=object)
    pw_prod = names[np.where(pw_prod_idx >= 0, pw_prod_idx, p_n)]

    return Latents(
        driver_prod=driver_prod, manifest_prod=manifest_prod, substituted=substituted,
        event_month=event_month, ramp_start=ramp_start, ramp_end=ramp_end, ramp_prod=ramp_prod,
        sig_strength=sig, in_ramp=in_ramp, k=k.astype(np.float32), ks=ks, intent=intent,
        pw_start=pw_start, pw_end=pw_end, pw_prod=pw_prod,
    )
