import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import ModelTrust from './ModelTrust'
import { renderScreen, session } from '../test/render'
import { errorResponse, jsonResponse, mockFetchRoutes } from '../test/http'
import { FUNNEL, PACK } from '../test/fixtures/sanket'
import sanketData from '../../public/sanket_data.json'

describe('ModelTrust — the validation table survives the committed pack', () => {
  it('renders the bundled sanket_data.json without crashing, including its "report" bands', async () => {
    // Regression for the video lane's crash report: SK-03/SK-06/SK-10 in the committed
    // export are `op: "report"` bands whose `observed` is a structured breakdown, not a
    // scalar (React throws "Objects are not valid as a React child" if handed one raw).
    // This is the actual file the app ships, not a hand-trimmed excerpt.
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'static', user: null, pack: sanketData })

    const table = await screen.findByRole('table', { name: /pre-registered validation criteria/i })
    expect(table).toBeInTheDocument()

    // SK-03: precision at 5% and 20% — a two-part object, summarised rather than dumped.
    expect(screen.getByText(/@5%/)).toBeInTheDocument()
    expect(screen.getByText(/@20%/)).toBeInTheDocument()
    // SK-06: the headline uplift object ({baseline_per_100, model_per_100, headline}).
    expect(screen.getByText(/9 → 29 \/ 100/)).toBeInTheDocument()
    // SK-10: the seven-way cut breakdown — named, not printed as [object Object].
    expect(screen.getByText(/reported, 7 parts/)).toBeInTheDocument()
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })
})

describe('ModelTrust — SK-04’s dual verdict', () => {
  const packWithDualVerdict = {
    ...PACK,
    metrics: {
      ...PACK.metrics,
      bands: {
        ...PACK.metrics.bands,
        'SK-04': {
          metric: 'window_respect_rate',
          band: 'window_respect_rate >= 0.9',
          verdict: 'pass',
          observed: 0.9009,
          seed_mean: 0.881,
          verdict_on_seed_mean: 'fail',
          agrees_across_seeds: false,
        },
      },
    },
  }

  it('discloses a second row when the packed-seed verdict and the 5-seed mean disagree', async () => {
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'static', user: null, pack: packWithDualVerdict })

    await screen.findByText('SK-04')
    // The packed-seed verdict still reads pass (upper-cased only by CSS)...
    const row = screen.getByText('SK-04').closest('tr')
    expect(row).toHaveTextContent('pass')
    // ...but the disclosed 5-seed mean is a second row, not silently dropped.
    const seedMeanRow = screen.getByText('↳ 5-seed mean').closest('tr')
    expect(seedMeanRow).toHaveTextContent('fail')
    expect(seedMeanRow).toHaveTextContent('0.881')
    // The header tally counts it as its own disclosed fail, separate from `fail`.
    expect(screen.getByText(/1 fail on 5-seed mean/)).toBeInTheDocument()
  })

  it('discloses the SK-04 five-seed fail from the committed five-seed pack', async () => {
    // The committed pack ran seeds 7–11: SK-04 passes on the packed seed (0.901)
    // and fails on the five-seed mean (0.881). The screen must show both.
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'static', user: null, pack: sanketData })
    await screen.findByText('SK-04')
    expect(sanketData.metrics.seeds.n).toBe(5)
    const seedMeanRow = screen.getByText('↳ 5-seed mean').closest('tr')
    expect(seedMeanRow).toHaveTextContent('fail')
  })
})

// SK-02 fails in PACK's bundled bands (`verdict: 'fail'`, no acceptance info — the pack
// never carries any). A live-mode acceptance overlay from GET /sanket/validation is the
// only thing that can mark it as accepted, and it must never launder it into a pass.
const ACCEPTED_VALIDATION = {
  report: { criteria: [] },
  criteria_states: { 'SK-01': 'pass', 'SK-02': 'accepted_failure', 'SK-03': 'not_measured' },
  accepted_failure_ids: ['SK-02'],
  accepted_failures: {
    accepted: ['SK-02'],
    criteria: [{
      id: 'SK-02',
      metric: 'precision_at_10',
      severity: 'high',
      status: 'fail',
      value: 0.21,
      threshold: 0.25,
      op: '>=',
      n: 12,
      detail: null,
      reason: 'Precision at the 10% budget is a real property of this model on this slice, disclosed and accepted for launch rather than tuned away.',
    }],
    still_blocking: [],
    listed_but_passing: [],
    listed_not_in_report: [],
    recorded_at: '2026-09-10T00:00:00Z',
    source: 'operator',
    note: null,
  },
  available: true,
  criteria_sha: 'sha-test',
  verify_result: 'ok',
  note: null,
}

