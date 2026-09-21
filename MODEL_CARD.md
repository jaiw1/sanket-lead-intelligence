# SANKET — Model Card

**Model:** one gradient-boosted classifier (LightGBM) that ranks a bank's **drop-off
population** — customers who started a loan application and walked away — and offers each of
them a **menu of four products** with a calibrated probability, a reason, a decision window
and a date to call by.

**Status:** research prototype on synthetic data. Nothing here has been fitted to, validated
on, or deployed against real customers. Every number below is reproducible from this repo with
`python3 src/make_book.py && python3 src/make_journeys.py && python3 src/score_and_pack.py`.

**Owner:** RR Squad (Jai Wadhwa, Yuvraj Kundargi) — IDBI Innovate 2026, Prospect Assist AI track.
**Card version:** SM-1/SM-2/SM-3/SM-4/SM-5/SM-6. **Written:** 2026-09-16.

---

## 1. What changed, and why it matters

The pre-SM-1 pipeline trained **three** LightGBMs — one each for home, auto and personal loans
— over the whole liability book, and reported *"1% → 36% conversion, a 28× lift"*.

Three things were wrong with that, and the mentors named all three.

| Was | Is | Why |
|---|---|---|
| three models, one per product | **one** model, `product` as a categorical over a stacked (customer, month, product) frame | a per-product model cannot share what it learns about "this customer is ready to borrow", and has nothing to say about the three products it never saw |
| scored the whole liability book | scores the **drop-off population** only | a customer who never applied is a lead-generation problem, and lead generation is out of scope |
| baseline = random call to *anyone* ≈ 1% | baseline = random call to a **drop-off** ≈ 9% | the old denominator flattered the model by roughly 3×. The claim is now `9 → 29 disbursements per 100 RM calls`, built from the two measured numbers and never typed |
| conversion = an event on the book | conversion = **disbursement inside the product's decision window, after an RM contact** | mentor mandate. personal 1d · gold 1d · auto 3d · education 7d · home 14d · lap 14d |
| three products | **six** | home, loan-against-property, gold, auto, education, personal |

`1% → 36%` and `28×` are retired. Nothing in `src/model/` can emit them: the headline string is
assembled from the measured baseline and the measured precision at the registered budget
(`model.metrics.headline`), and a test asserts it moves when the numbers move.

---

## 2. Intended use, and what it must not be used for

**Intended.** Ordering a relationship manager's outbound calling list for the coming month,
over customers who already applied for credit with this bank and did not finish. Each lead
carries: a ranked menu of four products with calibrated probabilities, the reasons the model
used, the **negative** signals it also used, an EMI headroom figure, a bilingual call script,
and a `contact_by` date derived from the offered product's decision window.

**Not for.**

* **Not a credit decision.** The model estimates whether a conversation will *convert*, not
  whether the customer can repay. It has no bureau data, no arrears data and no underwriting
  in it. Nothing here may gate, price or decline an application.
* **Not lead generation.** It cannot rank a customer with no application history; the
  population is defined by having abandoned one.
* **Not a contactability decision.** Who *may* be called is decided by the suppression rule
  before scoring (§7), not by the score.
* **Not calibrated for real customers.** The probabilities are calibrated against a synthetic
  generator whose parameters were chosen to match mentor-stated rates. On real data the
  machinery transfers; the numbers do not.

---

## 3. Data

| Table | Grain | Rows (default seed) | Built by |
|---|---|---|---|
| `data/customer_panel.csv` | customer × month | 60,000 × 30 | `src/book/` (SD-S1) |
| `data/customer_book.csv` | customer | 60,000 | `src/book/` (SD-S1) |
| `data/journeys.csv` + `journey_events.csv` | application attempt / stage transition | 21,682 / 119,793 | `src/journeys/` (SD-S2, SD-S3) |
| `data/campaigns.csv` | outbound touch | 373,800 | `src/journeys/campaigns.py` (SD-S6) |
| **`data/labels.csv`** | **(customer, month) of the drop-off pool** | **127,767 over 13,258 customers** | `src/journeys/labels.py` (SD-S4) |
| `data/label_truth.csv` | same grain, latents | 127,767 | measurement only |

Everything is **synthetic**. `DATA_CARD.md` carries the full provenance table, the
sourced-vs-assumed split and 30+ documented unrealisms. Every parameter in the journey, label
and campaign layers is `assumed`; eight book parameters carry a `sourced-approx` anchor.

**Training frame.** `data/labels.csv` filtered to `eligible_for_contact = 1` — consented,
contactable customers with an abandoned attempt in the trailing 365 days and no disbursement in
flight. Each such (customer, month) row becomes **six** rows, one per candidate product.

---

## 4. Label

`label_disbursed_in_window` — **a potential outcome under contact, Y(1)**: *if an RM called
this customer this month, would a disbursement of some product follow inside that product's
decision window?*

