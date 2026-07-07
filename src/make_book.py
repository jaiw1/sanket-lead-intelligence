"""
SANKET synthetic liability book  ->  data/customer_book.csv (static) + data/customer_panel.csv (monthly)

15,000 liability-side customers observed monthly for 27 months (months 0..26).
"Today" in the cockpit is month 23 (2025-06); months 24-26 exist only as the
held-out future used to MEASURE precision honestly.

Each eventual converter gets ONE (product, event_month) and a causal run-up
planted 4-8 months earlier:
  HOME : rent step-up + balance accretion (down-payment saving) + home-page dwell, ages 26-40
  AUTO : fuel+cab surge + no existing auto EMI + auto-page dwell
  PL   : deepening pre-salary balance dips + costly external EMI + pl-page dwell

Hard negatives keep it honest: window-shoppers (dwell without financial signal)
and dormant-rich customers (capacity without intent) mostly do NOT convert.
Random-contact 3-month conversion lands near the bank-stated ~1%.
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260709)
ROOT = __file__.rsplit("/src/", 1)[0]
N = 15_000
M = 27                      # months 0..26 ; snapshot month = 23
SNAP = 23

SEGMENTS = ["salaried", "self-employed", "gig"]
SEG_P = [0.60, 0.25, 0.15]
PRODUCTS = ["home", "auto", "pl"]
# product mix among converters, by segment
PROD_P = {"salaried": [0.34, 0.30, 0.36], "self-employed": [0.28, 0.34, 0.38], "gig": [0.10, 0.28, 0.62]}


def month_label(i):
    y, m = divmod(4 + i, 12)   # month 0 = 2023-05
    return f"{2023 + y}-{m + 1:02d}"


def main():
    seg = RNG.choice(SEGMENTS, N, p=SEG_P)
    age = np.clip(RNG.normal(36, 9, N).astype(int), 21, 62)
    city = RNG.choice([1, 2, 3], N, p=[0.38, 0.40, 0.22])
    tenure = RNG.integers(8, 180, N)
    consent = RNG.random(N) < 0.85

    # base income by segment (monthly credits, ₹)
    base_inc = np.where(seg == "salaried", RNG.lognormal(11.05, 0.35, N),
               np.where(seg == "self-employed", RNG.lognormal(11.15, 0.5, N),
                        RNG.lognormal(10.45, 0.45, N)))
    base_inc = np.clip(base_inc, 18_000, 900_000)

    # one conversion event per ~8.5% of customers -> ~1.4% random 3-month contact rate
    is_conv = RNG.random(N) < 0.085
    prod = np.array([RNG.choice(PRODUCTS, p=PROD_P[s]) if c else "" for s, c in zip(seg, is_conv)])
    # home buyers skew 26-40
    for i in np.where((prod == "home") & ((age < 26) | (age > 42)))[0]:
        if RNG.random() < 0.7:
            prod[i] = RNG.choice(["auto", "pl"])
    event_m = np.where(is_conv, RNG.integers(9, M, N), -1)

    # hard-negative archetypes among non-converters
    r = RNG.random(N)
    window_shopper = (~is_conv) & (r < 0.09)                      # browse hard, never buy
    dormant_rich = (~is_conv) & (r >= 0.09) & (r < 0.16)          # capacity without intent
    red_herring = (~is_conv) & (r >= 0.16) & (r < 0.30)           # life-noise: rent hike / fuel surge / EMI creep with NO purchase
    near_miss = (~is_conv) & (r >= 0.30) & (r < 0.33)             # full signal bundle + browsing, then life happens: no purchase

    # converter signal texture: some research on our app, some do not; some convert silently
    sig_strength = np.where(RNG.random(N) < 0.12, 0.0, RNG.uniform(0.45, 1.0, N))   # 12% silent converters
    browses = RNG.random(N) < 0.60                                                   # only 60% research in-app

    rent_base = np.where(RNG.random(N) < 0.55, base_inc * RNG.uniform(0.12, 0.30, N), 0.0)  # 55% rent
    ext_emi_base = np.where(RNG.random(N) < 0.38, base_inc * RNG.uniform(0.06, 0.22, N), 0.0)
    has_auto_emi = (RNG.random(N) < 0.22)
    school_base = np.where((age > 29) & (RNG.random(N) < 0.4), base_inc * RNG.uniform(0.04, 0.10, N), 0.0)
    fd_base = np.where(RNG.random(N) < 0.45, base_inc * RNG.uniform(1.5, 8.0, N), 0.0)

    rows = []
    for i in range(N):
        inc = base_inc[i]
        vol = {"salaried": 0.05, "self-employed": 0.16, "gig": 0.30}[seg[i]]
        drift = RNG.normal(0.004, 0.003)                      # gentle income growth
        bal = inc * RNG.uniform(0.5, 2.2)
        fd = fd_base[i]
        rent = rent_base[i]
        ev, pr = event_m[i], prod[i]
        s = sig_strength[i]
        ramp_start = ev - RNG.integers(4, 9) if (ev >= 0 and s > 0) else -1
        # near-miss customers behave exactly like ramping converters, but never buy
        if near_miss[i]:
            pr = RNG.choice(PRODUCTS)
            s = RNG.uniform(0.4, 1.0)
            fake_ev = RNG.integers(12, M)
            ramp_start, ev_like = fake_ev - RNG.integers(4, 9), fake_ev
        else:
            ev_like = ev
        # which sub-signals THIS customer expresses (nobody shows the full textbook bundle)
        use_dwell = browses[i] or near_miss[i]
        c_a = RNG.random() < 0.78          # primary financial signal
        c_b = RNG.random() < 0.72          # secondary financial signal
        # window-shopper dwell burst window
        ws_start = RNG.integers(6, 20) if window_shopper[i] else -1
        ws_prod = RNG.choice(PRODUCTS) if window_shopper[i] else ""
        # red-herring financial ramp (no dwell, no conversion) — e.g. landlord hike you absorb,
        # a new commute, or an external EMI you just keep paying
        rh_start = RNG.integers(6, 20) if red_herring[i] else -1
        rh_kind = RNG.choice(PRODUCTS) if red_herring[i] else ""
        rh_len = RNG.integers(4, 9) if red_herring[i] else 0

        for m in range(M):
            credits = inc * (1 + drift) ** m * max(0.25, 1 + RNG.normal(0, vol))
            spend_ess = credits * RNG.uniform(0.30, 0.45)
            fuel = credits * RNG.uniform(0.015, 0.045)
            ecom = credits * RNG.uniform(0.02, 0.08)
            school = school_base[i] * (1 + 0.05 * (m // 12))
            emi = ext_emi_base[i]
            dwell = {"home": 0.0, "auto": 0.0, "pl": 0.0}
            dip = 0.0

            in_ramp = ramp_start >= 0 and ramp_start <= m < ev_like
            k = (m - ramp_start) / max(1, ev_like - ramp_start) if in_ramp else 0.0   # 0->1 through the ramp
            ks = k * s                                                                 # strength-scaled progress

            if in_ramp:
                if use_dwell:
                    dwell[pr] += RNG.uniform(1, 7) * (0.4 + ks)
                if pr == "home":
                    rent_now = rent * (1 + 0.38 * ks) if c_a else rent   # landlord hike pushing to buy
                    if c_b:
                        bal += credits * RNG.uniform(0.06, 0.20) * (0.5 + s)  # down-payment accretion
                    if k > 0.6 and fd > 0 and RNG.random() < 0.2 * s:
                        fd *= 0.5                                     # breaking FDs near the end
                elif pr == "auto":
                    fuel *= (1 + (1.5 if c_a else 0.6) * ks)          # cabs + fuel surge
                    rent_now = rent
                elif pr == "pl":
                    emi = emi + credits * (0.08 if c_a else 0.03) * ks   # expensive external debt creeps up
                    if c_b:
                        dip = credits * RNG.uniform(0.06, 0.22) * ks  # pre-salary squeeze deepens
                    rent_now = rent
            else:
                rent_now = rent
                bal = bal * RNG.uniform(0.97, 1.03) + credits * RNG.uniform(-0.02, 0.04)
                if red_herring[i] and rh_start <= m < rh_start + rh_len:
                    kk = (m - rh_start) / rh_len
                    if rh_kind == "home":
                        rent_now = rent * (1 + 0.35 * kk)
                        bal += credits * RNG.uniform(0.05, 0.15)
                    elif rh_kind == "auto":
                        fuel *= (1 + 1.4 * kk)
                    else:
                        emi = emi + credits * 0.09 * kk
                        dip = credits * RNG.uniform(0.08, 0.22) * kk

            if dormant_rich[i]:
                bal = max(bal, inc * 4.5)
            if window_shopper[i] and ws_start <= m < ws_start + 4:
                dwell[ws_prod] += RNG.uniform(6, 14)                  # heavy browsing, no follow-through
            # ambient light browsing
            if RNG.random() < 0.12:
                dwell[RNG.choice(PRODUCTS)] += RNG.uniform(0.5, 3)

            outflow = spend_ess + fuel + ecom + school + emi + rent_now
            min_bal = max(500.0, bal * RNG.uniform(0.15, 0.5) - dip)
            bal = max(1_000.0, bal + (credits - outflow) * 0.25)

            rows.append((
                f"LB-{2_000_000 + i}", m, month_label(m), round(credits), round(bal), round(min_bal),
                round(rent_now), round(fuel), round(school), round(ecom), round(emi),
                int(has_auto_emi[i]), round(fd), round(dwell["home"], 1), round(dwell["auto"], 1), round(dwell["pl"], 1),
            ))

    panel = pd.DataFrame(rows, columns=[
        "cust_id", "month", "date", "credits", "bal_avg", "bal_min", "rent", "fuel_cab", "school_fees",
        "ecommerce", "ext_emi", "has_auto_emi", "fd_bal", "dwell_home", "dwell_auto", "dwell_pl"])

    book = pd.DataFrame({
        "cust_id": [f"LB-{2_000_000 + i}" for i in range(N)],
        "segment": seg, "age": age, "city_tier": city, "tenure_m": tenure, "consent": consent.astype(int),
        "product": prod, "event_month": event_m,
        "window_shopper": window_shopper.astype(int), "dormant_rich": dormant_rich.astype(int),
    })

    panel.to_csv(f"{ROOT}/data/customer_panel.csv", index=False)
    book.to_csv(f"{ROOT}/data/customer_book.csv", index=False)

    conv3 = ((book.event_month > SNAP) & (book.event_month <= SNAP + 3)).mean()
    print(f"{N:,} customers x {M} months -> {len(panel):,} rows")
    print(f"eventual converters: {is_conv.mean():.1%} | product mix: {pd.Series(prod[prod != '']).value_counts().to_dict()}")
    print(f"random-contact 3m conversion at snapshot: {conv3:.2%}  (bank-stated baseline ~1%)")
    print(f"consent: {consent.mean():.0%}")


if __name__ == "__main__":
    main()
