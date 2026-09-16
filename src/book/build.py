"""CLI entry point: assemble and write the SANKET synthetic liability book.

    python3 src/make_book.py                       # 60,000 customers x 30 months, 6 products
    python3 src/make_book.py --legacy-size         # the pre-SD-S1 book, for equivalence testing
    python3 src/make_book.py --n 5000 --months 24  # anything else
    python3 src/make_book.py --seed 7 --out /tmp/book

Outputs (into ``--out``, default ``data/``)

``customer_panel.csv``       one row per customer-month — the observable channels
``customer_book.csv``        one row per customer — statics + archetype/uplift truth
``liability_book_truth.csv`` one row per customer-month — the **latent** intent and
                             capacity processes.  Never shipped to the app, never a
                             model feature; SD-S2 and the validation lane read it.

Compatibility shim
------------------
``score_and_pack.py`` is frozen until SM-1 and still speaks the three-product
vocabulary, so ``product`` and ``p_prod`` are written in the compat spelling
(``personal`` -> ``pl``) and ``dwell_pl`` duplicates ``dwell_personal``.  The
canonical six-product labels live beside them in ``product_canonical`` /
``p_prod_canonical``.  Both shims go away at SM-1.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import BaseRates, BookConfig
from .channels import build_channels
from .hard_negatives import assign_archetypes
from .latent import build_latents
from .population import build_population
from .products import to_compat

ROOT = Path(__file__).resolve().parents[2]

#: Column order of the pre-SD-S1 panel.  Held first and unchanged so the old
#: schema is a strict prefix of the new one.
LEGACY_PANEL_COLUMNS = [
    "cust_id", "month", "date", "credits", "bal_avg", "bal_min", "rent", "fuel_cab",
    "school_fees", "ecommerce", "ext_emi", "has_auto_emi", "fd_bal",
    "dwell_home", "dwell_auto", "dwell_pl",
]
#: Column order of the pre-SD-S1 book.
LEGACY_BOOK_COLUMNS = [
    "cust_id", "segment", "age", "city_tier", "tenure_m", "consent", "product", "event_month",
    "window_shopper", "dormant_rich", "dnd", "persuadable", "p_win_start", "p_win_end", "p_prod",
    "true_income", "inc_drift",
]

#: Monthly columns written as rupee integers, matching the pre-SD-S1 rounding.
_MONEY_COLUMNS = [
    "credits", "bal_avg", "bal_min", "rent", "fuel_cab", "school_fees", "ecommerce",
    "ext_emi", "fd_bal", "upi_p2m_value", "emi_outflow_to_other_bank", "card_spend",
    "insurance_premium", "bonus_or_irregular_credit",
]
_COUNT_COLUMNS = [
    "upi_p2m_count", "salary_credit_day", "salary_credit_source_count",
    "external_emi_count", "mandate_failure_count",
]
_FLAG_COLUMNS = [
    "min_balance_charge_flag", "fd_premature_closure_flag", "address_change_flag",
    "nominee_change_flag",
]


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def build_frames(cfg: BookConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate the book and return ``(panel, book, truth)``."""
    pop = build_population(cfg)
    arche = assign_archetypes(cfg, pop)
    lat = build_latents(cfg, pop, arche)
    ch = build_channels(cfg, pop, arche, lat)

    n, m_n = cfg.n, cfg.months
    labels = cfg.month_labels()

    # ---- panel ------------------------------------------------------------- #
    panel: dict[str, np.ndarray] = {
        "cust_id": np.repeat(pop.cust_id, m_n),
        "month": np.tile(np.arange(m_n, dtype=np.int16), n),
        "date": np.tile(np.array(labels, dtype=object), n),
    }
    for c in _MONEY_COLUMNS:
        panel[c] = ch.monthly[c].round().astype(np.int32).ravel()
    panel["has_auto_emi"] = np.repeat(pop.has_auto_emi.astype(np.int8), m_n)
    for p in cfg.products:
        panel[f"dwell_{p}"] = ch.dwell[p].round(1).ravel()
    panel["dwell_pl"] = panel["dwell_personal"]        # compat duplicate, dropped at SM-1
    for c in _COUNT_COLUMNS:
        panel[c] = ch.monthly[c].round().astype(np.int16).ravel()
    for c in _FLAG_COLUMNS:
        panel[c] = ch.monthly[c].astype(np.int8).ravel()

    ordered = LEGACY_PANEL_COLUMNS + [c for c in panel if c not in LEGACY_PANEL_COLUMNS]
    panel_df = pd.DataFrame({c: panel[c] for c in ordered})

    # ---- book -------------------------------------------------------------- #
    names = np.array(list(cfg.products) + [""], dtype=object)
    manifest = names[np.where(lat.manifest_prod >= 0, lat.manifest_prod, cfg.n_products)]
    driver = names[np.where(lat.driver_prod >= 0, lat.driver_prod, cfg.n_products)]
    compat = np.vectorize(to_compat, otypes=[object])

    book_df = pd.DataFrame({
        "cust_id": pop.cust_id,
        "segment": pop.segment, "age": pop.age, "city_tier": pop.city_tier,
        "tenure_m": pop.tenure_m, "consent": pop.consent.astype(np.int8),
        "product": compat(manifest), "event_month": lat.event_month,
        "window_shopper": arche.window_shopper.astype(np.int8),
        "dormant_rich": arche.dormant_rich.astype(np.int8),
        "dnd": arche.dnd.astype(np.int8), "persuadable": arche.persuadable.astype(np.int8),
        "p_win_start": lat.pw_start, "p_win_end": lat.pw_end, "p_prod": compat(lat.pw_prod),
        "true_income": pop.base_income.round(0), "inc_drift": pop.inc_drift.round(5),
        # ---- SD-S1 additions ----
        "product_canonical": manifest, "p_prod_canonical": lat.pw_prod,
        "driver_product": driver, "substituted": lat.substituted.astype(np.int8),
        "red_herring": arche.red_herring.astype(np.int8),
        "near_miss": arche.near_miss.astype(np.int8),
        "silent_converter": arche.silent_converter.astype(np.int8),
        "browses": arche.browses.astype(np.int8),
        "sig_strength": lat.sig_strength.round(4),
        "ramp_start": lat.ramp_start, "ramp_end": lat.ramp_end,
        "has_auto_emi": pop.has_auto_emi.astype(np.int8),
        "salary_day_base": pop.salary_day_base.astype(np.int8),
        "salary_regular": pop.salary_regular.astype(np.int8),
        "salary_sources": pop.salary_sources.astype(np.int8),
        "has_card": pop.has_card.astype(np.int8),
        "has_insurance": pop.has_insurance.astype(np.int8),
        "insurance_annual": pop.insurance_annual.round(0),
        "owns_property": pop.owns_property.astype(np.int8),
        "has_home_loan": pop.has_home_loan.astype(np.int8),
        "gold_holding_g": pop.gold_holding_g.round(1),
        "dependants": pop.dependants.astype(np.int8),
        "upi_share": pop.upi_share.round(3),
        "amb_threshold": pop.amb_threshold.astype(np.int32),
        "fee_sensitivity": pop.fee_sensitivity.round(3),
        "doc_reluctance": pop.doc_reluctance.round(3),
    })
    assert list(book_df.columns[: len(LEGACY_BOOK_COLUMNS)]) == LEGACY_BOOK_COLUMNS

    # ---- truth (latents; never shipped to the app) ------------------------- #
    truth: dict[str, np.ndarray] = {
        "cust_id": panel["cust_id"], "month": panel["month"],
    }
    for i, p in enumerate(cfg.products):
        truth[f"intent_{p}"] = lat.intent[:, i, :].ravel()
    truth["capacity_abs"] = ch.capacity_abs.round(0).ravel()
    truth["capacity_ratio"] = ch.capacity_ratio.ravel()
    truth["ramp_progress"] = lat.ks.astype(np.float32).ravel()
    truth["in_ramp"] = lat.in_ramp.astype(np.int8).ravel()
    truth_df = pd.DataFrame(truth)

    return panel_df, book_df, truth_df


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def check(cfg: BookConfig, panel: pd.DataFrame, book: pd.DataFrame, truth: pd.DataFrame) -> dict[str, float]:
    """Assert the book is internally coherent; return the headline statistics."""
    snap = cfg.snapshot_month
    h = cfg.base_rates.label_horizon_months
    ev = book.event_month.values
    stats = {
        "rows": float(len(panel)),
        "converters": float((ev >= 0).mean()),
        "contact_conversion_3m": float(((ev > snap) & (ev <= snap + h)).mean()),
        "consent": float(book.consent.mean()),
        "window_shopper": float(book.window_shopper.mean()),
        "dormant_rich": float(book.dormant_rich.mean()),
        "red_herring": float(book.red_herring.mean()),
        "near_miss": float(book.near_miss.mean()),
        "persuadable": float(book.persuadable.mean()),
        "dnd": float(book.dnd.mean()),
        "substituted": float(book.substituted.mean()),
    }

    assert len(panel) == cfg.n * cfg.months, "panel is not a complete rectangle"
    assert not panel.isna().any().any(), "panel contains NaN"
    assert not book.isna().any().any(), "book contains NaN"
    assert not truth.isna().any().any(), "truth contains NaN"
    for c in LEGACY_PANEL_COLUMNS:
        assert c in panel.columns, f"legacy panel column {c} disappeared"
    for c in LEGACY_BOOK_COLUMNS:
        assert c in book.columns, f"legacy book column {c} disappeared"

    for c in _MONEY_COLUMNS:
        assert (panel[c].values >= 0).all(), f"{c} went negative"
    assert (panel.bal_avg.values >= 1_000).all(), "balance floor breached"
    assert panel.salary_credit_day.between(1, 28).all(), "impossible salary credit day"
    assert (panel.mandate_failure_count.values <= panel.external_emi_count.values).all(), \
        "more mandate failures than mandates"
    assert (panel.emi_outflow_to_other_bank.values <= panel.ext_emi.values + 1).all(), \
        "other-bank EMI exceeds total external EMI"

    # the label the scorer measures must stay near the bank-stated cold-call rate
    target = cfg.base_rates.target_contact_conversion_3m
    assert abs(stats["contact_conversion_3m"] - target) < 0.006, (
        f"random-contact {h}-month conversion {stats['contact_conversion_3m']:.3%} "
        f"is too far from the {target:.2%} target")
    assert abs(stats["consent"] - cfg.consent_share) < 0.02, "consent share drifted"
    # hard negatives must survive: they are what keeps the AUC honest
    assert 0.06 < stats["window_shopper"] < 0.11, "window-shopper share out of band"
    assert 0.10 < stats["red_herring"] < 0.16, "red-herring share out of band"
    assert 0.015 < stats["near_miss"] < 0.045, "near-miss share out of band"
    return stats


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> BookConfig:
    ap = argparse.ArgumentParser(
        prog="make_book", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20260709, help="RNG seed (default: 20260709)")
    ap.add_argument("--n", type=int, default=None, help="customers (default: 60000)")
    ap.add_argument("--months", type=int, default=None, help="panel months (default: 30)")
    ap.add_argument("--legacy-size", action="store_true",
                    help="reproduce the pre-SD-S1 book: 15,000 x 27, three products, "
                         "no seasonality. Used for equivalence testing.")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default: data/)")
    a = ap.parse_args(argv)

    out = a.out if a.out is not None else ROOT / "data"
    if a.legacy_size:
        cfg = BookConfig.legacy(seed=a.seed, out_dir=out)
        if a.n is not None or a.months is not None:
            cfg = BookConfig(n=a.n or cfg.n, months=a.months or cfg.months, seed=a.seed,
                             preset="legacy", out_dir=out, anchor=cfg.anchor,
                             base_rates=cfg.base_rates)
        return cfg
    return BookConfig(n=a.n or 60_000, months=a.months or 30, seed=a.seed,
                      preset="modern", out_dir=out, base_rates=BaseRates())


