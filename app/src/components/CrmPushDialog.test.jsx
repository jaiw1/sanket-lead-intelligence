import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import CrmPushDialog from './CrmPushDialog'
import { renderScreen } from '../test/render'
import { jsonResponse } from '../test/http'

/**
 * The dialog's own sentence about a dedupe verdict, against the server's.
 *
 * The dialog deliberately prints its own framing under the server's `detail` — an
 * `unknown` verdict must never read like a pass, whatever reassuring words came back. That
 * only works while the two agree. The `clear` framing used to assert a fact of its own,
 * "API 456 found no existing master record that matches this customer", which holds for a
 * count of ZERO and for nothing else — and the ordinary clear answer here is a count of
 * ONE, because every SANKET lead is already a bank customer and their own master record is
 * what the bank finds. The screen then said "1 matching record — this customer's own"
 * immediately above "found no existing master record", and "Matching records: 1" below it.
 */
const LEAD = { id: 'LB-2006372', product: 'personal', productMenu: [{ product: 'personal' }] }

function dryRun(dedupe) {
  const body = {
    dry_run: true,
    would_send: { apiId: '428', operation: 'createLead', caution: null, lead: { custId: LEAD.id } },
    dedupe: { api_id: '456', ...dedupe },
    crm_push_id: 1,
    gateway: { mode: 'off', client_available: false, writes_allowed: false },
    note: 'Nothing was sent.',
  }
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, { data: body, meta: {} })))
}

const open = () => renderScreen(
  <CrmPushDialog open lead={LEAD} onClose={() => {}} />, { path: '/queue' },
)

describe('CrmPushDialog — the dedupe panel says one thing, not two', () => {
  it('does not deny the matching record the server just reported', async () => {
    dryRun({
      verdict: 'clear',
      detail: "API 456 reports 1 matching record — this customer's own; no duplicate.",
      customer_count: 1,
    })
    open()
    const panel = await screen.findByTestId('crm-dedupe')

    expect(panel).toHaveTextContent(/1 matching record — this customer's own/)
    expect(panel).toHaveTextContent(/Matching records/)
    // The contradiction itself: a claim that nothing matched, beside a count of one.
    expect(panel).not.toHaveTextContent(/found no existing master record/i)
    expect(panel).toHaveTextContent(/not treated as a duplicate/i)
  })

  it('says the same true thing when the bank really did match nobody', async () => {
    dryRun({
      verdict: 'clear',
      detail: 'API 456 reports no matching customer records.',
      customer_count: 0,
    })
    open()
    const panel = await screen.findByTestId('crm-dedupe')
    expect(panel).toHaveTextContent(/no matching customer records/)
    expect(panel).toHaveTextContent(/not treated as a duplicate/i)
  })

  it('still refuses to let `unknown` read like a pass', async () => {
    dryRun({ verdict: 'unknown', detail: 'The dedupe service did not answer.', customer_count: null })
    open()
    const panel = await screen.findByTestId('crm-dedupe')
    expect(panel).toHaveAttribute('data-verdict', 'unknown')
    expect(panel).toHaveTextContent(/This is not a pass/)
  })

  it('shows the payload’s caution where a reviewer reads the payload', async () => {
    dryRun({ verdict: 'clear', detail: 'API 456 reports no matching customer records.', customer_count: 0 })
    open()
    await screen.findByTestId('crm-dedupe')
    expect(screen.getByText(/The exact API 428 payload/)).toBeInTheDocument()
  })
})
