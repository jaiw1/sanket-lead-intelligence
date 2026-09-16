// Runs once, before any spec, against the REAL backend.
//
// For each of the five demo roles this signs in (forcing the initial password change when
// the account has never been changed yet), and saves the resulting session as a storage
// state file under e2e/.auth/. The specs then start each test already signed in via
// `test.use({ storageState: statePath(<role>) })` instead of re-running the login form —
// login itself is covered once, here, for every role, rather than five times over in specs
// that are not about login.
//
// It also makes sure BOTH relationship managers carry at least a chance of having leads, by
// running the manager's round-robin assignment once. rm.spec.js's "own queue only" check is
// meaningless if the RM's queue is unconditionally empty.

import { chromium, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { INITIAL_PASSWORD, ROLES, statePath } from './roles.js'

// This backend hashes with argon2id at 64 MiB / 4 lanes (deliberately expensive — see
// rrsquad-platform's app/security/passwords.py) and this suite runs against a real,
// possibly loaded machine, so a single login round trip can genuinely take several
// seconds — observed up to ~30s under heavy concurrent load on this box. 90s gives real
// headroom without masking an actual hang.
const TIMEOUT = 90_000
const DEFAULT_APP_ORIGIN = 'http://localhost:5191'

function resolveAppOrigin(config) {
  return config?.projects?.[0]?.use?.baseURL || DEFAULT_APP_ORIGIN
}

/**
 * Open /login and wait for the actual sign-in form, retrying the navigation a few times if
 * it does not show up.
 *
 * The app's own health probe (src/lib/mode.js `resolveMode`) budgets only 4s before
 * deciding the backend is unreachable and falling back to its static-demo bundle — on a
 * machine under heavy load a slow-but-alive backend can trip that budget, and static mode
 * never renders a login form at all (Login.jsx redirects away from it). Reloading gives the
 * probe another, independent 4s window rather than failing the whole run on one slow beat.
 */
async function gotoLoginForm(page, appOrigin, attempts = 5) {
  for (let i = 0; i < attempts; i += 1) {
    await page.goto(`${appOrigin}/login`)
    const visible = await page.locator('#login-username')
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (visible) return
  }
  throw new Error(
    `[global-setup] /login did not render its sign-in form after ${attempts} attempts. The app may have ` +
    'fallen back to its static-demo mode because its 4s backend health-check probe timed out — this ' +
    'machine appears to be under heavy load right now.',
  )
}

/**
 * Submit the login form and resolve on the login POST's own response — not on a UI guess —
 * so a slow render can never be mistaken for a failed sign-in or vice versa.
 */
async function attemptSignIn(page, appOrigin, username, password) {
  await gotoLoginForm(page, appOrigin)
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(password)

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.request().method() === 'POST' && res.url().includes('/api/v1/auth/login'),
      { timeout: TIMEOUT },
    ),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ])

  if (!response.ok()) return 'failed'

  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: TIMEOUT })
  return 'signed-in'
}

async function completeForcedPasswordChange(page, appOrigin, currentPassword, nextPassword) {
  await page.waitForURL((url) => url.pathname.endsWith('/change-password'), { timeout: TIMEOUT })
  await page.locator('#cp-current').fill(currentPassword)
  await page.locator('#cp-new').fill(nextPassword)
  await page.locator('#cp-confirm').fill(nextPassword)

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.request().method() === 'POST' && res.url().includes('/api/v1/auth/password'),
      { timeout: TIMEOUT },
    ),
    page.getByRole('button', { name: 'Change password' }).click(),
  ])

  if (!response.ok()) {
    const body = await response.text().catch(() => '')
    throw new Error(`[global-setup] The forced password change POST failed (${response.status()}): ${body}`)
  }

  await page.waitForURL(
    (url) => !url.pathname.endsWith('/change-password') && !url.pathname.endsWith('/login'),
    { timeout: TIMEOUT },
  )
}

