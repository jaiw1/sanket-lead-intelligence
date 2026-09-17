# SANKET — Lead Intelligence for the Liability Book

*An entry for **IDBI Innovate 2026 · Track 2 (Prospect Assist AI)**.*

**🟠 Interim demo (pre-sandbox):** **https://sanket-leads.vercel.app** — no login, no
backend behind this particular static build. This is a development demo, not the
submission deployment: the bank-sandbox deployment (EC2 behind nginx, the real
backend, real auth) is in progress this week and is not live as of this writing
(2026-09-17). Do not read this link as "the deployment."

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
- **Windows.** Each offered product carries its own decision window and a
  `contact_by` date computed from it (SK-04, `window_respect_rate`).
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

**The sandbox itself is a static mock, not a live data source.** All 23 readable approved
APIs were called for real on 2026-09-17. Every one answered HTTP 200 with **no auth header
and no subscription check**, and every one answered with **its own structured mock record** —
the earlier reading, that the sandbox served one shared 106-key blob everywhere, generalised
from API 433, which is the single endpoint that does return a composite record carrying a
slice for every API. What holds everywhere is that the request body is ignored: the same
sample customer comes back whatever you ask for. So a `BANK_API` tag here means "the wiring
works and the sandbox answered," not "this is a real customer's data," and it always travels
with `sandbox_fixture: true`. `data/bank/pulled.json` has never existed for this repo — no live Atlas pull has
ever run against SANKET's book — so every run to date is `mode: fixture` or
`mode: simulated`; the current shipped app export
(`app/public/sanket_data.json` → `provenance`) reads `"mode": "fixture"`, with
`identity`/`casa_behaviour`/`holdings`/`cross_bank` = `FIXTURE` for the 120 of 60,000
customers the committed `data/bank/fixture.json` covers, and `SIMULATED` for everyone
else and for `digital`/`consent`/`journey`. `MODEL_CARD.md` §12–13; `DATA_CARD.md` §0.

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
unknown key answers `{"message": "Data not found", "sentKey": "acctId#SANDBOX-ACCT-3"}`.
A live pull on 2026-09-17 walked every documented identifier, and this is what came back:

| API | Real for | What it gave |
|---|---|---|
| 365 account enquiry | accounts `SANDBOX-ACCT-1`, `SANDBOX-ACCT-2`, `SANDBOX-ACCT-5` | balances, scheme, branch, customer name |
| 391 loan account details | accounts `SANDBOX-ACCT-1`, `SANDBOX-ACCT-2` | net interest rate, open date, customer |
| 394 accounts by CIF | CIF `SANDBOX-CIF-2` | one account, ₹56,780.25 |
| 402 overdue details | customer `SANDBOX-CIF-1` | three loan positions, DPD and NPA status |
| 442 customer limits | CIF `SANDBOX-CIF-2` (SAMPLE CUSTOMER) | exposure summary, ten limits, `accountManager` |
| 456 dedupe | customer `SANDBOX-CIF-1` | name, DOB, PAN, CKYC |
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
source — but the one CIF the sandbox answers for returns `accountManager: "SYSCODE"`, a
bank system code with no manager name and no branch beside it. That value is reported
verbatim in the export's `roster.bank_account_managers`, and `roster.bank_source_note`
says in one sentence why it did not become an RM. Putting "RM: SYSCODE" with a blank
branch in front of a relationship manager would be a worse claim than an honestly
labelled seeded roster, not a better one.

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

**Current report** (`validation/report/REPORT.md`, generated 2026-09-17T00:07:26+05:30
from commit `4263d8e2d1a4`; all 25 criteria graded — none pending at time of writing):
**16 pass · 0 gating fail · 9 reported (no target) · 2 of those reported criteria carry
a disclosed failing value.**

| ID | Metric | Band | Value | Verdict |
|---|---|---|---|---|
| SK-01 | random-contact disbursement rate | ∈ [8, 10]% | 9.48% | pass |
| SK-02 | precision@10% budget | ∈ [25, 35]% | 29.06% | pass |
| SK-03 | precision @5% / @20% | reported | 35.8% / 23.0% | reported |
| SK-04 | window respect rate | ≥ 90% | 90.1% (packed seed) | **pass on the packed seed, FAIL on the 5-seed mean (88.1%)** — see below |
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

- **SK-04, window respect — passes on the packed seed, fails on the 5-seed mean.**
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
  measurement, never a gate a run can pass by tuning. The visible cause: the
  behavioural income estimate is accurate for only 76.4% of gig workers within ±15%
  (vs 95.2% overall), which depresses their capacity score and their rank. Two
  mitigations are designed, not yet load-bearing: capacity uses the behavioural
  *median* rather than a payslip, and production is meant to add segment-aware calling
  quotas. `MODEL_CARD.md` §8.

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
# (optional) python3 src/make_radar.py              # real-data Business Radar; needs the source
                                                      # financial dataset, not in this repo

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
- **No live Atlas pull has ever run against SANKET's book at all.** `data/bank/pulled.json`
  has never existed for this repo. The committed `data/bank/fixture.json` covers 120
  of 60,000 customers as an offline stand-in; every `BANK_API`-tagged code path is
  exercised in tests against a synthetic fixture, not a real sandbox response, with the
  single exception of the one live API 433 probe recorded above.
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

> Hackathon prototype. The demo runs on a synthetic liability book engineered to
> mentor-stated baselines; the bank-sandbox deployment and any real customer data
> connect only after shortlisting, and — as of this writing — no live sandbox pull has
> ever populated this book.
