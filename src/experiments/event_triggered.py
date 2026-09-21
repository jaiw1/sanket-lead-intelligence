#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Would event-triggered scoring rescue the one-day products? And what is the SLA?

    python3 src/experiments/event_triggered.py          # ~1 min, writes the JSON

Two questions the pack could not answer
---------------------------------------
**1. Contact-SLA compliance is measured nowhere.** SK-04 measures *conversion
timing among converters* — of the leads that disbursed, the share that disbursed
inside the offered product's window. It says nothing about whether a relationship
manager reached the customer before ``contact_by``, because nothing in the
pipeline observes an RM dialling. This script measures that separately, by
simulating the dialling, and the two numbers are reported apart on purpose.

**2. A monthly snapshot cannot serve a one-day product.** ``personal`` and
``gold`` close in **one day** from abandonment. A monthly batch first sees the
customer on the first of the following month — on average about fifteen days
after they walked away, and never fewer than one. The window is shut before the
lead exists. The fix is to score on the abandonment event instead of the
calendar, and the question is how much it actually buys once ingestion lag,
weekends and a finite calling capacity are put back in.

What is simulated, and what is read from the model
--------------------------------------------------
Read from the model: which leads the policy selects, in what order
(``model.policy``), each lead's ``abandoned_at``, its product's window and its
label. **Simulated:** the dialling — arrival of the lead in the queue, an
ingestion lag, working days, and a finite number of calls per day.

Regimes
-------
* ``monthly`` — today's pipeline. Every lead of the month becomes available at
  the snapshot instant, plus the ingestion lag.
* ``event`` — the lead becomes available at its own abandonment timestamp, plus
  the ingestion lag.

Both are given the **same** monthly calling capacity, so the comparison is about
*when* the calls happen, not how many.

The honest limit, stated before the numbers
-------------------------------------------
**This cannot show what late contact costs in conversions.** The generator's
label is a potential outcome under contact with no decay after ``contact_by`` —
a customer contacted on day 40 converts exactly as often as one contacted on day
1. So post-contact disbursement is reported *beside* SLA compliance rather than
derived from it, and the two do not move together here even though they certainly
would in a bank. Anyone reading a conversion uplift out of the SLA improvement
below is reading something this simulation did not model. Quantifying the decay
needs a real contact-time-to-outcome dataset, which is exactly what a pilot would
produce.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from model import WINDOW_DAYS, ModelConfig  # noqa: E402
from model import policy as PO  # noqa: E402
from model.pack import _held, build_frames  # noqa: E402
from model.train import fit_ranker, split_customers  # noqa: E402

OUT_REL = Path("data") / "experiments" / "event_triggered.json"

#: A lead is "new this month" if the customer abandoned within this many days of
#: the scoring instant — i.e. the monthly batch is the first chance anyone had.
NEW_LEAD_DAYS = 31

#: Ingestion lags replayed, in days: same-day, overnight batch, and a three-day
#: lag of the kind a weekly reconciliation produces.
LAGS = (0, 1, 3)

#: Calling capacity, as a multiple of the budgeted monthly volume. 1.0 is "the
#: team can make exactly the calls the budget buys"; 0.5 is the overload replay.
CAPACITIES = (1.0, 0.5)

WORKING_DAYS_PER_MONTH = 22


