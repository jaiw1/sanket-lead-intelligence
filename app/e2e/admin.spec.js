// The administrator: the roster, the audit log, and the one action nobody else gets —
// replaying a stored Account Aggregator webhook when the sandbox cannot reach this box.

import { test, expect } from '@playwright/test'
import { statePath } from './roles.js'

test.describe('administration screen', () => {
  test.use({ storageState: statePath('admin') })

  test('/admin renders the users table and the audit log', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByTestId('state-denied')).toHaveCount(0)

    const usersCard = page.locator('section[aria-labelledby="admin-users-title"]')
    await expect(usersCard.getByRole('heading', { name: 'Users', exact: true })).toBeVisible()
    await expect(usersCard.locator('table')).toBeVisible()

    const auditCard = page.locator('section[aria-labelledby="admin-audit-title"]')
    await expect(auditCard.getByRole('heading', { name: 'Audit log', exact: true })).toBeVisible()
    await expect(auditCard.locator('table')).toBeVisible()
  })

  test('consent replay moves the state machine, or shows the response panel', async ({ page }) => {
    await page.goto('/consent')

    const list = page.getByTestId('consent-list')
    const listVisible = await list.isVisible().catch(() => false)

    if (!listVisible) {
      // Nothing has ever been requested on this backend — request one against a real lead,
      // so there is a genuine artefact to select and replay.
      const queueResponse = await page.request.get('/api/v1/sanket/queue?limit=1')
      expect(queueResponse.ok()).toBeTruthy()
      const lead = ((await queueResponse.json()).data ?? [])[0]
      if (!lead) throw new Error('[admin.spec] The book has no lead to request a consent against.')
      const custId = String(lead.cust_id ?? lead.lead_id ?? lead.id)

      await page.getByTestId('consent-request-open').click()
      await page.locator('#consent-cust').fill(custId)
      await page.getByTestId('consent-request-submit').click()
      await expect(page.getByText(/^Requested —/)).toBeVisible()
      await page.getByRole('button', { name: 'Done' }).click()
      await expect(list).toBeVisible()
    }

    await list.locator('button').first().click()
    await expect(page).toHaveURL(/[?&]id=/)
    const handle = new URL(page.url()).searchParams.get('id')
    expect(handle).toBeTruthy()

    // Read which transitions the server itself says are still open for this artefact, so
    // the replay event picked is one the state machine can actually take — not a guess.
    const consentResponse = await page.request.get(`/api/v1/sanket/consent/${encodeURIComponent(handle)}`)
    expect(consentResponse.ok()).toBeTruthy()
    const consent = (await consentResponse.json()).data
    const nextEvent = consent?.may_transition_to?.[0] || 'ACTIVE'

    const stateMachine = page.getByTestId('consent-state-machine')
    await expect(stateMachine).toBeVisible()
    const before = await stateMachine.locator('[data-current="true"]').getAttribute('data-state')

    await page.getByTestId('consent-replay-open').click()
    const dialog = page.getByTestId('consent-replay-dialog')
    await expect(dialog).toBeVisible()
    await dialog.locator('#replay-event').selectOption(nextEvent)
    await dialog.getByTestId('consent-replay-confirm').click()

    const detailCard = page.locator('section[aria-labelledby="consent-detail-title"]')
    await expect(async () => {
      const after = await stateMachine.locator('[data-current="true"]').getAttribute('data-state')
      const responseShown = await detailCard.locator('pre').count()
      expect(after !== before || responseShown > 0, 'either the current state changed, or the replay response panel appeared').toBe(true)
    }).toPass({ timeout: 20_000 })
  })
})

test.describe('a manager cannot replay consent', () => {
  test.use({ storageState: statePath('manager') })

  test('no replay button in the UI, and the API itself refuses', async ({ page }) => {
    const listResponse = await page.request.get('/api/v1/sanket/consent/list?limit=1')
    expect(listResponse.ok()).toBeTruthy()
    const consent = ((await listResponse.json()).data ?? [])[0]
    test.skip(!consent, 'no consent artefact exists yet to check the manager view against')
    const handle = consent.consent_handle

    await page.goto(`/consent?id=${encodeURIComponent(handle)}`)
    await expect(page.getByTestId('consent-state-machine')).toBeVisible()
    await expect(page.getByTestId('consent-replay-open')).toHaveCount(0)

    const csrf = (await page.context().cookies()).find((c) => c.name === 'rrsq_csrf')?.value
    const replayResponse = await page.request.post(`/api/v1/sanket/consent/${encodeURIComponent(handle)}/replay`, {
      data: { event: 'ACTIVE', api_id: '497' },
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
    expect(replayResponse.status()).toBe(403)
  })
})
