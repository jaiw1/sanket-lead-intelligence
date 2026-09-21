# SANKET — Lead Intelligence for the Liability Book

*An entry for **IDBI Innovate 2026 · Track 2 (Prospect Assist AI)**.*

**Deployed:** SANKET runs on IDBI's own sandbox server at **`https://172.16.8.60/sanket/`**
(nginx, the real backend, real auth). That is a **private** address inside the bank's
AWS sandbox VPC — there is no public IP, and it is reached over an SSM port forward, so
the link will not open from an ordinary browser.

**🟠 Public demo build:** **https://sanket-leads.vercel.app** — the same front end as a
static bundle, no login and no backend behind it. Useful for looking at the screens
when you cannot reach the sandbox; it is not the deployment.

## What SANKET is

A bank sitting on its own savings and current-account book already knows who is
worth calling — it just doesn't act like it: relationship managers cold-call an
unranked list at whatever the branch does today, and the customer who started a
home-loan application last month and quietly abandoned it gets nothing. SANKET reads
that liability book's behaviour — salary rhythm, rent step-ups, balance build-ups,
fuel/cab spend, app dwell — and turns it into a ranked, explained calling list, but
only over the population the mentors said matters: **customers who already started an
application and dropped off**, not the whole book (lead generation is explicitly out
of scope — see "What we did not build," below). **Conversion means disbursement**, per
the mentor mandate — not a lead touched, not an application opened, but the loan
actually funded inside that product's decision window after an RM makes contact. Every
lead gets a menu of the four products they're most likely to take, a window to call
them by, the reasons in plain English, and — beyond plain propensity — an uplift
estimate of whether the call itself is what moves them.

## The headline

> **9 → 29 disbursements per 100 RM calls**

That is two measured numbers over the *same* hundred calls, the *same* population,
and the *same* label — not a lift ratio, not a comparison across denominators:

| | value | how it's measured | source |
|---|---|---|---|
| random-contact disbursement rate (the 9) | **9.48%** (95% CI 8.46–10.59%, n=2,915; 5-seed mean 9.10%, range 8.93–9.48%) | contact a uniformly random 10% of the eligible drop-off population, at seed 7 / across seeds 7–11 | `data/model_metrics.json` → `metrics.baseline_ladder` ("random contact" rung), `metrics.seeds.spread.baseline`; `validation/report/REPORT.md` SK-01 |
| precision at the 10%-budget queue (the 29) | **29.06%** (95% CI 27.44–30.73%, n=2,915; 5-seed mean 28.11%, range 27.47–29.06%) | contact the model's top-10%-ranked slice of the *same* population | `data/model_metrics.json` → `metrics.precision_at_10pct`, `metrics.seeds.spread.precision_at_budget`; `validation/report/REPORT.md` SK-02 |

**Population and label, exactly.** The scoring unit is one **(customer, month) row**
for customers in the **drop-off population** — consented, contactable customers with
at least one abandoned loan application in the trailing 365 days and no disbursement
already in flight — evaluated at the first instant of the month, before anything that
happens inside that month can leak in. The label is 1 if, contacted that month, the
customer disburses *some* product inside *that product's own* decision window
(personal 1 day · gold 1 day · auto 3 days · education 7 days · home 14 days ·
lap/loan-against-property 14 days). Both the 9 and the 29 are disbursement rates over
that same eligible population and the same 100 calls — one caller dials at random, the
other dials the model's top decile. Full derivation: `DATA_CARD.md` §12.1–§12.3.

This retires **every** earlier framing of the number: `1% → 36%`, `28×` lift, and
`top-2%` are gone. The old `1%` baseline was measured over the *whole* liability book
at a 3-month horizon (a customer no RM would ever call is still in that denominator);
the mentor-stated `8–10%` baseline is specifically about calling a **drop-off list**,
which is a different, smaller, harder population, and it inflated the apparent lift by
roughly 3×. (The whole-book `~1%` bank-stated cold-call rate is still real and still
the motivating problem — see "The problem" in the app's Mission Control tab — it is
just not the number the 29 should be measured against.)

