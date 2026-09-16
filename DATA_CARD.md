# DATA CARD — SANKET synthetic liability book and application journeys

**Artefact:** `data/customer_panel.csv`, `data/customer_book.csv`, `data/liability_book_truth.csv`,
`data/journeys.csv`, `data/journey_events.csv`, `data/journey_truth.csv`, `data/journey_params.json`
**Generator:** `src/book/` (CLI: `src/make_book.py`) and `src/journeys/` (CLI: `src/make_journeys.py`)
**Version:** SD-S2 / SD-S3 (plan §B/L6), 2026-09-16 · builds on SD-S1
**Status:** SD-S4 (label windows + contact effect θ), SD-S5 (substitution scoring), SD-S6
(campaign/contact history) and SD-S7 (realism suite) are **not yet implemented**; §9 says so
explicitly. §11 documents the application-journey layer.

> This is synthetic data. It is engineered to bank-stated baselines, not sampled from any real
> customer book. No IDBI, Atlas-sandbox or customer record is used anywhere in this file or in
> the generator. Nothing here should be read as a measurement of IDBI's portfolio.

---

## 0. Provenance legend

Every parameter in this card carries one of three labels.

| Label | Meaning |
|---|---|
| `sourced` | A public figure, stated with its source, that the generator reproduces directly. |
| `sourced-approx` | A real published aggregate used as an **anchor** for the shape of a distribution, recalled without the document in hand. **Must be checked against the named source before it appears in the README, the deck or the portal submission** (honesty gate G5). |
| `assumed` | A modelling choice. Not a measurement, not defensible as one. |

Most of this book is `assumed`, and that is the honest position: a synthetic book's job is to be
*coherent and hard*, not to claim it measured India.

---

## 1. What is generated

| File | Grain | Rows (default) | Shipped to the app? |
|---|---|---|---|
| `data/customer_panel.csv` | customer × month | 1,800,000 (34 columns) | no — features are derived from it |
| `data/customer_book.csv` | customer | 60,000 (43 columns) | no |
| `data/liability_book_truth.csv` | customer × month | 1,800,000 (12 columns) | **never.** Latent ground truth. Not a feature, not an input to any model. SD-S2 and the validation lane read it to grade against. |
| `data/journeys.csv` | application attempt | 21,682 (49 columns) | no — features are derived from it, point-in-time (§11.9) |
| `data/journey_events.csv` | stage transition | 119,793 (8 columns) | no |
| `data/journey_truth.csv` | application attempt | 21,682 (17 columns) | **never.** Window-shopper truth and the hazard's own odds. |
| `data/journey_params.json` | one run | — | no — the solved intercepts and the realised headline numbers |

```bash
python3 src/make_book.py                        # 60,000 customers × 30 months, 6 products
python3 src/make_journeys.py                    # the journey layer on top of it
python3 src/make_book.py --legacy-size          # the pre-SD-S1 book (15,000 × 27, 3 products)
python3 src/make_book.py --n 5000 --months 24   # anything else
python3 src/make_book.py --seed 7 --out /tmp/b  # different seed / destination
```

**Calendar.** Panel month 0 is 2024-04; month 26 (the snapshot, "today" in the cockpit) is
2026-06; months 27–29 are the held-out future used to measure precision honestly. Under
`--legacy-size` the anchor reverts to the old calendar (month 0 = 2023-05, snapshot = month 23),
which is the month `score_and_pack.py` still hard-codes.

**Product vocabulary shim.** The canonical six-product vocabulary is
`home, lap, gold, auto, education, personal`. `score_and_pack.py` is frozen until SM-1 and still
speaks the three-product vocabulary, so the CSVs carry **both**: `product` / `p_prod` in the
compat spelling (`personal` written as `pl`) and `dwell_pl` duplicating `dwell_personal`, with
`product_canonical` / `p_prod_canonical` / `dwell_personal` beside them. Both shims are deleted
at SM-1. The alias map lives in `src/book/products.py`.

---

## 2. Population — `src/book/population.py`

60,000 customers, static attributes drawn once.

| Attribute | Distribution | Provenance |
|---|---|---|
| `segment` | salaried 60% / self-employed 25% / gig 15% | `assumed`. PLFS 2023-24 puts regular wage/salaried employment near a fifth of *all workers*; a bank **savings-account book** skews far more salaried because that is who gets a salary account opened for them, so the national figure is an anchor for the direction, not the level (`sourced-approx` for the PLFS anchor). |
| `age` | N(36, 9) clipped to [21, 62] | `assumed` (lending-age window). |
| `city_tier` | 1 / 2 / 3 at 38% / 40% / 22% | `assumed`. |
| `tenure_m` | U{8 … 179} months | `assumed`. |
| `consent` | 85% carry marketing consent | `assumed`. In production this is a live join against the DPDP consent register, not a draw. |
| `base_income` (recurring monthly credits) | lognormal(11.05, 0.35) salaried · (11.15, 0.50) self-employed · (10.45, 0.45) gig, clipped to ₹18k–₹900k. Medians ≈ ₹63k / ₹70k / ₹34k | `assumed`, shaped by PLFS 2023-24 regular-wage earnings (`sourced-approx` anchor). Deliberately above the all-India wage distribution — unbanked informal workers are absent from a liability book by construction. |
| `inc_drift` | N(0.004, 0.003) per month ≈ 5%/yr nominal | `assumed`. |
| `income_vol` | 5% salaried / 16% self-employed / 30% gig | `assumed`. The gig figure is what makes behavioural income estimation fail for gig workers, and that failure is reported honestly in the model card. |
| `rent_base` | 55% pay rent, at 12–30% of income | `assumed`. |
| `ext_emi_base` | 38% service an external EMI, at 6–22% of income | `assumed`. |
| `home_emi_base` | housing EMI for the 14% with an existing home loan, 18–32% of income (zero under `--legacy-size`) | `assumed`. RBI's sectoral credit data makes housing the largest personal-loan category by value (`sourced-approx` anchor); the per-customer level is assumed. |
| `has_auto_emi` | 22% | `assumed`. |
| `school_base` | 40% of over-29s, at 4–10% of income | `assumed`. |
| `fd_base` | 45% hold an FD, at 1.5–8× monthly income | `assumed`. |
| `owns_property` | logistic in age and log income → 32% of the book | `assumed`. |
| `has_home_loan` | 45% of owners → 14% of the book | `assumed`. |
| `gold_holding_g` | 70% hold gold; lognormal, median ≈ 45 g among holders | `assumed` shape. World Gold Council's estimate that Indian households hold on the order of 25,000 t of gold is the anchor (`sourced-approx`). |
| `dependants` | Poisson, mean rising with age, capped at 4 | `assumed`. |
| `has_card` | logistic in income, segment and tier → 31% of the book | `assumed` shape; RBI's credit-cards-in-force series is the anchor for the level (`sourced-approx`). |
| `has_insurance` | 55% | `assumed`. IRDAI's life-insurance penetration of roughly 3% of GDP is the anchor (`sourced-approx`). |
| `salary_day_base` | 1st 30% · 30th 18% · 5th 12% · 7th 12% · 10th 8% · 2nd–3rd 11% · 15th 5% · 25th 4% | `assumed`. Indian payroll clusters on the 1st and the last working day. |
| `salary_regular` | 97% salaried / 55% self-employed / 8% gig | `assumed`. This is the generative reason the *variance* of `salary_credit_day` is itself a gig signal. |
| `salary_sources` | 1 (mostly) salaried · 1 + Poisson(1.6) self-employed · 1 + Poisson(2.4) gig | `assumed`. |
| `other_bank_emi_share` | 10% service everything with us; the rest send 40–100% of their EMI elsewhere | `assumed`. **This is the gap AA / API 595/739 closes** — without account-aggregator consent the bank cannot see the other lender's EMI at all. |
| `upi_share`, `upi_ticket` | share of retail spend routed P2M ≈ 55/46/36% by tier; per-customer median ticket lognormal(log 300, 0.45) | `assumed`. NPCI's UPI product statistics — P2M as a majority of UPI volume, at a low ticket — are the anchor (`sourced-approx`). See §9.6 for the tension this creates. |
| `amb_threshold` | ₹10,000 / ₹5,000 / ₹2,500 by tier | `assumed`. Public schedules of charges run slabs of this shape; the exact numbers vary by product variant and are not reproduced from any bank's schedule. |
| `fee_sensitivity`, `doc_reluctance` | Beta(2,3) / Beta(2,4), shifted by segment | `assumed`. Journey friction truth, consumed by SD-S2, never a feature. |

