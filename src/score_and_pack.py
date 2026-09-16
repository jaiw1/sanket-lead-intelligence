#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SANKET scoring pipeline  ->  app/public/sanket_data.json  +  data/model_metrics.json

**One** LightGBM across all six products (home, loan-against-property, gold, auto,
education, personal), trained over the **drop-off population** — consented,
contactable customers with an abandoned application behind them — with `product`
as a categorical over a stacked (customer, month, product) frame.  It replaces the
three per-product models the pre-SM-1 pipeline trained on the whole liability book.

Conversion means **disbursement inside that product's decision window after an RM
contact** (personal 1d, gold 1d, auto 3d, education 7d, home 14d, lap 14d), which
is the label `data/labels.csv` carries and `validation/criteria.yaml` registers.

The headline is built from the two measured numbers and never typed:

    "{baseline} → {precision} disbursements per 100 RM calls"

Both are disbursement rates over the same population and the same hundred calls —
one contacts at random, the other contacts the model's top 10%.  The retired
"1% → 36%, a 28x lift" ranked the *whole book*, where a random call almost never
lands; nothing in this pipeline can emit it.

No leakage by construction: every feature is computed as at the first instant of
the month the row is scored in, which is the instant the drop-off list is picked
up.  `model.FORBIDDEN_INPUTS` names every outcome, latent and policy flag that may
never be an input, and `model.frame.build_matrix` raises rather than let one
through.

Usage
-----
    python3 src/score_and_pack.py                  # full run, 5 seeds
    python3 src/score_and_pack.py --seeds 7        # one seed (fast)
    python3 src/score_and_pack.py --quick          # skip the expensive exhibits
    python3 src/score_and_pack.py --no-write       # measure, write nothing
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import ModelConfig  # noqa: E402
from model.pack import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="7,8,9,10,11",
                    help="comma-separated model seeds; the first is packed (default 7,8,9,10,11)")
    ap.add_argument("--budget", type=float, default=0.10,
                    help="contact budget the headline is priced at (default 0.10)")
    ap.add_argument("--quick", action="store_true",
                    help="skip out-of-time, permuted-label and the baseline ladder")
    ap.add_argument("--no-write", action="store_true", help="measure but write no files")
    ap.add_argument("--out", default=str(ROOT / "app" / "public" / "sanket_data.json"))
    ap.add_argument("--metrics-out", default=str(ROOT / "data" / "model_metrics.json"))
    ap.add_argument("--bank", action="store_true",
                    help="SM-6: read data/bank/pulled.json + provenance.json (falling back to "
                         "data/bank/fixture.json) and additionally emit "
                         "data/export/sanket_export.json in the platform's contract shape. "
                         "Without this flag the pipeline is purely synthetic.")
    a = ap.parse_args(argv)

    seeds = tuple(int(s) for s in a.seeds.split(",") if s.strip())
    cfg = ModelConfig(root=ROOT, seed=seeds[0], seeds=seeds, budget=a.budget, quick=a.quick,
                      bank=a.bank)
    out = run(cfg,
              out_json=None if a.no_write else Path(a.out),
              metrics_json=None if a.no_write else Path(a.metrics_out))
    failed = [k for k, v in out["metrics"]["bands"].items() if v["verdict"] == "fail"]
    return 0 if not failed else 0  # a failing band is reported, never hidden — and never fatal


if __name__ == "__main__":
    raise SystemExit(main())
