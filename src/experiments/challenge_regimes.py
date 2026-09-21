#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze the development world, then hit the frozen model with worlds it never saw.

    python3 src/experiments/challenge_regimes.py            # ~10 min
    python3 src/experiments/challenge_regimes.py --quick     # scoring-time regimes only

Review §9: "strengthen the synthetic experiments without tuning the simulator to
success". The risk being managed is circular: the generator was solved to hit a
mentor-stated baseline, the model was built against that generator, and the model
looks good. Nothing in that loop tells you whether the model would survive a world
it was not built for.

So:

1. **The development generator config is frozen to a file**
   (``data/experiments/frozen_generator.json``) before anything else runs. Every
   challenge below is a *named departure* from that file, and the file is written
   first so the departures cannot be quietly relabelled afterwards.
2. **The model is fitted once, on the development world, and never refitted.**
   Every regime is scored with that frozen model. No hyper-parameter is touched,
   no threshold is moved, no calibrator is refitted. A regime that hurts, hurts.
3. **The model seed and the generator seed are separate arguments.** Challenge
   worlds use a generator seed the development world never used, and all of them
   are scored at the same model seed, so a degradation cannot be a training-split
   accident. A ``fresh world, same config`` control regime is included precisely
   to size that: whatever it moves is the cost of a new world, not of the
   challenge.

The regimes
-----------
Generator-level (a world is regenerated, ~1 min each):

* ``fresh_world`` — the control. Same frozen config, new generator seed.
* ``base_rate_half`` / ``base_rate_double`` — the drop-off recovery rate the
  generator solves for, halved and doubled.
* ``signal_correlation`` — the window-shopper share of drop-offs moved from 0.30
  to 0.50, which changes what the shopper signals mean about the label.

Scoring-time (applied to the development world, so its control is the development
number; no regeneration):

* ``source_latency`` — every behavioural feature is a month stale, the way a feed
  that missed its window would deliver it.
* ``extra_missingness`` — 15% of behavioural feature values blanked at random.
* ``macro_shock`` — incomes and balances deflated 15%, EMI burden inflated 20%.
* ``customer_turnover`` — scored on the newest-tenure quartile only, standing in
  for a book whose customers have largely been replaced since training.

Uplift and savings
------------------
Any rupee figure derived from these numbers is a **simulation result**, and the
output carries an assumption range rather than a point. See ``economics`` in the
JSON: it multiplies out the measured precision under each regime against a stated
contact cost and a stated margin, both of which are assumptions this repo cannot
verify, and reports the whole range rather than the flattering end of it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from model import ModelConfig  # noqa: E402
from model import frame as F  # noqa: E402
from model import metrics as M  # noqa: E402
from model import policy as PO  # noqa: E402
from model.pack import _held, build_frames  # noqa: E402
from model.train import fit_ranker, split_customers  # noqa: E402

OUT_REL = Path("data") / "experiments" / "challenge_regimes.json"
FROZEN_REL = Path("data") / "experiments" / "frozen_generator.json"

#: The world the model was built against. Everything else is a departure from it.
DEV_GENERATOR_SEED = 20260709
#: A seed the development world never used, for every challenge world.
CHALLENGE_GENERATOR_SEED = 20270131

#: Feature families that a stale feed, a missing feed or a macro shock would move.
#: `profile` and `journey` are excluded from the latency and missingness regimes:
#: age and tenure do not arrive on a nightly feed, and the journey layer is the
#: trigger rather than an enrichment.
BEHAVIOURAL = ("income", "balance", "outflow", "debt")

#: Economics, as assumptions. Neither number is verifiable from this repo and the
#: output reports the whole range they imply, not the flattering end.
COST_PER_CALL_INR = (40.0, 120.0)
MARGIN_PER_DISBURSEMENT_INR = (6_000.0, 18_000.0)