A pre-registered **oracle ceiling** exists for the 29: the generator solves its
signal-to-noise knob so that a ranker who could see the *latent* index the label is
drawn from — which no real model can — reaches precision@10% ≈ 0.32. The model reads
those latents only through noisy observables and lands below that, at 0.29. Detail:
`DATA_CARD.md` §12.3.

**The number describes the list an RM actually receives.** Until 2026-09-21 it did
not: precision was measured by ranking held-out rows on the top product's probability,
while the delivered queue was ranked on `0.65 × intent-percentile + 0.35 × capacity`
and then truncated — so the headline priced a list nobody was handed. One function,
`src/model/policy.py`, now performs the whole selection (suppression → eligibility →
ranking → truncation → tie-break on customer id) and **both** the evaluator and the
packer call it; `tests/test_model_policy.py` compares the exported queue's customer ids
against the evaluator's, in order.

Reconciling the two forced a choice of ranking, and it was made by measurement against
a rule fixed in advance — keep the capacity blend only if it came within 2 percentage
points of probability-only ranking at the 10% budget:

| ranking | precision@10%, seed 7 | 5-seed mean |
|---|---|---|
| calibrated product probability | **29.06%** | 28.11% |
| 0.65 intent + 0.35 capacity (the old queue order) | 21.92% | 20.52% |

The blend costs **7.1 percentage points**, three and a half times the tolerance, so the
queue now ranks on probability and `capacity` survives as a displayed signal an RM can
read rather than a ranking input. `Hot` is cut on that same ranking, which it was not
before: of the 320 leads the old cockpit queue delivered, only 147 were in its own `hot`
tier. Both rankings are re-measured every run into `data/model_metrics.json` →
`metrics.ranking_comparison`.

The cockpit exports the first **320** rows of that ranked list rather than the whole
553 the 10% budget buys — a tighter budget (5.8%), whose held-out precision is
**33.1%** (95% CI 30.9–35.4%), reported separately as
`metrics.delivered_queue.precision_at_queue_size`. The 29 is the number for a 10%
calling budget; 33 is the number for the 320 rows the demo ships. Neither is measured on
a different selection rule from the other.

The whole-population baseline ladder (`data/model_metrics.json` →
`metrics.baseline_ladder`; SK-25, reported not gated):

| Rung | precision @ 10% budget | 95% CI |
|---|---|---|
| random contact | 9.48% | 8.46–10.59% |
| balance-ranked (what a branch does today) | 9.95% | 8.91–11.09% |
| logistic scorecard, 16 features | 25.83% | 24.28–27.45% |
| **SANKET — one LightGBM, six products** | **29.06%** | 27.44–30.73% |

Ranking by account balance — the intuition a branch actually uses — is worth half a
point over calling at random. A plain logistic model gets most of the way there; the
gradient-boosted model adds another 3.2 points on top of it. Both of those are
findings a pitch deck would rather not have, and both are published.

## How it works

```
book (60,000 customers × 30 months, 6 products)
  → journeys (application attempts, funnel, window-shopper latent)
    → labels (drop-off population, label_disbursed_in_window, decision windows)
      → ONE model (LightGBM, `product` as a categorical, isotonic-calibrated per product)
        → menu of 4 (top-4 products per lead, probability + plain-English reason)
          → windows (contact_by date, per product's decision window)
            → suppression (8 reasons, priority order — see below)
              → RM queue (Hot / Warm / Cold, round-robin RM assignment)
                → CRM push (dry run → 456 dedupe → 428 createLead, manager-gated)
```

- **Book → journeys → labels.** `src/make_book.py` generates the liability panel;
  `src/make_journeys.py` layers application attempts, the window-shopper latent, and
  the drop-off labels on top of it, and writes `data/labels.csv` — the file the model
  trains and the validation runners grade on. `DATA_CARD.md` §11–§12.
- **One model, six products.** Pre-SM-1 this was three separate LightGBMs (home,
  auto, personal) trained over the *whole* book. SM-1 replaced that with **one**
  LightGBM over a stacked (customer, month, product) frame, `product` as a
  categorical, scored only on the drop-off population, across all **six** products
  (home, loan-against-property, gold, auto, education, personal). `MODEL_CARD.md` §1,
  §6.