const funnelRoute = jsonResponse(200, { data: FUNNEL, meta: { model_run_id: 'run-1', provenance_mode: 'fixture' } })

describe('ModelTrust — an accepted validation failure', () => {
  it('renders SK-02 as a failure, never a pass, and shows its reason', async () => {
    mockFetchRoutes({
      '/api/v1/sanket/funnel': funnelRoute,
      '/api/v1/sanket/validation': jsonResponse(200, { data: ACCEPTED_VALIDATION, meta: {} }),
    })
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'live', user: session('manager'), pack: PACK })

    const row = await screen.findByText('SK-02')
    const tr = row.closest('tr')
    expect(tr).toHaveTextContent('FAIL — ACCEPTED')
    expect(tr.textContent.toLowerCase()).not.toMatch(/\bpass\b/)

    // The reason is shown as a sub-row, not invented and not omitted.
    expect(await screen.findByText(/disclosed and accepted for launch/)).toBeInTheDocument()

    // The tally counts it as its own disclosed thing — PACK has exactly one genuine pass
    // (SK-01); if SK-02 had been folded into `pass` this would read "2 pass".
    expect(screen.getByText('1 pass')).toBeInTheDocument()
    expect(screen.getByText(/1 accepted failure/)).toBeInTheDocument()
  })
})

describe('ModelTrust — the validation table degrades cleanly without acceptance', () => {
  it('static mode never sees acceptance: SK-02 stays a plain, unaccepted fail', async () => {
    // Static mode has no live fetch at all — this is also the pre-existing behaviour this
    // change must not disturb.
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'static', user: null, pack: PACK })
    const row = await screen.findByText('SK-02')
    const tr = row.closest('tr')
    expect(tr).toHaveTextContent('fail')
    expect(tr).not.toHaveTextContent('ACCEPTED')
    expect(screen.getByText('1 pass')).toBeInTheDocument()
  })

  it('a failed /sanket/validation fetch leaves the table exactly as it renders without one', async () => {
    mockFetchRoutes({
      '/api/v1/sanket/funnel': funnelRoute,
      '/api/v1/sanket/validation': errorResponse(400, { code: 'bad_request', message: 'Malformed request.' }),
    })
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'live', user: session('manager'), pack: PACK })
    const row = await screen.findByText('SK-02')
    const tr = row.closest('tr')
    expect(tr).toHaveTextContent('fail')
    expect(tr).not.toHaveTextContent('ACCEPTED')
    expect(screen.getByText('1 pass')).toBeInTheDocument()
    // The rest of the screen survives too — the side-fetch failure never blanks it.
    expect(screen.getByRole('table', { name: /pre-registered validation criteria/i })).toBeInTheDocument()
  })

  it('a validation response with no acceptance fields leaves the table unchanged', async () => {
    mockFetchRoutes({
      '/api/v1/sanket/funnel': funnelRoute,
      '/api/v1/sanket/validation': jsonResponse(200, {
        data: {
          report: null, criteria_states: {}, accepted_failure_ids: [], accepted_failures: null,
          available: false, criteria_sha: null, verify_result: null, note: 'not run for this model run',
        },
        meta: {},
      }),
    })
    renderScreen(<ModelTrust />, { path: '/trust', mode: 'live', user: session('manager'), pack: PACK })
    const row = await screen.findByText('SK-02')
    const tr = row.closest('tr')
    expect(tr).toHaveTextContent('fail')
    expect(tr).not.toHaveTextContent('ACCEPTED')
    expect(screen.getByText('1 pass')).toBeInTheDocument()
  })
})
