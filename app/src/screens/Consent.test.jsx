import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Consent from './Consent'
import { renderScreen, session } from '../test/render'
import { jsonResponse } from '../test/http'

const HANDLE = 'RRSQ-536811a3c8b7422ab18e'

const LIST_ROW = {
  consent_handle: HANDLE,
  consent_id: null,
  cust_id: 'LB-2000002',
  status: 'REQUESTED',
  fi_types: ['DEPOSIT'],
  requested_at: '2026-09-16T09:44:39Z',
  approved_at: null,
  expires_at: '2027-09-16T09:44:39Z',
  data_ready: false,
}

const DETAIL = {
  ...LIST_ROW,
  vua: 'LB-2000002@rrsquad-aa',
  purpose: 'Loan eligibility assessment',
  last_fetch_at: null,
  may_transition_to: ['ACTIVE', 'EXPIRED', 'FAILED', 'PENDING', 'REJECTED'],
  terminal: false,
  customer_sees: {
    requested_by: 'IDBI Bank (SANKET prospect assist)',
    purpose: 'Loan eligibility assessment',
    purpose_code: '101',
    data_requested: ['DEPOSIT'],
    period: 'Transaction history for the last 12 months',
    frequency: 'One fetch, on approval',
    valid_until: '2027-09-16T09:44:39Z',
    you_can: ['Decline without affecting any existing relationship with the bank.'],
    we_will_not: ['Fetch anything before you approve.', 'Use this data for a credit-bureau enquiry.'],
  },
}

