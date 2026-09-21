# SANKET demo — narration transcript

Recorded via `video-autopilot/sanket-autopilot.mjs` against a **live rrsquad-platform
backend**: `app/` built from `main` (sanket@7e9c53f) with `VITE_API_BASE` unset and a
same-origin dev-server proxy (`VITE_DEV_API_PROXY`) to a real `uvicorn` process
(rrsquad-platform@7312ae5) backed by its own local dev Postgres database, migrated,
seeded with the five real demo users, and loaded with the committed
`app/public/sanket_data.json` (patched to carry `suppression_reasons` per lead — the
export's own `suppression_reason` singular field, renamed to the contract's plural array
— and loaded with `--allow-invalid`, because the contract gained `customers`/
`journeys`/`amortisation_schedules` blocks this export doesn't carry; every number the
export carries is unchanged by the patch). Before recording, the hero lead and 15 others
were assigned to the RM this script signs in as, via a real `POST /sanket/assign`
(`mode=explicit`) — the seed roster's EINs don't match this run's simulated one by
default, exactly the mismatch `seeds/users.yaml` warns about, so an unassigned RM would
sign in to an empty queue. This is a real signed-in session end to end: real cookies,
real CSRF, a real password change out of band before recording, real role checks, and two
real writes — a recorded disposition and a CRM-push dry run — both hash-chained into the
append-only audit log. Recorded 2026-09-21. Every number below is read directly off the
screen at the timestamp given; none is asserted from memory. **Bold** marks the words the
on-screen karaoke caption highlights.

The recorded file has no spoken audio (no human narrator was available to this
autonomous run) — the on-screen caption bar carries this exact text, word-synced, burned
into the video. A presenter can read this transcript aloud over the video, live, during
the demo slot.

Total run time: **≈2:29** (well inside the 3-minute cap the deck template requires).

## Why this replaces the 21 Sep static-demo take

A same-day agent had re-recorded this video against the app's **static demo** mode (no
login, no backend, "Push to CRM" not even rendered) to hit the 3-minute cap quickly. That
hid this product's actual differentiators — role-scoped queues, a real audited
disposition, a real CRM-push dry run with its dedupe verdict, the live validation/audit
surface — which is exactly what a bank reviewer needs to see. This take goes back to a
live backend (as the original 17 Sep recording did) but paced to stay under 3 minutes:
nine scenes, two role switches (RM → manager → admin), no dwell time wasted.

- **Real sign-in, three times.** Scene 1 signs in as `v.rathore` (relationship manager,
  seeing only his own assigned leads — confirmed on screen). Scene 5 switches to
  `r.venkataraman` (manager) because pushing to CRM is a manager/admin action
  (`authorize(Role.M, Role.A)` on `POST /sanket/lead/{id}/crm-push`) — an RM cannot do it,
  honestly. Scene 8 switches again to `a.deshmukh` (admin) to reach the audit log, which
  is admin-only (`RequireRole allow={['A']}`).
- **"Record a call outcome" is actually clicked.** A real `POST
  /sanket/lead/{id}/disposition` write — "Connected — interested" — appended to the
  audit log under the signed-in RM's own id.
- **The CRM push is a real dry run, not a mock.** A real `POST
  /sanket/lead/{id}/crm-push` (`dry_run: true`) that returns the exact API-428 payload
  that would go and a real dedupe verdict from API 456. In this sandbox (`ATLAS_MODE=off`,
  no bank connection configured) that verdict is honestly **"Unknown — no dedupe check
  was made"**, not a fabricated "clear" — the same three-state contract
  (`clear`/`duplicate`/`unknown`) production uses, shown as it actually resolves here.
- **The validation table's SK-04 dual row is real.** The packed-seed criterion passes
  (0.9009 ≥ 0.90) on this run's own registered report; the five-seed-mean sub-row the
  screen renders alongside it (`ModelTrust.jsx`'s own parse of the criterion's detail
  text) reads the same 0.8813-fails-the-band fact `MODEL_CARD.md` documents — shown, not
  hidden, exactly as SK-04 is meant to be read.

---

**0:00–0:10 — Sign in, live**
> SANKET, signed in for real — a live rrsquad-platform session, not a frozen bundle.

