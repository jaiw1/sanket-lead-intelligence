# SANKET — stale-string sweep (SB-1)

Swept: `README.md`, `MODEL_CARD.md`, `DATA_CARD.md`, `app/src/**` copy, the deck
(`SANKET — Prototype Submission Deck.pptx`). Patterns: `1.3%`, `36.0%`, `28×`/`28x`,
`1% → 36%`, `three models`/`3 models`, `9,000 imaginary`, `15,000`, `pl` as a product
label, `complements SAJAG`, vercel URLs presented as the deployment, the word
`accuracy`.

Source of truth for every replacement: `validation/report/REPORT.md` +
`validation/report/report.json` (25/25 criteria graded, commit `4263d8e2d1a4`,
generated 2026-09-17T00:07:26+05:30), `data/model_metrics.json`, `MODEL_CARD.md` §8,
`app/public/radar_data.json`. Headline: **"9 → 29 disbursements per 100 RM calls"**
(SK-06, `data/model_metrics.json` → `metrics.headline`).

Per the task split: I fixed every README and deck row myself (edits committed on
`main`). Cards (`MODEL_CARD.md`, `DATA_CARD.md`) are L7's lane, not L12's — rows
found there are logged as "kept" (they narrate the *retired* numbers on purpose, as
history) and are not mine to edit. `app/src/**` rows are listed for L11; I did not
edit `app/**`.

## README.md (FIXED — this lane)