---

## 3. Latent structure — `src/book/latent.py`

**Generative direction: intent is the cause, the channels are its consequences.** A customer
acquires a product-specific need; the need builds over a product-specific run-up; and while it
builds it *shows*. The model's job is to read the tells. Nothing in the generator lets a channel
cause an intent, so there is no circularity to leak.

### 3.1 Intent — `intent_<product>`, exported to the truth file

`intent[customer, product, month] ∈ [0, 1]` is the sum of

1. **base curiosity** — 0.02, scaled by eligibility (`assumed`);
2. **the ramp** — linear progress 0 → 1 across the run-up, scaled by the customer's signal
   strength `s ∈ {0} ∪ [0.45, 1.0]`, on the *manifest* product;
3. **shadow intent** — the same ramp at 0.6 × the substitution affinity on every other product,
   so a customer shopping for a gold loan carries real (smaller) personal-loan intent at the same
   time (`assumed`);
4. **archetype intent** — window shoppers carry genuine 0.20–0.40 interest they never act on;
   red herrings carry sub-threshold 0.05–0.15 ambivalence (0.15–0.32 if a call would convert
   them). Both `assumed`.

### 3.2 Run-up length by product

| Product | Months of observable run-up | SD-S4 decision window (days) | Provenance |
|---|---|---|---|
| `home` | 5–9 | 14 | `assumed` |
| `lap` | 4–8 | 14 | `assumed` |
| `auto` | 3–6 | 3 | `assumed` |
| `education` | 3–6 | 7 | `assumed` |
| `personal` | 2–5 | 1 | `assumed` |
| `gold` | 1–3 | 1 | `assumed` |

Ordering is the defensible part: property-backed borrowing takes a season, gold and personal
loans are decided in weeks. Under `--legacy-size` every product uses the old flat 4–8 months.

### 3.3 Product-specific triggers (how intent becomes observable)

| Product | Tells expressed during the run-up | Parameters | Provenance |
|---|---|---|---|
| `home` | rent step-up (the landlord hike that pushes a renter to buy), balance accretion (down-payment saving), FD broken late in the ramp, address change in the last third | rent × (1 + 0.38·ks); balance + 6–20% of credits; FD-break p = 0.20·s past 60% of the ramp | `assumed` |
| `auto` | fuel + cab surge with **no existing auto EMI** | fuel × (1 + 1.5·ks) if the primary tell is expressed, else 0.6 | `assumed` |
| `personal` | EMI stacking (external EMI creeping up), deepening pre-salary balance dip, rising card spend, rising external-EMI count | EMI + 8% of credits · ks; dip 6–22% of credits · ks; card × (1 + 0.6·ks) | `assumed` |
| `education` | school-fee outflow stepping up (admission and term fees), fee-season amplification | fees × (1 + 0.9·ks), × 1.6 in Apr–Jun | `assumed` |
| `gold` | acute liquidity squeeze — balance drawn down, deep pre-salary dip, mandate failures, minimum-balance charges. Short fuse. | dip 15–35% of credits · ks; balance × (1 − 0.12·ks) — both riding a **shared market factor** | `assumed` |
| `lap` | existing home-loan EMI present (equity), balance drawdown, FD broken, dwell | balance × (1 − 0.05·ks); FD-break p = 0.25·s past 50% | `assumed` |

`ks` = ramp progress × signal strength. Only **78% / 72%** of customers express the primary /
secondary tell of their product — nobody shows the whole textbook bundle, which is what stops the
features being collinear (`assumed`).

**A deliberate confounder.** Gold ramps ride a shared AR(1) market factor (ρ = 0.75, σ = 0.35),
so every gold prospect in the book deepens *at the same time*. A model that reads a balance
drawdown as a per-customer story will be wrong in high-factor months. `assumed`; it is a synthetic
series, not the gold price.

### 3.4 Capacity

`capacity_abs = median(credits, trailing 6 months) − (rent + external EMI + school fees +
insurance + 0.38 × median credits)`, with `capacity_ratio` the same over median credits. The
0.38 essential-spend floor matches what `score_and_pack.build_features` already assumes for
retained income, so the truth file and the model's estimate are directly comparable. `assumed`.

