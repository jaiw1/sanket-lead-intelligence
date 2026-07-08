# SANKET — Lead Intelligence for the Liability Book

*An entry for **IDBI Innovate 2026 · Track 2 (Prospect Assist AI)**.*

**🟠 Live demo:** **https://sanket-leads.vercel.app** — no login, no backend.

**One line:** Every transaction is a signal. SANKET reads a bank's own liability-side accounts — salary rhythm, rent step-ups, fuel spend, balance build-ups — and turns them into a **ranked, explained, consent-clean loan pipeline**: from ~1% cold-calling to a **measured ~39% conversation rate at a top-2% calling budget**.

---

## The problem

Banks sit on their best lead list — their own savings and current accounts — and still cold-call at **~1% conversion**. Relationship managers burn hours on lists nobody ranked; customers get pitched products they don't need; and the people who *are* two months away from taking a home loan get a generic SMS.

## What SANKET does

1. **Reads signals** from account behaviour: salary/credit rhythm, rent step-ups, fuel + cab surges, pre-salary balance dips, FD breaks, product-page dwell.
2. **Scores two things separately** — the two axes the bank's own PM framed:
   - **Intent** — does the need exist *right now*?
   - **Capacity** — can they repay comfortably? (behavioural **retained-income** estimate, not just declared salary)
3. **Ranks a queue** (Hot / Warm / Cold, next-best-product) — after screening out every customer without marketing consent. They're never scored at all.
4. **Briefs the RM**: plain-English reasons, a data-grounded opening script (every claim traceable to a signal chip), the likely objection with its answer, retained-income → safe-EMI headroom, and a next-best-action with timing.

## The honest numbers

| What | Value | How it's measured |
|---|---|---|
| Cold-call baseline | **1.3%** | random-contact conversion in the book (engineered to the bank-stated ~1%) |
| Top-2% queue precision | **~39%** (**30× lift**) | held-out customers, outcomes 3 months forward |
| Ranking quality | AUC **0.83 / 0.89 / 0.97** (home / auto / PL) | customer-grouped split, temporally forward test |
| Real-data proof | **2.0× backtest lift** | on **26,000+ real Indian businesses**: top-decile radar prospects actually raised borrowings next FY at 2× the rate of the rest |

We deliberately do **not** claim "30% conversion guaranteed." The demo book is synthetic (bank data arrives post-shortlisting); what we claim is the **machinery** — ranking, explanation, consent screening and honest measurement — shown working end-to-end, plus a real-data backtest proving the prospecting logic holds outside toy data.

## The four screens

| Tab | What it proves |
|---|---|
| **Mission Control** | The 1% → ~39% economics, live: drag the calling-capacity slider, watch precision/lift/contacts trade off. |
| **Lead Queue** | Ranked book with separate intent & capacity scores, consent badges, greyed **"not queued — no consent (DPDP)"** rows, and a full call briefing per lead. |
| **Business Radar** | The same engine pointed at **real businesses** (anonymised, from published financials): headroom by sector + a backtest that the ranking predicts real next-year borrowing. |
| **Model & Trust** | Calibration, lift decay, per-product AUC, and **"features we refused to use"** — anti-leakage and fairness shown before anyone asks. |

## Privacy & compliance by construction

- **Consent-first:** non-consented customers are excluded *before scoring* — visible in the product as greyed rows and an excluded-count KPI.
- **DPDP-aligned:** bank's own first-party data, purpose-limited to offers the customer can decline; no third-party lists; no bureau pulls at prospecting stage.
- **No proxy discrimination:** gender, religion, caste, pin-code and similar fields are excluded outright (see the Trust tab).
- **Human-in-the-loop:** SANKET advises; the RM decides.

## How it's built

- **Data + models:** Python (pandas, LightGBM, scikit-learn). One propensity model per product; SHAP-style contributions become plain-English reasons. Everything precomputes to static JSON — the live demo has no backend to crash.
- **App:** React + Vite + Tailwind + Recharts.
- **Real-data module:** derived aggregates + anonymised exemplars only; raw company data never ships.

### Run it locally

```bash
# 1) generate the book, train, pack (from the repo root)
python3 src/make_book.py        # synthetic liability book (15,000 customers × 24 months + measured future)
python3 src/score_and_pack.py   # trains 3 LightGBMs, measures precision@budget, writes app/public/sanket_data.json
# (optional) python3 src/make_radar.py  # real-data Business Radar (needs the source financial dataset, not in repo)

# 2) run the app
cd app && npm install && npm run dev   # http://localhost:5191
```

## Production path (post-shortlisting)

Swap the synthetic book for CBS/UPI/card feeds via a nightly feature pipeline (S3 + Glue), retrain per product on SageMaker with a model registry, serve scores to this same cockpit behind bank SSO, and recalibrate the precision curve on real outcomes. The consent register becomes a live join against the bank's DPDP consent store. Architecture is deliberately batch-first — no real-time inference needed for a monthly calling program.

---

> Hackathon prototype. The demo runs on a synthetic liability book engineered to bank-stated baselines; sandbox data connects after shortlisting.
