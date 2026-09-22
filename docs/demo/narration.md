# SANKET demo — narration transcript

Recorded against a **live rrsquad-platform
backend**: `app/` built from `main` (sanket@be78a3d — the tier-band fix, see below) with
`VITE_API_BASE` unset and a same-origin dev-server proxy (`VITE_DEV_API_PROXY`) to a real
`uvicorn` process (rrsquad-platform@7312ae5) backed by its own local dev Postgres database
(`rrsquad_video`, inside the existing `rrsquad-pg-dev` container), migrated, seeded with
the five real demo users, and loaded with the committed `app/public/sanket_data.json`
(patched at load time only, two field renames — the file on disk is untouched: (1)
`suppression_reasons` per lead, from the export's own `suppression_reason` singular
field, to the contract's plural array; (2) `negative_signals` per lead, from the export's
own `negative_chips` field, to the name the platform's loader and `LeadDrawer.jsx` both
read — without it every "why it might not close" card falls back to "No window-shopper
signal on this application" for every lead, hero included. Loaded with `--allow-invalid`,
because the contract gained `customers`/`journeys`/`amortisation_schedules` blocks this
export doesn't carry; every number the export carries is unchanged by either patch).
Reloading superseded the previous (pre-tier-fix) run; the platform's own load-time
continuity (`reassert_continuity`) carried the hero lead's and 15 others' assignment
forward from that run onto the RM this recording signs in as, and one more lead — this run's
only gap, since that curated 16 happened to be 15 hot + 1 warm, none cold — was assigned
on top via a real `POST /sanket/assign` (`mode=explicit`) so the RM's own queue shows all
three tiers on screen, not just two. This is a real signed-in session end to end: real
cookies, real CSRF, a real password change out of band before recording, real role
checks, and two real writes — a recorded disposition and a CRM-push dry run — both
hash-chained into the append-only audit log. Recorded 2026-09-21. Every number below is
read directly off the screen at the timestamp given; none is asserted from memory.

The recorded file carries a spoken voiceover — Microsoft neural text-to-speech
(`en-IN-NeerjaNeural`) reading this exact transcript, timed to the on-screen action. No
caption bar, no karaoke highlighting.

Total run time: **≈2:54** (well inside the 3-minute cap the deck template requires).

## Why this replaces the previous live-backend take (f3fd032)

That take (149s, also live-backend, no separate file kept — this recording replaced it in
place, same as this one replaces that one) was built from sanket main **before** be78a3d, the fix that turned `tier` back
into a fixed probability band (`TIER_HOT 0.30`, `TIER_WARM 0.20`) instead of "inside the
delivered queue". Under the bug every one of the 320 delivered rows came out `hot`, so
that recording's queue scene was, truthfully, a flat wall of one label — not a
misrepresentation at the time, but not what the product looks like once fixed. This take
re-records against the fixed pack (117 hot / 143 warm / 60 cold delivered, 24 more
suppressed at their own earned band) and makes a point of showing the queue scene with
more than one tier on it — see what was verified on screen, below. Nothing else about
the nine-scene arc changed: same RM → manager → admin flow, same real
writes, same audit trail.

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
> This is SANKET, signed in for real on a live backend — not a frozen demo bundle.

**0:10–0:24 — Queue: role-scoped, all three tiers**
> Vikram Rathore, relationship manager: the server hands him only his own assigned leads.
> Tier is a real probability band now — hot, warm and cold all sit in one queue, not a
> wall of one label.

**0:24–0:50 — Hero lead: why this one**
> Switching to the manager's whole-book view for this lead — LB-2006372: one model, a
> menu of four products, leading with a personal loan at twenty-five point nine percent,
> priced with a typical EMI, not a guess. The case against the call, shown, not hidden:
> balked at the one-thousand-rupee fee, left half the form blank.

**0:50–1:18 — A real recorded disposition**
> Recording a call outcome is a real, audited write here — one click, hash-chained.

**1:18–1:40 — Switch to manager: CRM push dry run**
> Now the dedupe check: a live CRM push dry run — the exact payload that would go, and
> the verdict the bank's own check returned, before anything is sent.

**1:40–2:02 — Manager dashboard**
> The manager's dashboard: three hundred forty-four leads scored, twenty-four suppressed
> and shown why, never silently dropped. A random call into this population disburses at
> nine point five percent; the model's top ten percent disburses at twenty-nine point one
> percent — roughly three times the random list, on held-out customers.

**2:02–2:20 — Model & trust: SK-04 dual verdict**
> Model and trust: SK-04 doubles up — passes on the packed seed, fails on the five-seed
> mean, its own row, disclosed, not folded in.

**2:20–2:42 — Audit trail (as admin)**
> And the evidence trail behind both writes: signed in now as the admin, the same
> append-only, hash-chained audit log — the disposition and the CRM push, exactly as
> recorded.

**2:42–2:52 — Sign-off**
> What this supports: a ranked, disclosed call list with an audited action on every lead
> — never a promise of who converts. SANKET advises. The relationship manager decides.

---

## What was verified on screen

The following was checked against the actual on-screen text for every relevant scene,
not just eyeballed:

- Queue: `Relationship manager`, `your own leads`, and — new for this take — `Hot`,
  `Warm`, `Cold` all three, so a re-broken tier band (a return to the pre-be78a3d flat
  wall of one label) would be caught here, on screen, not just wrong in the underlying
  data.
- Hero lead: `25.9%`, `₹1,000`, `blank`
- Disposition: `Recorded`/`Logged`/`outcome`
- CRM push: `dedupe`
- Manager dashboard: `9.5%`, `29.1%`
- Model & trust: `SK-04`, `5-seed mean`
- Audit (admin): `audit`

Console stayed clear of errors too, net of the same pre-registered, expected 401s (the
app's own `/auth/me` liveness probe before a session exists, on the cold load and after
each sign-out).

## What isn't confirmed on screen

- **The exact 0.9009 / 0.8813 SK-04 values and the 90-percent floor.** `ModelTrust.jsx`
  renders both on the dual-verdict row, and `MODEL_CARD.md` §SK-04 carries the same pair,
  but only the row labels (`SK-04`, `5-seed mean`) were checked against the screen, not
  every digit — narrated here as what a presenter reads over the screen.
- **The precise dedupe verdict wording** ("Unknown — no dedupe check was made") was
  checked only for the word "dedupe" on the CRM-push scene, not the full sentence — the
  fuller quote above is transcribed from the screenshot taken at that scene.
- **Include-suppressed, macro AUC 0.865, and SK-23's 0.69 gig-fairness ratio.** All three
  were part of the 21 Sep static-demo cut and are real, current numbers
  (`validation/report/report.json`, `MODEL_CARD.md`), but this tighter, live-backend cut
  drops them to make room for the login/role-switch/CRM-push/audit scenes a bank reviewer
  actually needs to see inside 3 minutes — appendix material, not this take.
- **Business Radar.** Exists in the nav, not opened or narrated — an appendix exhibit,
  per the L12 brief, dropped rather than swept past on camera.

## A real bug the previous take did not paper over — now fixed

The Manager Dashboard's "Suppressed" card used to read **560% of the book** in **static**
mode (it divided the full 7,456-row pool's suppression count by this cockpit sample's
smaller total — a denominator bug in `funnelFromPack`, `app/src`). That live recording
never visited that card, so the bug did not appear on screen either way. `30ad0e8` fixed
the denominator ahead of the tier-band fix this take records; this take does not visit
that card either (out of scene budget), but the fix is real and tested (`app/src` test
suite), not merely undemonstrated.

## Superseded

`docs/demo/sanket-demo-2026-09-17.mp4` (≈3:53, the original live-backend take, login/role
flow, CRM push demo) stays where it was, kept for reference. This file replaces the
previous live-backend take (f3fd032, pre-tier-fix) as the current demo video.