- **Menu of four.** Each lead gets its top-4 products by probability with a
  plain-English reason per product (menu-of-4 hit rate 96.5%, SK-13). The menu's real
  value is on the 29% of positives who switch product from the one they abandoned —
  read `MODEL_CARD.md` §8 "The menu of four" before quoting the top-1 number alone;
  the drop-off anchor (offer them what they abandoned) already gets top-1 right 70.5%
  of the time with no model at all.
- **Windows, and which clock they run on.** Each offered product carries its own
  decision window. `contact_by` = **abandonment timestamp + that window** — the same
  rule the platform backend applies to `journeys.abandon_ts`, and not, as it was until
  2026-09-21, the scoring snapshot plus the window. Every lead now states all three
  instants separately: `abandoned_at`, `scored_at`, `contact_by`, plus
  `outcome_horizon_days` (days **after contact** inside which a disbursement counts).
  A `contact_by` in the past is a correct answer and means the window shut before the
  monthly snapshot reached that customer. **Which clock should drive urgency is an open
  question for the mentors**; abandonment is the assumption this build documents and
  implements end to end.
- **Suppression.** Eight reasons, evaluated in priority order, first match wins:
  `deceased` · `no_marketing_consent` · `dnd` · `account_dormant` ·
  `application_in_flight` · `recent_decline` · `recent_contact` (7-day cool-off) ·
  `already_holds_product`. Suppressed rows are scored and shown **with the reason
  attached** and never enter the queue, a metric, or training. At the current
  snapshot: 1,927 of 7,456 pool rows (25.8%) suppressed, reason histogram in
  `data/model_metrics.json` → `metrics.suppression`. `MODEL_CARD.md` §7.
- **RM queue, round-robin.** Queued leads are assigned an RM by **deterministic
  round-robin** over the roster, keyed by customer id — never by score, month, or
  queue position — so a customer keeps the same RM across runs (`src/model/roster.py`,
  SM-4). A suppressed lead never gets an RM.
- **CRM push — dry run → 456 dedupe → 428.** Pushing a lead into the bank's CRM is
  API 428 (`createLead`), the only *write* anywhere in this platform's 25-API
  surface. The UI (`app/src/components/CrmPushDialog.jsx`) is a two-step flow: step 1
  is always a **dry run** that shows the exact 428 payload and the API-456 dedupe
  verdict (has the bank already got a matching record?) with nothing sent; step 2, a
  manager-gated confirm, sends `dry_run:false` + `confirm:true` together. On the
  backend (`rrsquad-platform/app/atlas/adapters/a428_create_lead.py`) a real write
  additionally needs `ATLAS_ALLOW_WRITES=1` and `ATLAS_MODE=live`, and every attempt
  is written to the audit log with its `leadId`. See "What we did not build" — no
  live write has ever actually gone out; every run to date is dry-run only.

## What is real, what is synthetic, what is bank-sandbox

Every field in this product carries one of these provenance tags (`data/bank/SCHEMA.md`,
mirrored in `rrsquad-platform/app/atlas/README.md`):

| Tag | Means |
|---|---|
| `BANK_API` | Pulled live from an IDBI Atlas sandbox endpoint that actually answered. |
| `SIMULATED` | Generated by `src/book`/`src/journeys` because no Atlas API supplies this at all (the roster seed, journey/consent/digital columns). |
| `FIXTURE` | Stood in from the committed `data/bank/fixture.json` because a live pull was unavailable or incomplete for that specific customer. |
| `NOT_COLLECTED` | Deliberately never fetched — the one case is API 408 (CIBIL/bureau), see below. |

