# DATA CARD — SANKET synthetic liability book

**Artefact:** `data/customer_panel.csv`, `data/customer_book.csv`, `data/liability_book_truth.csv`
**Generator:** `src/book/` (CLI wrapper: `src/make_book.py`)
**Version:** SD-S1 (plan §B/L6), 2026-09-16 · supersedes the pre-SD-S1 row-loop generator
**Status:** initial card. SD-S2 (journeys), SD-S3 (window-shopper as a causal negative), SD-S4
(label windows + contact effect θ), SD-S6 (campaign/contact history) and SD-S7 (realism suite)
are **not yet implemented**; §9 says so explicitly.

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

```bash
python3 src/make_book.py                        # 60,000 customers × 30 months, 6 products
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

1. **No application journey.** Conversion is a single `event_month`. There are no stages, no
   drop-off, no ₹1,000 fee balk, no document refusal — SD-S2 adds them, and SD-S3 then replaces
   the window-shopper *archetype* with window-shopping as a causal outcome of the journey. Until
   then the drop-off population the mentor asked for does not exist in this book.
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
| SD-S1 | 2026-09-16 | Vectorised into `src/book/`; 60,000 × 30; six products (`pl` → `personal` with a compat alias); 14 new channels; explicit latent intent/capacity exported to `liability_book_truth.csv`; cross-product substitution matrix; back-solved base rate; equivalence and performance tests. |
| pre-SD-S1 | 2026-07-10 | `src/make_book.py` row loop: 15,000 × 27, three products. |
