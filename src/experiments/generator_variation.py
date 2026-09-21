#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""How much of the headline is the model, and how much is this particular world?

    python3 src/experiments/generator_variation.py                 # 3 worlds, ~30 min
    python3 src/experiments/generator_variation.py --seeds 11,12    # pick them
    python3 src/experiments/generator_variation.py --n 20000        # smaller worlds, faster

The third uncertainty field
---------------------------
``metrics.uncertainty`` keeps three estimands apart, because they answer three
questions and merging them answers none:

* **sample** — which customers landed in the book. Customer-clustered bootstrap
  over the packed seed's held-out predictions, queue re-selected inside every
  resample (``model.bootstrap``).
* **training_seed** — which fit/calibrate/holdout split the model drew. The
  five-seed percentile spread the pack already computes.
* **generator** — *this* script. The book, the journey layer and the labels are
  all drawn from one generator seed. Re-draw the world and re-measure: whatever
  moves is a property of the synthetic data rather than of the model.

**The generator seed and the model seed are separated deliberately.** Every world
is scored at the same model seed (``--model-seed``, default 7), so nothing here
is contaminated by training-split variance — that is the field above. A run that
varied both at once would produce one number that could not be attributed to
either.

Cost, and why this is not inside ``score_and_pack.py``
------------------------------------------------------
One world is a full ``make_book`` + ``make_journeys`` + frame build + fit: about
ten minutes and ~350 MB of CSV. Three of them is half an hour. ``score_and_pack``
has an eleven-minute budget and runs on every change, so this runs on its own and
leaves ``data/experiments/generator_variation.json`` behind; ``model.pack`` reads
that file if it exists and reports ``status: not_measured`` if it does not,
rather than quietly showing nothing.

Worlds are written to a scratch directory and **deleted as soon as each is
measured**, so peak disk is one world, not three.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from model import ModelConfig  # noqa: E402
from model import metrics as M  # noqa: E402
from model import policy as PO  # noqa: E402
from model.pack import _held, build_frames  # noqa: E402
from model.train import fit_ranker, split_customers  # noqa: E402

#: The seed the shipped book was drawn from. It is world #1 so the published
#: numbers appear in the table rather than sitting outside it.
SHIPPED_GENERATOR_SEED = 20260709

OUT_REL = Path("data") / "experiments" / "generator_variation.json"


def build_world(out_dir: Path, seed: int, n: int, months: int) -> None:
    """One complete synthetic world — book, journeys, campaigns, labels."""
    from book import BookConfig
    from book.build import build_frames as book_frames
    from journeys import JourneyConfig
    from journeys.build import generate_all

    out_dir.mkdir(parents=True, exist_ok=True)
    bcfg = BookConfig(n=n, months=months, seed=seed, out_dir=out_dir)
    panel, book, truth = book_frames(bcfg)
    panel.to_csv(out_dir / "customer_panel.csv", index=False)
    book.to_csv(out_dir / "customer_book.csv", index=False)
    truth.to_csv(out_dir / "liability_book_truth.csv", index=False, float_format="%.4g")
    del panel, book, truth

    jcfg = JourneyConfig(book_dir=out_dir, out_dir=out_dir, seed=seed)
    b = generate_all(jcfg)
    b.journeys.to_csv(out_dir / "journeys.csv", index=False)
    b.events.to_csv(out_dir / "journey_events.csv", index=False)
    b.truth.to_csv(out_dir / "journey_truth.csv", index=False)
    b.campaigns.to_csv(out_dir / "campaigns.csv", index=False)
    b.labels.to_csv(out_dir / "labels.csv", index=False)
    b.label_truth.to_csv(out_dir / "label_truth.csv", index=False)
    (out_dir / "journey_params.json").write_text(json.dumps(b.params, default=str))