def main(argv: list[str] | None = None) -> None:
    cfg = parse_args(argv)
    t0 = time.perf_counter()
    panel, book, truth = build_frames(cfg)
    t_gen = time.perf_counter() - t0

    stats = check(cfg, panel, book, truth)

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    t1 = time.perf_counter()
    panel.to_csv(cfg.out_dir / "customer_panel.csv", index=False)
    book.to_csv(cfg.out_dir / "customer_book.csv", index=False)
    truth.to_csv(cfg.out_dir / "liability_book_truth.csv", index=False, float_format="%.4g")
    t_io = time.perf_counter() - t1

    mix = book.loc[book["product"] != "", "product_canonical"].value_counts().to_dict()
    print(f"{cfg.n:,} customers x {cfg.months} months -> {len(panel):,} rows "
          f"[{cfg.preset} preset, {cfg.n_products} products, snapshot month {cfg.snapshot_month} "
          f"= {cfg.month_labels()[cfg.snapshot_month]}]")
    print(f"eventual converters: {stats['converters']:.1%} | product mix: {mix}")
    print(f"random-contact {cfg.base_rates.label_horizon_months}m conversion at snapshot: "
          f"{stats['contact_conversion_3m']:.2%}  (target {cfg.base_rates.target_contact_conversion_3m:.2%})")
    print(f"hard negatives: window-shopper {stats['window_shopper']:.1%} | dormant-rich "
          f"{stats['dormant_rich']:.1%} | red-herring {stats['red_herring']:.1%} | "
          f"near-miss {stats['near_miss']:.1%}")
    print(f"archetypes: persuadable {stats['persuadable']:.1%} | do-not-disturb {stats['dnd']:.1%} | "
          f"substituted product {stats['substituted']:.1%}")
    print(f"consent: {stats['consent']:.0%}")
    print(f"generated in {t_gen:.1f}s, written in {t_io:.1f}s -> {cfg.out_dir}")


if __name__ == "__main__":
    main()