def _cal_to_working(day: np.ndarray, weekends: bool) -> np.ndarray:
    """Calendar day -> index of the next day anyone is actually at a desk.

    Day 0 is a Monday. With ``weekends=False`` every day is a calling day (the
    idealised replay); with ``weekends=True`` a lead that lands on Saturday waits
    until Monday, which for a one-day product is the whole window and then some.
    """
    day = np.maximum(day, 0).astype(np.int64)
    if not weekends:
        return day
    return (day // 7) * 5 + np.minimum(day % 7, 5)


def _working_to_cal(idx: np.ndarray, weekends: bool) -> np.ndarray:
    if not weekends:
        return idx.astype(float)
    return ((idx // 5) * 7 + (idx % 5)).astype(float)


def _serve(available_wd: np.ndarray, rank: np.ndarray, per_day: float) -> np.ndarray:
    """A FIFO queue on a shared calendar with a daily call limit.

    Leads are served in arrival order, ties broken by the policy's own ranking,
    ``per_day`` of them per working day, on ONE calendar shared by the whole
    queue. The shared calendar is the point: a newly abandoned one-day lead does
    not get a private RM, it queues behind whatever else the month produced, and
    a backlog carries forward. That is what makes the overload replay mean
    anything.
    """
    order = np.lexsort((rank, available_wd))
    served = np.empty(len(order), dtype=np.int64)
    day, used = -1, 0.0
    for pos in order:
        want = int(available_wd[pos])
        if want > day:
            day, used = want, 0.0
        elif used >= per_day:
            day += 1
            used = 0.0
        served[pos] = day
        used += 1.0
    return served


def simulate(d: pd.DataFrame, regime: str, lag: int, weekends: bool,
             per_day: float) -> dict:
    """One regime x lag x weekend x capacity cell, on a shared absolute calendar.

    Every day below is an absolute day of the panel, so leads from different
    months genuinely compete for the same calling capacity and ``contact_by``
    (abandonment + window) is comparable with the contact date.
    """
    abandoned = d["abandoned_abs"].to_numpy(np.int64)
    scored = d["scored_abs"].to_numpy(np.int64)
    window = d["window_days"].to_numpy(float)
    rank = d["rank"].to_numpy(float)

    if regime == "event":
        # ONE lead per abandonment event. Today's monthly batch re-emits the same
        # customer every month they stay in the pool; an event-triggered system
        # emits them once, when they walk away. That saving is real and is part of
        # what the regime buys, so the volumes are reported beside the rates.
        first = d.groupby(["cust_id", "abandoned_abs"], sort=False)["rank"].transform("min")
        keep = (d["rank"].to_numpy(float) == first.to_numpy(float))
    else:
        keep = np.ones(len(d), dtype=bool)
    available_cal = (abandoned if regime == "event" else scored) + int(lag)
    # a dropped duplicate is parked far past the horizon rather than removed, so
    # every array stays row-aligned with `d` and the masks below still apply
    available_wd = _cal_to_working(available_cal, weekends)
    sort_rank = np.where(keep, rank, rank + 10 ** 9)
    served_wd = _serve(available_wd, sort_rank, per_day)
    contacted_cal = _working_to_cal(served_wd, weekends)

    days_to_contact = contacted_cal - abandoned
    in_time = days_to_contact <= window
    # the window had already shut before the queue could even offer the lead
    already_shut = (available_cal - abandoned) > window
    y = d["y"].to_numpy(int)

    def _block(mask0: np.ndarray) -> dict:
        mask = mask0 & keep
        n = int(mask.sum())
        if not n:
            return dict(n=0)
        return dict(
            n=n,
            sla_compliance=round(float(in_time[mask].mean()), 4),
            dead_on_arrival=round(float(already_shut[mask].mean()), 4),
            median_days_to_contact=round(float(np.median(days_to_contact[mask])), 2),
            p90_days_to_contact=round(float(np.percentile(days_to_contact[mask], 90)), 2),
            post_contact_disbursement=round(float(y[mask].mean()), 4),
            post_contact_disbursement_in_time=(
                round(float(y[mask & in_time].mean()), 4)
                if (mask & in_time).any() else None),
        )

    one_day = (window <= 1)
    fresh = (d["days_since_abandon"].to_numpy(float) <= NEW_LEAD_DAYS)
    return dict(
        regime=regime, ingestion_lag_days=lag, weekends_excluded=bool(weekends),
        calls_per_working_day=round(float(per_day), 1),
        leads_contacted=int(keep.sum()),
        duplicate_rows_suppressed=int((~keep).sum()),
        all_products=_block(np.ones(len(d), dtype=bool)),
        one_day_products=_block(one_day),
        longer_windows=_block(~one_day),
        newly_abandoned=_block(fresh),
        newly_abandoned_one_day=_block(fresh & one_day),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=float, default=0.10)
    ap.add_argument("--out", default=str(ROOT / OUT_REL))
    a = ap.parse_args(argv)

    t0 = time.time()
    cfg = ModelConfig(root=ROOT, seed=a.seed, seeds=(a.seed,), budget=a.budget, quick=True)
    base, stacked, _ = build_frames(cfg)
    sp = split_customers(base["cust_id"].unique(), cfg, a.seed)
    rk = fit_ranker(stacked, sp, cfg)
    P = rk.matrix(stacked)
    h = _held(base, sp)
    hb = base[h].reset_index(drop=True)
    Ph = P[h]

    sc = PO.score_pool(hb["cust_id"].to_numpy(), hb["safe_emi"].to_numpy(), Ph,
                       hb["eligible_for_contact"].to_numpy() == 1)
    order = PO.select(sc, budget=a.budget)
    rank_of = {int(p): i for i, p in enumerate(order)}

    sel = hb.iloc[order].copy().reset_index(drop=True)
    sel["rank"] = [rank_of[int(p)] for p in order]
    sel["product"] = [sc.nbp[int(p)] for p in order]
    sel["window_days"] = [WINDOW_DAYS[p] for p in sel["product"]]
    sel["y"] = sel["t_label"].to_numpy().astype(int)

    # One absolute calendar for the whole queue, so leads from different months
    # compete for the same RMs. Day 0 is the panel's first scoring instant and is
    # treated as a Monday; the weekend replay depends only on the day-of-week
    # pattern, not on which Monday it is.
    scored_ts = pd.to_datetime(sel["date"])
    origin = scored_ts.min()
    sel["scored_abs"] = (scored_ts - origin).dt.days.to_numpy(np.int64)
    sel["abandoned_abs"] = sel["scored_abs"] - sel["days_since_abandon"].to_numpy(np.int64)

    months = int(hb["month"].nunique())
    # Capacity 1.0 = enough calls to clear the BUSIEST month. Sizing it to the
    # mean instead leaves a system whose arrivals are bursty permanently in
    # backlog, which would make every regime look identically terrible for a
    # reason that is about queue theory rather than about scoring triggers.
    busiest = int(sel.groupby("month", observed=True).size().max())
    base_per_day = busiest / WORKING_DAYS_PER_MONTH
    n_new = int((sel["days_since_abandon"] <= NEW_LEAD_DAYS).sum())
    n_one_day = int((sel["window_days"] <= 1).sum())

    print(f"selected {len(sel):,} leads across {months} months "
          f"({n_new:,} newly abandoned <= {NEW_LEAD_DAYS}d, {n_one_day:,} one-day "
          f"products); busiest month {busiest} -> {base_per_day:.1f} calls/working "
          f"day at capacity 1.0  [{time.time() - t0:.0f}s]", flush=True)

    cells = []
    for regime in ("monthly", "event"):
        for lag in LAGS:
            for weekends in (False, True):
                for cap in CAPACITIES:
                    cells.append(simulate(sel, regime, lag, weekends,
                                          max(1.0, base_per_day * cap)))

    def pick(regime, lag, weekends, cap_mult):
        per_day = round(max(1.0, base_per_day * cap_mult), 1)
        return next(c for c in cells if c["regime"] == regime
                    and c["ingestion_lag_days"] == lag
                    and c["weekends_excluded"] == weekends
                    and c["calls_per_working_day"] == per_day)

    realistic_monthly = pick("monthly", 1, True, 1.0)
    realistic_event = pick("event", 1, True, 1.0)
    one_day_share = float((sel["window_days"] <= 1).mean())

    doc = dict(
        seed=a.seed, budget=a.budget,
        n_selected=int(len(sel)), n_new_leads=n_new,
        n_one_day_products=n_one_day,
        one_day_share_of_queue=round(one_day_share, 4),
        months_in_holdout=months,
        calls_per_working_day_at_capacity_1=round(base_per_day, 2),
        busiest_month_volume=busiest,
        working_days_per_month=WORKING_DAYS_PER_MONTH,
        lags_replayed=list(LAGS), capacity_multipliers=list(CAPACITIES),
        cells=cells,
        headline=dict(
            comparison="newly abandoned one-day products (personal, gold), 1-day "
                       "ingestion lag, weekends excluded, capacity 1.0",
            monthly_sla=realistic_monthly["newly_abandoned_one_day"].get("sla_compliance"),
            event_sla=realistic_event["newly_abandoned_one_day"].get("sla_compliance"),
            monthly_dead_on_arrival=realistic_monthly["newly_abandoned_one_day"].get("dead_on_arrival"),
            event_dead_on_arrival=realistic_event["newly_abandoned_one_day"].get("dead_on_arrival"),
            monthly_median_days=realistic_monthly["newly_abandoned_one_day"].get("median_days_to_contact"),
            event_median_days=realistic_event["newly_abandoned_one_day"].get("median_days_to_contact"),
            all_products_monthly_sla=realistic_monthly["all_products"].get("sla_compliance"),
            all_products_event_sla=realistic_event["all_products"].get("sla_compliance"),
        ),
        separation=dict(
            contact_sla_compliance="share of selected leads an RM reaches on or before "
                                   "contact_by (= abandonment + the product's window). "
                                   "SIMULATED dialling; nothing in the pipeline observes "
                                   "a real call.",
            post_contact_disbursement="share of the same leads whose label is 1, i.e. that "
                                      "disburse inside the product's window AFTER contact. "
                                      "Measured from the generator's potential outcome.",
            why_separate="They are different quantities and SK-04 is neither of them. "
                         "SK-04 is conversion timing among converters and must never be "
                         "quoted as an SLA result.",
            unmodelled="The generator's label has NO decay after contact_by: a customer "
                       "contacted on day 40 converts as often as one contacted on day 1. "
                       "So post_contact_disbursement barely moves between regimes here, "
                       "and the conversion value of better SLA compliance is NOT "
                       "measurable from this simulation. Only a pilot with real "
                       "contact-time-to-outcome data can price it.",
        ),
        runtime_s=round(time.time() - t0, 1),
    )

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    print("\nnewly abandoned one-day products, weekends excluded, capacity 1.0:")
    print(f"  {'regime':<9}{'lag':>5}{'SLA':>9}{'dead on arrival':>18}{'median days':>14}")
    for regime in ("monthly", "event"):
        for lag in LAGS:
            c = pick(regime, lag, True, 1.0)["newly_abandoned_one_day"]
            print(f"  {regime:<9}{lag:>5}{c.get('sla_compliance', 0):>9.3f}"
                  f"{c.get('dead_on_arrival', 0):>18.3f}"
                  f"{c.get('median_days_to_contact', 0):>14.2f}")
    print("\nunder overload (capacity 0.5), event regime, lag 1:")
    for key in ("newly_abandoned_one_day", "newly_abandoned", "all_products"):
        c = pick("event", 1, True, 0.5)[key]
        print(f"  {key:<20} SLA {c.get('sla_compliance')}  "
              f"p90 days to contact {c.get('p90_days_to_contact')}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