It has to be a potential outcome, because both pre-registered bands are statements about the
same population under two different contact policies (SK-01 contacts a uniform 10%, SK-02
contacts the model's top 10%). `data/labels.csv` therefore carries Y(1) and Y(0)
(`label_no_contact`) for every row. DATA_CARD §12.1–§12.3 documents how the counterfactual
table is tied to the observed journeys: every observed recovery is forced in, Y(0) is *solved*
to reproduce the observed self-return rate, and both layers read the same latents.

The six `label_product_<p>` columns partition the row label (exactly one can be 1), so
`P(row) = Σ_p P(product p)` and the stacked model learns all six at once.

### Any-product probability

Because the labels are mutually exclusive, the probability that a lead disburses
*something* is the **sum** of the six, not `1 − ∏(1 − p)`. Until 2026-09-21 both the
evaluator and the packer used the independence formula, which is the union of six
events that *can* co-occur — they cannot — and read low for exactly the customers the
queue ranks highest. `model.policy.any_product_probability` is now the one definition,
and `p_any` in the export is that sum.

**It is clipped at 1, and the clip is a disclosure, not a fix.** The six isotonic
calibrators are fitted independently, one per product; nothing constrains their outputs
to sum to at most one. A sum above one is a coherence failure of the calibration, and
clipping hides its size rather than repairing it. A genuinely coherent treatment would
model the seven-way outcome (six products plus no disbursement) jointly, or calibrate
`P(any)` separately against the row label and rescale the six to match. Neither is
built. On the shipped run the overall ECE against the row label is 0.0074, so the sums
are not badly incoherent in practice — but "not badly" is an observation about one run,
not a property of the method.

### Three clocks, and which one drives urgency

| field | what it is | example |
|---|---|---|
| `abandoned_at` | when the customer walked away from the application | 2026-07-04 |
| `scored_at` | the snapshot instant the model ranked the pool; every feature is as at this moment | 2026-09-01 |
| `contact_by` | `abandoned_at` + the offered product's window — the deadline for an RM to call | 2026-07-05 |
| `outcome_horizon_days` | days **after contact** inside which a disbursement counts | 1 |

`contact_by` and `outcome_horizon_days` are the same number of days measured from two
different events, which is exactly why they are two fields. Until 2026-09-21 the export
computed `contact_by` as `scored_at + window` while the platform backend computed
`abandon_ts + window`; the two disagreed by however long the customer had been sitting
in the drop-off pool, which for a one-day product is most of its life. The export now
uses abandonment, and agrees with the backend.

**A `contact_by` in the past is correct output.** For `personal` and `gold` (one-day
windows) scored off a *monthly* snapshot, the window has almost always shut before the
lead is produced. That is a real property of scoring one-day opportunities on a monthly
clock, not a rendering bug, and the cockpit shows those leads as closed rather than
inventing urgency.

### Contact-SLA compliance, and whether event triggering would fix it

SK-04 does not measure whether an RM called in time, and nothing else in the pipeline
did either. `src/experiments/event_triggered.py` measures it, by simulating the dialling
over the delivered queue on one shared calendar: an ingestion lag, working days only, and
a finite number of calls per day sized to clear the busiest month. For **newly abandoned
one-day products** (personal, gold), weekends excluded, capacity 1.0:

| regime | ingestion lag | contact-SLA compliance | window already shut when the lead appeared | median days, abandonment → call |
|---|---|---|---|---|
| monthly batch (today) | same-day | 0.7% | 96.0% | 26 |
| monthly batch (today) | overnight | **0.0%** | 98.7% | 27 |
| monthly batch (today) | 3 days | 0.0% | 100% | 29 |
| **event-triggered** | same-day | **63.0%** | 0% | 1 |
| **event-triggered** | overnight | **46.2%** | 0% | 2 |
| event-triggered | 3 days | 0.0% | 100% | 4 |

Three readings:

1. **The monthly batch cannot serve a one-day product at all.** Not "serves it badly" —
   0.0% with an overnight ingestion lag, because by the time the lead exists its window
   has shut for 98.7% of them. Every `personal` and `gold` lead in today's cockpit is a
   lead whose stated deadline has already passed.
2. **Event triggering fixes it, and the ingestion lag is the whole game.** Same-day
   ingestion gets 63%; an overnight batch costs 17 points; a three-day lag returns the
   number to zero, because three days is longer than a one-day window. Any pilot that
   proposes event triggering and then runs the feed nightly has built the monthly system
   again with extra steps.
3. **Capacity dominates the trigger once the queue is overloaded.** Halve the calls per
   day and event-triggered SLA compliance collapses to 1.4% with a p90 of 232 days from
   abandonment to contact. Triggering earlier does nothing if nobody is free to dial.

**What this cannot tell you.** Post-contact disbursement is reported beside SLA
compliance (34.5% on the contacted set) and is deliberately **not** derived from it. The
generator's label is a potential outcome under contact with **no decay after
`contact_by`** — a customer contacted on day 40 converts exactly as often as one
contacted on day 1 — so the conversion value of better SLA compliance is not measurable
from this simulation, and anyone reading an uplift out of the table above is reading
something that was not modelled. Pricing it needs real contact-time-to-outcome data,
which is exactly what a pilot produces. Both quantities are reported in
`validation/report/REPORT.md` under SK-04, as **reported, never-graded** exhibits: adding
a band for either after seeing the numbers would be inventing a pre-registration.

Event-triggered scoring is therefore **designed and measured, and not built**: it is a
pipeline change (a stream trigger on the abandonment event, and a feed that is not
nightly), not a model change.

**Which clock *should* drive urgency is an open question for the mentors.** Abandonment
is the assumption documented and implemented here, end to end — label, export, backend
and screen. It is recorded as an assumption, not settled.

**The honest caveat, stated once and loudly:** *the counterfactual is generated, not validated.*
Nothing in this repo proves that an RM call is worth 8–10%; that is what the mentors stated and
what the generator's contact effect θ was solved to reproduce. The derived contact lift is 26×,
and DATA_CARD §12.3 records the alternative reading that would put it near 10×.

---

## 5. Features

69 inputs in 10 families (`model.frame.FEATURE_FAMILIES`), every one computed **as at the first
instant of the scored month** — the instant the drop-off list is picked up.

| Family | What it is | n |
|---|---|---|
| `income` | 6-month median credits, volatility, growth, bonus share, salary-source count, salary-day drift | 6 |
| `balance` | average / minimum balance, growth, FD ratio and breaks, min-balance charges | 6 |
| `outflow` | rent, fuel & cab, school fees, e-commerce, card, insurance, UPI P2M | 10 |
| `debt` | EMI share and growth, external mandate count, **share going to other lenders**, mandate failures | 6 |
| `life_event` | address / nominee changes in 6 months | 1 |
| `profile` | age, occupation segment, city tier, tenure | 4 |
| `journey` | stage reached, attempts, in-flight, fee paid, document shortfall, amounts, recency | 16 |
| `shopper` | **the four mentor signals** + revisits + products browsed | 7 |
| `contact` | trailing 30/90/183-day touch counts, days since last contact, last-pitched product | 5 |
| `product` | the candidate product, whether it is the one they abandoned, its window, dwell on its pages, EMI headroom | 7 |

**The four window-shopper signals the mentors named** — `journey_blank_field_ratio`,
`journey_refused_income`, `journey_fee_balk`, `journey_doc_refusal` — carry a **monotone
decreasing constraint**: each may only push the disbursement probability down. §8 reports the
realised effect both with and without that constraint, because a constraint that forbids the
wrong answer is not evidence that the data agrees.

### What is deliberately excluded

* Gender, religion, caste, marital status — excluded outright by policy.
* Pin code / neighbourhood — an income proxy that quietly discriminates.
* Credit-bureau score (API 408) — needs purpose-specific consent; pulled at application, never
  at prospecting. A governance choice, not an availability one.
* Everyone the suppression rule holds back — scored, shown, never queued.
* **Anything timestamped at or after the moment the list is picked up**, including whether the
  bank actually called and what happened next.

`model.FORBIDDEN_INPUTS` names 60+ columns across three families (outcomes, generator latents,
policy flags). `model.frame.build_matrix` **raises** rather than let one through — the guard is
in the code path, not only in a test, and `tests/test_model_inputs.py` asserts it from the other
side.

### Point-in-time safety

The journey block is **not re-aggregated here**. It is computed by
`journeys.features.journey_features_as_at`, in the lane that owns the timestamps, which enforces
the rule with a test that recomputes the whole frame from tables *physically truncated* at the
snapshot instant. The contact block and the suppression decision are read back verbatim from
`labels.csv` for the same reason: a consumer that re-derived them would drift from the table the
labels were built against.

A customer with no application history has **no journey row**, which is not the same as having a
clean one; `has_journey` flags it and the numerics stay `NaN` rather than being filled with
zeros. In the drop-off population it is 1 on every row by construction (`build_frames` asserts
it), but the builder keeps the flag so the same code can score a whole-book frame without
teaching the model that never-applied looks like clean-applied.

---

## 6. Model and splits

**Estimator.** One `LGBMClassifier` — 600 trees, learning rate 0.04, 31 leaves,
`min_child_samples` 60, 80% row and column subsampling, monotone constraints on the four mentor
signals (`monotone_constraints_method="advanced"`). Categoricals: `product`, `dropoff_product`,
`segment`, `journey_last_channel`. Giving the model both `product` and `dropoff_product` lets it
learn the cross-product substitution structure (gold ↔ personal, home ↔ lap) **from the data**
rather than importing the generator's affinity matrix, which would have been leakage dressed as
a feature.

**Calibration.** Isotonic, **per product**, on a customer-disjoint calibration fold. One global
calibrator is well behaved on average and systematically over-confident on the products it saw
least — which is exactly what SK-12 exists to catch. The per-product maps are monotone, so they
re-rank nothing *within* a product; what they buy is comparability *across* products, which is
what the menu of four needs.

**Splits.** Customer-grouped, so every month of a customer falls wholly on one side:

| Fold | Share of customers | Used for |
|---|---|---|
| fit | 52.5% | training |
| calibrate | 17.5% | the six isotonic maps |
| **hold out** | **30%** | every number in this card |

Out-of-time: train on months 7–23, test on months 24–29, held-out customers only. The
registered 14-day embargo is satisfied *structurally* rather than by dropping rows — a row is
dated to the first of its month and its label resolves within 14 days, i.e. inside that same
month, so a cut at a month boundary leaves no training label that had not yet happened.

**The queue is scored by exactly the model that was measured** — no refit on the full data. The
cockpit queue covers the whole snapshot pool and is never a measurement surface
(`validation/criteria.yaml`, `splits.holdout.scoring_population`).

**Ranking.** A customer-month's score is `max_p` calibrated probability (the design-mandated
rule). `1 - Π(1 - p_p)` is emitted beside it as the row-level probability, and the precision
under a sum-ranking is reported as a comparison so the choice is evidenced rather than asserted.

**Seeds.** Five model seeds (7, 8, 9, 10, 11 — the list `validation/criteria.yaml` registers).
A seed changes the customer split and the estimator's randomisation; the frame and the generated
data do not change, because the data lane (SD-S4) reports its own five-seed spread of θ and the
signal-to-noise knob separately. The packed JSON carries the default seed's run plus the spread
across all five.

---

## 7. Suppression — who is scored but never called

The rule is decided once in `journeys.campaigns` and read back, never re-derived. Eight reasons,
evaluated in priority order, first match wins:

`deceased` · `no_marketing_consent` · `dnd` · `account_dormant` · `application_in_flight` ·
`recent_decline` · `recent_contact` (7-day cool-off) · `already_holds_product`

Suppressed rows are **scored and shown with the reason attached**, and never enter the queue,
never enter a metric, and never enter training. The count and the reason histogram are a KPI in
their own right (`metrics.suppression`), because "how many people we chose not to call, and why"
is the part of a prospecting product a compliance reviewer reads first.

**`in_arrears` is missing, and that is a gap, not an oversight.** SANKET's book is a *liability*
book with no loan performance in it, so "never pitch anyone in arrears" cannot be enforced from
this data. Recorded rather than faked. In the bank's environment it comes from API 402
(`dpd`, `npaStatus`).

---

## 8. Results

Held-out 30% of customers, default seed 7, unless a spread is quoted. Source of record:
`data/model_metrics.json`, regenerated by `python3 src/score_and_pack.py`.

### The headline

> **9 → 29 disbursements per 100 RM calls** *(seed 7; the five-seed mean is 9.1 → 28.1)*

| | value | 95% CI (packed seed) | 5-seed spread |
|---|---|---|---|
| random-contact disbursement (the 9) | **9.48%** | 8.46 – 10.59% | mean 9.10%, 8.93 – 9.48% |
| precision @ 10% budget (the 29) | **29.06%** | 27.44 – 30.73% | mean 28.11%, 27.47 – 29.06% |
| precision @ 5% | 35.80% | 33.38 – 38.30% | mean 32.64% |
| precision @ 20% | 23.01% | 21.95 – 24.11% | mean 21.96% |
| lift over random contact @10% | **3.1×** | | |