---

## 4. Cross-product substitution matrix — `src/book/products.py`

Plan SD-S5 pulled forward **as a data structure only**. Symmetric, diagonal 1.0, every value
`assumed`. It is used when sampling which product a latent intent actually manifests as: weights
are `SUBSTITUTION ** 4.0`, which leaves ~13% of converters taking a substitute for their
underlying need (`substituted` in the book file).

|  | home | lap | gold | auto | education | personal |
|---|---|---|---|---|---|---|
| **home** | 1.00 | 0.65 | 0.10 | 0.15 | 0.12 | 0.20 |
| **lap** | 0.65 | 1.00 | 0.25 | 0.15 | 0.30 | 0.35 |
| **gold** | 0.10 | 0.25 | 1.00 | 0.20 | 0.35 | 0.70 |
| **auto** | 0.15 | 0.15 | 0.20 | 1.00 | 0.12 | 0.45 |
| **education** | 0.12 | 0.30 | 0.35 | 0.12 | 1.00 | 0.45 |
| **personal** | 0.20 | 0.35 | 0.70 | 0.45 | 0.45 | 1.00 |

The *ordering* is the defensible part, not the numbers:
gold ↔ personal (both short-tenor liquidity; gold wins on rate, personal on speed and on not
pledging jewellery) · home ↔ lap (both property-backed; an owner refinances rather than buys) ·
auto ↔ personal and education ↔ personal (medium; an unsecured loan funds the down payment or the
fee deadline) · gold ↔ education (a jewellery-backed bridge over fee season).

**Eligibility gates** applied before sampling (`assumed`): `lap` requires owned property; `gold`
requires a gold holding; `home` × 0.25 if the customer already owns property and × 0.35 outside
age 24–48; `auto` × 0.30 if an auto EMI is already running; `education` × 0.15 with no dependants
past 35. These exist so the book contains no impossible states.

**Converter product mix by segment** (count shares, `assumed`; RBI's *Sectoral Deployment of Bank
Credit* is the anchor for the ordering — housing dominates by value, gold and other-personal by
account count — `sourced-approx`):

| Segment | home | lap | gold | auto | education | personal |
|---|---|---|---|---|---|---|
| salaried | 0.22 | 0.06 | 0.08 | 0.18 | 0.10 | 0.36 |
| self-employed | 0.18 | 0.14 | 0.18 | 0.16 | 0.06 | 0.28 |
| gig | 0.05 | 0.03 | 0.26 | 0.16 | 0.04 | 0.46 |

Realised mix at the default seed (after eligibility and substitution): personal 39%, auto 19%,
home 14%, gold 14%, education 10%, lap 4%.

---

## 5. Channels — `src/book/channels.py`

### 5.1 Carried over from the pre-SD-S1 book (unchanged)

| Column | Definition | Provenance |
|---|---|---|
| `credits` | recurring monthly credit inflow (salary / regular business receipts) | `assumed` |
| `bal_avg` | average balance; a damped net-flow recursion, 25% of net flow persists, floor ₹1,000 | `assumed` |
| `bal_min` | minimum balance in the month; 15–50% of the opening balance less the pre-salary dip, floor ₹500 | `assumed` |
| `rent`, `fuel_cab`, `school_fees`, `ecommerce` | 30–45% / 1.5–4.5% / — / 2–8% of credits | `assumed` |
| `ext_emi` | total external EMI outflow | `assumed` |
| `has_auto_emi` | static flag, repeated per row | `assumed` |
| `fd_bal` | fixed-deposit balance; halved on a premature break | `assumed` |
| `dwell_<product>` | minutes on the bank's own product pages | `assumed` |

### 5.2 New in SD-S1

| Column | Definition | Parameters | Provenance | Observed at default seed |
|---|---|---|---|---|
| `upi_p2m_count` | UPI person-to-merchant transactions | `upi_p2m_value / upi_ticket`, capped at 600 | `assumed`; NPCI UPI statistics anchor (`sourced-approx`) | mean 33/month |
| `upi_p2m_value` | value routed P2M | (0.50·essential + 0.80·e-commerce + 0.60·fuel) × `upi_share`, with +0.6%/month adoption drift | `assumed` | mean ₹8,900; implied ticket ₹270 |
| `salary_credit_day` | day-of-month the salary lands | fixed day + jitter {−2,−1,0,+1} at {10,22,56,12}% for the disciplined; U{1…28} every month for gig | `assumed` | mean day 10.8 |
| `salary_credit_source_count` | distinct recurring credit sources | static for the disciplined; Poisson resampled monthly otherwise, clipped 1–12 | `assumed` | mean 1.9 |
| `emi_outflow_to_other_bank` | standing debits to **other lenders** — the AA / API-595 gap | `ext_emi × other_bank_emi_share` | `assumed` | 43% of months non-zero, mean ₹3,839 |
| `external_emi_count` | distinct external EMI mandates | static base + housing loan + EMI stacking during a personal-loan ramp | `assumed` | 47% of months non-zero |
| `card_spend` | credit-card bill routed through the account. **A routing label over existing discretionary spend, not an extra outflow.** | 5–28% of credits × U(0.5,1.6), ×1.5 in Oct–Nov, ×(1+0.6·ks) under personal-loan stress | `assumed`; RBI credit-card spend per card (≈ ₹15k/month) is the anchor (`sourced-approx`) | ₹14,377/month among the 31% who hold a card |
| `insurance_premium` | premium outflow | 2–8% of annual credits for the 55% insured; 30% pay by monthly standing instruction, the rest in one annual renewal month | `assumed`; IRDAI penetration anchor (`sourced-approx`) | 20% of months non-zero |
| `min_balance_charge_flag` | average-monthly-balance shortfall penalty | `bal_min < amb_threshold`, enforced 85% of the time (banks waive), ₹150–600 | `assumed` | 0.9% of months — see §9.4 |
| `mandate_failure_count` | NACH / e-mandate bounces | Binomial(`external_emi_count`, p), p = 1.5% + 55% × squeeze, capped at 45% | `assumed`; NPCI NACH debit success ratios are the anchor (`sourced-approx`), but those are dominated by NBFC/MFI mandates so the level here is deliberately far lower | 2.7% of mandates fail |
| `fd_premature_closure_flag` | FD broken this month | the product-driven break, plus 0.2%/month ambient | `assumed` | 0.1% of months |
| `address_change_flag` | KYC address update | 0.4%/month base, ×6 in the last third of a home ramp (property finalisation), ×2 for renters under 32 | `assumed` | 0.5% of months |
| `nominee_change_flag` | nominee update | 0.2%/month base, ×3 at the very end of any ramp | `assumed` | 0.2% of months. **Deliberately near-useless** — not every new column should predict something. |
| `bonus_or_irregular_credit` | non-recurring credits, reported **separately from** `credits` | salaried: 45% in Mar–Apr, 25% in Oct–Nov, 2% otherwise, at 35–160% of a month's credits; self-employed and gig: 14% any month at 20–90% | `assumed` | 13% of months non-zero |

