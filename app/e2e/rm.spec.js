// The relationship manager: the narrowest role. Every assertion here is really about the
// SERVER'S scoping and refusal, not the browser's — the UI simply has to agree with it.

import { test, expect } from '@playwright/test'
import { ROLES, statePath } from './roles.js'

test.use({ storageState: statePath('rm') })

const RM_EIN = ROLES.rm.ein
const OTHER_RM_EIN = ROLES.rm2.ein

async function csrfToken(page) {
  const cookie = (await page.context().cookies()).find((c) => c.name === 'rrsq_csrf')
  if (!cookie) throw new Error('rrsq_csrf cookie is missing — the RM storage state is not actually signed in.')
  return cookie.value
}

test.describe('own queue only', () => {
  test('the queue is scoped server-side to this RM, and another EIN is refused', async ({ page }) => {
    const ownResponse = await page.request.get('/api/v1/sanket/queue?limit=100')
    expect(ownResponse.status(), 'GET /sanket/queue as the RM should succeed').toBe(200)
    const ownRows = (await ownResponse.json()).data ?? []
    for (const row of ownRows) {
      expect(row.assigned_rm_id, `lead ${row.lead_id ?? row.id} must be assigned to this RM`).toBe(RM_EIN)
    }

    const otherResponse = await page.request.get(`/api/v1/sanket/queue?rm=${encodeURIComponent(OTHER_RM_EIN)}`)
    expect(otherResponse.status(), "an RM passing another EIN's scope must be refused").toBe(403)

    await page.goto('/queue')
    const rows = page.getByTestId('queue-row')

    if (ownRows.length === 0) {
      // No leads assigned to this RM yet — the empty state must render, and the proof that
      // the scope is real still comes from the API assertions above, not from an absence.
      await expect(page.getByTestId('state-empty')).toBeVisible()
      await expect(rows).toHaveCount(0)
      return
    }

    await expect(rows.first()).toBeVisible()
    const ownIds = new Set(ownRows.map((r) => String(r.lead_id ?? r.id)))
    const count = await rows.count()
    expect(count).toBeGreaterThan(0)
    for (let i = 0; i < count; i += 1) {
      const leadId = await rows.nth(i).getAttribute('data-lead-id')
      expect(ownIds.has(leadId), `row ${leadId} rendered in the RM's queue must be one of this RM's own leads`).toBe(true)
    }
  })
})

test.describe('denied on assign', () => {
  test('no assign button, and the API itself refuses the round-robin', async ({ page }) => {
    await page.goto('/queue')
    await expect(page.getByTestId('assign-open')).toHaveCount(0)

    const response = await page.request.post('/api/v1/sanket/assign', {
      data: { mode: 'round_robin' },
      headers: { 'X-CSRF-Token': await csrfToken(page) },
    })
    expect(response.status()).toBe(403)
  })
})

test.describe('denied on the manager screens', () => {
  test('/dashboard shows permission-denied, not a crash and not the dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('state-denied')).toBeVisible()
    await expect(page.getByTestId('headline')).toHaveCount(0)
  })

  test('/trust shows permission-denied, not a crash and not the scorecard', async ({ page }) => {
    await page.goto('/trust')
    await expect(page.getByTestId('state-denied')).toBeVisible()
  })
})

test.describe('disposition', () => {
  test('recording a call outcome on an own lead shows the confirmation', async ({ page }) => {
    const ownResponse = await page.request.get('/api/v1/sanket/queue?limit=1')
    const lead = ((await ownResponse.json()).data ?? [])[0]
    test.skip(!lead, 'this RM genuinely has no leads to disposition')
    const leadId = String(lead.lead_id ?? lead.id)

    await page.goto(`/queue?lead=${encodeURIComponent(leadId)}`)
    const drawer = page.getByTestId('lead-drawer')
    await expect(drawer).toBeVisible()

    await drawer.getByTestId('open-disposition').click()
    const dialog = page.getByTestId('disposition-dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('radio', { name: 'Connected — interested' }).check()
    await dialog.getByRole('button', { name: /record outcome/i }).click()

    await expect(dialog.getByTestId('disposition-confirmed')).toBeVisible()
  })
})

test.describe('no CRM push for an RM', () => {
  test('the lead briefing has no "Push to CRM" action', async ({ page }) => {
    const ownResponse = await page.request.get('/api/v1/sanket/queue?limit=1')
    const lead = ((await ownResponse.json()).data ?? [])[0]
    test.skip(!lead, 'this RM genuinely has no leads to inspect')
    const leadId = String(lead.lead_id ?? lead.id)

    await page.goto(`/queue?lead=${encodeURIComponent(leadId)}`)
    await expect(page.getByTestId('lead-drawer')).toBeVisible()
    await expect(page.getByTestId('open-crm-push')).toHaveCount(0)
  })
})
