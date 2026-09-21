import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LeadDrawer from './LeadDrawer'
import { renderScreen, session } from '../test/render'
import { jsonResponse } from '../test/http'
import { LEAD_DETAIL, LEGACY_PACK, PACK } from '../test/fixtures/sanket'

function routes({ lead = LEAD_DETAIL, dryRun, confirmed, disposition } = {}) {
  const calls = []
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase()
    const body = init.body ? JSON.parse(init.body) : null
    calls.push({ url: String(url), method, body })
    if (String(url).includes('/crm-push')) {
      return jsonResponse(200, { data: body?.dry_run === false ? confirmed : dryRun, meta: {} })
    }
    if (String(url).includes('/disposition')) return jsonResponse(201, { data: disposition, meta: {} })
    if (String(url).includes('/sanket/lead/')) return jsonResponse(200, { data: lead, meta: {} })
    throw new Error(`no mock route for ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

const DRY_RUN = {
  dry_run: true,
  would_send: { apiId: '428', operation: 'createLead', lead: { custId: 'LB-2000002', productCode: 'personal' } },
  dedupe: { verdict: 'unknown', detail: 'No dedupe check was made: ATLAS_MODE=off.', api_id: '456', customer_count: null },
  crm_push_id: 1,
  gateway: { mode: 'off', client_available: false, writes_allowed: false, reason: 'ATLAS_MODE=off' },
  note: 'Nothing was sent. Send dry_run=false with confirm=true to push.',
}

const NOT_SENT = {
  dry_run: false,
  sent: false,
  status: 'NOT_SENT',
  reason: 'ATLAS_MODE=off — no call is made, and nothing is reported as collected.',
  crm_lead_id: null,
  crm_push_id: 2,
  sent_payload: DRY_RUN.would_send,
  dedupe: DRY_RUN.dedupe,
}

describe('LeadDrawer — the briefing', () => {
  it('shows the menu of four with a probability, a reason and a window each', async () => {
    routes()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    const items = await screen.findAllByTestId('menu-item')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('Personal Loan')
    expect(items[0]).toHaveTextContent('59.8%')
    expect(items[0]).toHaveTextContent('1-day window')
    expect(items[0]).toHaveTextContent(/fold the EMIs you pay elsewhere/)
    expect(items[3]).toHaveTextContent('Education Loan')
  })

  it('shows the positive reasons AND the negative window-shopper chips', async () => {
    routes()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    expect(await screen.findByText(/53 min on personal-loan pages/)).toBeInTheDocument()
    expect(screen.getByText(/Dropped at the Rs 1,000 processing fee/)).toBeInTheDocument()
  })

  it('distinguishes "no negative signal" from "this build has no such field"', async () => {
    routes({ lead: { ...LEAD_DETAIL, negative_signals: [] } })
    const { unmount } = renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    expect(await screen.findByText(/No window-shopper signal on this application/)).toBeInTheDocument()
    unmount()

    const stripped = { ...LEAD_DETAIL }
    delete stripped.negative_signals
    routes({ lead: stripped })
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    expect(await screen.findByText(/Window-shopper signals is not in this build/)).toBeInTheDocument()
  })

  it('switches the script between English and Hindi', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    const body = await screen.findByTestId('pitch-body')
    expect(body).toHaveTextContent(/I look after personal banking/)
    expect(body).toHaveAttribute('lang', 'en')

    await user.click(screen.getByRole('button', { name: 'हिन्दी' }))
    await waitFor(() => expect(screen.getByTestId('pitch-body')).toHaveAttribute('lang', 'hi'))
    expect(screen.getByTestId('pitch-body')).toHaveTextContent(/शाखा/)
  })

  it('marks a script for another menu product as generic, not as this customer’s evidence', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    await screen.findByTestId('pitch-body')
    expect(screen.getByText(/every claim traces to a chip above/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Product for the script'), 'gold')
    expect(await screen.findByText(/Generic script\./)).toBeInTheDocument()
    expect(screen.getByText(/cites nothing about this customer/)).toBeInTheDocument()
  })

  it('shows a real amortisation schedule with its rate provenance', async () => {
    routes()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    const panel = await screen.findByTestId('amortisation')
    expect(within(panel).getByText('₹16,429')).toBeInTheDocument()
    expect(within(panel).getByText('11.25% p.a.')).toBeInTheDocument()
    expect(within(panel).getByText('36 months')).toBeInTheDocument()
    expect(screen.queryByTestId('typical-emi')).not.toBeInTheDocument()
  })

  it('badges a TYPICAL_EMI loudly when there is no schedule', async () => {
    const stripped = { ...LEAD_DETAIL }
    delete stripped.amortisation
    routes({ lead: { ...stripped, emi_source: 'TYPICAL_EMI' } })
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    const panel = await screen.findByTestId('typical-emi')
    expect(panel).toHaveTextContent('Typical EMI — not from bank rates')
    expect(panel).toHaveTextContent(/Do not quote it to the customer/)
  })

  it('warns, and blocks a push, when the lead is suppressed', async () => {
    routes({ lead: { ...LEAD_DETAIL, suppressed: true, suppression_reasons: ['dnd'] } })
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    expect(await screen.findByText(/This lead is suppressed — do not call/)).toBeInTheDocument()
    expect(screen.getByTestId('open-crm-push')).toBeDisabled()
  })
})

describe('LeadDrawer — the CRM push', () => {
  it('runs a dry run first, and sends nothing until a second explicit act', async () => {
    const calls = routes({ dryRun: DRY_RUN, confirmed: NOT_SENT })
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })

    await user.click(await screen.findByTestId('open-crm-push'))
    const dedupe = await screen.findByTestId('crm-dedupe')
    expect(dedupe).toHaveAttribute('data-verdict', 'unknown')
    expect(dedupe).toHaveTextContent(/no dedupe check was made/i)
    expect(dedupe).toHaveTextContent(/This is not a pass|nothing is claimed about duplicates/)

    const pushes = calls.filter((c) => c.url.includes('/crm-push'))
    expect(pushes).toHaveLength(1)
    expect(pushes[0].body).toMatchObject({ dry_run: true })

    await user.click(screen.getByTestId('crm-continue'))
    expect(await screen.findByText(/this writes into a bank system/i)).toBeInTheDocument()
    expect(calls.filter((c) => c.url.includes('/crm-push'))).toHaveLength(1) // still nothing sent

    await user.click(screen.getByTestId('crm-confirm'))
    await screen.findByTestId('crm-result')
    const sent = calls.filter((c) => c.url.includes('/crm-push')).at(-1)
    // Two flags, per the contract: a client that forgets a default cannot write by omission.
    expect(sent.body).toMatchObject({ dry_run: false, confirm: true })
  })

  it('displays NOT_SENT honestly instead of swallowing it as a success', async () => {
    routes({ dryRun: DRY_RUN, confirmed: NOT_SENT })
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    await user.click(await screen.findByTestId('open-crm-push'))
    await screen.findByTestId('crm-dedupe')
    await user.click(screen.getByTestId('crm-continue'))
    await user.click(screen.getByTestId('crm-confirm'))

    const result = await screen.findByTestId('crm-result')
    expect(result).toHaveAttribute('data-status', 'NOT_SENT')
    expect(result).toHaveTextContent('NOT SENT — nothing reached the bank')
    expect(result).toHaveTextContent(/ATLAS_MODE=off/)
    expect(result).toHaveTextContent(/A 502 here would blame the bank for our own decision/)
  })

  it('blocks the push when the dedupe check found a duplicate', async () => {
    routes({ dryRun: { ...DRY_RUN, dedupe: { verdict: 'duplicate', detail: 'Already on file.', api_id: '456', already_pushed_as: 'CRM-9' } } })
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    await user.click(await screen.findByTestId('open-crm-push'))
    expect(await screen.findByTestId('crm-dedupe')).toHaveAttribute('data-verdict', 'duplicate')
    expect(screen.getByTestId('crm-continue')).toBeDisabled()
    expect(screen.getByText(/writes no `crm_push` row/)).toBeInTheDocument()
  })

  it('is not offered to a relationship manager', async () => {
    routes()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue', user: session('relationship_manager') })
    await screen.findAllByTestId('menu-item')
    expect(screen.queryByTestId('open-crm-push')).not.toBeInTheDocument()
    expect(screen.getByText(/Pushing to the bank CRM is a manager action/)).toBeInTheDocument()
  })
})

describe('LeadDrawer — recording an outcome', () => {
  it('offers the contract’s eight outcomes and announces the confirmation', async () => {
    const calls = routes({
      disposition: { id: 7, lead_id: 'LB-2000002', outcome: 'callback_requested', at: '2026-09-16T12:00:00Z', lead_status: 'in_progress' },
    })
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })

    await user.click(await screen.findByTestId('open-disposition'))
    const dialog = await screen.findByTestId('disposition-dialog')
    expect(within(dialog).getAllByRole('radio')).toHaveLength(8)

    await user.click(within(dialog).getByRole('radio', { name: /Call-back requested/ }))
    // The call-back time field appears only for the one outcome that can use it.
    expect(within(dialog).getByLabelText(/When should we call back/)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: /Record outcome/ }))
    const confirmed = await screen.findByTestId('disposition-confirmed')
    expect(confirmed).toHaveTextContent('Recorded — Call-back requested')
    expect(confirmed).toHaveTextContent(/append-only audit log/)
    const posted = calls.filter((c) => c.url.includes('/disposition'))
    expect(posted).toHaveLength(1)
    expect(posted[0].body).toMatchObject({ outcome: 'callback_requested' })
  })

  it('hides the call-back field for outcomes that cannot use one', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={() => {}} />, { path: '/queue' })
    await user.click(await screen.findByTestId('open-disposition'))
    const dialog = await screen.findByTestId('disposition-dialog')
    await user.click(within(dialog).getByRole('radio', { name: /Wrong number/ }))
    expect(within(dialog).queryByLabelText(/When should we call back/)).not.toBeInTheDocument()
  })
})

describe('LeadDrawer — static mode', () => {
  it('reads a packed lead, and disables the actions that need a backend', async () => {
    renderScreen(<LeadDrawer leadId="LB-3000001" onClose={() => {}} />, {
      path: '/queue', mode: 'static', user: null, pack: PACK,
    })
    const items = await screen.findAllByTestId('menu-item')
    expect(items[0]).toHaveTextContent('Home Loan')
    expect(items[0]).toHaveTextContent('41.0%')
    expect(screen.getByTestId('open-disposition')).toBeDisabled()
    expect(screen.getByTestId('typical-emi')).toBeInTheDocument()
  })

  it('says the menu is absent from a pre-SM-1 export rather than inventing one', async () => {
    renderScreen(<LeadDrawer leadId="LB-1000001" onClose={() => {}} />, {
      path: '/queue', mode: 'static', user: null, pack: LEGACY_PACK,
    })
    expect(await screen.findByText(/The menu of four is not in this build/)).toBeInTheDocument()
    expect(screen.getByText(/product_menu/)).toBeInTheDocument()
  })
})

describe('LeadDrawer — the dialog behaves like one', () => {
  it('is a modal dialog with an accessible name, and Escape closes it', async () => {
    routes()
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderScreen(<LeadDrawer leadId="LB-2000002" onClose={onClose} />, { path: '/queue' })
    const drawer = await screen.findByTestId('lead-drawer')
    const dialog = within(drawer).getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('LB-2000002')

    await user.keyboard('{Escape}')
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})

describe('Lead drawer — contactability', () => {
  // `contactability` reached the client on every lead and was read by nothing, so the
  // "do not call" judgement the product claims to support was never on the RM's screen.
  const CONTACTABILITY = {
    contactable: true,
    queueable: false,
    eligible: true,
    consent: { state: 'granted', source: 'batch', granted: true, at: null, expires_at: null },
    suppression: { suppressed: false, reasons: [], contact_reasons: [], eligibility_reasons: [] },
    blockers: ['window_expired'],
  }

  it('shows the consent state and what is blocking the call', async () => {
    routes({ lead: { ...LEAD_DETAIL, contactability: CONTACTABILITY, contactable: true } })
    renderScreen(<LeadDrawer leadId={LEAD_DETAIL.lead_id} onClose={() => {}} />, { session: session('manager') })
    const panel = await screen.findByTestId('contactability')
    expect(within(panel).getByText(/Contactable, with conditions/)).toBeInTheDocument()
    expect(within(panel).getByText('granted')).toBeInTheDocument()
    expect(within(panel).getByText(/window expired/)).toBeInTheDocument()
  })

  it('says plainly when the customer may not be contacted', async () => {
    routes({
      lead: {
        ...LEAD_DETAIL,
        contactability: {
          ...CONTACTABILITY,
          contactable: false,
          consent: { state: 'denied', granted: false, source: 'batch' },
          blockers: ['no_marketing_consent'],
        },
      },
    })
    renderScreen(<LeadDrawer leadId={LEAD_DETAIL.lead_id} onClose={() => {}} />, { session: session('manager') })
    const panel = await screen.findByTestId('contactability')
    expect(within(panel).getByText('Not contactable')).toBeInTheDocument()
    expect(within(panel).getByText('not granted')).toBeInTheDocument()
  })

  it('renders nothing at all when the payload carries no contactability', async () => {
    routes({ lead: LEAD_DETAIL })
    renderScreen(<LeadDrawer leadId={LEAD_DETAIL.lead_id} onClose={() => {}} />, { session: session('manager') })
    await screen.findByTestId('lead-drawer')
    await waitFor(() => expect(screen.queryByTestId('contactability')).not.toBeInTheDocument())
  })
})

