import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Queue from './Queue'
import { renderScreen, session } from '../test/render'
import { jsonResponse, mockFetchRoutes } from '../test/http'
import { LEGACY_PACK, PACK, QUEUE_ROW, SUPPRESSED_ROW } from '../test/fixtures/sanket'

const QUEUE_META = { total: 2, limit: 50, offset: 0, scope: 'all', model_run_id: 'run-1', provenance_mode: 'fixture' }

/** Route everything under /sanket/queue to one handler, whatever the query string. */
function queueRoute(rows = [QUEUE_ROW], meta = QUEUE_META) {
  const calls = []
  const fetchMock = vi.fn(async (url, init = {}) => {
    calls.push(url)
    if (String(url).includes('/sanket/queue')) return jsonResponse(200, { data: rows, meta })
    if (String(url).includes('/sanket/assign')) {
      return jsonResponse(200, {
        data: {
          mode: 'round_robin', assigned: 2, per_rm: { 'EIN-100471': 1, 'EIN-100482': 1 },
          roster: [{ ein: 'EIN-100471', name: 'Vikram Rathore' }, { ein: 'EIN-100482', name: 'Priya Nair' }],
          allocation: {}, note: null,
        },
        meta: {},
      })
    }
    throw new Error(`no mock route for ${init.method || 'GET'} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

describe('Queue — what comes back', () => {
  it('renders a row per lead, with the product, window and score', async () => {
    queueRoute()
    renderScreen(<Queue />, { path: '/queue' })
    const rows = await screen.findAllByTestId('queue-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('Personal Loan')).toBeInTheDocument()
    expect(within(rows[0]).getByTestId('window-badge')).toHaveAttribute('data-window-state', 'expired')
    expect(rows[0]).toHaveTextContent('60') // score 0.5976 -> 60
  })

  it('names the scope, so an RM knows the queue is filtered by the server', async () => {
    queueRoute([QUEUE_ROW], { ...QUEUE_META, scope: ['EIN-100471'] })
    renderScreen(<Queue />, { path: '/queue', user: session('relationship_manager', { ein: 'EIN-100471' }) })
    expect(await screen.findByText(/your own leads/)).toBeInTheDocument()
  })

  it('shows a suppressed lead with its reason rather than hiding it', async () => {
    queueRoute([SUPPRESSED_ROW])
    renderScreen(<Queue />, { path: '/queue?suppressed=1' })
    const row = (await screen.findAllByTestId('queue-row'))[0]
    expect(row).toHaveAttribute('data-suppressed', 'true')
    expect(within(row).getByText(/No marketing consent \(DPDP\)/)).toBeInTheDocument()
  })

  it('keeps the tier and the suppression flag as two separate facts', async () => {
    // `tier` is a band on the score; `suppressed` is whether the bank may ring them.
    // This fixture row is BOTH suppressed and hot, and the screen has to show both —
    // when every suppressed row was relabelled `cold`, the tier column was just the
    // suppression flag wearing a colour.
    queueRoute([SUPPRESSED_ROW])
    renderScreen(<Queue />, { path: '/queue?suppressed=1' })
    const row = (await screen.findAllByTestId('queue-row'))[0]
    expect(within(row).getByText(/Hot tier/)).toBeInTheDocument()
    expect(within(row).getByText(/Suppressed/)).toBeInTheDocument()
  })

  it('renders an empty state, with RM-specific wording, when nothing comes back', async () => {
    queueRoute([], { ...QUEUE_META, total: 0 })
    renderScreen(<Queue />, { path: '/queue', user: session('relationship_manager') })
    expect(await screen.findByTestId('state-empty')).toBeInTheDocument()
    expect(screen.getByText(/only leads assigned to their own EIN/)).toBeInTheDocument()
  })

  it('renders permission-denied on a 403 rather than an empty queue', async () => {
    mockFetchRoutes({}) // any call throws; override below
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(403, { error: { code: 'forbidden', message: 'No.' } })))
    renderScreen(<Queue />, { path: '/queue' })
    expect(await screen.findByTestId('state-denied')).toBeInTheDocument()
  })
})

describe('Queue — the filters are server queries', () => {
  it('sends product, tier, status, window_due and sort as query parameters', async () => {
    const { calls } = queueRoute()
    const user = userEvent.setup()
    renderScreen(<Queue />, { path: '/queue' })
    await screen.findAllByTestId('queue-row')

    await user.selectOptions(screen.getByLabelText('Product'), 'home')
    await waitFor(() => expect(calls.at(-1)).toContain('product=home'))

    await user.selectOptions(screen.getByLabelText('Contact window'), 'true')
    await waitFor(() => expect(calls.at(-1)).toContain('window_due=true'))

    await user.selectOptions(screen.getByLabelText('Sort by'), 'safe_emi')
    await waitFor(() => expect(calls.at(-1)).toContain('sort=safe_emi'))
  })

  it('asks the server for suppressed rows rather than filtering them in the browser', async () => {
    const { calls } = queueRoute()
    const user = userEvent.setup()
    renderScreen(<Queue />, { path: '/queue' })
    await screen.findAllByTestId('queue-row')
    await user.click(screen.getByLabelText(/include suppressed/i))
    await waitFor(() => expect(calls.at(-1)).toContain('include_suppressed=true'))
  })

  it('offers only the five sort keys the backend allowlists', async () => {
    queueRoute()
    renderScreen(<Queue />, { path: '/queue' })
    const select = await screen.findByLabelText('Sort by')
    expect([...select.options].map((o) => o.value))
      .toEqual(['score', 'intent', 'capacity', 'uplift_pct', 'safe_emi'])
  })

  it('offers all six products', async () => {
    queueRoute()
    renderScreen(<Queue />, { path: '/queue' })
    const select = await screen.findByLabelText('Product')
    expect([...select.options].map((o) => o.value))
      .toEqual(['', 'personal', 'gold', 'auto', 'education', 'home', 'lap'])
  })
})

describe('Queue — round-robin assignment', () => {
  it('is offered to a manager and confirmed before it runs', async () => {
    const { calls } = queueRoute([{ ...QUEUE_ROW, assigned_rm_id: null }])
    const user = userEvent.setup()
    renderScreen(<Queue />, { path: '/queue' })
    await screen.findAllByTestId('queue-row')

    await user.click(screen.getByTestId('assign-open'))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent(/1 lead currently on screen with no relationship manager/)
    // Nothing has been sent yet: opening a confirmation must not be the action itself.
    expect(calls.some((c) => String(c).includes('/assign'))).toBe(false)

    await user.click(screen.getByTestId('assign-confirm'))
    expect(await screen.findByTestId('assign-result')).toHaveTextContent('Assigned 2 leads')
    expect(calls.some((c) => String(c).includes('/assign'))).toBe(true)
  })

  it('warns that a two-RM roster does not demonstrate load balancing', async () => {
    queueRoute([{ ...QUEUE_ROW, assigned_rm_id: null }])
    const user = userEvent.setup()
    renderScreen(<Queue />, { path: '/queue' })
    await screen.findAllByTestId('queue-row')
    await user.click(screen.getByTestId('assign-open'))
    await user.click(screen.getByTestId('assign-confirm'))
    expect(await screen.findByText(/seeding more RMs/)).toBeInTheDocument()
  })

  it('is not offered to a relationship manager', async () => {
    queueRoute()
    renderScreen(<Queue />, { path: '/queue', user: session('relationship_manager') })
    await screen.findAllByTestId('queue-row')
    expect(screen.queryByTestId('assign-open')).not.toBeInTheDocument()
  })
})

describe('Queue — static mode', () => {
  it('reads the bundled export and disables the server-only window filter', async () => {
    renderScreen(<Queue />, { path: '/queue', mode: 'static', user: null, pack: PACK })
    expect(await screen.findAllByTestId('queue-row')).toHaveLength(1)
    expect(screen.getByLabelText('Contact window')).toBeDisabled()
  })

  it('survives a pre-SM-1 export whose leads have no menu and no suppression', async () => {
    renderScreen(<Queue />, { path: '/queue', mode: 'static', user: null, pack: LEGACY_PACK })
    const rows = await screen.findAllByTestId('queue-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveAttribute('data-suppressed', 'false')
    // `pl` is not in the six-product table: the raw code is shown, never a wrong label.
    expect(within(rows[0]).getByText('pl')).toBeInTheDocument()
  })
})