/**
 * Sign a single role in: its target password first, the shared initial password if that
 * fails, completing the forced password change when the account lands on /change-password.
 * Returns the still-open {context, page} so the caller can reuse it (the manager needs its
 * session again immediately after) rather than sign in twice.
 */
async function signInRole(browser, appOrigin, key, role) {
  const context = await browser.newContext()
  const page = await context.newPage()

  let outcome = await attemptSignIn(page, appOrigin, role.username, role.password)
  let passwordUsed = role.password

  if (outcome === 'failed') {
    outcome = await attemptSignIn(page, appOrigin, role.username, INITIAL_PASSWORD)
    passwordUsed = INITIAL_PASSWORD
  }

  if (outcome === 'failed') {
    await context.close()
    throw new Error(
      `[global-setup] Could not sign in role "${key}" (username "${role.username}") with either its target ` +
      `password or the shared initial password. Seed/reset the demo users first — from rrsquad-platform, run:\n` +
      `  SEED_INITIAL_PASSWORD=${INITIAL_PASSWORD} python -m app.seeds --reset-passwords\n` +
      `then re-run the suite. (A silent skip here would hide every downstream spec for this role.)`,
    )
  }

  if (new URL(page.url()).pathname.endsWith('/change-password')) {
    await completeForcedPasswordChange(page, appOrigin, passwordUsed, role.password)
  }

  await expect(
    page,
    `role "${key}" should have left /login and /change-password after sign-in`,
  ).not.toHaveURL(/\/(login|change-password)(?:[/?#]|$)/)

  fs.mkdirSync(path.dirname(statePath(key)), { recursive: true })
  await context.storageState({ path: statePath(key) })

  return { context, page }
}

/**
 * Round-robin once, as the manager, so both RMs have a chance of carrying leads. A 400
 * ("nothing to assign") is fine — it means a previous run already distributed the book. A
 * 401/403 here means the manager's own session or CSRF token is broken, which is worth
 * failing loudly over, since every manager.spec assign test depends on the same mechanism.
 */
async function assignRoundRobinAsManager({ context }, appOrigin) {
  const cookies = await context.cookies(appOrigin)
  const csrf = cookies.find((c) => c.name === 'rrsq_csrf')?.value

  if (!csrf) {
    throw new Error(
      '[global-setup] The manager session has no readable rrsq_csrf cookie — cannot perform the ' +
      'round-robin assignment that seeds both RMs with leads.',
    )
  }

  const response = await context.request.post(`${appOrigin}/api/v1/sanket/assign`, {
    data: { mode: 'round_robin' },
    headers: { 'X-CSRF-Token': csrf },
  })

  if (response.status() === 400) return // nothing unassigned left — a previous run already did this

  if (response.status() === 401 || response.status() === 403) {
    const body = await response.text().catch(() => '')
    throw new Error(
      `[global-setup] POST /sanket/assign was refused (${response.status()}) even though the manager is ` +
      `signed in with a fresh CSRF token: ${body}`,
    )
  }

  if (!response.ok()) {
    const body = await response.text().catch(() => '')
    throw new Error(`[global-setup] POST /sanket/assign failed unexpectedly (${response.status()}): ${body}`)
  }
}

export default async function globalSetup(config) {
  const appOrigin = resolveAppOrigin(config)
  const browser = await chromium.launch()

  try {
    let managerHandle = null

    for (const [key, role] of Object.entries(ROLES)) {
      const handle = await signInRole(browser, appOrigin, key, role)
      if (key === 'manager') {
        managerHandle = handle
      } else {
        await handle.context.close()
      }
    }

    if (!managerHandle) {
      throw new Error('[global-setup] roles.js has no "manager" entry — cannot seed RM assignments.')
    }

    await assignRoundRobinAsManager(managerHandle, appOrigin)
    await managerHandle.context.close()
  } finally {
    await browser.close()
  }
}
