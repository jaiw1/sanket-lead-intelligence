// axe against every screen this build ships, at the roles that can actually reach them.
//
// A bare violation count is useless when something fails, so every check prints the rule
// id, its impact, the help text and the failing selectors — see `formatViolations` below.
// Only `serious`/`critical` impact fails the test; anything lower is still logged (to the
// test's stdout) so it shows up in the run without blocking the suite over it.

import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { statePath } from './roles.js'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
const BLOCKING_IMPACT = new Set(['serious', 'critical'])

function formatViolations(violations) {
  if (!violations.length) return '(none)'
  return violations
    .map((v) => {
      const targets = v.nodes.map((n) => `      ${n.target.join(' ')}`).join('\n')
      return `  [${v.impact}] ${v.id} — ${v.help} (${v.helpUrl})\n${targets}`
    })
    .join('\n')
}

async function assertNoSeriousViolations(page, label) {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const blocking = results.violations.filter((v) => BLOCKING_IMPACT.has(v.impact))

  // Logged unconditionally so every violation this run found — including below "serious"
  // — is visible in the test output, not just the ones that fail the assertion below.
  console.log(`[a11y] ${label}: ${results.violations.length} violation(s)\n${formatViolations(results.violations)}`)

  expect(
    blocking.length,
    `${label} has serious/critical accessibility violations:\n${formatViolations(blocking)}`,
  ).toBe(0)
}

test.describe('login (unauthenticated)', () => {
  test('login', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('#login-username')).toBeVisible()
    await assertNoSeriousViolations(page, '/login')
  })
})

test.describe('manager-scoped screens', () => {
  test.use({ storageState: statePath('manager') })

  test('change-password', async ({ page }) => {
    await page.goto('/change-password')

    const settled = await Promise.race([
      page.locator('#cp-current').waitFor({ state: 'visible', timeout: 8000 }).then(() => 'rendered').catch(() => 'timeout'),
      page.waitForURL((url) => !url.pathname.endsWith('/change-password'), { timeout: 8000 }).then(() => 'redirected').catch(() => 'timeout'),
    ])
    test.skip(settled === 'redirected', 'the app redirected away from /change-password for this session — nothing to scan')

    await expect(page.locator('#cp-current')).toBeVisible()
    await assertNoSeriousViolations(page, '/change-password')
  })

  test('dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('headline')).toBeVisible()
    await assertNoSeriousViolations(page, '/dashboard')
  })

  test('queue', async ({ page }) => {
    await page.goto('/queue')
    await expect(page.getByTestId('queue-row').first().or(page.getByTestId('state-empty'))).toBeVisible()
    await assertNoSeriousViolations(page, '/queue')
  })

  test('queue with the lead drawer open (a modal dialog)', async ({ page }) => {
    const response = await page.request.get('/api/v1/sanket/queue?limit=1')
    const lead = ((await response.json()).data ?? [])[0]
    test.skip(!lead, 'no lead is available to open a briefing for')
    const leadId = String(lead.lead_id ?? lead.id)

    await page.goto(`/queue?lead=${encodeURIComponent(leadId)}`)
    await expect(page.getByTestId('lead-drawer')).toBeVisible()
    await assertNoSeriousViolations(page, '/queue (lead drawer open)')
  })

  test('consent', async ({ page }) => {
    await page.goto('/consent')
    await expect(page.getByTestId('consent-request-open')).toBeVisible()
    await assertNoSeriousViolations(page, '/consent')
  })

  test('consent with a consent selected', async ({ page }) => {
    const response = await page.request.get('/api/v1/sanket/consent/list?limit=1')
    const consent = ((await response.json()).data ?? [])[0]
    test.skip(!consent, 'no consent artefact exists yet to select')

    await page.goto(`/consent?id=${encodeURIComponent(consent.consent_handle)}`)
    await expect(page.getByTestId('consent-state-machine')).toBeVisible()
    await assertNoSeriousViolations(page, '/consent (selected)')
  })

  test('trust', async ({ page }) => {
    await page.goto('/trust')
    await assertNoSeriousViolations(page, '/trust')
  })

  test('radar', async ({ page }) => {
    await page.goto('/radar')
    await assertNoSeriousViolations(page, '/radar')
  })

  test('sources', async ({ page }) => {
    await page.goto('/sources')
    await assertNoSeriousViolations(page, '/sources')
  })

  test('queue at tablet viewport (768x1024)', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.goto('/queue')
    await expect(page.getByTestId('queue-row').first().or(page.getByTestId('state-empty'))).toBeVisible()
    await assertNoSeriousViolations(page, '/queue @768x1024')
  })

  test('queue at 1400x900', async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 })
    await page.goto('/queue')
    await expect(page.getByTestId('queue-row').first().or(page.getByTestId('state-empty'))).toBeVisible()
    await assertNoSeriousViolations(page, '/queue @1400x900')
  })
})

test.describe('admin-scoped screens', () => {
  test.use({ storageState: statePath('admin') })

  test('admin', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByTestId('state-denied')).toHaveCount(0)
    await assertNoSeriousViolations(page, '/admin')
  })
})
