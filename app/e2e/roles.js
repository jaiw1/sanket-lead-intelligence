// The demo principals these specs sign in as, and where their storage states are kept.
//
// `INITIAL` is whatever `python -m app.seeds` was given as SEED_INITIAL_PASSWORD. Every
// seeded user is created with must_change_password: true, so global-setup drives the
// forced change once per role and saves the resulting session — which means the forced
// password change is exercised on every run rather than mocked.

export const INITIAL_PASSWORD = process.env.SEED_INITIAL_PASSWORD || 'RrSquad-Demo-2026!x'

export const ROLES = {
  admin: { username: 'a.deshmukh', password: 'E2E-Admin-2026!x', role: 'admin', ein: 'EIN-100114' },
  manager: { username: 'r.venkataraman', password: 'E2E-Manager-2026!x', role: 'manager', ein: 'EIN-100237' },
  officer: { username: 's.kulkarni', password: 'E2E-Officer-2026!x', role: 'credit_officer', ein: 'EIN-100358' },
  rm: { username: 'v.rathore', password: 'E2E-Rm-2026!x', role: 'relationship_manager', ein: 'EIN-100471' },
  rm2: { username: 'p.nair', password: 'E2E-Rm2-2026!x', role: 'relationship_manager', ein: 'EIN-100482' },
}

export const statePath = (key) => `e2e/.auth/${key}.json`

export const API = process.env.E2E_API || 'http://127.0.0.1:8001/api/v1'