The "95% CI" column is a Wilson interval around the packed seed's own number. The
"5-seed spread" column is a different estimand — the dispersion of five point estimates
from five training splits — and is never a confidence interval around anything. They
are kept in separate columns for that reason; see §9.

**Both numbers price the same hundred calls**, over the same population: one caller picks at
random, the other takes the model's top decile. That is the whole of the claim. The retired
`1% → 36%, 28× lift` compared a top-2% slice of the *whole liability book* against a random
call to *anyone on the book* — a denominator no RM ever dials.

### The delivered queue, and why it ranks on probability

**The number above describes the list an RM receives.** Until 2026-09-21 it did not.
`evaluate_seed` measured precision by ranking held-out rows on `max(product
probabilities)`; the queue `build_queue` handed to the cockpit and the platform was
ranked on `0.65 × intent-percentile + 0.35 × capacity`, then truncated to 320 rows, and
the `hot`/`warm`/`cold` tiers were cut on a *third* ordering. Of the 320 leads the old
queue delivered, 147 were in its own `hot` tier.

`src/model/policy.py` now owns the whole selection — suppression → eligibility →
ranking → truncation → tie-break (customer id ascending) — and both the evaluator and
the packer call it. `tests/test_model_policy.py` compares the exported queue's customer
ids against the evaluator's, in order, so the two cannot drift apart again silently.

Unifying them forced a choice of ranking. It was made against a rule fixed before the
measurement: keep the blend only if its held-out precision@10% came within 2 percentage
points of probability-only ranking.

| ranking | precision@5% | **precision@10%** | precision@20% | 5-seed mean @10% |
|---|---|---|---|---|
| calibrated product probability | 35.80% | **29.06%** | 23.01% | 28.11% |
| 0.65 intent + 0.35 capacity | 23.59% | **21.92%** | 20.70% | 20.52% |

The blend costs **7.14 percentage points** — three and a half times the tolerance — so
the queue ranks on probability. `capacity` and `blend` are still computed and exported:
an RM sees whether the customer can comfortably afford the product, it just no longer
decides who gets called. Both rankings are re-measured every run into
`metrics.ranking_comparison`, so the decision is re-checkable rather than a one-off.

Why the blend lost so much: `intent` is a *percentile rank* of the probability, which
throws away the shape of the distribution — the difference between a 0.62 lead and a
0.31 lead becomes one rank step — and then 35% of the ordering is given to an
affordability ratio that is close to uncorrelated with whether the customer converts.

**What the cockpit exports is a prefix, and is reported as one.** The 10% budget buys
553 calls at the snapshot; the cockpit ships the first 320 of them (5.8% of the eligible
pool). That tighter budget's held-out precision is **33.12%** (95% CI 30.91 – 35.40%),
carried as `metrics.delivered_queue.precision_at_queue_size` with its own per-100 line,
"9 → 33". The 29 prices a 10% calling budget; the 33 prices the 320 rows the demo
ships. Both come from the same ranked list and the same selection function.

### Ranking

| | value | 95% CI |
|---|---|---|
| macro AUC (unweighted mean of six) | **0.865** | seeds 0.864 – 0.872 |
| row-level AUC (does this customer disburse at all) | 0.737 | |

| Product | AUC | 95% CI | positives | ECE | 5-seed AUC range |
|---|---|---|---|---|---|
| home | 0.931 | 0.914 – 0.948 | 426 | 0.002 | 0.926 – 0.943 |
| auto | 0.892 | 0.874 – 0.911 | 505 | 0.002 | 0.882 – 0.895 |
| education | 0.872 | 0.851 – 0.894 | 435 | 0.003 | 0.854 – 0.872 |
| lap | 0.847 | 0.810 – 0.883 | 169 | 0.001 | 0.847 – 0.909 |
| gold | 0.843 | 0.818 – 0.868 | 371 | 0.002 | 0.824 – 0.853 |
| personal | 0.804 | 0.786 – 0.822 | 858 | 0.003 | 0.800 – 0.814 |

`lap` is the thin product (169 positives) and carries the widest seed-to-seed swing, 5.6 pp.
It clears the 0.75 floor on every seed, but it is the cell to watch when the generator moves.

### The menu of four

| | value |
|---|---|
| menu-of-4 hit rate | **96.5%** (5-seed mean 96.8%) |
| top-1 product accuracy | 70.4% |
| **"offer them what they abandoned" — the same measurement, no model** | **70.5%** |
| menu hit rate among the 29% who switched product | 88.1% |
| top-1 accuracy among the switchers | **1.0%** |

**Read those last two rows before quoting the first.** The drop-off anchor does essentially all
of the top-1 work: the model's rank-1 product is the product they abandoned, and against the
814 held-out positives who took something *else*, rank 1 is right 1% of the time. The menu is
where the value is — it still contains the realised product for 88% of the switchers. A
single-recommendation product would have been wrong for all of them, which is precisely the
argument the mentors made for a menu, now with a number on it.

`validation/criteria.yaml` registers SK-14 (top-1) as **report, no target**, deliberately:
"setting a top-1 target would push the model back toward the single-recommendation behaviour
the menu exists to replace". That is why this is published rather than optimised.

### The four window-shopper signals (SK-15)

Mean SHAP (log-odds) where the signal is on, minus where it is off, on 12,000 sampled held-out
rows:

| Signal | shipped model (constrained) | unconstrained twin | n rows "on" |
|---|---|---|---|
| blank-answer ratio ≥ 0.25 | **−0.197** | −0.173 | 7,361 |
| refused to share income | **−0.022** | **+0.002** | 2,622 |
| balked at the ₹1,000 fee | **−0.208** | −0.191 | 4,239 |
| refused documents | **−0.166** | −0.165 | 3,901 |

Four out of four negative in the shipped model, which is what SK-15 grades. **Three out of
four negative when the monotone constraints are removed** — and the one that is not,
income refusal, comes out at +0.002, i.e. null rather than reversed.

That is worth stating plainly rather than burying: on the *original application's* completion,
the generator makes income refusal strongly negative (the data lane measures a logistic
coefficient of −1.44). On *this* label — will a drop-off, if called, disburse inside the window
— it carries almost no independent information once blank answers, the fee balk and the
document refusal are in the model. The shipped model's negative sign on it is the monotone
constraint doing its job, not the data speaking. We keep the constraint, because an RM chip
that said "would not share income — and the model liked that" would be indefensible, and we
publish the unconstrained number beside it so nobody has to take the constraint on trust.

### Calibration, timing, stability, leakage

| Criterion | value | band |
|---|---|---|
| ECE overall | 0.0074 | ≤ 0.03 |
| ECE worst product (education) | 0.0027 | ≤ 0.03 |
| conversion timing among converters, @ 10% budget (SK-04) | **0.901** (n = 908) | ≥ 0.90 — **5-seed mean 0.881, below the floor** |
| out-of-time degradation (months 24–29) | **−0.80 pp** (i.e. it improved) | ≤ 5 pp |
| PSI, early months vs last six | 0.009 | ≤ 0.10 |
| permuted-label AUC (full retrain) | 0.506 | ∈ [0.48, 0.52] |
| forbidden inputs used | **0** of a 60-column forbidden set | = 0 |
| window-shopper detector AUC | 0.847 (0.842 – 0.853) | ≥ 0.70 |
| cross-seed precision@10% interval width | 1.46 pp | ≤ 4 pp |

**SK-04 is the honest problem — and first, what it is.** It measures **conversion timing
among converters**: of the held-out leads inside the contact budget that *did* disburse,
the share whose disbursement landed inside the window of the product the model offered.
It is **not** contact-SLA compliance. It does not measure whether an RM called before
`contact_by`, and nothing in this pipeline observes an RM dialling — there are no
contact timestamps in the delivered pack — so contact-SLA compliance is unmeasured here
and everywhere else in this repo. Any earlier reading of the 90.1% as "contact lands
inside the window" was wrong; `validation/criteria.yaml` carries a dated amendment
correcting the criterion's own description, with the threshold untouched.

It clears the 0.90 floor on the packed seed (0.901)
and misses it on the five-seed mean (0.881, range 0.869 – 0.901). The mechanism is not a bug:
the model offers the product the customer abandoned, and when the customer comes back for a
*different* product with a shorter window, the disbursement lands outside the offered
product's clock. Raising the number would mean biasing the top-1 choice toward long-window
products, which games the metric rather than serving the RM, so the number stands as measured
and `metrics.bands["SK-04"]` carries both verdicts.

### The baseline ladder (SK-25)

| Rung | precision @ 10% | 95% CI |
|---|---|---|
| random contact | 9.48% | 8.46 – 10.59% |
| balance-ranked (what a branch does today) | 9.95% | 8.91 – 11.09% |
| logistic scorecard, 16 features | 25.83% | 24.28 – 27.45% |
| **SANKET — one LightGBM, six products** | **29.06%** | 27.44 – 30.73% |

