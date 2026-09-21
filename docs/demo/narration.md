# SANKET demo — narration transcript

Recorded via `video-autopilot/sanket-autopilot.mjs` against the **static demo build**:
`app/` built from `main` with no `VITE_API_BASE`, served by a plain static file server
that answers every `/api/*` request with an immediate 404 and proxies nothing (see
`video-autopilot/static-only-server.js`) — no `rrsquad-platform`, no Postgres, no login.
`src/lib/mode.js::resolveMode()` sees the failed health check and resolves to
`MODE.STATIC`, the app's own first-class "frozen demo bundle" mode (the same one shipped
at `https://sanket-leads.vercel.app`): every read comes straight from the committed
`app/public/sanket_data.json`, and every mutating control (record a call outcome, push to
CRM) is honestly disabled, hidden, or unavailable, with its own on-screen explanation,
rather than faked. Recorded 2026-09-21, against `main` (sanket@7c98f14, which by then
already included the merged `deepening/validation-experiments` branch — checked before
building; every number below is unchanged by that merge). Every number below is read
directly off the screen at the timestamp given; none is asserted from memory. **Bold**
marks the words the on-screen karaoke caption highlights.

The recorded file has no spoken audio (no human narrator was available to this
autonomous run) — the on-screen caption bar carries this exact text, word-synced, burned
into the video. A presenter can read this transcript aloud over the video, live, during
the demo slot.

Total run time: **≈2:35** (well inside the 3-minute cap the deck template requires).

## Why this is a shorter, simpler recording than the 17 Sep take

The bank's numbers changed today, and the deck template now requires a video under 3
minutes, not 4. The 17 Sep recording drove a real backend (login, two roles, live writes:
a disposition, a CRM push dry-run → confirm → NOT_SENT) and ran ≈3:53. This take uses the
app's own **static demo** mode instead — no backend needed at all. Concretely, that means:

- **No sign-in, no role switching.** Static mode has no session; every route is open, and
  the queue screen treats the viewer as a manager (`manager = isStatic || ...`) so the
  manager dashboard and lead assignment views are reachable without a role switch.
- **"Record a call outcome" is shown, not clicked.** The button is visibly disabled, with
  its own on-screen text: *"Actions need the backend. This page load is the frozen static
  demo."*
- **"Push to CRM" and "Consent & AA" are gone, not patched around.** `canPush = !isStatic
  && roleMatches(role, ['M','A'])` in `LeadDrawer.jsx` — the button does not render at all
  in static mode, so there is nothing to demo. `Consent.jsx` renders `NotInBuild` outright:
  *"A consent artefact is platform state, not model output, so the bundled export carries
  none. This screen needs the backend."* Neither scene from the 17 Sep take is possible
  here, honestly, so neither is narrated.
- **"Data sources" is also gone.** `DataSources.jsx` calls `GET /meta/sync` etc.
  unconditionally, with no static fallback — it would show a live error with no backend.
  Dropped rather than faked.
- **The ranking is by product probability only.** The old 65/35 intent-capacity blend is
  retired; the queue's `SORT BY` control still offers Capacity as a column and a sort key,
  but the default ranking (and the `score` column) is the product probability — capacity
  is shown, never what ranks the queue.
- **Business Radar is not covered.** It exists in this build's nav but is an appendix
  exhibit, not part of a 3-minute cut, exactly as it was before.

---

**0:00–0:13 — Queue overview**
> This is SANKET's **static demo** build — no login, no backend — reading a frozen
> snapshot of **344** drop-off leads, ranked by product probability. Capacity is shown
> here, never what ranks the queue.

**0:13–0:40 — Hero lead: menu of four + negative chips**
> Lead LB-2006372 — the menu of four, one model ranking all six products, leads with a
> personal loan at **25.9%**. And the case against the call, shown rather than hidden:
> this customer **balked at the ₹1,000 fee**, left half the form blank, refused to submit
> documents.

**0:40–0:58 — EMI + Hindi pitch**
> EMI headroom **₹10,100** for that personal loan, priced from the bank's own schedule.
> And the pitch drafts itself — here in **Hindi** — every line traced back to a chip
> above.

**0:58–1:12 — What action: record a call outcome (honestly disabled)**
> Recording a call outcome is normally one click. This frozen bundle is honest about the
> limit instead: the control is **disabled** — actions need a backend this build does not
> have.

**1:12–1:34 — What the evidence supports: manager dashboard**
> The manager's view: a random call into this population disburses at **9.5%**; the
> model's top 10% disburses at **29.1%** — **3.1 times** the random list, measured on
> held-out customers, not asserted.

**1:34–1:52 — Suppressed, shown not dropped**
> Back on the queue: ticking **include suppressed** adds **24** more leads — **7%** of
> this bundle — shown, never silently dropped.

**1:52–2:10 — Model & Trust: report card**
> The model's report card: macro AUC **0.865** across six products, precision at the top
> ten percent, **29.1%**. **Seventeen pass, one fail.**

**2:10–2:28 — SK-04 dual verdict + SK-23 fairness**
> **SK-04** doubles up — **passes** on the packed seed, **fails** on the five-seed mean,
> its own row, not folded in. The gig-worker fairness ratio, **0.69** against a 0.80
> floor, stays on screen too — disclosed, not tuned away.

**2:28–2:35 — Sign-off**
> SANKET advises. The relationship manager decides.

---

## What `--verify` confirmed on screen (regex-asserted, not just eyeballed)

`sanket-autopilot.mjs --verify` asserts these on every relevant scene and fails loudly if
any is missing:

- Queue: `344`, a `Score` sort column
- Hero lead: `25.9%`, `₹1,000`, `blank`
- EMI: `10,100`
- Manager dashboard: `9.5%`, `29.1%`, `3.1×`
- Queue with suppressed included: `344` (up from 320 with the checkbox off — the delta is
  demonstrated live, by toggling the checkbox on camera, not asserted from a static
  count)
- Model & Trust: `0.865`, `29.1%`, `17 pass`, `1 fail`, `0.69`

## What `--verify` could not confirm on screen

- **The "24 suppressed / 7%" figure as a single rendered number.** It is demonstrated
  live instead (the queue's row count changes from 320 to 344 when "include suppressed"
  is ticked — 24 rows, 7.0% of 344), which is more honest than the alternative: the
  Manager Dashboard's own "Suppressed" card reads **1,927 — "560% of the book"**, because
  it divides the full 7,456-row snapshot pool's suppression count by this bundle's
  344-lead sample — a real display bug in `funnelFromPack` in static mode, not narrated
  or swept past on camera, and not fixed here (out of scope for a video re-record).
- **API 473 vs API 433 for the EMI figure.** The product-menu card shows only "EMI
  headroom ₹10,100" with no rate, tenor, or API number attached in the DOM. A *different*
  EMI figure lower on the same screen (₹22,500, "comfortable EMI headroom") explicitly
  states on screen that it is *not* from API 433 or 473, but a scoring-package table
  constant. The 17 Sep narration's claim of "12.75% for 36 months, API 433" for the
  ₹10,100 figure was not re-verified as an on-screen fact here and is not repeated.
- **Business Radar.** Exists in the nav, not opened or narrated — an appendix exhibit,
  per the L12 brief.

## Superseded

The 17 Sep recording is kept at `docs/demo/sanket-demo-2026-09-17.mp4` (≈3:53, real
backend, login/role flow, CRM push demo). This file replaces it as the current demo
video.