| Line (before) | String | Replacement | Why |
|---|---|---|---|
| 5 | `Live demo: https://sanket-leads.vercel.app` | `Interim demo (pre-sandbox): https://sanket-leads.vercel.app — the bank-sandbox EC2 deployment is not live yet (IN-6/G4 land later this week); this link is not "the deployment."` | vercel presented as *the* deployment |
| 7 | `~1% to a measured 36% conversation rate at a top-2% calling budget` | `9 → 29 disbursements per 100 RM calls at a top-10% contact budget over the drop-off population` | headline retired (§J.3, SM-2) |
| 29 | `Cold-call baseline \| 1.3%` | Two rows: bank-wide random cold-call ≈1% (unchanged problem statement, `DATA_CARD.md` §12 rationale) **and** SK-01 random-contact-to-drop-offs = **9.48%** (CI 8.46–10.59%, n=2,915; 5-seed mean 9.10%) | `1.3%` was the *whole-book* 3-month baseline; the registered baseline is over the drop-off population, not the whole book — conflating them overstates the lift |
| 30 | `Top-2% queue precision \| 36.0% (28× lift)` | `precision@10% budget = 29.06% (CI 27.44–30.73%, 5-seed mean 28.11%)` | SM-1/SM-2 rebase; `28×` retired everywhere |
| 31 | `Uplift targeting (Qini) \| 30.3 vs 11.4` | `228 vs 92 incremental conversions per 1,000 calls (top-20% uplift-ranked vs untargeted)` | Y(1)/Y(0) now read from `data/labels.csv`, not reconstructed (MODEL_CARD §8) |
| 32 | `AUC 0.85 / 0.88 / 0.95 (home / auto / PL)` | `macro AUC 0.865 across all 6 products; per-product 0.804 (personal) – 0.931 (home)` | three-product framing gone (SM-1: one model, six products); `PL` as a product label retired (`product_canonical` = `personal`) |
| 33 | `95% within ±15% (gig: 73%)` | `95.2% within ±15% (gig: 76.4%)` | `income_acc.gig_within15` = 0.764, not 0.73 |
| 34 | `8 of 9 group ratios pass — gig fails at 0.51` | `12 of 14 group ratios pass — gig fails at 0.69, income-Q1 at 0.79, both disclosed with mitigation` | SK-23; the deck/README had a stale gig ratio (0.51 vs measured 0.69) and an undercount of cells (9 vs 14) |
| 35 | `2.0× backtest lift... 26,000+ real Indian businesses` | kept — still true | matches `app/public/radar_data.json`: `top_multiple=2.0`, `n_companies_str="26,000+"` |
| 37 | `"30% conversion guaranteed"` disclaimer | `"29% conversion guaranteed"` disclaimer, same structure | number moved with the headline |
| 43 | `The 1% → 36% economics` (Mission Control row) | `The 9 → 29 economics` | same retirement |
| 57 | `no backend to crash` | `a real backend now exists (FastAPI + Postgres, roles + audit + CRM-push dry-run — rrsquad-platform); the cockpit itself still reads precomputed JSON` | a real backend was built this week (owner mandate #4); this claim is now false |
| 65 | `python3 src/make_book.py # synthetic liability book (15,000 customers × 24 months...)` | `python3 src/make_book.py && python3 src/make_journeys.py` — book is 60,000 × 30 months now; `--legacy-size` gives the old 15,000 × 27 | book size changed at SD-S1/SM-1; the old run command was also missing the `make_journeys.py` step entirely |

Also checked and **not present** in README.md: `9,000 imaginary` (DRISHTi-only, not
a SANKET string), `complements SAJAG` (DRISHTi-only), `three models`/`3 models`
(README never used this phrasing — MODEL_CARD did, see below), the bare word
`accuracy` (not used).

## MODEL_CARD.md / DATA_CARD.md (L7's lane — logged, not edited)

| File:line | String | Status |
|---|---|---|
| `MODEL_CARD.md:20` | `reported "1% → 36% conversion, a 28× lift"` | **kept** — describes the *retired* pre-SM-1 pipeline in a "what changed and why" table; correctly framed as history, not a current claim |
| `MODEL_CARD.md:26` | `three models, one per product` | **kept** — same table, same reason; the adjacent "Is" column already says "one model" |
| `MODEL_CARD.md:32,246` | `1% → 36%` / `28×` | **kept** — both instances explicitly say "retired" |
| `DATA_CARD.md:393` | `top-2% 36.0% at 27.9× lift, uplift 30.3 vs 11.4` | **kept** — this is the *pre-SD-S1 legacy generator's* own measured output, cited as a historical data point in a changelog-style table, not a claim about the current build |
| `DATA_CARD.md:458` | `pre-SD-S1 ... 15,000 × 27, three products` | **kept** — changelog row, correctly dated |
| `DATA_CARD.md:345` | `~1%, engineered to 1.3%` | **kept** — this is the bank-stated whole-book baseline the generator targets, a different (and still valid) number from SK-01's drop-off-population baseline; not stale, just a different denominator (see README fix at line 29) |

None of these needed a fix: every one is already correctly scoped as retired/historical
by its own surrounding text. Flagging here only because the raw substring matched the
grep.

## app/src/** (for L11 — not edited, per instructions)

| File:line | String | Note |
|---|---|---|
| `app/src/components/ScreenHelp.test.jsx:58-59` | asserts `1% → 36%`, `28×`, `28x` are **absent** from in-app help copy | this is a guard test, not a stale claim — nothing to fix, flagging so L11 knows it exists and should keep it green |
| `app/src/lib/fmt.js:52` | `personal: { label: 'Personal Loan', short: 'PL' }` | `PL` only as a **display abbreviation** on the canonical `personal` key — not a stale product-key issue, `pl` shim is confirmed gone from `app/src/**` (comment at `fmt.js:6` says so). No action needed, noting for completeness. |

No occurrences of `9,000 imaginary`, `15,000`, `complements SAJAG`, vercel-as-deployment,
or the bare word `accuracy` (outside the legitimate "Income accuracy" label in
`ModelTrust.jsx`) were found in `app/src/**`.

## Deck — `SANKET — Prototype Submission Deck.pptx` (FIXED — this lane, SB-3)

See the SB-3 before/after table below; every stale number found in the deck sweep is
listed there rather than duplicated here. Backup taken before editing:
`SANKET — Prototype Submission Deck.backup-2026-09-17.pptx` (beside the original,
outside the repo).

## Known follow-up (not mine to fix, flagging for the record)

Slide 2 and Slide 6 embed **screenshots** of the live app (`Picture 64`, `Picture 91`,
and the four snapshots on Slide 10) that still show pre-SM-1 numbers baked into the
pixels (`36.0%`, `28+`, `15,000`, `27.9x` visible in one screenshot). These are
images, not text runs — SB-3's mandate is text runs + swapping a *chart* PNG
rendered from `data/model_metrics.json`; these are full app screenshots, which is
SB-4's job ("final screenshots"), not SB-1/SB-3's. Recapturing them requires driving
the live app, which is out of this lane's budget (no model runs, no browser
automation set up here).