Ranking the drop-off list by account balance is worth **half a percentage point** over calling
at random — the intuition a branch actually uses is worth almost nothing here. A plain logistic
scorecard on the same features gets most of the way; the gradient boosting adds 3.2 pp on top
of it. Both of those are findings a deck would rather not have, and both are in the export.

### Uplift (kept from the pre-SM-1 build, rebased)

Y(1) and Y(0) now come from `data/labels.csv` directly instead of being reconstructed from the
book's persuadability window; only the 50/50 assignment is simulated.

| | value |
|---|---|
| incremental conversions per 1,000 calls, top-20% uplift-ranked | **228.1** |
| per 1,000 calling everyone | 91.5 |
| share of the top-uplift quintile who are true persuadables | 19.0% (book: 11.8%) |

### Fairness (SK-23 / SK-24) — the failure, stated

Four-fifths rule on the *contact* rate at the live 10% budget, over the snapshot queue
(n = 5,529 contactable):

| Attribute | worst group | selection rate | ratio to best | |
|---|---|---|---|---|
| Occupation segment | **gig** | 7.61% | **0.69** | **FAIL** |
| Income band | Q1 (lowest) | 8.77% | **0.79** | **FAIL** |
| City tier | tier 3 | 9.04% | 0.84 | pass |
| Age band | 46+ | 9.31% | 0.91 | pass |

This is the documented gig-worker failure, and it is a **reported** criterion in
`validation/criteria.yaml` — not a gate — because tuning it away on synthetic data would be
pretending to have solved it.

**The mechanism is not the capacity blend**, and this card said otherwise until
2026-09-21. SK-23 has always been measured on the probability-ranked selection, and the
ratio is unchanged at **0.69** now that capacity has been removed from the queue's
ranking entirely (§8) — so a term that was never in the measured selection cannot have
been depressing it.

`src/experiments/fairness_probe.py` replaces that wrong explanation with measurements.
It runs on the **held-out split** rather than the snapshot, so its ratios are stricter
than SK-23's graded 0.69 and are not a substitute for it; what they are is diagnostic.

**1. The queue amplifies a small outcome gap into a large contact gap.**

| segment | n | contact rate | four-fifths ratio | conversion rate | precision when selected |
|---|---|---|---|---|---|
| gig | 4,437 | 6.54% | **0.57** | 8.74% | **32.4%** |
| self-employed | 7,106 | 8.43% | 0.73 | 9.34% | 32.2% |
| salaried | 17,611 | 11.50% | 1.00 | 9.72% | 27.6% |

Gig workers convert at 0.90× the salaried rate and are contacted at 0.57× — the ranking
**amplifies the gap by 1.58×**. And the gig workers it does select convert **4.8
percentage points better** than the salaried ones it selects. That is what a stricter
effective threshold looks like: only the most obvious gig cases clear it, so the ones
that do are unusually good. A group being under-selected while over-performing on
selection is a property of the ranking, not of the population.

**2. At the same score, gig workers convert slightly more, not less.** Within pooled
score deciles the gig-minus-salaried conversion gap averages **+1.7 pp**. The model is
not badly mis-calibrated within segment; the deficit is in where gig workers land in the
score distribution, not in what the score means once they are there.

**3. The retired capacity blend was far worse than SK-23 ever reported.** On this split:

| ranking | precision@10% | gig ratio |
|---|---|---|
| probability only (shipped) | 29.06% | **0.57** |
| blend, capacity weight 0.15 | 27.79% | 0.45 |
| blend, capacity weight 0.35 (the queue delivered until 2026-09-21) | 21.92% | **0.21** |

The queue an RM actually received was contacting gig workers at **0.21×** the salaried
rate while SK-23 reported 0.69, because SK-23 was measuring the probability-ranked list
and the queue was not. Removing capacity from the ranking (§8) was a large fairness
improvement that nobody was claiming credit for, because nobody had measured the list
being delivered.

**4. Which features carry it.** Mean TreeSHAP for the pitched product, gig minus
salaried, on rows within six percentiles of the contact cut: `is_dropoff_product`
(−0.104), `journey_stated_income_ratio` (−0.096), `journey_last_product_matches`
(−0.042), `journey_fee_balk` (−0.037), then the behavioural-income family —
`credits_cv_6m` (−0.026, income volatility), `upi_share` (−0.023),
`emi_headroom_ratio` (−0.020). The irregular-income story is real but small; the larger
terms are journey-shape features, which is a different and more tractable problem.

**The remedies, priced.** Nothing below was tuned to 0.80 — this is an exchange rate, and
the choice belongs to a human.

| option | precision@10% | cost | gig ratio |
|---|---|---|---|
| shipped (probability ranking, no quota) | 29.06% | — | 0.57 |
| minimum four-fifths floor of 0.80, within segment | 29.02% | **−0.04 pp** | 0.80 |
| equal selection rate per segment | 28.92% | **−0.14 pp** | 1.00 |
| blend, capacity weight 0.15 | 27.79% | −1.27 pp | 0.45 |
| blend, capacity weight 0.35 | 21.92% | −7.14 pp | 0.21 |

A within-segment quota that lifts the worst ratio to 0.80 costs **four hundredths of a
percentage point** of precision — about one conversion in every 2,500 calls. Equalising
the rate outright costs 0.14 pp. Both are, on this data, close to free, and both are far
cheaper than the capacity blend that was being delivered for free in the other direction.

**This is not shipped.** A contact quota is a policy the bank must choose, not a default
a model author should install, and choosing it on synthetic data would be choosing it on
a simulation. What ships is the measurement and the price. The quota rule itself is
implemented and tested (`src/experiments/fairness_probe.py::_quota`) so that turning it
on is a decision rather than a project.

| Income estimation (held-out, snapshot month, n = 1,694) | |
|---|---|
| within ±10% | 89.0% |
| within ±15% | 95.2% |
| **gig workers within ±15%** | **76.4%** |
| median error, all / gig | 2.5% / **8.7%** |

### Suppression — the KPI (SM-3)

Snapshot pool 7,456 customer-months; **1,927 (25.8%) suppressed and never queued**:

| reason | rows |
|---|---|
| no marketing consent | 1,192 |
| contacted in the last 7 days | 446 |
| declined or opted out within 90 days | 128 |
| account dormant | 85 |
| on the DND list | 42 |
| application already in flight | 25 |
| deceased | 8 |
| already holds the product the need points at | 1 |

Each of these reaches the platform under its own name. `deceased` and `account_dormant`
used to be exported as the contract's `kyc_expired`, which passed schema validation and
told an RM to go and re-KYC a customer who had died; the contract now carries `deceased`
and `dormant` as distinct values, and `tests/test_model_export.py` asserts the mapping is
total over every reason a suppressed row can carry and injective. The negative-signal
chips got the same treatment: a repeated-contact chip used to arrive as `vague_answers`
and now arrives as `contact_fatigue`. Two chips still collapse onto `vague_answers` —
`journey_stated_income_ratio` (stated income above what the account shows) and
`journey_open_now` (another application already open) — because neither has a contract
value yet; that is open contract debt, listed here so it is not invisible.

Queue at the snapshot: **553 hot** — the top 10% of the eligible pool on the queue's own
ranking, i.e. the month's calling list — 829 warm, 4,147 cold. The cockpit exports the
first 320 of the hot slice. Before 2026-09-21 the tiers were cut on a different ordering
from the queue, and only 147 of the 320 delivered leads were in the `hot` tier at all.

### Runtime

Full run — frame build, 5 seeds, out-of-time, permuted-label, ladder, uplift, shopper, queue —
about **11 minutes** on an unloaded laptop (638 s measured, on a machine simultaneously running
three other builds). `--seeds 7 --quick` is about 3 minutes.

---

## 9. Pre-registered bands

`validation/criteria.yaml` was committed before any of these numbers existed, and carries a
dated amendment (2026-09-16) that scopes SK-01/SK-02/SK-17/SK-18 to the drop-off population
**without moving a single threshold**. `model.metrics.REGISTERED_BANDS` transcribes the bands
and `tests/test_model_bands.py` reads the YAML and asserts the transcription, so neither side
can drift.

Every band verdict is packed into the JSON under `metrics.bands`, failures included. A failure
is the finding; it is never hidden and never tuned toward.