### 5.3 Seasonality (modern preset only; off under `--legacy-size`)

| Effect | Months | Multiplier | Provenance |
|---|---|---|---|
| School-fee season | Apr–Jun | fees × 1.6 | `assumed` |
| Festive discretionary spend | Oct–Nov | e-commerce × 1.4, card × 1.5 | `assumed` |
| Bonus season | Mar–Apr (FY end), Oct–Nov (festive) | see `bonus_or_irregular_credit` | `assumed` |
| Gold/liquidity market factor | every month | AR(1), ρ 0.75, σ 0.35 | `assumed` |

---

## 6. Hard negatives and uplift truth — `src/book/hard_negatives.py`

A synthetic book is only useful if the **negatives are hard**. All five archetypes are carried
over unchanged from the pre-SD-S1 book, because they are the reason the model cannot separate
products trivially. All shares `assumed` — they are a modelling choice tuned so precision@budget
lands in the band the plan pre-registers, not a measurement.

| Archetype | Share | What it does | What it caps |
|---|---|---|---|
| `window_shopper` | 9% of non-converters (8.4% of the book) | heavy product-page dwell for four months, no financial movement, never buys | punishes any model leaning on browsing alone |
| `dormant_rich` | 7% of non-converters (6.1%) | permanently fat balance (≥ 4.5× income), no intent | capacity ≠ intent |
| `red_herring` | 14% of non-converters (12.8%) | a genuine financial run-up — an absorbed rent hike, a new commute, an external EMI that just keeps being paid — with no browsing and no purchase | **caps precision**, and hides most of the persuadable customers |
| `near_miss` | 3% of non-converters (2.7%) | the full bundle, ramp *and* browsing, then life happens | indistinguishable from a converter at the snapshot, by construction |
| `silent_converter` | 12% of converters | converts with zero signal strength: no ramp, no dwell | **caps recall** |

**Uplift potential outcomes** (`score_and_pack.py` reads these column names directly — they are
load-bearing):

| Column | Meaning | Share | Provenance |
|---|---|---|---|
| `dnd` | do-not-disturb: would convert organically, but a pushy call kills the sale | 12% of converters (1.1% of the book) | `assumed` |
| `persuadable` | converts **only** if contacted inside an active-signal window | 55% of near-misses + 18% of red-herrings (3.7% of the book) | `assumed` |
| `p_win_start`, `p_win_end`, `p_prod` | the window in which a call converts them | — | `assumed` |