**0:10–0:24 — Queue: role-scoped**
> Vikram Rathore, relationship manager: the server hands him only **his own** assigned
> leads, ranked by product probability. Capacity is shown, never what ranks the queue.

**0:24–0:48 — Hero lead: why this one**
> Why this lead — LB-2006372: one model, a menu of four products, leading with a
> personal loan at **25.9%**. The case against the call, shown, not hidden: **balked at
> the ₹1,000 fee**, left half the form blank.

**0:48–1:04 — A real recorded disposition**
> Recording a call outcome is a real, audited write here — one click, hash-chained.

**1:04–1:22 — Switch to manager: CRM push dry run**
> Now the manager: a live **CRM push dry run** — the exact payload that would go, and the
> dedupe verdict the bank's own check returned, before anything is sent.

**1:22–1:38 — Manager dashboard**
> The manager's dashboard: a random call into this population disburses at **9.5%**; the
> model's top 10% disburses at **29.1%** — roughly **3 times** the random list, on
> held-out customers.

**1:38–1:56 — Model & trust: SK-04 dual verdict**
> Model & trust: SK-04 doubles up — **passes** on the packed seed, **fails** on the
> five-seed mean, its own row, disclosed, not folded in.

**1:56–2:18 — Audit trail (as admin)**
> And the evidence trail behind both writes: signed in now as the admin, the same
> append-only, hash-chained audit log — the disposition and the CRM push, exactly as
> recorded.

**2:18–2:28 — Sign-off**
> What this supports: a ranked, disclosed call list with an audited action on every lead
> — never a promise of who converts. SANKET advises. The relationship manager decides.

---

## What `--verify` confirmed on screen (regex-asserted, not just eyeballed)

`sanket-autopilot.mjs --verify` asserts these on every relevant scene and fails loudly if
any is missing:

- Queue: `Relationship manager`, `your own leads`
- Hero lead: `25.9%`, `₹1,000`, `blank`
- Disposition: `Recorded`/`Logged`/`outcome`
- CRM push: `dedupe`
- Manager dashboard: `9.5%`, `29.1%`
- Model & trust: `SK-04`, `5-seed mean`
- Audit (admin): `audit`

Console errors are asserted at zero too, net of the same pre-registered, expected 401s
DRISHTi's script ignores (the app's own `/auth/me` liveness probe before a session
exists, on the cold load and after each sign-out).

## What `--verify` could not confirm on screen

- **The exact 0.9009 / 0.8813 SK-04 values and the 90-percent floor.** `ModelTrust.jsx`
  renders both on the dual-verdict row, and `MODEL_CARD.md` §SK-04 carries the same pair,
  but `--verify`'s target list checks the row labels (`SK-04`, `5-seed mean`), not every
  digit — narrated here as what a presenter reads over the screen.
- **The precise dedupe verdict wording** ("Unknown — no dedupe check was made") is
  asserted only as `/dedupe/i` on the CRM-push scene, not the full sentence — the fuller
  quote above is transcribed from the screenshot taken at that scene, not a second regex.
- **Include-suppressed, macro AUC 0.865, and SK-23's 0.69 gig-fairness ratio.** All three
  were part of the 21 Sep static-demo cut and are real, current numbers
  (`validation/report/report.json`, `MODEL_CARD.md`), but this tighter, live-backend cut
  drops them to make room for the login/role-switch/CRM-push/audit scenes a bank reviewer
  actually needs to see inside 3 minutes — appendix material, not this take.
- **Business Radar.** Exists in the nav, not opened or narrated — an appendix exhibit,
  per the L12 brief, dropped rather than swept past on camera.

## A real bug this recording did not paper over

The Manager Dashboard's "Suppressed" card reads **560% of the book** in **static** mode
(it divides the full 7,456-row pool's suppression count by this cockpit sample's smaller
total — a real denominator bug in `funnelFromPack`, `app/src`). This live recording never
visits that card, so the bug does not appear on screen either way; see Task 2 of this
same work item for the fix and its test, tracked separately from the video re-record.

## Superseded

Two earlier recordings are kept for reference: `docs/demo/sanket-demo-2026-09-17.mp4`
(≈3:53, the original live-backend take, login/role flow, CRM push demo) stays where it
was. This file replaces the 21 Sep **static-demo** take as the current demo video.