| ID | metric | band | value | verdict |
|---|---|---|---|---|
| SK-01 | random_contact_disbursement_rate | in [0.08, 0.10] | 0.0948 | **pass** |
| SK-02 | precision_at_10pct_budget | in [0.25, 0.35] | 0.2906 | **pass** |
| SK-03 | precision at 5% and 20% | reported | 0.358 / 0.230 | report |
| SK-04 | conversion timing among converters (`window_respect_rate`) | ≥ 0.90 | 0.9009 | **pass on the packed seed, FAIL on the 5-seed mean (0.881)** |
| SK-05 | window_shopper_auc | ≥ 0.70 | 0.847 | **pass** |
| SK-06 | headline uplift | reported | 9 → 29 per 100 | report |
| SK-07 | oot degradation (pp) | ≤ 5.0 | −0.80 | **pass** |
| SK-08 | per-product AUC ×6 | ≥ 0.75 | min 0.804 (personal) | **pass** |
| SK-09 | macro_auc | ≥ 0.78 | 0.865 | **pass** |
| SK-10 | AUC + precision by cut | reported | 7 cuts emitted | report |
| SK-11 | ECE overall | ≤ 0.03 | 0.0074 | **pass** |
| SK-12 | ECE per product | ≤ 0.03 | max 0.0027 | **pass** |
| SK-13 | menu_of_4_hit_rate | ≥ 0.80 | 0.965 | **pass** |
| SK-14 | top_1_product_accuracy | reported | 0.704 | report |
| SK-15 | 4 signals negative | ≥ 4 | 4 | **pass** |
| SK-16 | PSI | ≤ 0.10 | 0.009 | **pass** |
| SK-17 | forbidden inputs used | = 0 | 0 | **pass** |
| SK-18 | permuted_label_auc | in [0.48, 0.52] | 0.506 | **pass** |
| SK-19 | ablation by family | reported | **not run — runner 08** | not run |
| SK-20 | n_seeds_run | ≥ 5 | 5 | **pass** |
| SK-21 | cross-seed CI width (pp) | ≤ 4.0 | 1.46 | **pass** |
| SK-22 | stress scenarios | reported | **not run — runner 10** | not run |
| SK-23 | adverse_impact_ratio | ≥ 0.80 (reported) | **0.69 (gig)** | **FAIL, disclosed** |
| SK-24 | gig failure disclosed | exists | yes | **pass** |
| SK-25 | baseline ladder | reported | 4 rungs | report |

**17 pass · 1 gating band that passes on the packed seed and fails on the seed mean (SK-04) ·
1 reported failure (SK-23, the gig gap) · 2 not run in this script (SK-19, SK-22 — validation
runners 08 and 10 emit them; `validation/report/REPORT.md` has their values).**

### Uncertainty: three questions, three answers, never added together

`metrics.uncertainty` keeps three estimands apart. They are not interchangeable and they
do not combine into one interval, which is why the validation report's column is called
`Interval` and every row says which kind it carries.

| what varies | precision@10% | kind | how |
|---|---|---|---|
| **Sampling** — which customers landed in the book | **26.76 – 31.18%** | genuine 95% CI | `cust_id` resampled with replacement, 1,000 times, over 3,305 held-out customers; **the queue is re-selected by `model.policy` inside every resample** |
| **Training seed** — which fit/calibrate/holdout split | 27.50 – 28.96% | spread, not a CI | 2.5–97.5 percentile across the registered seeds [7, 8, 9, 10, 11] |
| **Generator** — which synthetic world the book came from | 25.73 – 29.27% | spread, not a CI | 8 worlds regenerated end to end (book + journeys + labels), each scored at the *same* model seed 7 |

The headline with its own sampling interval: **9–10 → 27–31 disbursements per 100 RM
calls** (95% customer-clustered bootstrap).

Three things follow, and none of them is comfortable:

1. **The registered method is now honoured.** `criteria.yaml confidence.method` asks for
   a percentile bootstrap resampled at `cust_id`. The pack persists the packed seed's
   held-out predictions (`data/predictions/holdout_seed7.npz`) and `model.bootstrap`
   resamples them. The interval is wider than the Wilson one it replaces (27.44–30.73%)
   because a customer's thirty monthly rows are not thirty independent observations —
   which is exactly the correction a row-level interval was hiding. Resampling the
   *queue selection* rather than the row outcomes is what makes it a statement about the
   policy: `k`, the eligible pool and the percentiles all move with the pool.
2. **The generator spread is the widest of the three, at 3.5 pp.** Eight worlds give a
   mean precision@10% of **27.64%**, against the shipped world's 29.06%. The shipped
   generator seed is near the optimistic end of its own distribution (it is not the
   maximum — 20260712 reaches 29.27% — so it is not cherry-picked, but the headline
   would read "9 → 28" as a mean across worlds rather than "9 → 29"). **Most of the
   uncertainty in this number is a property of the synthetic data, not of the model**,
   and a real deployment would have none of it because it would have one real world.
   That is the strongest argument in this card for treating every figure in it as a
   statement about a simulation until real data arrives.
3. **They are separated on purpose.** Every world in the generator experiment is scored
   at model seed 7, so nothing in that 3.5 pp is training variance; the seed spread is
   computed on one world, so nothing in its 1.5 pp is generator variance. Mixing them
   would produce one number attributable to neither.

Reproduce: `python3 src/score_and_pack.py` writes the first two;
`python3 src/experiments/generator_variation.py` (about eight minutes) writes the third
into `data/experiments/generator_variation.json`, which the pack reads and reports as
`not_measured` if it is absent.

### The frozen model against worlds it was not built for

The risk this section exists to manage is circular: the generator was *solved* to hit a
mentor-stated baseline, the model was built against that generator, and the model looks
good. Nothing inside that loop says whether it would survive a world it was not built
for. `src/experiments/challenge_regimes.py` breaks the loop under three rules:

1. **The development generator config is frozen to a file**
   (`data/experiments/frozen_generator.json`) *before* any challenge runs, so every
   regime is a named departure from a recorded baseline rather than a retuning that
   could be relabelled afterwards.
2. **The model is fitted once, on the development world, and never refitted.** No
   hyper-parameter moves, no calibrator is refitted, no threshold is touched. A regime
   that hurts, hurts.
3. **Model seed and generator seed are separate arguments.** Every challenge world uses
   generator seed 20270131, which the development world never used, and all of them are
   scored at model seed 7 — so a degradation cannot be a training-split accident. A
   `fresh_world` control (same frozen config, new seed) sizes what a new world costs on
   its own, and every regenerated regime is read against *that*, not against the
   development number, which would charge it twice.

| regime | what departs | precision@10% | lift | vs its control |
|---|---|---|---|---|
| development world | — | 29.06% | 3.06 | — |
| `source_latency` | every behavioural feature one month stale | 26.93% | 2.84 | −2.13 pp |
| `extra_missingness` | 15% of behavioural values blanked | 26.83% | 2.83 | −2.23 pp |
| `macro_shock` | incomes/balances −15%, EMI burden +20% | 29.26% | 3.09 | +0.20 pp |
| `customer_turnover` | newest-tenure quartile only | 26.49% | 2.84 | −2.57 pp |
| **`fresh_world`** (control) | new generator seed | **27.51%** | 3.00 | — |
| `base_rate_half` | recovery rate 0.09 → 0.045 | 23.87% | 2.74 | **−3.64 pp** |
| `base_rate_double` | recovery rate 0.09 → 0.18 | 26.89% | 3.01 | −0.62 pp |
| `signal_correlation` | shopper share of drop-offs 0.30 → 0.50 | 29.38% | 3.36 | +1.87 pp |

What it says:

- **Nothing breaks the model.** The worst regime, a halved base rate, still ranks at
  2.74× its own world's random-contact rate. Nothing here collapses to chance.
- **The lift is the stable quantity, not the precision.** Precision/baseline stays inside
  **[2.74, 3.36]** across every regime, while absolute precision ranges from 23.9% to
  29.4%. Absolute precision tracks whatever base rate a world happens to have; the ratio
  is the part that belongs to the model. Any pilot should be sized on the ratio.
- **A stale feed and a missing feed cost about the same, and both cost about as much as
  a fresh world.** Two percentage points each. That is a useful operational fact: the
  data-engineering failure modes and the "this is a different book" risk are the same
  order of magnitude, and neither is catastrophic.
- **Being handed a much harder book is the real risk.** Halving the recovery rate costs
  3.6 points beyond the cost of the new world itself — more than any feed failure.
- **A macro shock and a changed signal correlation did not hurt**, and the second
  actively helped (more window-shoppers means more signal for the shopper features to
  carry). Reported as measured rather than trimmed for looking too good.

**Rupees.** `economics` in the JSON multiplies each regime's measured precision against a
contact cost and a per-disbursement margin, both of which this repo cannot verify, and
reports the **range** they imply rather than the flattering end. Every such figure is a
simulation result over the generator's potential outcomes, not observed money. Quote the
range or nothing.

### The menu against rules that need no model

Quoting a 96.5% menu-of-4 hit rate on its own is a claim about the population: most
converters take the product they abandoned, so a rule with no model in it already scores
well. `metrics.menu_baselines` puts all three side by side, on every converter and on the
**switchers** — the 814 converters who took a different product from the one they walked
away from, the only group where a menu can add anything.

