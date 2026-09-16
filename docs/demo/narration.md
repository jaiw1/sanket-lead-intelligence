# SANKET demo — narration transcript

Recorded via `video-autopilot/sanket-autopilot.mjs` against the real running app (real
FastAPI backend, real Postgres, real sessions — not a static bundle) on 2026-09-17.
Every number below is read directly off the screen at the timestamp given; none is
asserted from memory. **Bold** marks the words the on-screen karaoke caption highlights.

The recorded file has no spoken audio (no human narrator was available to this
autonomous run) — the on-screen caption bar carries this exact text, word-synced, burned
into the video. A presenter can read this transcript aloud over the video, live, during
the demo slot.

This is a re-record. The DRISHTi video lane found that this script's burned-in caption
clock (`window.__kStart`) lives only in the page's own JS context, so it gets wiped by
every hard navigation (`page.goto` — every sign-in round trip through `/login`, and the
mid-demo jump back to `/queue`) and the caption bar goes dark for the rest of the take
after the first one. `resyncKaraoke()` is now ported into this script (called right
after every such navigation) and re-anchors the clock to the same elapsed time it had
before the jump, so the caption keeps speaking through both role switches. Confirmed on
this take at 0:30, 2:00 and 3:30 — the caption is live and on-topic at all three marks,
including 3:30, which falls after two hard navigations (the manager sign-in at 1:42 and
the `/queue` jump at 2:10).

Total run time: **3:53** (well inside the 4-minute budget for the 10-minute slot).

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
> top ten percent **29.1%**. Pre-registered criteria: **17 pass, 1 fail**. **SK-04**
> doubles up — **passes** on the packed seed, **fails** on the five-seed mean — its own
> row, not folded in. The gig-worker fairness ratio, **0.69** against a 0.80 floor,
> stays on screen too — disclosed, not tuned away.

**3:34–3:46 — Data sources**
> And where every number comes from: **0 of 24** registered bank APIs called live in
> this sandbox — every figure here is fixture or simulated, and the product says so on
> its own dashboard.

**3:46–3:53 — Sign-off**
> SANKET advises. The relationship manager decides.

---

## Honesty notes (not spoken, for the record)

- **SK-04 is now shown twice on screen, and the narration says so.** The validation
  table renders a second "↳ 5-seed mean" row directly under SK-04 whenever
  `bands["SK-04"].verdict_on_seed_mean` disagrees with the packed-seed `verdict` —
  0.9009 (pass) on the seed the export packs, 0.8813 (fail) on the mean across the 5
  registered seeds (`n_seeds_run = 5`, SK-20 pass). The tally badge above the table
  counts this separately too: "17 pass · 1 fail · 1 fail on 5-seed mean · 5
  report-only". As of this run, `app/public/sanket_data.json` and
  `sanket/data/model_metrics.json` agree byte-for-byte on `metrics.bands` (checked
  directly), so this is the pipeline's own committed output, not a patched-in number —
  see the recaptured `sanket/docs/screenshots/05-model-trust.png`.
- **Three criteria still ship an object where `ModelTrust.jsx` expects a scalar**
  (SK-03, SK-06, SK-10), which crashes the app via the top-level ErrorBoundary if
  rendered raw. The autopilot still patches the `sanket_data.json` response in flight to
  stringify just those three — same pipeline's own output, not invented numbers — purely
  so `/trust` renders. Open for L7/L11 to fix at the source (`src/model/pack.py`).
- **CRM dedupe is honestly "unknown," not "clear."** With `ATLAS_MODE=off` in this
  sandbox, API 456 is never called, so the dry-run correctly reports "no dedupe check
  was made" rather than claiming a pass.