This is what separates propensity ("who will convert") from uplift ("who converts *because* you
called"), and it is the reason the persuadables live among the lookalikes rather than at the top
of the propensity ranking.

---

## 7. Base-rate hooks (for SD-S4)

`BaseRates` in `src/book/__init__.py` exposes the knobs SD-S4 will solve against:

| Field | Default | Meaning |
|---|---|---|
| `target_contact_conversion_3m` | 0.0135 | Bank-stated cold-calling baseline (~1%, engineered to 1.3%). The converter share is **back-solved** from this rather than hard-coded, so moving the target moves the whole book coherently: `converter_share = target × (months − first_event_month) / horizon`. |
| `first_event_month` | 9 | Earliest disbursement month — a run-up needs history in front of it. |
| `label_horizon_months` | 3 | The label window `score_and_pack` measures, `(m, m+3]`. |
| `theta_contact_effect` | `None` | **Not yet solved.** SD-S4 fills this in when it fits the contact effect so random-contact disbursement lands in [8%, 10%] on the *journey* label. |

`build.check()` asserts the realised 3-month random-contact rate stays within 0.6 pp of the
target, and that the hard-negative shares stay in band, so a generator regression fails the run
rather than quietly flattering the model.

---

## 8. Reproducibility, performance, equivalence

**Reproducible.** `--seed` fully determines the output. Each block of the generator draws from its
own named RNG substream (`substream(seed, "channels")` etc.) rather than one sequential stream, so
adding a channel cannot shift the numbers another block produces.
`tests/test_book_equivalence.py::test_same_seed_is_reproducible` asserts frame-level equality.

**Performance** (MacBook, Python 3.12, numpy 2.4 / pandas 3.0):

| Size | Generation | + CSV write | Budget |
|---|---|---|---|
| `--legacy-size` (15,000 × 27) | 0.4 s | **4.0 s** | < 10 s |
| default (60,000 × 30) | 2.1 s | **21.8 s** | < 60 s |

The pre-SD-S1 row loop took 8.6 s for the legacy size alone and would have taken minutes at the
new size. The only remaining loop is over **months** (30 iterations), which is unavoidable: the
balance path is a recursive state machine and the trailing-6-month capacity median needs the
months already produced. Everything inside it is vectorised across customers.

**Equivalence** (`tests/test_book_equivalence.py`, at `--legacy-size`). Vectorising changes the
*order* random numbers are drawn in, so bit-for-bit equality is impossible; what is asserted is
distributional equivalence against a fixture summarising the original row loop (git blob
`26454a512`, commit `435263f`):

* the legacy schema survives — every legacy column, in its original position (additions allowed,
  removals not);
* quantiles (p10/p25/p50/p75/p90) and means of all twelve feature-bearing columns within 6%;
* random-contact 3-month conversion within 0.2 pp (1.44% vs 1.37%);
* archetype shares within 2 pp;
* converter product mix within 4 pp.

All pass. The `_legacy.py` copy of the old loop was deleted once the fixture existed; recover it
with `git show 26454a5128aafcd8a94b43a6f1e6e3e909dca171`.

**Downstream metrics.** `score_and_pack.py` (unchanged) on the `--legacy-size` book: per-product
AUC 0.82 / 0.83 / 0.96, macro 0.872, top-2% precision 45.5% at 28.7× lift, uplift 33.6 vs 10.9
incremental conversions per 1,000 calls. The pre-SD-S1 book produced 0.85 / 0.88 / 0.95, macro
0.893, top-2% 36.0% at 27.9× lift, uplift 30.3 vs 11.4. Across four seeds the vectorised generator
spans macro AUC 0.871–0.899 and top-2% precision 24.7–42.9%, so both books sit inside the same
seed-to-seed spread — **the single-seed headline numbers in the current README were never stable**,
which is exactly why the validation lane pre-registers ≥ 5 seeds with confidence intervals.

---

## 9. Known unrealisms

Written down deliberately. Every one of these is a place a jury could push.

1. ~~**No application journey.**~~ **Fixed at SD-S2/SD-S3** — see §11. The book itself still
   carries conversion as a single `event_month`; the stages, the drop-offs, the ₹1,000 fee balk
   and the document refusal live in `data/journeys.csv` beside it. What remains unrealistic
   about *that* layer is listed in §11.11.
2. **No delinquency.** The liability book never defaults, so the capacity estimate is never
   validated against actual repayment. Capacity is an assumption about affordability, not a
   measured outcome.
3. **One product, once.** Every converter takes exactly one product exactly once in the panel.
   No repeat borrowing, no rejection, no prepayment, no cross-sell sequence, no top-up.
4. **Balances are too high, so balance-stress channels are too rare.** Median minimum balance is
   ≈ ₹53k against a tier-1 AMB floor of ₹10k, so `min_balance_charge_flag` fires in under 1% of
   months and mandate failures in under 2%. In a real savings book both are materially more
   common. This is inherited from the pre-SD-S1 income and balance model, which was kept for
   equivalence; it should be revisited when the equivalence constraint is retired.
5. **`bal_min` is a draw, not a path.** There is no intra-month transaction sequence, so the
   minimum balance is sampled from the opening balance rather than being the true minimum of a
   ledger. Anything that would depend on transaction *ordering* within a month is unavailable.
6. **UPI ticket vs UPI count cannot both match NPCI.** P2M value is pinned to retail spend and
   count to per-user frequency; under a single ticket distribution the implied average ticket
   (₹270) lands below NPCI's reported P2M average. We chose to match frequency.
7. **`credits` excludes bonuses.** Total credits is the sum of two columns. A real core banking
   statement shows one stream, and separating them is a convenience the model should not rely on.
8. **Everything is observed.** No missing data, no garbled narration, no unclassified merchants,
   no customer with under six months of history. A real book has all four. Missingness blocks are
   not modelled here and should be added before the leakage and stress runners (validation 07/10)
   claim anything about robustness.
9. **Dwell assumes a clean analytics-to-CIF join.** Product-page dwell presumes web/app analytics
   are joined to the customer ID. In practice that join is partial and biased toward app users.
10. **Consent is static.** A single per-customer flag. DPDP consent is time-varying, purpose-scoped
    and revocable; modelling it as a constant flatters the consent story.
11. **Seasonality is a fixed calendar multiplier.** Identical every year. Festival dates drift,
    fee calendars differ by board, and there are no macro shocks of any kind.
12. **The gold market factor is invented.** An AR(1) series, not the gold price.
13. **Substitution is resolved once, at event time.** A real customer's product choice depends on
    what they were offered, at what price, and by whom — none of which exists in this book yet.
14. **Thin demographics by design.** City tier is a three-level integer; there is no pin code, no
    gender, no religion, no caste, no marital status. That is a policy choice (see the model's
    excluded-features list), and it does mean geography-driven realism is absent.
15. **No lifecycle.** No joint accounts, no NRI accounts, no minors, no dormancy, no account
    closure, no salary-account churn to another bank, no fraud or mule behaviour.
16. **Three of six products are invisible to the current scorer.** `score_and_pack.py` still trains
    only home / auto / personal, so the ~28% of converters taking `lap`, `gold` or `education` are
    scored as negatives. That is a scorer limitation (SM-1), not a data limitation, but it is why
    precision at the new default size (29.5% at top-2%) reads lower than at legacy size.

---

## 10. Change log

| Version | Date | Change |
|---|---|---|
| SD-S2 / SD-S3 | 2026-09-16 | Application-journey layer in `src/journeys/`: eight stages, a discrete-time hazard with solved intercepts, per-stage timeouts, multi-attempt histories, five channels, and window shopping as a causal latent read through four independent signal channels. Three new artefacts plus a params manifest; point-in-time-safe feature builder for L7. |
| SD-S1 | 2026-09-16 | Vectorised into `src/book/`; 60,000 × 30; six products (`pl` → `personal` with a compat alias); 14 new channels; explicit latent intent/capacity exported to `liability_book_truth.csv`; cross-product substitution matrix; back-solved base rate; equivalence and performance tests. |
| pre-SD-S1 | 2026-07-10 | `src/make_book.py` row loop: 15,000 × 27, three products. |

---

## 11. Application journeys — `src/journeys/`

> **The mandate.** Conversion means **disbursement**, not lead creation. The population that
> matters is the **drop-offs** — customers who started an application and did not finish. Window
> shoppers are real and they have tells: vague answers, refusal to share details, balking at the
> ₹1,000 processing fee, refusing documents, revisiting several products without committing.
> Precision over recall. The book alone could express none of this; §11 is the layer that does.

```bash
python3 src/make_book.py && python3 src/make_journeys.py     # the book first, always
python3 src/make_journeys.py --seed 8                         # a different journey draw
python3 src/make_journeys.py --book-dir /tmp/b --out /tmp/b
```

The book is **read-only ground truth** to this layer. It already decided who disburses and in
which month; the journey layer never re-decides that, it draws a *path* consistent with it. Every
assertion in `journeys.build.check()` that starts "consistency with the book" exists to make that
non-negotiable in code rather than in prose.

### 11.1 The funnel

Eight stages, seven gates:

```
start → eligibility → kyc → docs → fee (₹1,000) → offer → accept → disburse
      g0           g1    g2     g3            g4        g5       g6
```

At each gate,

```
P(advance) = σ(α_stage + β·intent + γ·capacity + δ_stage·friction + product_effect + channel_effect)
```

and otherwise the attempt **times out** at that stage: it sits there for a per-stage number of
days and the file is closed. `last_stage` is where it stopped — which is exactly the
`stage_reached` cut `validation/criteria.yaml` pre-registers (8 levels), and the cut that makes
the drop-off population visible at all.

`intent` and `capacity` come from `data/liability_book_truth.csv`, read at the month **before**
the application: the need builds, *then* the customer applies. `β = 2.20`, `γ = 1.60`, both
centred. All `assumed`.

**The intercepts are solved, not written down.** A hand-set `α_s` makes the funnel's shape an
accident of whatever the friction weights happen to be. Instead the shape is the declared
parameter and `funnel.solve_intercepts()` fits `α` to two constraints at once:

| Constraint | Target | Realised (default size) |
|---|---|---|
| where abandonments land | `ABANDON_SHARE` below | within 0.3 pp at every stage |
| the hazard's own completion rate, over all attempts | the book's (disbursed ÷ attempts) | 25.8% vs 25.8% |

The second constraint is what keeps the conditioning honest. Without it the shape alone is
satisfied by a degenerate funnel in which the model thinks nobody could ever finish and the 26%
who do are a miracle. With it, attempts that disburse come out with visibly better odds
(mean `p_complete` 0.51) than attempts that do not (0.17) — asserted in-script, and re-asserted
as an AUC floor in `tests/test_journeys.py`.

**Funnel shape** (`funnel.ABANDON_SHARE`, share of *abandonments* at each stage, all `assumed` —
shaped like a retail-lending funnel for an existing bank customer, not measured from one):

| stage | start | eligibility | kyc | docs | fee | offer | accept |
|---|---|---|---|---|---|---|---|
| target | 18% | 14% | 10% | 22% | 20% | 9% | 7% |
| realised | 18.1% | 14.1% | 9.9% | 22.2% | 20.1% | 8.7% | 7.0% |

Documents are the classic killer and the ₹1,000 fee is the mentors' signature drop. The tail after
Offer is thin because a customer who has paid a fee and seen a number usually finishes.

**Solved intercepts** at the default size: start 2.03 · eligibility 2.83 · kyc 2.95 · docs 2.55 ·
fee 1.66 · offer 2.06 · accept 1.78. They are written to `data/journey_params.json` on every run.

**Performance.** The whole layer costs **≈ 6 s** end to end at the default 60,000 × 30 book
(2 s to read the book's three CSVs and generate, 2 s of in-script assertions, 2 s to write) —
well inside the 60 s tuning budget plan §J.1 sets. Everything is vectorised across attempts; the
only Python-level loops are over the seven gates, the three attempt slots and the twelve
fixed-point iterations of the intercept solver.

### 11.2 Conditioning on the book

An attempt the book says disburses walks every stage. An attempt that abandons draws its stopping
stage from the hazard **conditioned on not disbursing**,

```
P(abandon at s | does not disburse) = [∏_{j<s} p_j · (1 − p_s)] / (1 − ∏_j p_j)
```

which is Bayes conditioning, not a re-roll. Because window-shopper propensity loads negatively on
`is_converter` (§11.6), the attempts the book sends to a disbursement systematically carry better
covariates, so the conditioning is not fighting the hazard.

### 11.3 The 8–10% baseline: which denominator, and why

**This is the single most important interpretation in this lane, and it is a reading, not a fact.**

The mentors said the bank's baseline for RM-called prospects is 8–10% disbursement and the target
is 30%. The plan turns that into `baseline ≈ 9%` and the headline *"9 → 30 disbursements per 100
RM calls"*. Three denominators are available and they are not close to each other:

| Candidate denominator | Rate in this data | Verdict |
|---|---|---|
| a random consented customer, contacted at the snapshot, disbursing inside the product window | ~0.1% | far too low; this is the book's cold-call rate (1.35% at a three-month horizon), the number the README used to quote as "~1%" |
| a random *application attempt* reaching Disburse | **25.8%** | this is a funnel completion rate, not a calling baseline |
| a random **drop-off** — a customer who abandoned an application — later disbursing | **9.0%** | ✅ adopted |

The third is adopted because it is the only one that matches all three of: the mentors' own words
("the population that matters is drop-offs"), the business action being priced (an RM works a lead
list, not 60,000 savings customers), and the size of the number. It is also realistic: a recovery
rate near one in eleven is what an untargeted call-back campaign on a stale drop-off list gets.

`cfg.target_recovery_rate` is solved for, not observed: `attempts.select()` scales the share of
converters that carry an earlier abandoned attempt so the realised rate lands on 9%, and
`check()` fails the run outside [8%, 10%].

**What SD-S4 and L9 have to decide.** `validation/criteria.yaml` SK-01 registers
`random_contact_disbursement_rate ∈ [0.08, 0.10]` against a label definition written at the
*(cust_id, month)* grain of the book. On that grain the number is ~0.1%, not 9%. Either SK-01's
scoring population is the drop-off list (the reading above), or the contact effect θ has to be
large enough to *cause* 8–10% of random contacts to disburse within days, which would not be
credible. This lane has no authority to amend a pre-registered criterion; it is flagged here, in
`journey_params.json`, and in the SD-S2 hand-off.

### 11.4 Volumes

| Quantity | Target | Source | Realised |
|---|---|---|---|
| customers with ≥ 1 attempt | 30% of the book (band 25–35%) | plan §B/L6 SD-S2, `assumed` | 30.0% (18,000 of 60,000) |
| attempts | — | — | 21,682 |
| attempts per applicant | — | — | 1.20 (14,465 × 1, 3,388 × 2, 147 × 3) |
| disbursed / abandoned / still open | — | — | 25.8% / 73.8% / 0.3% |
| drop-off recovery (§11.3) | 9% (band 8–10%) | mentor-stated, `assumed` | 8.96% |
| window shoppers among drop-offs | 30% (band 25–35%) | plan §B/L6 SD-S3, `assumed` | 30.0% |
| attempts for an ineligible product | 2% | `assumed` | 1.1% |

Who applies is not uniform: the selection weights the book's hard-negative archetypes heavily,
because that is what they are for. A *near-miss* (the full run-up, then life happens) is a
drop-off by definition and is 12× as likely to apply as a plain non-converter; a *window shopper*
6×; a *red herring* 3×; a *dormant-rich* customer 0.45× (capacity without intent rarely even
starts). Latent intent then scales all of them. All `assumed`.

**Attempts still open when the panel ends** carry no `abandoned_at` and no `disbursed_at` — they
are `in_flight`. Only 0.3% of attempts end that way, but as at the *snapshot* month the
point-in-time view (§11.9) shows ~1% of customers with a live application, which is the queue an
RM would actually be working.

### 11.5 The clock

Journey length is scaled by the product's own decision window (`book.products.DECISION_WINDOW_DAYS`
— `personal` 1, `gold` 1, `auto` 3, `education` 7, `home` 14, `lap` 14, plan §B/L6 SD-S4):

* total advance time ~ Gamma, mean **0.42 × window**, split across the seven gates
  5/8/12/30/12/18/15 % — documents take the longest;
* **stalls** are the realistic reason a disbursement misses its window: a customer who balked at
  the fee (mean 0.26 × window) or had to go and find a document (0.24 × window) and then complied;
* **timeouts** before the bank closes a stalled file: 2.5 / 4 / 6 / 11 / 8 / 9 / 12 days at a
  7-day product, scaled by product speed, capped at 45 days;
* an RM call that *precedes* the application leads it by up to 0.12 × window.

All `assumed`. Realised median journey, disbursed attempts: gold 0.5 d · personal 0.5 d ·
auto 1.6 d · education 3.9 d · lap 8.1 d · home 8.2 d.

**Window respect** — of disbursements where an RM had contacted the customer, the share where the
disbursement fell inside the product's window — is **94.9%** at the default size (92.5–96.0%
across seeds 7/8/11). `validation/criteria.yaml` SK-04 pre-registers ≥ 90% for a *different*
measurement (the clock starting at the model's contact at the snapshot, not at the RM's call
during the journey); the generator's figure is the upstream headroom, not the criterion.