| rule | menu-of-4 hit | top-1 | menu hit, switchers | top-1, switchers |
|---|---|---|---|---|
| **SANKET** | **96.5%** | 70.4% | **88.1%** | **1.0%** |
| abandoned product, then popularity | 90.8% | 70.6% | 68.8% | 0.0% |
| the 4 most-taken products | 80.5% | 31.0% | 70.9% | **39.3%** |

Two readings, and the second is the uncomfortable one:

- **The menu earns its keep on switchers.** 88.1% against 70.9% for the best no-model
  rule is 17 points, on the group that matters. On all converters the margin over the
  abandoned-product rule is 5.7 points, which is real but much smaller than the headline
  96.5% suggests.
- **Top-1 on switchers is 1.0%, and a constant rule beats it at 39.3%.** The model
  almost always names the product the customer abandoned, so for a customer who switched
  it is almost always wrong at position one. Offering the four most popular products
  would be right nine times as often for that group. This is the clearest evidence in the
  card that SK-14 (top-1 accuracy, reported with no target) should stay untargeted, and
  that the menu — not the top pick — is the product. It is also a concrete lead: a
  second-stage model that predicts *whether* a customer will switch could route those
  cases differently.

The most-popular ordering is computed from **training** positives only; building it from
the held-out labels would be reading the answer sheet.

---

## 10. Known limits — what this model does *not* do

1. **The counterfactual is generated, not validated.** §4.
2. **The drop-off anchor does most of the menu's work.** 71% of positives take the product they
   abandoned, so "offer them what they walked away from" is already a strong top-1 rule. The
   menu's marginal value is reported separately, on the positives who *switched* product.
3. **The window-shopper detector is graded against the generator's latent flag**, which a real
   bank does not have. In production the target is the observable proxy — two or more
   abandonments and no disbursement in twelve months — and the reported AUC is an upper bound on
   what that proxy would reach.
4. **Nobody in this data is ever rejected.** Every abandonment is the customer walking away;
   there is no credit decline, no policy reject, no fraud decline. A model trained here cannot
   tell "changed their mind" from "we said no" (DATA_CARD §11.11).
5. **No arrears, no delinquency, no repayment behaviour.** §7.
6. **Gig workers are under-contacted**, and the fairness table says by how much (0.69).
   Irregular gig income reads as instability to a model whose training mass is salaried.
   The capacity blend is *not* the cause — the ratio is unchanged now that capacity has
   been removed from the ranking (§8) — so the feature-level mechanism is still an open
   question rather than a diagnosed one. Segment-aware calling quotas are designed, not
   built. The gap is disclosed, not tuned away, because tuning it away on synthetic data
   would be pretending to have solved it.
7. **EMI figures price one sandbox rate, not a per-product quote.** Every product prices off
   the same 12.75% p.a. figure (`rateInfo.effectiveRate`), because a live API 433 call returns
   a single rate-card reading and there is no per-product rate to be had. What *is* fetched is
   the schedule: API 473 is an amortisation engine, the batch asks it once per reference
   ticket, and `emi_source = "BANK_API_473_schedule"` is what a normal run reports. Below it,
   in order: `BANK_API_433_sandbox_fixture` (no fetched schedule for this ticket — the 433 rate
   through a standard reducing-balance annuity, `DERIVED_FROM_433`) and `TYPICAL_EMI` (neither;
   the retained flat table, reachable but not normal). The reference ticket size and tenor per
   product are still `assumed` — the *ticket* is ours even when the *schedule* is the bank's.
   *(Correction history: this card said API 473 "has never returned a body in this sandbox at
   all", then that swapping to a fetched schedule was an open change. Both are now stale — 473
   answers, and SM-5 reads it. The instalment it computes matches our own formula to the paise
   on all six reference tickets, which is why the switch moved no published number; the
   agreement is asserted in `tests/test_model_emi.py`, not assumed.)*
8. **`rm_id` is a fabricated roster, not a real HRMS directory, and it will stay that way.**
   **The bank rejected API 508 (`fetchHRMSEmployeeDetails`).** Twenty-four of the twenty-five
   APIs we requested were approved; that one was not, so there is no HRMS directory to read and
   the roster is simulated. SM-4 fills `rm_id` / `rm_name` / `rm_branch` by deterministic
   round-robin over `data/roster.yaml` — eight fabricated names, branches and EINs, tagged
   `SIMULATED`. `src/model/roster.py` reads `data/bank/pulled.json`'s API 442 `accountManager`
   first, tagged `BANK_API`, and there is no longer a 508 branch in it at all — the platform's
   `app/atlas/policy.py` refuses 508 to both products, so no pull can put a 508 record there.
   **A live pull on 2026-09-17 walked all five documented CIFs and 442 answered for one**
   (one sandbox corporate customer) with an `accountManager` value that is a bank system
   code, with no manager name and no branch beside it. It is carried verbatim into the
   export's `roster.bank_account_managers` as evidence of what the endpoint returned, and
   `roster.bank_source_note` states in one sentence why it did not become an RM. The roster
   therefore stays `SIMULATED` by finding, not by default: that bank code standing in for
   "RM:" with a blank branch in front of a relationship manager would be a worse claim than
   an honestly labelled seed.
   `roster.rms[].source` badges each RM individually, so the moment 442 carries a *name* the
   two kinds can sit side by side on a screen.
   Suppressed leads are never assigned an RM at all — a customer who is never going to be called
   should not be shown as tied to one.
9. **The bank overlay (SM-6, `--bank`) covers 120 of 60,000 customers, honestly.**
   `data/bank/fixture.json` is the committed offline stand-in for a live Atlas pull; it is not
   sized to cover the whole book. A customer whose `cust_id` is one of the fixture's 120 reads
   `FIXTURE` for `identity` / `casa_behaviour` / `holdings` / `cross_bank`; every other customer
   reads `SIMULATED` for those same families even in a `--bank` run, because nothing was actually
   substituted for them (`model.bank.BankContext.provenance_for`). This is the same partial-
   coverage shape `data/bank/SCHEMA.md` documents for real AA consent — "consent is per customer
   and the customer may say no" — reproduced honestly rather than papered over with an aggregate
   `FIXTURE` badge that would overstate what happened for any one row.
10. **A live pull exists now, and it reached no customer in this book.** `data/bank/pulled.json`
    is written by the platform's enrichment stage (gitignored), so a `--bank` run reads
    `mode: mixed`. Every identifier the sandbox answered about belongs to its own handful of
    sample records, none of which is a customer here, so **no customer row is badged
    `BANK_API`** — the run-level family badge and the per-row badge are deliberately different
    statements (§ the provenance legend). The `BANK_API`-path tests in `tests/test_model_bank.py`
    / `tests/test_model_roster.py` still drive the *mechanism* from a synthetic `pulled.json`,
    which is what lets them pin the rule on a checkout with no pull at all. What the pull really
    contributed is run-level: the fetched amortisation schedules SM-5 now prices off (§ item 7)
    and the account-manager field SM-4 reports (§ the roster).
11. **SANKET never writes back to the bank.** API 428 (`createLead`, the only write in the 25-API
    surface `data/bank/SCHEMA.md` lists) is not called anywhere in this pipeline. Nothing here
    pushes a lead into a real CRM; `leads[]` is a read-only export for a human RM to act on.
12. **Ablation (SK-19) and stress (SK-22) are not run here.** The feature-family map they need is
    emitted (`metrics.feature_families`); the runs belong to validation runners 08 and 10.
13. **One contact per month, binary.** No call attempts that do not connect, no voicemail, no
    time-of-day effect — and an RM call costs the same as an SMS in the data, even though the
    whole product exists because it does not.
14. **The shopper detector, the uplift pair and the ranker are three fits, not one.** Only the
    ranker is "the model" in the mentors' sense; the other two are exhibits.
15. **The Business Radar screen is an appendix exhibit and validates nothing here.**
    `src/make_radar.py` scores real Indian companies' published filings with four
    hand-chosen weights over four financial ratios. It shares no code, features, label or
    population with this model. Its backtest **is** point-in-time as of 2026-09-21 —
    eligibility uses only defaults dated on or before each scored year, the percentile
    transforms are fitted on an expanding window of prior filings, deciles are cut within
    the year, and the interval is a company-clustered bootstrap: **1.88× (1.83–1.93)**
    across seven evaluation years, against **1.96×** for the retired look-ahead
    calculation, which is published beside it. The lift drifts down over the window
    (1.87× in 2018 to 1.61× in 2024). What no rebuild fixes: its outcome, "total
    borrowings rose on the next filing", is not an IDBI disbursement, and nobody called
    those companies, so nothing there evidences that an RM call causes anything.
16. **The delivered queue is a prefix of the priced budget.** The headline prices a 10%
    contact budget (553 calls at the snapshot); the cockpit ships the first 320 of the
    same ranked list. Both numbers are published (§8) and both come from one selection
    function, but a reader who takes "29 per 100" to describe the 320 rows on screen is
    reading the wrong budget — those 320 measure 33.1%.