def measure_world(root: Path, model_seed: int, budget: float) -> dict:
    """Fit at the fixed model seed and read the delivered policy's numbers off it."""
    cfg = ModelConfig(root=root, seed=model_seed, seeds=(model_seed,),
                      budget=budget, quick=True)
    base, stacked, _tables = build_frames(cfg)
    sp = split_customers(base["cust_id"].unique(), cfg, model_seed)
    rk = fit_ranker(stacked, sp, cfg)
    P = rk.matrix(stacked)
    h = _held(base, sp)
    hb = base[h].reset_index(drop=True)
    Ph, y = P[h], hb["t_label"].to_numpy().astype(int)
    sc = PO.score_pool(hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy(), Ph,
                       hb["eligible_for_contact"].to_numpy() == 1)
    pp = M.per_product(Ph, hb, budget)
    out = dict(
        n_holdout_rows=int(len(y)), n_holdout_customers=int(hb.cust_id.nunique()),
        baseline=round(float(y.mean()), 4),
        macro_auc=round(float(np.mean([v["auc"] for v in pp.values()])), 4),
        menu_of_4_hit_rate=round(M.menu_metrics(Ph, hb, cfg.menu_k)["menu_of_4_hit_rate"], 4),
    )
    for b in (0.05, budget, 0.20):
        out[f"precision_at_{int(round(b * 100))}pct"] = round(
            PO.precision_at(y, sc, b)["precision"], 4)
    out["headline"] = M.headline(out["baseline"], out[f"precision_at_{int(round(budget * 100))}pct"])
    return out


def _spread(values: list[float]) -> dict:
    v = np.asarray(values, dtype=float)
    return dict(mean=round(float(v.mean()), 4), min=round(float(v.min()), 4),
                max=round(float(v.max()), 4), n=int(len(v)),
                range_pp=round(100.0 * float(v.max() - v.min()), 2))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=f"{SHIPPED_GENERATOR_SEED},20260710,20260711",
                    help="generator seeds; the first should be the shipped book's")
    ap.add_argument("--model-seed", type=int, default=7,
                    help="held fixed across worlds so this measures the generator only")
    ap.add_argument("--n", type=int, default=60_000, help="customers per world")
    ap.add_argument("--months", type=int, default=30)
    ap.add_argument("--budget", type=float, default=0.10)
    ap.add_argument("--out", default=str(ROOT / OUT_REL))
    ap.add_argument("--keep", action="store_true",
                    help="do not delete each world after measuring it")
    a = ap.parse_args(argv)

    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    scratch = Path(tempfile.mkdtemp(prefix="sanket-worlds-"))
    t0 = time.time()
    worlds = []
    try:
        for seed in seeds:
            world_root = scratch / f"world{seed}"
            print(f"world {seed}: generating {a.n:,} x {a.months} …", flush=True)
            build_world(world_root / "data", seed, a.n, a.months)
            print(f"world {seed}: fitting at model seed {a.model_seed} "
                  f"[{time.time() - t0:.0f}s]", flush=True)
            row = measure_world(world_root, a.model_seed, a.budget)
            row["generator_seed"] = seed
            row["shipped"] = seed == SHIPPED_GENERATOR_SEED
            worlds.append(row)
            print(f"world {seed}: {row['headline']} | "
                  f"precision@{int(a.budget * 100)}% "
                  f"{row[f'precision_at_{int(round(a.budget * 100))}pct']:.4f} "
                  f"[{time.time() - t0:.0f}s]", flush=True)
            if not a.keep:
                shutil.rmtree(world_root, ignore_errors=True)
    finally:
        if not a.keep:
            shutil.rmtree(scratch, ignore_errors=True)

    key = f"precision_at_{int(round(a.budget * 100))}pct"
    doc = dict(
        status="measured",
        estimand="variability across generator seeds (a different synthetic world, "
                 "the same model recipe and the same model seed)",
        method="regenerate book + journeys + labels at each generator seed, refit at "
               "one fixed model seed, re-select the queue with model.policy",
        model_seed=int(a.model_seed), generator_seeds=seeds,
        n_customers_per_world=int(a.n), months=int(a.months), budget=a.budget,
        worlds=worlds,
        spread={
            "baseline": _spread([w["baseline"] for w in worlds]),
            "precision_at_budget": _spread([w[key] for w in worlds]),
            "macro_auc": _spread([w["macro_auc"] for w in worlds]),
            "menu_of_4_hit_rate": _spread([w["menu_of_4_hit_rate"] for w in worlds]),
        },
        runtime_s=round(time.time() - t0, 1),
        note="This is NOT a confidence interval and is not comparable with the "
             "customer-clustered bootstrap: it measures how much the answer depends "
             "on the synthetic world, which a real deployment would not have at all. "
             "A wide spread here means the headline is a statement about the "
             "generator; a narrow one means the generator is not doing the work.",
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nprecision@{int(a.budget * 100)}% across {len(worlds)} worlds: "
          f"{doc['spread']['precision_at_budget']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