**Attempts never overlap.** A customer's next application starts after the previous one closed
plus a return gap (Gamma, mean 26 days; realised median gap between attempts 54 days). A
converter's final attempt is *pinned* to the book's `event_month`, so an earlier attempt that
would run into it is compressed rather than pushing it.

### 11.6 Window shopping as a causal negative (SD-S3)

`shopper_propensity` is a per-customer latent. Its logit (all weights `assumed`):

| term | weight | why |
|---|---|---|
| the book's `window_shopper` archetype | **+4.30** | browses hard, never buys — the journey layer makes the archetype *behave* rather than replacing it |
| `near_miss` | +0.90 | the full textbook run-up and then no purchase |
| `red_herring` | +0.40 | a real financial event, no purchase intent |
| curiosity (new latent: browsing breadth) | +0.70 | |
| price sensitivity = the book's `fee_sensitivity` | +0.35 | reused, not re-invented, so the fee balk cannot contradict the book |
| document reluctance | +0.18 | |
| **`is_converter`** | **−1.60** | this is the term that gives the four signals a negative marginal effect on disbursement |
| peak latent intent | −1.10 | |
| intercept | solved (−2.31) | so shoppers are 30% of abandoned attempts |

Realised: **73.2%** of the book's `window_shopper` archetype are journey shoppers, against 8.9% of
everyone else; 69% of shoppers are book-archetype window shoppers, so the latent is correlated
with the archetype without collapsing into it.