---

## 11. Reproducing

```bash
python3 src/make_book.py                       # 60,000 x 30 liability book
python3 src/make_journeys.py                   # journeys, campaigns, labels
python3 src/score_and_pack.py                  # 5 seeds, full exhibits
python3 src/score_and_pack.py --seeds 7 --quick   # one seed, no OOT/permutation/ladder
python3 -m pytest tests/test_model*.py -q
```

Outputs: `app/public/sanket_data.json` (the cockpit) and `data/model_metrics.json` (the
validation runners' input). Neither is committed; both are regenerable.

---

## 12. The export contract — what the front end must change

The key diff against the pre-SM-1 `app/public/sanket_data.json` is **purely additive**: nothing
was removed or renamed at any level. What changed is *values*, and three of them will break a
build that has not been updated.

### Breaking on values, not keys

1. **`metrics.per_product` now has six keys** — `personal` (was `pl`), `gold`, `auto`,
   `education`, `home`, `lap`. A lookup table with three entries throws on the other three.
2. **`leads[].product` and every `product_menu[].product`** use the same six. `pl` is gone.
3. **`leads[].consent` now means *queueable*, not the DPDP flag.** It is `false` for every
   suppressed row whatever the reason — which keeps the behaviour right (a suppressed customer
   must never be queued) but makes a hard-coded "no marketing consent" caption wrong for the
   other seven reasons. The raw flag is `leads[].consent_marketing`; the reason is
   `leads[].suppression_reason`; `leads[].queued` is the clean boolean.
4. **`counts.no_consent` is now the snapshot drop-off pool's no-consent count**, not the whole
   book's — a few thousand, not tens of thousands. `counts.suppressed` is the full exclusion.
5. **`metrics.blended.baseline` is ~0.09, not ~0.013**, and the lifts in `prec_curve` are
   3–5×, not 20–30×. A screen that opens on a 2% budget will read ~41% at ~4.4× lift; the
   registered operating point is **10%**, and `metrics.headline` is the sentence to show.

### Added — top level

`provenance` *(new)* · `meta.{snapshot_month, population, model, generated_at, runtime_s}` ·
`counts.suppressed`

### Added — `metrics`

| Key | What it carries |
|---|---|
| `headline`, `headline_parts` | the sentence, and the two numbers it is built from |
| `baseline_dropoff_disbursement`, `precision_at`, `precision_at_10pct` | `{value, ci_low, ci_high, n, method}` |
| `per_product_auc`, `macro_auc` / `auc_macro`, `ece`, `oot_degradation_pp` | the brief's own spellings |
| `menu_hit_rate` / `menu_of_4_hit_rate`, `window_respect` / `window_respect_rate`, `shopper_signal_auc` / `shopper_auc` | each with its interval |
| `menu` | hit rate, top-1, the drop-off-anchor comparison, the switcher sub-metrics |
| `windows` | respect rate + `per_product_days` |
| `suppression` | `suppressed_count`, `suppressed_share`, `reasons` histogram, pool sizes |
| `shopper`, `signal_effects` | the detector's AUC; the four signals constrained *and* unconstrained |
| `bands` | `{SK-xx: {metric, band, op, threshold, value, observed, verdict, severity, gating, seed_mean, verdict_on_seed_mean, agrees_across_seeds}}` |
| `registered` | every value keyed by the exact `metric:` string in `validation/criteria.yaml` |
| `seeds` | `{n, list, default, spread, per_seed}` |
| `by_cut` | AUC + precision@budget for channel, segment, income band, tenure band, stage reached, city tier, age band |
| `oot`, `stability`, `leakage`, `baseline_ladder`, `feature_families` | the model-risk exhibits |
| `blended.{budget, precision_at_budget, precision_ci, row_auc}` | the operating point |
| `per_product[p].{auc_ci, ece, label, precision_at_budget}` | `auc_ci` is an object, not a pair |
| `prec_curve[].{ci_low, ci_high}` | Wilson bounds on every budget |
| `fairness[].n`, plus an **Income band** dimension | |
| `income_acc.{n, n_gig, gig_median_err}` | |

### Added — `leads[]`

`product_menu` (4 × `{product, label, p, reason, window_days, contact_by, emi, indicative_emi,
emi_source}`) · `negative_chips` (`{signal, text, impact, mentor_signal}`) · `suppressed` ·
`suppression_reason` · `queued` · `consent_marketing` · `contact_by` · `window_days` ·
`probability` · `p_any` · `shopper_score` · `dropoff_stage` · `dropoff_product` ·
`days_since_abandon` · `contacts_30d` · `last_contact_days` · `provenance` · `rm_id` / `rm_name` /
`rm_branch` (SM-4 — an EIN + name + branch on every **queued** lead, `null` on a suppressed one) ·
`emi_source` (SM-5 — `"BANK_API_433_sandbox_fixture"` on a normal run, `"TYPICAL_EMI"` only if the
sandbox rate is ever unavailable)

**Added 2026-09-21 (SM-7):** `abandoned_at` · `scored_at` · `outcome_horizon_days` ·
`queue_rank` · `blend`. `contact_by` changed meaning — it is now `abandoned_at + window`,
agreeing with the platform backend, where it used to be `scored_at + window` (§4, "Three
clocks"). `score` changed meaning too: it is the queue's **ordering key**
(`model.policy.DEFAULT_RANKING`, currently the calibrated product probability) carried at
six decimals, so sorting on it descending reproduces the delivered order; the old
`0.65 × intent + 0.35 × capacity` composite is still exported, as `blend`, as a displayed
signal. `queue_rank` is the lead's 1-based position in the delivered list, `null` on a
suppressed lead. The platform contract
(`rrsquad-platform/contracts/sanket_export.schema.json`) carries all of these, plus the
new `deceased` / `dormant` suppression reasons and the `contact_fatigue` negative signal
(§8, "Suppression").

**SM-5's two EMI numbers, disambiguated for L11:** `product_menu[].emi` is the number to say out
loud — the bank-rate EMI on that product's reference ticket, computed by `src/model/emi.py`'s
annuity formula from the captured API 433 rate (12.75% p.a., every product, since the sandbox
returns the same record regardless of the request body). `product_menu[].indicative_emi` is no
longer a second number: it is a **label** naming the ticket, tenor and rate `emi` was computed
from, so a screen never has to guess which of the two figures is the one to quote. The lead-level
`safe_emi` is unrelated to either — it stays the customer's own behavioural affordability ceiling,
used for the retained-income (capacity) check and for filling `{emi}` in the pitch/objection text.

### Added — top level, again

`roster` *(new, SM-4)* — `{source: "BANK_API"|"SIMULATED", n_rms, n_active, rms: [{rm_id, rm_name,
rm_branch, active}]}`. `provenance.families` (SM-6) now genuinely varies with `--bank`; without it,
every family is still `SIMULATED`, unchanged from SM-1–3.

### Not this lane's

Everything SM-1/SM-2/SM-3 flagged here — `rm_id`, real EMI, the bank-enrichment overlay — landed
at SM-4/SM-5/SM-6 (§ 13). What is still genuinely outside SANKET's scope: any real Atlas
credential or endpoint approval (owned by the platform, `rrsquad-platform/batch/`); API 428
`createLead` (never called — § 10 item 11); `meta.model_run_id` / `git_sha` / `criteria_sha` in
the platform export, filled by the batch that runs this script, not by this script.

### For the platform batch

`src/score_and_pack.py` keeps its zero-argument CLI and accepts `--out` (the export),
`--metrics-out`, and now `--bank` (§ 13). **Pass `--metrics-out` explicitly** from a batch runner:
it defaults to `data/model_metrics.json` inside this repo. A full five-seed run takes about 11
minutes; `--seeds 7 --quick` takes about 3 and skips the out-of-time, permuted-label and ladder
exhibits. The process exits 0 even when a band fails — a failing band is packed into
`metrics.bands`, and it is the *batch verifier's* job to refuse to publish, not the scorer's.
`--bank` adds one more file: `data/export/sanket_export.json`, in
`rrsquad-platform/contracts/sanket_export.schema.json`'s shape rather than this repo's own —
validate it with that repo's `contracts/validate.py sanket <path>` before publishing.

---

## 13. SM-4 / SM-5 / SM-6 — the RM roster, real EMI, and the bank-enrichment path

### SM-4 — the RM roster (`src/model/roster.py`, `data/roster.yaml`)

Source order, high to low: **1)** `data/bank/pulled.json`'s API 442 `accountManager` — tagged
`BANK_API`. **2)** `data/roster.yaml`, eight fabricated RMs across eight branches — tagged
`SIMULATED`. **API 508 (HRMS) was rejected by the bank**, so there is no HRMS branch in this code
at all and the roster is simulated as a matter of fact, not of convenience.