def freeze_config(path: Path) -> dict:
    """Write the development generator config, before any challenge runs."""
    from book import BookConfig
    from journeys import JourneyConfig

    b = BookConfig(seed=DEV_GENERATOR_SEED)
    j = JourneyConfig(seed=DEV_GENERATOR_SEED)

    def clean(d):
        return {k: (str(v) if isinstance(v, Path) else
                    asdict(v) if hasattr(v, "__dataclass_fields__") else
                    list(v) if isinstance(v, tuple) else v)
                for k, v in d.items() if k not in ("out_dir", "book_dir")}

    doc = dict(
        frozen_at_commit="see git log for this file",
        generator_seed=DEV_GENERATOR_SEED,
        book=clean(asdict(b)),
        journeys=clean(asdict(j)),
        note="This is the DEVELOPMENT configuration the shipped model was built "
             "against. It is written before any challenge regime runs so that every "
             "regime is a named departure from a recorded baseline rather than a "
             "retuning that could be relabelled afterwards. Nothing in "
             "src/experiments/challenge_regimes.py may edit this file.",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return doc


def build_world(out_dir: Path, seed: int, n: int, months: int, **journey_kw) -> None:
    from book import BookConfig
    from book.build import build_frames as book_frames
    from journeys import JourneyConfig
    from journeys.build import generate_all

    out_dir.mkdir(parents=True, exist_ok=True)
    panel, book, truth = book_frames(BookConfig(n=n, months=months, seed=seed, out_dir=out_dir))
    panel.to_csv(out_dir / "customer_panel.csv", index=False)
    book.to_csv(out_dir / "customer_book.csv", index=False)
    truth.to_csv(out_dir / "liability_book_truth.csv", index=False, float_format="%.4g")
    del panel, book, truth
    b = generate_all(JourneyConfig(book_dir=out_dir, out_dir=out_dir, seed=seed, **journey_kw))
    b.journeys.to_csv(out_dir / "journeys.csv", index=False)
    b.events.to_csv(out_dir / "journey_events.csv", index=False)
    b.truth.to_csv(out_dir / "journey_truth.csv", index=False)
    b.campaigns.to_csv(out_dir / "campaigns.csv", index=False)
    b.labels.to_csv(out_dir / "labels.csv", index=False)
    b.label_truth.to_csv(out_dir / "label_truth.csv", index=False)
    (out_dir / "journey_params.json").write_text(json.dumps(b.params, default=str))


# --------------------------------------------------------------------------- #
# scoring-time perturbations — the frozen model never sees them coming
# --------------------------------------------------------------------------- #

def _behavioural_columns() -> list[str]:
    cols: list[str] = []
    for fam in BEHAVIOURAL:
        cols += [c for c in F.FEATURE_FAMILIES.get(fam, ()) if c in F.FEATURES]
    return cols


def perturb(base: pd.DataFrame, regime: str, rng: np.random.Generator) -> pd.DataFrame:
    """Return a copy of ``base`` with the regime's damage applied to FEATURES only.

    Labels and truth columns are never touched: the world is what it is, and the
    regime changes what the model is allowed to see about it.
    """
    cols = _behavioural_columns()
    d = base.copy()
    if regime == "source_latency":
        # every behavioural feature is a month stale — the shape a feed that
        # missed its window actually has, not random noise
        d = d.sort_values(["cust_id", "month"], kind="stable")
        d[cols] = d.groupby("cust_id", observed=True)[cols].shift(1)
        d = d.sort_index()
    elif regime == "extra_missingness":
        for c in cols:
            mask = rng.random(len(d)) < 0.15
            d.loc[mask, c] = np.nan
    elif regime == "macro_shock":
        for c in ("credits_med_6m", "bal_avg"):
            if c in d:
                d[c] = d[c] * 0.85
        for c in ("emi_share", "other_bank_emi_share", "rent_share"):
            if c in d:
                d[c] = d[c] * 1.20
        for c in ("credits_gr_6m", "bal_gr_6m"):
            if c in d:
                d[c] = d[c] - 0.10
    elif regime == "customer_turnover":
        cut = float(d["tenure_m"].quantile(0.25))
        d = d[d["tenure_m"] <= cut]
    elif regime != "none":
        raise ValueError(f"unknown scoring-time regime {regime!r}")
    return d


def score_frozen(rk, base: pd.DataFrame, cfg: ModelConfig, sp, budget: float) -> dict:
    """Held-out precision under the frozen model. No refit, no recalibration."""
    h = _held(base, sp)
    hb = base[h].reset_index(drop=True)
    if len(hb) < 500:
        return dict(status="skipped_low_n", n=int(len(hb)))
    P = rk.matrix(F.as_categorical(F.stack(hb)))
    y = hb["t_label"].to_numpy().astype(int)
    sc = PO.score_pool(hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy(), P,
                       hb["eligible_for_contact"].to_numpy() == 1)
    pp = M.per_product(P, hb, budget)
    prec = PO.precision_at(y, sc, budget)["precision"]
    return dict(
        status="ok", n=int(len(y)), n_customers=int(hb.cust_id.nunique()),
        baseline=round(float(y.mean()), 4),
        precision_at_budget=round(float(prec), 4),
        lift=round(float(prec / max(y.mean(), 1e-9)), 2),
        macro_auc=round(float(np.mean([v["auc"] for v in pp.values()])), 4),
        menu_of_4_hit_rate=round(M.menu_metrics(P, hb, cfg.menu_k)["menu_of_4_hit_rate"], 4),
        headline=M.headline(float(y.mean()), float(prec)),
    )


def _economics(precision: float, baseline: float, calls: int = 100) -> dict:
    """Uplift per 100 calls, in rupees, as a RANGE of assumptions.

    Both inputs are assumptions this repo cannot verify — a contact costs what
    the bank's own cost-to-serve says it costs, and a disbursement is worth what
    its lifetime margin turns out to be. Reporting a point estimate here would be
    dressing two guesses as a finding, so the range is the answer.
    """
    extra = (precision - baseline) * calls
    lo = extra * MARGIN_PER_DISBURSEMENT_INR[0] - 0.0
    hi = extra * MARGIN_PER_DISBURSEMENT_INR[1] - 0.0
    return dict(
        extra_disbursements_per_100_calls=round(float(extra), 2),
        gross_margin_range_inr=[round(float(lo)), round(float(hi))],
        assumptions=dict(
            margin_per_disbursement_inr=list(MARGIN_PER_DISBURSEMENT_INR),
            cost_per_call_inr=list(COST_PER_CALL_INR),
            note="SIMULATION RESULT. Both assumptions are unverified by this repo, "
                 "the conversions are the generator's potential outcomes rather than "
                 "observed disbursements, and the calls are the same 100 in both arms. "
                 "Quote the range or nothing.",
        ),
        net_of_call_cost_range_inr=[
            round(float(lo - calls * COST_PER_CALL_INR[1])),
            round(float(hi - calls * COST_PER_CALL_INR[0]))],
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-seed", type=int, default=7)
    ap.add_argument("--generator-seed", type=int, default=CHALLENGE_GENERATOR_SEED,
                    help="a seed the development world never used")
    ap.add_argument("--n", type=int, default=60_000)
    ap.add_argument("--months", type=int, default=30)
    ap.add_argument("--budget", type=float, default=0.10)
    ap.add_argument("--quick", action="store_true",
                    help="skip the regenerated worlds; scoring-time regimes only")
    ap.add_argument("--out", default=str(ROOT / OUT_REL))
    a = ap.parse_args(argv)

    t0 = time.time()
    frozen = freeze_config(ROOT / FROZEN_REL)
    print(f"froze the development generator config -> {FROZEN_REL.as_posix()}", flush=True)

    # ---- the frozen model, fitted once on the development world ------------- #
    cfg = ModelConfig(root=ROOT, seed=a.model_seed, seeds=(a.model_seed,),
                      budget=a.budget, quick=True)
    dev_base, dev_stacked, _ = build_frames(cfg)
    sp_dev = split_customers(dev_base["cust_id"].unique(), cfg, a.model_seed)
    rk = fit_ranker(dev_stacked, sp_dev, cfg)
    dev = score_frozen(rk, dev_base, cfg, sp_dev, a.budget)
    dev.update(regime="development (the world the model was built on)", kind="baseline")
    print(f"development world: precision@{int(a.budget * 100)}% "
          f"{dev['precision_at_budget']:.4f}  [{time.time() - t0:.0f}s]", flush=True)

    results = [dev]
    scratch = Path(tempfile.mkdtemp(prefix="sanket-challenge-"))
    try:
        # ---- scoring-time regimes, on the development world ----------------- #
        rng = np.random.default_rng(a.model_seed)
        for regime in ("source_latency", "extra_missingness", "macro_shock",
                       "customer_turnover"):
            pert = perturb(dev_base, regime, rng)
            row = score_frozen(rk, pert, cfg, sp_dev, a.budget)
            row.update(regime=regime, kind="scoring-time")
            results.append(row)
            print(f"  {regime:<20} precision {row.get('precision_at_budget')}  "
                  f"[{time.time() - t0:.0f}s]", flush=True)

        # ---- regenerated worlds --------------------------------------------- #
        if not a.quick:
            worlds = [
                ("fresh_world", {}),
                ("base_rate_half", dict(target_recovery_rate=0.045)),
                ("base_rate_double", dict(target_recovery_rate=0.18)),
                ("signal_correlation", dict(target_shopper_share_of_dropoffs=0.50)),
            ]
            for name, kw in worlds:
                wroot = scratch / name
                print(f"  {name}: regenerating at generator seed {a.generator_seed} …",
                      flush=True)
                build_world(wroot / "data", a.generator_seed, a.n, a.months, **kw)
                wcfg = ModelConfig(root=wroot, seed=a.model_seed, seeds=(a.model_seed,),
                                   budget=a.budget, quick=True)
                wbase, _ws, _t = build_frames(wcfg)
                sp_w = split_customers(wbase["cust_id"].unique(), wcfg, a.model_seed)
                row = score_frozen(rk, wbase, wcfg, sp_w, a.budget)
                row.update(regime=name, kind="regenerated world",
                           departure=kw or "none (control)")
                results.append(row)
                print(f"  {name:<20} precision {row.get('precision_at_budget')}  "
                      f"baseline {row.get('baseline')}  [{time.time() - t0:.0f}s]",
                      flush=True)
                shutil.rmtree(wroot, ignore_errors=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    ref = dev["precision_at_budget"]
    fresh = next((r["precision_at_budget"] for r in results
                  if r.get("regime") == "fresh_world"
                  and r.get("precision_at_budget") is not None), None)
    for r in results:
        p = r.get("precision_at_budget")
        # Two comparators, because two kinds of regime. A scoring-time regime is
        # applied to the development world, so the development world is its
        # control. A regenerated world has already paid the cost of being a new
        # world, so `fresh_world` is its control and comparing it with the
        # development number would charge it twice.
        comparator = ("fresh_world" if r.get("kind") == "regenerated world" and fresh
                      else "development")
        cmp_value = fresh if comparator == "fresh_world" else ref
        r["comparator"] = comparator
        r["degradation_pp"] = round(100.0 * (ref - p), 2) if p is not None else None
        r["degradation_vs_comparator_pp"] = (
            round(100.0 * (cmp_value - p), 2) if p is not None and cmp_value else None)
        if p is not None and r.get("baseline") is not None:
            r["economics"] = _economics(p, r["baseline"])

    doc = dict(
        model_seed=a.model_seed,
        development_generator_seed=DEV_GENERATOR_SEED,
        challenge_generator_seed=a.generator_seed,
        frozen_config_file=FROZEN_REL.as_posix(),
        frozen_config_digest=dict(
            target_recovery_rate=frozen["journeys"]["target_recovery_rate"],
            target_attempt_share=frozen["journeys"]["target_attempt_share"],
            target_shopper_share_of_dropoffs=frozen["journeys"]["target_shopper_share_of_dropoffs"],
            n=frozen["book"]["n"], months=frozen["book"]["months"]),
        budget=a.budget,
        refitted=False,
        method="one model fitted on the development world and never refitted; every "
               "regime scored with it. Generator seed and model seed are separate "
               "arguments and the challenge worlds use a seed the development world "
               "never used.",
        regimes=results,
        lift_stability=dict(
            definition="precision@budget / that world's own baseline",
            values={r["regime"]: r.get("lift") for r in results},
            min=min((r["lift"] for r in results if r.get("lift")), default=None),
            max=max((r["lift"] for r in results if r.get("lift")), default=None),
            reading="Absolute precision tracks whatever base rate a world has. The "
                    "ratio is the part that belongs to the model, and it is the number "
                    "to watch across regimes."),
        reading="Compare every regime against `fresh_world`, not against the "
                "development world: a fresh world at a new generator seed already "
                "moves the number, and that movement is the cost of a new world "
                "rather than of the challenge. Anything beyond it is the regime.",
        runtime_s=round(time.time() - t0, 1),
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    print(f"\n{'regime':<28}{'precision':>11}{'baseline':>10}{'lift':>7}"
          f"{'vs control (pp)':>17}  control")
    for r in results:
        print(f"{r['regime'][:27]:<28}{r.get('precision_at_budget', float('nan')):>11.4f}"
              f"{r.get('baseline', float('nan')):>10.4f}{r.get('lift', float('nan')):>7.2f}"
              f"{r.get('degradation_vs_comparator_pp') or 0.0:>17.2f}  "
              f"{r.get('comparator', '')}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