**Informative, not deterministic.** 0.8% of disbursements are made by shoppers — small, as the
plan requires, but not zero. 4.2% of attempts balked at the fee and paid it anyway, and 70% of
those went on to disburse; 66% of fee-balkers are *not* shoppers, and 27% of the customers who
refused a document went on to file a complete set. `criteria.yaml` SK-05
registers a deliberately modest `shopper AUC ≥ 0.70`; the tests here assert an upper bound of 0.95
as well, because a synthetic book where shoppers are trivially separable has made the problem too
easy.

**Where shoppers die.** The shopper drag is per-gate and deliberately not uniform:
`(+0.15, +0.10, 0.0, −0.85, −1.05, −0.25, −0.30)`. Window shopping is free — a shopper is happy to
fill in a form and hear whether they qualify, that is what they came for. They stop when the bank
asks for something: documents, then a ₹1,000 cheque. That is what puts them at Docs and Fee, where
the mentors said they die, rather than at Start.

**Deliberately absent: an occupation term.** An explicit `+ gig` in the shopper logit would
manufacture the fairness problem the model is then measured on (SK-23/SK-24). There is none. Gig
workers still come out marginally shoppier — 26.8% vs 20.7% salaried and 24.0% self-employed —
purely through the book's own `fee_sensitivity`, which carries `+0.25 × gig`. That inheritance is
disclosed rather than hidden, and a test caps the between-segment ratio at 1.6.

### 11.7 The four signals, and when each becomes knowable

One **commitment** latent (`1.10 × is_converter + 0.55 × z(peak intent) + noise`) is read four
times through four *independent, noisy* channels. Independent measurement error is the whole
point: without it the four signals are one signal, and only the most precise of them survives a
regression that controls for the others.

| Mentor signal | Column | Knowable from | Realised rate |
|---|---|---|---|
| vague answers | `answers_blank_ratio` | `started_at` — it is the form they submitted | median 0.25 |
| won't share details | `income_shared = 0` | `started_at` | 20.3% |
| balks at the ₹1,000 fee | `fee_balk` (+ `fee_balk_at`) | the **Eligibility** conversation, where the fee is quoted | 30.0% of attempts that got that far |
| refuses documents | `doc_refusal` (+ `doc_refusal_at`) | the same conversation, where the checklist is read out | 28.2% |

> **Why the fee balk is recorded at Eligibility and not at the Fee stage.** The processing fee is
> quoted when the bank confirms eligibility, four stages before it is due; so is the document
> checklist. Recording both there is how a branch RM actually works — and it is also the only
> coding under which the two signals are honestly negative. Define `fee_balk` as "abandoned at the
> Fee stage" and it becomes *positive*: reaching the Fee stage means surviving four gates, and that
> survivorship outweighs the balk. We hit exactly that inversion in development. The fix was to
> model the disclosure where it really happens, not to re-weight the friction until the sign came
> out right.

The **measured** consequences are separate columns and arrive later: `docs_requested` /
`docs_supplied` at the Docs stage, `fee_paid` / `fee_paid_at` at the Fee stage,
`amount_offered` at Offer. Each is null until the attempt reaches the stage that produces it — a
customer who never saw the fee page cannot have paid it, and the file says so.

