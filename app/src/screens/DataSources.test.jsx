// Shapes drawn from `contracts/openapi.json` `x-response-shapes` (`metaSync`,
// `metaProvenance`): `served_from_cache` / `cached_calls` / `last_reused_at` per row, and
// the top-level `cached: {apis, calls, last_reused_at, note}` block on `/meta/provenance`.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import DataSources from './DataSources'
import { renderScreen } from '../test/render'
import { jsonResponse, mockFetchRoutes } from '../test/http'

afterEach(() => vi.unstubAllGlobals())

const render = () => renderScreen(<DataSources />, { path: '/data-sources' })

const VERSION = { version: '1.4.0', git_sha: 'abc1234', environment: 'staging' }

const LIVE_ROW = {
  api_id: '391', label: 'Loan details', used_by: ['drishti'], calls: 4, records: 120,
  last_status: 200, last_mode: 'live', last_pulled_at: '2026-09-20T02:00:00Z',
  last_success_at: '2026-09-20T02:00:00Z', subscription_status: 'approved',
  endpoint: '/loan', latency_ms: 210, error: null, note: null, live: true,
  served_from_cache: false, cached_calls: 0, last_reused_at: null,
}

const CACHED_ROW = {
  api_id: '442', label: 'CIF exposure and rating', used_by: ['sanket'], calls: 6, records: 240,
  last_status: 200, last_mode: 'cached', last_pulled_at: '2026-09-21T02:00:00Z',
  last_success_at: '2026-09-16T02:00:00Z', subscription_status: 'approved',
  endpoint: '/exposure', latency_ms: 190, error: null, note: null, live: false,
  served_from_cache: true, cached_calls: 2, last_reused_at: '2026-09-21T02:00:00Z',
}

function syncEnvelope(rows, metaOverrides = {}) {
  return jsonResponse(200, {
    data: rows,
    meta: {
      total: rows.length,
      runs: {},
      gateway: { mode: 'off', client_available: false, writes_allowed: false, reason: 'ATLAS_MODE=off' },
      real_data: rows.some((r) => r.live),
      live_apis: rows.filter((r) => r.live).map((r) => r.api_id),
      cached_apis: rows.filter((r) => r.served_from_cache).map((r) => r.api_id),
      note: 'Every row with `live: false` was answered by a fixture or never called at all.',
      ...metaOverrides,
    },
  })
}

function provenanceEnvelope(overrides = {}) {
  return jsonResponse(200, {
    data: {
      real_data: false,
      live_apis: [],
      live_records: 0,
      products: {},
      freshness: {},
      drift: {},
      cached: { apis: [], calls: 0, last_reused_at: null, note: null },
      note: 'Every family reported FIXTURE has not been pulled from a bank API.',
      ...overrides,
    },
    meta: {},
  })
}

function routes({ sync = syncEnvelope([LIVE_ROW]), provenance = provenanceEnvelope() } = {}) {
  return mockFetchRoutes({
    '/api/v1/meta/sync': sync,
    '/api/v1/meta/provenance': provenance,
    '/api/v1/meta/version': jsonResponse(200, { data: VERSION, meta: {} }),
  })
}

describe('Data sources and sync — cached last-good pulls', () => {
  it('renders a live row as Live, with no cached caveat', async () => {
    routes()
    render()
    const table = await screen.findByRole('table', { name: /registered bank APIs/i })
    const row = within(table).getByText('391').closest('tr')
    expect(row).toHaveTextContent('Live')
    expect(row).not.toHaveTextContent('Bank API · last good pull')
  })

  it('renders a reused endpoint as "Bank API · last good pull", dated by last_success_at', async () => {
    routes({ sync: syncEnvelope([CACHED_ROW]) })
    render()
    const table = await screen.findByRole('table', { name: /registered bank APIs/i })
    const row = within(table).getByText('442').closest('tr')
    expect(row).toHaveTextContent('Bank API · last good pull')
    // Dated by last_success_at (16 Sep), never by last_pulled_at (21 Sep) — the two differ
    // in this fixture on purpose, so a screen that confused them would fail here.
    const fmt = (iso) => new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
    expect(row).toHaveTextContent(fmt(CACHED_ROW.last_success_at))
    expect(row).not.toHaveTextContent(/^Live$/)
  })

  it('adds a disclosure line when the platform reused a cached answer', async () => {
    routes({
      provenance: provenanceEnvelope({
        cached: { apis: ['442', '408'], calls: 5, last_reused_at: '2026-09-21T02:00:00Z', note: 'reused' },
      }),
    })
    render()
    const intro = (await screen.findByText(/Every API SANKET is registered to call/)).closest('div')
    expect(intro).toHaveTextContent(/2 APIs answered tonight from a cached last-good pull/)
  })

  it('says nothing about a cached reuse when none happened', async () => {
    routes()
    render()
    const intro = (await screen.findByText(/Every API SANKET is registered to call/)).closest('div')
    expect(intro).not.toHaveTextContent(/cached last-good pull/)
  })
})
