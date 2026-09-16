# SANKET demo — narration transcript

Recorded via `video-autopilot/sanket-autopilot.mjs` against the real running app (real
FastAPI backend, real Postgres, real sessions — not a static bundle) on 2026-09-17.
Every number below is read directly off the screen at the timestamp given; none is
asserted from memory. **Bold** marks the words the on-screen karaoke caption highlights.

The recorded file has no spoken audio (no human narrator was available to this
autonomous run) — the on-screen caption bar carries this exact text, word-synced, burned
into the video. A presenter can read this transcript aloud over the video, live, during
the demo slot.

Total run time: **3:52** (well inside the 4-minute budget for the 10-minute slot).

---

**0:00–0:13 — Sign in (RM)**
> This is SANKET — IDBI's prospect-assist cockpit. Real FastAPI backend, real Postgres, a
> real session — not a static demo. I'm signing in as a relationship manager.

**0:13–0:31 — Lead queue (RM)**
> My queue — the leads assigned to me, scoped by the **server** to my own employee id,
> not the browser. Each row carries its ranked product and how long its contact window
> stays open.

**0:31–1:01 — Lead LB-2006372: menu of four + negative chips**
> Every lead opens into a full briefing. The menu of four — one model, ranking all six
> products — leads with a personal loan at **25.9%**. And the case against the call,
> shown rather than hidden: this customer **balked at the ₹1,000 processing fee**, left
> half the form blank, and refused documents.

**1:01–1:28 — EMI (bank sandbox rate) + Hindi pitch**
> The EMI — **₹10,100** a month, at **12.75%** for **36 months** — priced off the bank's
> own sandbox rate, API 433, not a guess. And the pitch drafts itself — here in
> **Hindi** — every line traced back to a chip above.

**1:28–1:42 — Disposition**
> Recording what actually happened on the call is one click, from a closed list of eight
> outcomes — **Connected, interested** — no free text pretending to be one.

**1:42–2:10 — Manager dashboard**
> Now the manager's view. **Nine to twenty-nine disbursements per hundred RM calls** —
> the same drop-off population, the same hundred calls, measured on held-out customers.
> And **24 leads, 7% of the book**, the bank chose to hold back — shown, never silently
> dropped.

**2:10–2:50 — Push to CRM (dry run → confirm → NOT_SENT)**
> Pushing a lead into the bank's CRM is a manager-only action, and it never happens by
> accident. Step one — a dry run: the dedupe check against API 456, and the exact
> payload that would go, before anything moves. This one comes back **unknown — no
> dedupe check was made**, because Atlas writes are off in this sandbox. Step two
> confirms it — and it comes back **NOT SENT**, at HTTP 200, not an error, because
> **we** switched writes off, not the bank. The attempt is still audited.

**2:50–3:10 — Consent & AA**
> Every Account Aggregator consent this platform has asked for lives on one real
> screen — the actual state machine, API 591. This one is **Active**; a fetch is
> refused unless it is — the product enforcing consent, not just declaring it.

**3:10–3:34 — Model & Trust**
> The model's report card. Macro AUC **0.865** across six products, precision at the
> top ten percent **29.1%**. Pre-registered criteria: **17 pass, 1 fail**, 5
> report-only. The failure stays on screen — a **0.69** fairness ratio for gig workers,
> against a 0.80 floor — disclosed, not tuned away.

**3:34–3:46 — Data sources**
> And where every number comes from: **0 of 24** registered bank APIs called live in
> this sandbox — every figure here is fixture or simulated, and the product says so on
> its own dashboard.

**3:46–3:52 — Sign-off**
> SANKET advises. The relationship manager decides.

---

## Honesty notes (not spoken, for the record)

- **The validation table shows 1 fail on screen (SK-23), not "two."** README.md
  documents a second, subtler honest complication — SK-04 (window-respect) passes on
  the packed single-seed run (90.1%) but fails on the 5-seed mean (88.1%); the
  `bands[*].verdict` field the on-screen table reads carries only the single verdict, so
  the narration above claims only what is literally visible: one disclosed numeric
  failure. The fuller SK-04 nuance is real and cited in README.md §Validation, just not
  claimable from this screen alone.
- **`app/public/sanket_data.json` is stale** relative to `data/model_metrics.json`
  (11 minutes older) and, unpatched, crashes the whole app via `ModelTrust.jsx`'s
  `ValidationTable` (three criteria carry an object where the component expects a
  scalar `observed` value). The autopilot patches the response in flight — same
  pipeline's own newer output, not invented numbers — so the screen recorded here is
  correct; the crash is real and open for L7/L11 to fix by regenerating the committed
  file. See the comment block at the top of `sanket-autopilot.mjs`.
- **CRM dedupe is honestly "unknown," not "clear."** With `ATLAS_MODE=off` in this
  sandbox, API 456 is never called, so the dry-run correctly reports "no dedupe check
  was made" rather than claiming a pass.