**The sandbox itself is mock data, not a live data source.** All 23 readable approved
APIs were called for real on 2026-09-17. Every one answered HTTP 200 with **no auth header
and no subscription check**, and every one answered with **its own structured mock record** —
the earlier reading, that the sandbox served one shared 106-key blob everywhere, generalised
from API 433, which is the single endpoint that does return a composite record carrying a
slice for every API. What is true everywhere is that the data is fabricated and the store is
**small**: it holds a handful of sample customers and accounts, and it really does look the
key up (see the next section). So a `BANK_API` tag here means "the wiring works and the
sandbox answered," not "this is a real customer's data," and it always travels with
`sandbox_fixture: true`.

**And "the endpoint answered" is not "the endpoint answered about you."** An enrichment pass
has now run against SANKET's book, so `data/bank/pulled.json` exists and a `--bank` run reads
`mode: mixed` — a family whose API answered is `BANK_API` at **run** level. Per customer it
stays honest: `src/model/bank.py` records the identifiers the pull actually came back with and
badges a customer `BANK_API` only if they are one of them. The sandbox's sample ids and this
book's generated ids are disjoint, so **no customer row carries `BANK_API`**; each reads
`FIXTURE` if the committed `data/bank/fixture.json` covers them (120 of 60,000) and `SIMULATED`
otherwise, exactly as before the pull. The genuine bank data in a `--bank` export is the
run-level endpoint block, the fetched amortisation schedules and what the account-manager API
returned — all carried and badged where they are. The currently shipped app export
(`app/public/sanket_data.json` → `provenance`) predates the pull and still reads
`"mode": "fixture"`; the metrics beside it are identical either way, since nothing the pull
returned reaches a model input. `MODEL_CARD.md` §12–13; `DATA_CARD.md` §0.

**Which of the 25 requested APIs SANKET uses.** Of the 25 APIs the team requested
across both tracks, **22** are in SANKET's own surface: nine shared with DRISHTi
(391 KYC, 402 overdue/arrears, 442 account manager, 362, 393, 365, 394, 456 customer
dedupe, 433 rate card — the first live call, zero customer-ID dependency), three more
shared (473 repayment schedule, 538, and 508 HRMS — **which the bank rejected**, so the
RM roster is simulated rather than seeded from HRMS), and nine SANKET-only (428
`createLead`, 590/591/592/593, 497/498 webhooks, 595/739 cross-bank transactions for
the EMI-outflow and salary-elsewhere gaps). 415 (CKYC) is subscribed but deliberately
never scored on. Plan §H has the full both/DRISHTi-only/SANKET-only split.

**What the sandbox actually holds, and which records are real.** It is a keyed store
with a handful of sample customers, not the canned blob an early probe took it for — an
unknown key answers a `{"message": "Data not found", "sentKey": "acctId#<the id sent>"}`
shaped error.
A live pull on 2026-09-17 walked every documented identifier, and this is what came back:

| API | Real for | What it gave |
|---|---|---|
| 365 account enquiry | three sandbox accounts | balances, scheme, branch, customer name |
| 391 loan account details | two of those three sandbox accounts | net interest rate, open date, customer |
| 394 accounts by CIF | one sandbox corporate customer | one account, ₹56,780.25 |
| 402 overdue details | that same sandbox customer | three loan positions, DPD and NPA status |
| 442 customer limits | that same sandbox customer | exposure summary, ten limits, `accountManager` |
| 456 dedupe | that same sandbox customer | name, DOB, PAN, CKYC |
| 473 repayment schedule | no customer id — it is a calculator | six bank-computed amortisations, one per reference ticket |

Everything else in the book — all 60,000 customers — stays `SIMULATED`. The three
accounts and two customer ids above are what a demo should open.

**EMI provenance: a fetched schedule, a rate, then a constant.** `emi_source` on every
lead and every product-menu row is one of three values, in that order of preference:
`BANK_API_473_schedule` (API 473 amortised this exact reference ticket — what a normal
run reports), `BANK_API_433_sandbox_fixture` (no fetched schedule, so the single 12.75%
p.a. 433 rate through a standard annuity formula), `TYPICAL_EMI` (neither — the retained
flat constant). API 473 was for a long time recorded here as an endpoint that returns
nothing; **that was wrong**, and it traced to 473 being absent from API 433's composite
record rather than from the sandbox. It answers, it is an amortisation engine, and the
instalment it computes agrees with our own formula to the paise on all six products —
which is why adopting it moved no published number. `MODEL_CARD.md` §13 (SM-5).

