# SANKET end-to-end + accessibility suite

Playwright, against a **real backend** — not a mock. Every spec proves something a
component test cannot: that an RM's queue is scoped by the server (not the browser), that a
manager-only action is a real 403 and not just a hidden button, that the CRM push takes two
deliberate steps and shows `NOT_SENT` honestly, and that a dead session ends up on the login
screen with an explanation rather than a broken page.

## Prerequisites

1. The `rrsquad-platform` backend running on `http://127.0.0.1:8001`:
   ```
   uvicorn app.main:app --port 8001
   ```
   with its Postgres up.
2. A published SANKET model run:
   ```
   python -m app.fixtures load --product sanket --source fixture
   ```
3. The five demo users seeded with a known initial password (`must_change_password: true`):
   ```
   SEED_INITIAL_PASSWORD=RrSquad-Demo-2026!x python -m app.seeds --reset-passwords
   ```
   `e2e/roles.js` defaults to this same password (`INITIAL_PASSWORD`) if
   `SEED_INITIAL_PASSWORD` is not set in the shell running Playwright — keep the two in sync,
   or export `SEED_INITIAL_PASSWORD` before `npm run e2e` as well.

The vite dev server (`npm run dev`, port 5191) is started automatically by
`playwright.config.js`'s `webServer` block if it is not already running, and proxies `/api`
to the backend above so the session cookie stays same-origin.

## Running

From `app/`:

```
npm run e2e          # headless run, single worker
npm run e2e:ui        # Playwright's UI mode, for developing/debugging a spec
npx playwright test e2e/rm.spec.js     # a single file
npx playwright show-report                # the HTML report from the last CI-mode run
```

Sessions, round-robin assignment and consent state are shared server state, so the config
runs everything on **one worker** — two workers racing over the same five demo users would
flake for reasons that have nothing to do with the UI.

## What `global-setup.js` does, and why

Login itself — including the forced password change every seeded account starts with — is
exercised exactly once per role here, not re-run inside every spec that is not actually
about login:

1. For each of the five roles in `roles.js`, it signs in (the role's target password first,
   falling back to the shared initial password), completes the forced password change when
   the account lands on `/change-password`, and saves the resulting authenticated session
   with `context.storageState()` to `e2e/.auth/<role>.json`.
2. It then runs one round-robin assignment as the manager (`POST /sanket/assign`), so both
   relationship managers have a realistic chance of carrying leads before `rm.spec.js`'s
   "own queue only" check runs — that check is meaningless if the RM's queue is
   unconditionally empty. A `400` ("nothing left to assign", e.g. a second run of the suite
   against a backend a previous run already distributed) is tolerated; a `401`/`403` here
   fails the whole run loudly, since it means the manager's session or CSRF plumbing is
   broken and every spec downstream of it would fail for a confusing, indirect reason.

If a role genuinely cannot be signed in — neither password works — global setup **throws**,
naming the role and the exact reset command, rather than silently skipping it. A skipped
role would otherwise show up as a wall of unrelated failures in five different spec files
with no clue why.

Each spec then starts already signed in via `test.use({ storageState: statePath('<role>') })`
and goes straight to the screen under test.

## `e2e/.auth/`

This is where the saved sessions from step 1 above live — real, live `rrsq_session` /
`rrsq_csrf` cookies for the seeded accounts. **It must never be committed.** `e2e/.gitignore`
already excludes it; if the app's own root `.gitignore` does not already ignore
`app/playwright-report/` and `app/test-results/` (Playwright's default output directories,
written at the app root, not under `e2e/`), add those two there as well — this suite does
not touch that file.