Realised marginal effects (logistic of disbursement on the four, 21,682 attempts, all
p < 10⁻⁶): blank ratio **−4.35**, income refused **−1.44**, fee balk **−0.87**, document refusal
**−1.03**. Stable across seeds (−4.4 to −4.7, −1.35 to −1.51, −0.81 to −0.89, −0.96 to −1.16 at
seeds 7/8/11). These are the signs SK-15 will ask the *model* to recover.

The fifth mentor behaviour, **not picking up the RM's call**, is `rm_contacted`: a shopper is 55%
less likely to be reached (20.7% vs 16.4% on non-`rm-call` attempts). An `rm-call` application is
exempt by construction — it started *because* they answered.

### 11.8 Channels

| | branch-walk-in | rm-call | app | web | dsa |
|---|---|---|---|---|---|
| share of attempts | 23.3% | 21.0% | 27.8% | 16.5% | 11.4% |
| disbursement rate | 34.7% | 33.3% | 20.7% | 18.2% | 17.5% |
| gate effect | +0.35 | +0.25 | 0.00 | −0.15 | −0.25 |

Channel is an **outcome** of commitment, not an exogenous assignment: a customer who means it
walks into a branch or takes the RM's call, a tyre-kicker taps the app at midnight. The base mix
is by segment and city tier (tier 3 walks in, tier 1 taps), then log-tilted by a noisy reading of
commitment. So the by-channel gap above is part selection and part friction — deliberately
confounded, because that is what the real comparison looks like, and it is what gives the
pre-registered by-channel cut something to find. All `assumed`.

### 11.9 Point-in-time features for L7 / SM-3

`journeys.features.journey_features_as_at(journeys, events, as_at)` returns one row per customer
with at least one attempt open or closed by `as_at`. **A customer with no row has no application
history — that is not the same as having a bad one, and must not be encoded as a zero.**

The six contract columns are spelled exactly as `data/bank/SCHEMA.md` specifies for the `journey`
family of `enriched.csv`: `journey_stage_reached`, `journey_blank_field_ratio`,
`journey_refused_income`, `journey_fee_balk`, `journey_doc_refusal`,
`journey_multi_product_revisits`. Sixteen more carry the same prefix for SM-3
(`journey_attempts`, `journey_open_now`, `journey_ever_abandoned`, `journey_ever_disbursed`,
`journey_stage_idx`, `journey_last_product`, `journey_last_channel`, `journey_fee_paid`,
`journey_docs_shortfall`, `journey_rm_contacted`, `journey_revisits_30d`,
`journey_products_viewed_30d`, `journey_amount_requested`, `journey_stated_income_ratio`,
`journey_days_since_last_event`, `journey_days_since_first_start`).

A fact is used only if it was on the bank's screen at `as_at`. An attempt that has started and not
finished is **in flight**: its stage is whatever it had reached, and its outcome is unknown.
`tests/test_journeys.py::test_features_as_at_use_no_future_information` recomputes the whole frame
from tables *physically truncated* at `as_at` and demands the same answer; that test found and
fixed one real leak (days-since-last-event was reading an in-flight attempt's future stage entry).
This is the property `validation/runners/07_leakage.py` (SK-17, zero tolerance) asserts.

### 11.10 Column shims

Two, both temporary, both in `journeys/build.py`:

* **validation contract aliases.** `07_leakage.py` pre-registered its `INPUTS` as
  `data/application_journeys.csv` with columns `cust_id, stage_reached, start_ts, abandon_ts,
  disburse_ts, blank_ratio, income_refused, revisit_count`. The file here is `data/journeys.csv`
  with the names the SD-S2 brief specifies, **plus** those eight as duplicate columns so the runner
  can be written against either. Delete them when runner 07 lands.
* **`rm_id` is empty** on every row. SM-4 fills it from the round-robin roster (API 442
  `accountManager` / API 508 HRMS); emitting placeholder ids now would only have to be undone.

### 11.11 Known unrealisms — the journey layer

These are additional to §9, which covers the book.

1. **Nobody is rejected.** Every abandonment is the *customer* walking away. There is no credit
   decline, no policy rejection, no negative bureau pull, no fraud decline. Real funnels lose a
   material share of applications to the bank's own "no", and a model trained here cannot tell the
   two apart. The Eligibility stage is the nearest thing, and even there the customer times out
   rather than being told no.
2. **The ₹1,000 fee is flat across all six products.** Real schedules of charges scale with ticket
   size and are routinely waived in campaigns. The mentors named one number and this layer uses it.
3. **An attempt is for exactly one product.** No one applies for two things at once, and nobody is
   cross-sold mid-journey into a different product — which is precisely the behaviour the
   "menu of four" is meant to exploit, so the menu's value cannot be measured on this data alone.
4. **The offer is a one-shot number.** There is no negotiation, no counter-offer, no re-pricing, no
   rate shopping against another lender. `amount_offered` is drawn once from capacity and a haircut.
5. **No partial disbursement, no cancellation after disbursement, no top-up.**
6. **6.3% of attempts begin one month after the month whose latents drove them**, because an
   earlier attempt of the same customer was still open when the drawn month arrived. The generator
   therefore read *older* information than the application, never newer — the safe direction — and
   `journey_truth.latent_month` records which month was used so the difference is auditable.
7. **Stage durations are independent draws.** A customer who is slow at KYC is not slow at Docs.
   Real files have a persistent "this one is dragging" character that this misses.
8. **Timeouts are the only abandonment mechanism**, so there is no "abandoned in three seconds
   because the form asked for a PAN". The `start` stage absorbs all of that into one distribution.
9. **No seasonality in applications.** The book has fee-season and festive effects on spending;
   the journey layer has none on volumes, which is wrong — loan applications are strongly seasonal.
10. **Channel is fixed for the whole journey.** Nobody starts on the app and finishes in a branch,
    which is the most common real pattern of all.
11. **The recovery population is generated, not observed.** Which drop-offs come back is drawn from
    a latent return propensity (§11.3); no contact, campaign or nudge causes it, because the contact
    effect θ is SD-S4's to fit. Until then, "what an RM call is worth" is not in this data.
12. **Every application is attributed to exactly one customer in the book.** There is no walk-in
    prospect, no joint application, no co-applicant, no guarantor — consistent with lead generation
    being out of scope, but it means the funnel has no top-of-funnel at all.