**The RM roster is simulated, and API 442 is why it stays that way.** The bank rejected
API 508 (HRMS), so there is no staff directory to read. API 442 carries the only
account-manager field left in the catalogue and it is wired as the top-ranked roster
source — but the one CIF the sandbox answers for returns an `accountManager` value that
is a short alphanumeric bank system code, not a person's name, with no manager name and
no branch beside it. That value is reported verbatim in the export's
`roster.bank_account_managers`, and `roster.bank_source_note` says in one sentence why it
did not become an RM. Putting that bank code in as "RM:" with a blank branch in front of
a relationship manager would be a worse claim than an honestly labelled seeded roster,
not a better one.

**API 408 (CIBIL/bureau) is never called at prospecting, on purpose.** It sits in
`EXCLUDED_FEATURES` and `app/atlas/policy.py` refuses it before a rate-limit slot or a
token is even spent — a governance decision, not an oversight: a credit-bureau pull at
the *prospecting* stage (before the customer has even been offered anything) is not
something a compliance reviewer should see this product do. It becomes available only
later, at lead→application.

## Validation

All 25 acceptance bands live in `validation/criteria.yaml`, and — the whole point of
pre-registration — that file first entered git at **2026-09-16T11:06:09+05:30**,
*before* any of these results existed; that commit timestamp is the evidence, not this
README. Run `make -C validation validate` to regenerate
`validation/report/{REPORT.md,report.json,figures/}` from scratch.

**The 16 Sep amendment (scoping, not thresholds).** SK-01/SK-02 (and the leakage
checks SK-17/SK-18) were re-pointed at the drop-off population once the
application-journey layer existed to define one — the original registration predates
that layer and so predates having a denominator to name. **No band's threshold moved.**
Full text of the amendment, verbatim, is in `validation/report/REPORT.md`'s
"Pre-registration" section and at the foot of `validation/criteria.yaml`.

**Current report** (`validation/report/REPORT.md`, generated 2026-09-21T15:25:52+05:30
from commit `b4d5c1c8d697`; all 25 criteria graded — none pending at time of writing):
**16 pass · 0 gating fail · 9 reported (no target) · 2 of those reported criteria carry
a disclosed failing value.**

| ID | Metric | Band | Value | Verdict |
|---|---|---|---|---|
| SK-01 | random-contact disbursement rate | ∈ [8, 10]% | 9.48% | pass |
| SK-02 | precision@10% budget | ∈ [25, 35]% | 29.06% | pass |
| SK-03 | precision @5% / @20% | reported | 35.8% / 23.0% | reported |
| SK-04 | conversion timing among converters | ≥ 90% | 90.1% (packed seed) | **pass on the packed seed, FAIL on the 5-seed mean (88.1%)** — see below |
| SK-05 | window-shopper detector AUC | ≥ 70% | 84.7% | pass |
| SK-06 | headline uplift | reported | "9 → 29 per 100" | reported |
| SK-07 | out-of-time degradation | ≤ 5.0 pp | −0.80 pp (improves) | pass |
| SK-08 | per-product AUC, ×6 | ≥ 0.75 each | min 0.804 (personal) | pass |
| SK-09 | macro AUC | ≥ 0.78 | 0.865 | pass |
| SK-10 | AUC + precision by cut (7 cuts) | reported | 33 cells | reported |
| SK-11 | ECE overall | ≤ 0.03 | 0.0074 | pass |
| SK-12 | ECE per product | ≤ 0.03 | max 0.0027 | pass |
| SK-13 | menu-of-4 hit rate | ≥ 80% | 96.5% | pass |
| SK-14 | top-1 product accuracy | reported | 70.4% | reported |
| SK-15 | 4 window-shopper signals negative | ≥ 4 | 4 | pass |
| SK-16 | population stability index | ≤ 0.10 | 0.009 | pass |
| SK-17 | forbidden inputs used | = 0 | 0 of 60 | pass |
| SK-18 | permuted-label AUC | ∈ [0.48, 0.52] | 0.506 | pass |
| SK-19 | ablation by feature family | reported | removing the shopper-signal family costs the most precision (−6.9 pp); a few families are slightly negative-cost | reported |
| SK-20 | seeds run | ≥ 5 | 5 | pass |
| SK-21 | cross-seed CI width | ≤ 4.0 pp | 1.46 pp | pass |
| SK-22 | stress scenarios | reported | 2× base-rate reweight +1.5 pp; missing-channel 0.0 pp | reported |
| SK-23 | adverse-impact ratio (fairness) | ≥ 0.80 (reported, not gated) | **0.69 (gig)** | **FAIL, disclosed on purpose** — see below |
| SK-24 | gig failure disclosed on screen | must exist | yes | pass |
| SK-25 | baseline ladder | reported | 4 rungs (table above) | reported |