A live pull has now run. It walked all five documented CIFs and API 442 answered for one —
one sandbox corporate customer — whose `accountManager` reads as a bank system code: no
manager name, no branch. `usable_managers()` admits an entry to the roster only
once it carries a name, so this one does not, and the roster stays seeded. What 442 returned is
not thrown away: it rides into the export as `roster.bank_account_managers`, with
`roster.bank_source_note` giving the one-sentence reason, so a disclosure screen can show the
genuine bank field beside the simulated roster instead of either hiding it or dressing it up as a
person. `roster.rms[].source` badges each RM. The `BANK_API` path — a 442 record that *does*
carry a name — is covered in `tests/test_model_roster.py` against a synthetic `pulled.json`;
the live shape it parses is the captured one, verbatim.
Assignment is a **deterministic round-robin** keyed by `cust_id`, sorted lexicographically — never
by score, month or queue position — over the *whole* drop-off population (not just one month's
snapshot), so a customer keeps the same RM across runs and across model seeds. A suppressed lead
is never assigned one. The `roster` top-level block carries the roster itself plus its provenance.

### SM-5 — a real EMI (`src/model/emi.py`)

**The rate.** A probe against the live IDBI Atlas sandbox on 2026-09-16 (API 433) returned a
106-key composite JSON record. A full pass on 2026-09-17 established that 433 is the *only*
endpoint that answers that way — every other API returns its own structured record
(`rrsquad-platform/contracts/atlas/samples/live/`) — and that the sandbox is a **keyed store**
rather than a body-ignoring blob: an unknown key comes back as `{"message": "Data not found",
"sentKey": "..."}`. Its `rateInfo` carries `effectiveRate: 12.75` (a rate-card reading, matching
`data/bank/SCHEMA.md`'s 433 → `card_rate_pa` mapping); its `loanInfo` carries `netIntRate: 8.75`
for an *existing* loan in the same record, kept only as a sanity check on the amortisation
formula (`tests/test_model_emi.py::test_the_sandbox_rate_sanity_checks_against_the_captured_loaninfo_blob`).
Per the brief — "if the blob has one rate, use it for all and say so" — every product prices off
the single 12.75% p.a. reading.

**The schedule.** API 473 (`generateLoanRepaymentScheduletest`) is an amortisation engine: give
it a principal, a rate and an instalment count and it returns the level instalment plus one row
per month. It takes no customer identifier, so `rrsquad-platform`'s batch pull asks it **once per
reference ticket** (`batch/pull.py::TICKET_LADDER`), and `data/bank/pulled.json` carries six real
bank-computed schedules that `emi.schedule_for()` reads straight through to
`amortisation_schedules{}`, provenance `schedule: BANK_API`.

This card and the platform's own adapter both recorded 473 for months as an API that "has never
returned a body in this sandbox at all". That was wrong, and the cause was the same in both
places: 473 is absent from API 433's composite record, and absence from that record was mistaken
for absence from the sandbox.

**Three sources, and `emi_source` distinguishes all three**, best to worst:

| `emi_source` | When | `provenance.schedule` |
|---|---|---|
| `BANK_API_473_schedule` | 473 amortised this exact reference ticket — a normal run | `BANK_API` |
| `BANK_API_433_sandbox_fixture` | no fetched schedule; the 433 rate through `annuity_emi` (`DERIVED_FROM_433`) | `SIMULATED` |
| `TYPICAL_EMI` | neither — a broken reference table falls here; reachable, not normal | `SIMULATED` |

`data/bank/pulled.json` is gitignored, so which of the first two a given checkout reports depends
on whether the batch pull has run on it. Both are bank sources; the tag says which.

**Adopting 473 moved no number.** All six reference tickets were fetched live on 2026-09-17 and
every level instalment matches `annuity_emi` to the paise — personal ₹10,072.10, gold ₹13,380.00,
auto ₹13,575.18, education ₹9,028.16, home ₹34,614.35, lap ₹24,976.74 — so `REFERENCE_EMI` is
unchanged (₹10,100 / ₹13,400 / ₹13,600 / ₹9,000 / ₹34,600 / ₹25,000 after the usual ₹100
rounding) and nothing downstream of it shifted. That agreement is asserted in
`tests/test_model_emi.py`, so a future divergence surfaces in a test rather than in a lead's EMI.
`TYPICAL_EMI` is retained as a fallback the code can actually reach, not dead code. The reference
ticket size and tenor per product (`REFERENCE_PRINCIPAL` / `REFERENCE_TENOR_MONTHS`) remain
`assumed`, the same convention `book/products.py` uses for the table SM-5 replaces — the ticket
is ours even when the schedule is the bank's.

### SM-6 — the `--bank` enrichment path (`src/model/bank.py`, `src/model/export.py`)

`--bank` on `src/score_and_pack.py` is the only thing SM-6 gates; without it the pipeline is
byte-for-byte the SM-1–5 pipeline, every family `SIMULATED`. With it:

1. Read `data/bank/pulled.json` (what each Atlas API answered) and `data/bank/provenance.json`
   (the platform batch's own family/endpoint summary) if either exists.
2. Apply `data/bank/SCHEMA.md`'s fallback rule exactly: an API that answered → `BANK_API`; an API
   that exists but did not answer → `FIXTURE` (from `data/bank/fixture.json`); a family no Atlas
   API supplies at all (`digital`, `consent`, `journey`) → always `SIMULATED`; the `model` family →
   the weakest of the other seven.
3. **Coverage is reported per customer, not just in aggregate.** `data/bank/fixture.json` covers
   120 of the book's 60,000 customers (`cust_id` overlaps by construction — see
   `tests/test_model_bank.py`). A customer outside those 120 reads `SIMULATED` for a family the
   run's own summary calls `FIXTURE`, because nothing was actually substituted for them — the same
   shape `data/bank/SCHEMA.md` describes for partial AA consent ("a book with approved 595/739
   endpoints and no consents still yields `cross_bank: FIXTURE`... consent is per customer").
4. Emit `data/export/sanket_export.json` in `rrsquad-platform/contracts/sanket_export.schema.json`'s
   shape — a different, larger contract than `app/public/sanket_data.json`: it adds `customers[]`
   (the whole scored snapshot pool, not just the ~320-lead queue), `journeys[]` (the most recent
   application attempt per exported customer), and `amortisation_schedules{}` (one schedule per
   product, keyed for reuse across every lead pitching it), and flattens most of `metrics` instead
   of nesting it under `blended`.

**Validated clean against `rrsquad-platform/contracts/validate.py` / the schema directly** (see
`tests/test_model_export.py`, which skips if the sibling platform repo is absent) — **zero
unexpected errors**, with exactly the three gaps the brief pre-authorised:
`meta.model_run_id`, `meta.git_sha`, `meta.criteria_sha`, all filled with valid-shaped placeholders
(a nil UUID, forty and sixty-four zero hex digits) that the platform's own batch is expected to
overwrite. Two mapping decisions worth recording: the schema's `confidence_interval.method` enum
(`wilson` / `bootstrap` / `delong` / `normal-approx`) has no slot for this repo's own
`"hanley-mcneil"` AUC-interval label, mapped onto `"delong"` as the nearest of the four; and
`amortisation_schedules[].provenance.schedule` reads `"BANK_API"` exactly when API 473 actually
amortised that ticket in the pull behind the run, and `"SIMULATED"` when the rows were derived
from the 433 rate instead — the platform's three-value enum has no slot for "derived", and
`SIMULATED` ("no API supplied this") is the nearest honest reading of it.

### Provenance legend

Three values only, everywhere a `provenance` block appears — per `data/bank/SCHEMA.md` and the
platform contracts:

| Value | Means |
|---|---|
| `BANK_API` | Pulled live from an Atlas sandbox endpoint that actually answered. |
| `SIMULATED` | Produced by `src/book` / `src/journeys` because no Atlas API supplies this at all — the roster seed, EMI reference table, journey/consent/digital columns. |
| `FIXTURE` | Stood in from the committed `data/bank/fixture.json` because a live pull was unavailable or incomplete for this customer. |

Trust order `BANK_API > SIMULATED > FIXTURE` (best to least trusted); the `model` family badge is
always the *weakest* of the other seven, so a screen never shows a stronger badge on the model
than on the weakest input that fed it.

**`BANK_API` on a customer means the bank answered about *that customer*.** A family is
`BANK_API` at **run** level once its endpoint answers — a statement about the call, not about
any particular row. Since the sandbox holds only a handful of sample customers the two levels
say different true things, and `src/model/bank.py` keeps them apart: it records the identifiers
the pull actually came back with and awards a row `BANK_API` only if it is one of them,
degrading everyone else to `FIXTURE` or `SIMULATED` exactly as before any pull existed. The
sandbox's sample ids and this book's generated ids are disjoint, so no customer row in this
build carries `BANK_API`. `NOT_COLLECTED` is a fourth, separate value reserved for a
column deliberately never fetched — API 408 (§ 5) is the one case of it in this repo.
