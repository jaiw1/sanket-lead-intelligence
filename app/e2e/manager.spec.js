// The manager: the widest role short of admin — dashboard, round-robin assignment, the
// CRM push (the platform's only write into a bank system), and the queue's server-side
// filters.

import { test, expect } from '@playwright/test'
import { statePath } from './roles.js'

test.use({ storageState: statePath('manager') })

test.describe('manager dashboard', () => {
  test('loads with the computed headline and the four KPI tiles', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByTestId('headline')).toBeVisible()
    await expect(page.getByTestId('kpi-leads')).toBeVisible()
    await expect(page.getByTestId('kpi-suppressed')).toBeVisible()
    await expect(page.getByTestId('kpi-window-open')).toBeVisible()
    await expect(page.getByTestId('kpi-unassigned')).toBeVisible()
  })
})

test.describe('round-robin assignment', () => {
  test('assigning from the queue shows a result', async ({ page }) => {
    await page.goto('/queue')
    await page.getByTestId('assign-open').click()

    const dialog = page.getByTestId('assign-dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByTestId('assign-confirm').click()

    await expect(dialog.getByTestId('assign-result')).toBeVisible()
  })
})

test.describe('CRM push — the platform\'s only write into a bank system', () => {
  test('dry run, dedupe verdict, confirm, and an honestly-shown result', async ({ page }) => {
    // Any non-suppressed lead will do; the queue excludes suppressed leads by default,
    // and a suppressed lead has no "Push to CRM" button to begin with.
    const queueResponse = await page.request.get('/api/v1/sanket/queue?limit=1')
    expect(queueResponse.ok()).toBeTruthy()
    const lead = ((await queueResponse.json()).data ?? [])[0]
    test.skip(!lead, 'the book has no queueable (non-suppressed) lead to push to the CRM')
    const leadId = String(lead.lead_id ?? lead.id)

    await page.goto(`/queue?lead=${encodeURIComponent(leadId)}`)
    const drawer = page.getByTestId('lead-drawer')
    await expect(drawer).toBeVisible()

    await drawer.getByTestId('open-crm-push').click()
    const dialog = page.getByTestId('crm-push-dialog')
    await expect(dialog).toBeVisible()

    // Step 1 of 2 — the dry run. Nothing has been sent yet.
    const dedupe = dialog.getByTestId('crm-dedupe')
    await expect(dedupe).toBeVisible()
    const verdict = await dedupe.getAttribute('data-verdict')
    expect(['clear', 'duplicate', 'unknown']).toContain(verdict)
    await expect(dialog.getByText(/exact API 428 payload/i)).toBeVisible()

    if (verdict === 'duplicate') {
      // The bank already holds this customer: the push is correctly refused, and there is
      // no second step to take. Continuing here would be testing a state the UI disallows.
      await expect(dialog.getByTestId('crm-continue')).toBeDisabled()
      return
    }

    // Step 2 of 2 — the deliberate second act.
    await dialog.getByTestId('crm-continue').click()
    await expect(dialog.getByTestId('crm-confirm')).toBeVisible()
    await dialog.getByTestId('crm-confirm').click()

    const result = dialog.getByTestId('crm-result')
    await expect(result).toBeVisible()
    const status = await result.getAttribute('data-status')
    expect(['OK', 'NOT_SENT', 'NOT_COLLECTED', 'ERROR']).toContain(status)

    // ATLAS_MODE=off on this backend: nothing can actually reach the bank, so a truthful
    // build must say NOT_SENT out loud rather than swallow it into a generic success.
    if (status === 'NOT_SENT') {
      await expect(result).toContainText('NOT SENT')
      await expect(result).toContainText(/nothing reached the bank/i)
    }
  })
})

test.describe('queue filters are server queries', () => {
  test('setting the product filter to Home Loan is reflected in the URL and every row', async ({ page }) => {
    await page.goto('/queue')
    const rows = page.getByTestId('queue-row')
    const empty = page.getByTestId('state-empty')
    await expect(rows.first().or(empty)).toBeVisible()

    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().includes('/sanket/queue') && res.url().includes('product=home')),
      page.selectOption('#f-product', 'home'),
    ])
    expect(response.ok()).toBeTruthy()
    await expect(page).toHaveURL(/product=home/)

    await expect(rows.first().or(empty)).toBeVisible()
    const count = await rows.count()

    if (count === 0) {
      await expect(empty).toBeVisible()
      return
    }
    for (let i = 0; i < count; i += 1) {
      await expect(rows.nth(i)).toContainText('Home Loan')
    }
  })
})