function routes({ list = [LIST_ROW], detail = DETAIL, onPost } = {}) {
  const calls = []
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase()
    const body = init.body ? JSON.parse(init.body) : null
    calls.push({ url: String(url), method, body })
    if (method === 'POST' && String(url).includes('/replay')) return jsonResponse(202, { data: { replayed: true, consent: { ...detail, status: 'ACTIVE' } }, meta: {} })
    if (method === 'POST' && String(url).includes('/fetch')) return jsonResponse(202, { data: { accepted: true }, meta: {} })
    if (method === 'POST' && String(url).includes('/consent/request')) {
      return jsonResponse(201, { data: { consent: { ...LIST_ROW, consent_handle: 'RRSQ-new' }, customer_sees: DETAIL.customer_sees }, meta: {} })
    }
    if (String(url).includes('/consent/list')) return jsonResponse(200, { data: list, meta: { total: list.length, states: [] } })
    if (String(url).includes('/consent/')) return jsonResponse(200, { data: detail, meta: {} })
    if (onPost) return onPost(url, init)
    throw new Error(`no mock route for ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

describe('Consent — the list', () => {
  it('lists the artefacts with their state', async () => {
    routes()
    renderScreen(<Consent />, { path: '/consent' })
    const list = await screen.findByTestId('consent-list')
    expect(within(list).getByText(HANDLE)).toBeInTheDocument()
    expect(within(list).getByText('REQUESTED')).toBeInTheDocument()
  })

  it('renders an empty state rather than a blank panel', async () => {
    routes({ list: [] })
    renderScreen(<Consent />, { path: '/consent' })
    expect(await screen.findByText(/No consent has been requested yet/)).toBeInTheDocument()
  })

  it('filters by state through the server', async () => {
    const calls = routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await screen.findByTestId('consent-list')
    await user.selectOptions(screen.getByLabelText('Filter by state'), 'ACTIVE')
    // Assert that SOME call carried the filter, not that the last one did: the detail pane
    // may fire its own request in between.
    await waitFor(() => expect(calls.some((c) => c.url.includes('status=ACTIVE'))).toBe(true))
  })

  it('offers only the states the database can store — PAUSED is gone', async () => {
    routes()
    renderScreen(<Consent />, { path: '/consent' })
    const select = await screen.findByLabelText('Filter by state')
    const values = [...select.options].map((o) => o.value)
    expect(values).toEqual(['', 'REQUESTED', 'PENDING', 'ACTIVE', 'REJECTED', 'REVOKED', 'EXPIRED', 'FAILED'])
    expect(values).not.toContain('PAUSED')
  })
})

describe('Consent — the detail', () => {
  it('draws the state machine with the current state and the moves still available', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByText(HANDLE))

    const machine = await screen.findByTestId('consent-state-machine')
    const current = within(machine).getByText('Requested').closest('li')
    expect(current).toHaveAttribute('data-current', 'true')
    expect(machine).toHaveTextContent(/Pending/)
    expect(screen.getByText(/Only a webhook from the Account Aggregator \(497\/498\) moves it/)).toBeInTheDocument()
  })

  it('does not draw PAUSED, which the database could never store', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByText(HANDLE))
    const machine = await screen.findByTestId('consent-state-machine')
    expect(within(machine).queryByText(/paused/i)).not.toBeInTheDocument()
  })

  it('shows what the customer sees, including what we will NOT do', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByText(HANDLE))
    expect(await screen.findByText('We will not')).toBeInTheDocument()
    expect(screen.getByText(/Use this data for a credit-bureau enquiry/)).toBeInTheDocument()
    expect(screen.getByText(/not a screenshot of/)).toBeInTheDocument()
  })

  it('disables the fetch unless the consent is ACTIVE, and says why', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByText(HANDLE))
    expect(await screen.findByTestId('consent-fetch')).toBeDisabled()
    expect(screen.getByText(/refused with 409 unless the consent is ACTIVE/)).toBeInTheDocument()
  })

  it('enables the fetch once the consent is ACTIVE', async () => {
    routes({ list: [{ ...LIST_ROW, status: 'ACTIVE' }], detail: { ...DETAIL, status: 'ACTIVE' } })
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByText(HANDLE))
    expect(await screen.findByTestId('consent-fetch')).toBeEnabled()
  })
})

describe('Consent — the admin-only replay', () => {
  it('is offered to an administrator and explains what the audit will say', async () => {
    routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent', user: session('admin') })
    await user.click(await screen.findByText(HANDLE))
    await user.click(await screen.findByTestId('consent-replay-open'))

    const dialog = await screen.findByTestId('consent-replay-dialog')
    expect(dialog).toHaveTextContent(/not the webhook endpoint with its signature check removed/)
    expect(dialog).toHaveTextContent('sanket.consent.replayed')
  })

  it('posts the chosen event and api id', async () => {
    const calls = routes()
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent', user: session('admin') })
    await user.click(await screen.findByText(HANDLE))
    await user.click(await screen.findByTestId('consent-replay-open'))
    await user.selectOptions(screen.getByLabelText('Event to synthesise'), 'REJECTED')
    await user.click(screen.getByTestId('consent-replay-confirm'))

    await waitFor(() => {
      const posted = calls.find((c) => c.url.includes('/replay'))
      expect(posted).toBeTruthy()
      expect(posted.body).toMatchObject({ event: 'REJECTED', api_id: '497' })
    })
  })

  it('is NOT offered to a manager or a relationship manager', async () => {
    for (const role of ['manager', 'relationship_manager']) {
      routes()
      const user = userEvent.setup()
      const { unmount } = renderScreen(<Consent />, { path: '/consent', user: session(role) })
      await user.click(await screen.findByText(HANDLE))
      await screen.findByTestId('consent-state-machine')
      expect(screen.queryByTestId('consent-replay-open'), role).not.toBeInTheDocument()
      unmount()
    }
  })
})

describe('Consent — requesting one', () => {
  it('sends the customer id and the purpose the customer will read', async () => {
    const calls = routes({ list: [] })
    const user = userEvent.setup()
    renderScreen(<Consent />, { path: '/consent' })
    await user.click(await screen.findByTestId('consent-request-open'))

    // The focus trap moves focus into the dialog on a timer. Typing before it lands loses
    // the first keystrokes — which showed up as a cust_id with its hyphen missing, one run
    // in four. Waiting for focus is both the fix and a real assertion: a dialog that does
    // not focus its own first field is broken for a keyboard user.
    const input = screen.getByLabelText('Customer id')
    await waitFor(() => expect(input).toHaveFocus())
    await user.type(input, 'LB-2000002')

    const submit = screen.getByTestId('consent-request-submit')
    await waitFor(() => expect(submit).toBeEnabled())
    await user.click(submit)

    await waitFor(() => {
      const posted = calls.find((c) => c.url.includes('/consent/request'))
      expect(posted.body).toMatchObject({ cust_id: 'LB-2000002', purpose: 'Loan eligibility assessment' })
    })
    expect(await screen.findByText(/Requested — RRSQ-new/)).toBeInTheDocument()
  })
})

describe('Consent — static mode', () => {
  it('says consent needs the backend rather than faking an artefact', async () => {
    renderScreen(<Consent />, { path: '/consent', mode: 'static', user: null })
    expect(await screen.findByText(/Consent is not in this build/)).toBeInTheDocument()
    expect(screen.getByText(/GET \/sanket\/consent\/list/)).toBeInTheDocument()
  })
})
