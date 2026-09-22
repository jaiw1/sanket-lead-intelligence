// The Outcome column on the audit log.
//
// `payload.outcome` means two different things depending on which kind of row carries it.
// On a `request.*` row it is the middleware's verdict on the HTTP call — "ok", "denied",
// "not_found". On a domain row it is a *business* word the route chose: a disposition of
// "callback_requested" is a perfectly successful call. Reading the second as the first is
// what painted a red **Failed** chip on rows that had failed at nothing, and that is what
// these tests pin down.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import Admin from './Admin'
import { renderScreen, session } from '../test/render'
import { jsonResponse, mockFetchRoutes } from '../test/http'

afterEach(() => vi.unstubAllGlobals())

const render = () => renderScreen(<Admin />, { path: '/admin', user: session('admin') })

const USER = {
  id: '11111111-2222-3333-4444-555555555555',
  username: 'a.deshmukh',
  full_name: 'Anjali Deshmukh',
  role: 'admin',
  is_active: true,
}

/** A domain row: the disposition itself. `outcome` here is the RM's answer, not a verdict. */
const DISPOSITION_ROW = {
  id: 426,
  at: '2026-09-21T09:14:00Z',
  actor: 'r.venkataraman',
  actor_role: 'relationship_manager',
  action: 'sanket.disposition.callback_requested',
  target_type: 'lead',
  target_id: 'SL-000412',
  request_id: 'req-disposition-1',
  payload: { outcome: 'callback_requested', has_note: true, status: 'in_progress' },
}

/** The request row the middleware wrote for the very same call. */
const REQUEST_OK_ROW = {
  id: 427,
  at: '2026-09-21T09:14:00Z',
  actor: 'r.venkataraman',
  actor_role: 'relationship_manager',
  action: 'request.post.sanket.lead.disposition',
  target_type: 'lead',
  target_id: 'SL-000412',
  request_id: 'req-disposition-1',
  payload: { method: 'POST', status: 201, outcome: 'ok', disposition_outcome: 'callback_requested' },
}

const REQUEST_DENIED_ROW = {
  id: 428,
  at: '2026-09-21T09:20:00Z',
  actor: 's.kulkarni',
  actor_role: 'credit_officer',
  action: 'request.post.sanket.assign',
  target_type: null,
  target_id: null,
  request_id: 'req-denied-1',
  payload: { method: 'POST', status: 403, outcome: 'denied' },
}

function routes(rows) {
  return mockFetchRoutes({
    '/api/v1/admin/users': jsonResponse(200, { data: [USER], meta: { total: 1 } }),
    '/api/v1/admin/audit?limit=50&offset=0': jsonResponse(200, { data: rows, meta: { total: rows.length } }),
  })
}

const auditTable = () => screen.findByRole('table', { name: /audit log entries/i })

const rowFor = (table, id) => within(table).getByText(String(id)).closest('tr')

describe('Administration — the audit log’s Outcome column', () => {
  it('shows no Failed chip for a domain row whose outcome is a business word', async () => {
    routes([DISPOSITION_ROW, REQUEST_OK_ROW])
    render()
    const table = await auditTable()
    const row = rowFor(table, DISPOSITION_ROW.id)

    expect(row).toHaveTextContent('sanket.disposition.callback_requested')
    expect(row).not.toHaveTextContent('Failed')
    expect(row).not.toHaveTextContent('OK')
    expect(row).toHaveTextContent('—')
  })

  it('shows OK for the request row of that same successful call', async () => {
    routes([DISPOSITION_ROW, REQUEST_OK_ROW])
    render()
    const table = await auditTable()
    const row = rowFor(table, REQUEST_OK_ROW.id)

    expect(row).toHaveTextContent('OK')
    expect(row).not.toHaveTextContent('Failed')
  })

  it('still shows Failed for a request row the platform denied', async () => {
    routes([REQUEST_DENIED_ROW, REQUEST_OK_ROW])
    render()
    const table = await auditTable()

    expect(rowFor(table, REQUEST_DENIED_ROW.id)).toHaveTextContent('Failed')
    expect(rowFor(table, REQUEST_OK_ROW.id)).toHaveTextContent('OK')
  })

  it('reads the status code on a pre-fix request row whose outcome word was clobbered', async () => {
    // Row 426 on the sandbox: a 201 written before the route stopped passing its own
    // `outcome=`. The log is append-only, so that payload cannot be corrected — but the
    // status beside it never lied, and it is what the row is judged by.
    routes([{
      ...REQUEST_OK_ROW,
      id: 426,
      payload: { method: 'POST', status: 201, outcome: 'callback_requested' },
    }])
    render()
    const table = await auditTable()
    const row = rowFor(table, 426)

    expect(row).toHaveTextContent('OK')
    expect(row).not.toHaveTextContent('Failed')
  })

  it('says nothing rather than Failed when a request row carries no verdict it knows', async () => {
    routes([REQUEST_OK_ROW, { ...REQUEST_DENIED_ROW, payload: { method: 'POST', outcome: 'mystery' } }])
    render()
    const table = await auditTable()

    expect(rowFor(table, REQUEST_DENIED_ROW.id)).not.toHaveTextContent('Failed')
  })

  it('still shows Failed for a denied request row with no status beside the word', async () => {
    routes([REQUEST_OK_ROW, { ...REQUEST_DENIED_ROW, payload: { method: 'POST', outcome: 'denied' } }])
    render()
    const table = await auditTable()

    expect(rowFor(table, REQUEST_DENIED_ROW.id)).toHaveTextContent('Failed')
  })

  it('never renders an object as [object Object] in the audit table', async () => {
    routes([{ ...DISPOSITION_ROW, payload: { red_thr: { before: 0.3437, after: 0.25 } } }])
    render()
    await auditTable()
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })
})

describe('Admin — the users panel introduces itself in English', () => {
  it('explains the missing columns without quoting the contract at the reader', async () => {
    routes([])
    render()
    expect(await screen.findByText(/The platform does not promise exactly which details it returns for a user account/)).toBeInTheDocument()
    expect(screen.getByText(/leaves out any of those this platform did not send/)).toBeInTheDocument()
    // The operation id and the contract's own vocabulary are not end-user copy.
    expect(screen.queryByText(/adminUsersList/)).not.toBeInTheDocument()
    expect(screen.queryByText(/x-response-shapes/)).not.toBeInTheDocument()
  })
})