**The two honest fails, both disclosed rather than tuned away:**

- **SK-04, conversion timing among converters — passes on the packed seed, fails on
  the 5-seed mean.** First, what it measures, because the earlier wording here was
  wrong: of the held-out leads inside the contact budget that **did** disburse, the
  share whose disbursement landed inside the window of the product the model offered.
  It is a statement about how fast conversions arrive. It is **not** contact-SLA
  compliance — it does not measure whether an RM called before `contact_by`, and
  nothing in this pipeline observes an RM dialling at all, so contact-SLA compliance is
  unmeasured everywhere in this repo. The criterion's own description in
  `validation/criteria.yaml` was corrected on 2026-09-21 (a dated amendment; the
  threshold did not move).
  90.1% on the seed the app ships (n=908) clears the ≥90% floor; the mean across 5
  registered seeds is 88.1% (range 86.9–90.1%), which does not. The mechanism: the
  model's top-1 recommendation is usually the product the customer abandoned, and when
  they come back for a *different*, shorter-window product instead, the disbursement
  lands outside the *offered* product's clock. Fixing it would mean biasing the top-1
  choice toward long-window products — metric-gaming rather than serving the RM — so
  it ships as measured, with both verdicts carried in
  `metrics.bands["SK-04"]` (`verdict`, `verdict_on_seed_mean`, `agrees_across_seeds`).
- **SK-23, gig-worker fairness — 0.69 four-fifths ratio, below the 0.80 line.** Of 14
  group cells checked (occupation segment × 3, city tier × 3, age band × 3, income
  band × 5), 12 pass; gig workers (0.69) and the lowest income band (0.79) do not.
  Severity is `report`, not `fail`, in `criteria.yaml` on purpose — it is a *reported*
  measurement, never a gate a run can pass by tuning. **What it is not caused by:
  capacity.** SK-23 has always been measured on the probability-ranked selection, and
  the ratio is unchanged at 0.69 now that capacity has been removed from the queue's
  ranking entirely — so the capacity blend was never the mechanism, whatever the
  earlier wording here implied. The standing hypothesis is the behavioural income
  estimate, accurate for only 76.4% of gig workers within ±15% (vs 95.2% overall),
  reaching the model through the income-derived features; that is a hypothesis this
  README should not state as a finding until it is tested feature by feature.
  Segment-aware calling quotas remain designed, not built. `MODEL_CARD.md` §8.

`MODEL_CARD.md` §9 carries the same table generated a few hours earlier
(2026-09-16), before validation runners 08–12 (ablation, stress, seeds, fairness,
baseline ladder) had finished landing — it still shows SK-19/SK-22 as "not run." The
table above, from `validation/report/REPORT.md`, is the current one; nothing was
pending at the time this README was written.

## Architecture

The product-facing pieces (`src/`, `app/`) live in this repo. The real backend — auth,
roles, the audit trail, and the batch pipeline that runs this repo's own scripts as
subprocesses — lives in a **sibling repo**,
[`rrsquad-platform`](https://github.com/jaiw1/rrsquad-platform) (private during
judging; the team's repos flip public on submission day). No secrets, credentials, or
Atlas tokens live in either repo's git history.

- **Roles:** `admin` · `manager` · `credit_officer` · `relationship_manager`, enforced
  server-side; a credit officer is scoped to assigned portfolios, an RM to assigned
  leads.
- **Audit:** an append-only, hash-chained `audit_log` table — `UPDATE`/`DELETE` are
  both `REVOKE`d from the application's database role *and* blocked by a trigger, so
  tampering isn't just discouraged, it's rejected at the database.
- **Batch gate:** scoring is a batch job, never a live request. Seven stages — pull →
  enrich → generate → score → load → **verify** → publish. The verify stage runs this
  repo's own `validation/run.py` and attaches the result to the run record; **a run
  that fails validation stays `candidate` and the previously-published run is left
  untouched** — nothing this repo's model produces reaches a bank employee's screen
  without passing the table above first.

Full detail, including the seven-stage batch, the authorisation matrix, and the
security posture (argon2id, session cookies, CSRF, rate limits, no CORS): that repo's
own `README.md`.

## How to run locally

```bash
# 1) generate the book, the journey/label layer, train, and pack (from this repo's root)
python3 src/make_book.py                          # 60,000 customers x 30 months, 6 products
python3 src/make_journeys.py                       # journeys, campaigns, labels (drop-off population)
python3 src/score_and_pack.py                       # 5 seeds, full exhibits (~11 min)
python3 src/score_and_pack.py --seeds 7 --quick     # 1 seed, skips OOT/permutation/ladder (~3 min)
# (optional) python3 src/make_radar.py              # appendix Business Radar exhibit; needs the
                                                      # source financial dataset, not in this repo

# 2) run the app
cd app && npm install && npm run dev                # http://localhost:5191

# 3) validate
make -C validation validate                         # writes validation/report/{REPORT.md,report.json,figures/}
python3 -m pytest -q                                # unit tests (repo root)
cd app && npm test                                  # frontend unit tests (vitest)
```

`app/public/sanket_data.json` and `data/model_metrics.json` are both regenerable
outputs of step 1 and are gitignored, not committed — regenerate them, don't expect
them checked in.

## Appendix — the Business Radar exhibit

The app carries one screen, **Business radar**, that is not part of SANKET. It scores
real Indian companies' published annual filings as business-banking prospects and
backtests whether the top-ranked ones raised borrowings the following year (`2.0×` the
rest, top decile vs the other nine). It is included because the retail book is
synthetic and it is worth showing that the team can work with real filings.

It proves nothing about SANKET, and three specific things about it are worth stating
plainly rather than leaving for a reader to find:

1. **It is a different model.** Four hand-chosen weights over four financial ratios
   (income growth 40, interest cover 25, borrowing headroom 25, positive net worth 10).
   SANKET is a trained LightGBM over a retail drop-off population predicting
   disbursement inside a product window after an RM call. They share no code, no
   features, no label and no population.
2. **The backtest is not point-in-time, so the `2.0×` is an upper bound.** Companies
   with any default anywhere in their recorded history are excluded *before* the
   historical years are scored (`src/make_radar.py`, `load_default_history`), and each
   ratio's percentile rank is taken across all company-years pooled together
   (`pctl`). Both use information that did not exist at the dates being scored. Doing
   it properly means recomputing eligibility and the percentile transforms as of each
   historical date, with an expanding-window backtest and company-clustered
   uncertainty. That has not been done, and until it is, the number belongs in an
   appendix.
3. **"Raised borrowings" is not an IDBI disbursement.** The outcome is an increase in
   total borrowings from *any* lender on the next filing. Nobody called these
   companies — there is no treatment and therefore no causal claim available.

Only derived aggregates and anonymised exemplars ship with the app; no company names
and no raw rows.

## What we did not build, and why

- **Lead generation.** SANKET scores the drop-off population only — a customer who
  never started an application is out of scope by mentor mandate, not by omission.
  Finding *new* prospects (look-alike acquisition) is listed as future work, not built.
- **A live CRM write.** The 428 `createLead` write path is fully implemented — the UI
  dry-run, the 456 dedupe check, the manager-gated confirm, the audit row — but it has
  never actually fired a real write. The backend additionally guards it behind
  `ATLAS_ALLOW_WRITES=1` and `ATLAS_MODE=live`, neither of which has been set outside a
  test. Every push to date is dry-run only; nothing synthetic has ever landed in a
  real CRM.
- **A live Account-Aggregator consent round-trip.** Consent is `SIMULATED` in every
  run to date — there is no real DPDP consent-store join, because no real customer
  consent has ever existed to join against. The webhook plumbing for it (497/498) is
  built and tested against the mock only; nothing here has ever proven a live consent
  round-trip.
- **Live token-based OAuth (UAT/production).** The sandbox needs no token at all — a
  live API 433 call on 2026-09-16 answered with no `Authorization` header and no
  subscription check — so the client-credentials exchange the bank's portal describes
  for UAT/production is written and tested only against a mock token endpoint; the
  bank has not published the real token URL, and nothing here has ever exercised it
  against a live one.
- **A live Atlas pull has now run, and it reached none of this book's customers.**
  `data/bank/pulled.json` exists (gitignored), so a `--bank` run is `mode: mixed` rather
  than `mode: fixture`; what it holds is the sandbox's own handful of sample records — real
  responses, fabricated data — and none of their identifiers is a customer in this book.
  So no customer row is badged `BANK_API`: the committed `data/bank/fixture.json` still
  covers 120 of 60,000 as the offline stand-in and everyone else stays `SIMULATED`. What
  the pull genuinely contributed is run-level: the endpoint block, the fetched amortisation
  schedules behind `emi_source`, and what the account-manager API returned.
- **The `pl` product-vocabulary shim is still present in `src/book/`**, kept for one
  legacy-equivalence test (`tests/test_book_equivalence.py`) and because
  `src/journeys/**` reads the canonical `product_canonical` spelling regardless — no
  *consumer* of the data (model, app, export) reads the compat spelling any more, but
  the shim itself was not deleted, contrary to the original SD-S1 plan.
- **In-arrears suppression.** "Never pitch anyone in arrears" cannot be enforced from
  this data — SANKET's book is a liability book with no loan-performance data in it.
  In the bank's real environment it would come from API 402 (`dpd`/`npaStatus`); here
  it is a recorded gap, not a faked signal.
- **Per-app API rate-limit split.** The bank's own sandbox rate limit (120 requests/min)
  is enforced **per account, not per application** — so it does not separate SANKET's
  traffic from DRISHTi's on the bank's side. The platform enforces a shared
  token-bucket client-side instead (`rrsquad-platform/app/atlas/`), because the bank
  does not.

## Data and model cards

- [`MODEL_CARD.md`](MODEL_CARD.md) — what changed at SM-1–6, intended use, features,
  suppression, full results, known limits, the export contract.
- [`DATA_CARD.md`](DATA_CARD.md) — the generator, the population, the journey and
  label layers, every parameter's provenance (`sourced` / `sourced-approx` / `assumed`),
  known unrealisms.
- [`validation/README.md`](validation/README.md) and
  [`validation/criteria.yaml`](validation/criteria.yaml) — the pre-registration
  contract itself.

## Team, licence

**Team RR Squad** — Yuvraj Kundargi, Jai Wadhwa. IDBI Innovate 2026, Track 2 (Prospect
Assist AI).

**All rights reserved.** No licence is granted. This repository is published so that the
evaluators of IDBI Innovate 2026 can read and assess the work; it is not offered for reuse.
Materials produced for the hackathon are subject to the non-disclosure agreement executed with
IDBI Bank on 31 August 2026, which governs ownership of the deliverables.

No AI-generated content is attributed anywhere in this repository or its commit history.

---

> Hackathon prototype. The model runs on a synthetic liability book engineered to
> mentor-stated baselines. It is deployed and running on the bank's sandbox server
> (private address `172.16.8.60`, reached over an SSM port forward), where it reads the
> sandbox's own APIs — which serve mock records, not real customer data. No live pull
> has ever populated this book, and real customer data connects only after
> shortlisting.
