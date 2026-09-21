import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import ManagerDashboard from './ManagerDashboard'
import { renderScreen, session } from '../test/render'
import { jsonResponse, mockFetchRoutes } from '../test/http'
import { FUNNEL, LEGACY_PACK, PACK } from '../test/fixtures/sanket'

const funnelRoute = (data = FUNNEL, meta = { model_run_id: 'run-1', provenance_mode: 'fixture' }) =>
  mockFetchRoutes({ '/api/v1/sanket/funnel': jsonResponse(200, { data, meta }) })

describe('ManagerDashboard — the headline', () => {
  it('computes "N → M disbursements per 100 RM calls" from the two measured rates', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })

    const headline = await screen.findByTestId('headline')
    // 9% random baseline, 30% at the top-10% budget — both from published_metrics.
    expect(headline).toHaveTextContent('9')
    expect(headline).toHaveTextContent('30')
    expect(headline).toHaveTextContent(/disbursements per 100 RM calls/)
    expect(await screen.findByText(/3\.3×/)).toBeInTheDocument()
  })

  it('shows the confidence interval beside the precision, not just the point estimate', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByText(/95% CI 15\.0%–50\.0%/)).toBeInTheDocument()
  })

  it('refuses to quote a lift when the random baseline is zero', async () => {
    funnelRoute({
      ...FUNNEL,
      published_metrics: {
        ...FUNNEL.published_metrics,
        baseline_dropoff_disbursement: { n: 120, value: 0, ci_low: 0, ci_high: 0.031 },
      },
    })
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByText(/no multiple to quote/i)).toBeInTheDocument()
    expect(screen.queryByText(/×/)).not.toBeInTheDocument()
  })

  it('says which keys it wanted when neither rate is published', async () => {
    funnelRoute({ ...FUNNEL, published_metrics: { note: 'nothing measured' } })
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    const absent = await screen.findAllByTestId('not-in-build')
    expect(absent.length).toBeGreaterThan(0)
    expect(screen.getByText(/baseline_dropoff_disbursement/)).toBeInTheDocument()
  })
})

describe('ManagerDashboard — the panels', () => {
  it('shows the KPI row, including the suppressed count as a share of the book', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByTestId('kpi-leads')).toHaveTextContent('120')
    expect(screen.getByTestId('kpi-suppressed')).toHaveTextContent('83')
    expect(screen.getByTestId('kpi-suppressed')).toHaveTextContent('69% of the book')
    expect(screen.getByTestId('kpi-window-open')).toHaveTextContent('14')
  })

  it('renders all six products in the mix, in contract order', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    await screen.findByTestId('kpi-leads')
    // recharts does not render in jsdom, so the accessible data table is what proves it.
    const table = screen.getByRole('table', { name: /leads by product/i })
    const rows = table.querySelectorAll('tbody tr th')
    expect([...rows].map((r) => r.textContent)).toEqual([
      'Personal Loan', 'Gold Loan', 'Auto Loan', 'Education Loan', 'Home Loan', 'Loan Against Property',
    ])
  })

  it('splits the SLA into open, closed and no-window', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByText(/window open — call now/i)).toBeInTheDocument()
    expect(screen.getByText(/38% of the book is still inside its window/)).toBeInTheDocument()
  })

  it('shows the suppression histogram with a label per reason', async () => {
    funnelRoute()
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByText('Called too often recently')).toBeInTheDocument()
    expect(screen.getByText('On the DND registry')).toBeInTheDocument()
    expect(screen.getByText('No marketing consent (DPDP)')).toBeInTheDocument()
  })

  it('says so rather than drawing an empty chart when a panel’s data is absent', async () => {
    funnelRoute({ ...FUNNEL, sla: null, product_mix: null, rm_load: [] })
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    await screen.findByTestId('kpi-leads')
    expect(screen.getByText(/The window split is not in this build/)).toBeInTheDocument()
    expect(screen.getByText(/The product mix is not in this build/)).toBeInTheDocument()
    expect(screen.getByText(/Nothing has been assigned yet/)).toBeInTheDocument()
  })
})

describe('ManagerDashboard — the four states', () => {
  it('renders permission-denied on a 403 from the data call, not a crash', async () => {
    mockFetchRoutes({
      '/api/v1/sanket/funnel': jsonResponse(403, { error: { code: 'forbidden', message: 'Not yours.' } }),
    })
    renderScreen(<ManagerDashboard />, { path: '/dashboard', user: session('relationship_manager') })
    expect(await screen.findByTestId('state-denied')).toBeInTheDocument()
  })

  it('renders an error state with a retry on a 500', async () => {
    mockFetchRoutes({
      '/api/v1/sanket/funnel': jsonResponse(500, { error: { code: 'server_error', message: 'Boom.', request_id: 'req-9' } }),
    })
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByTestId('state-error')).toBeInTheDocument()
    expect(screen.getByText('req-9')).toBeInTheDocument()
  })

  it('says nothing is published rather than showing zeros', async () => {
    funnelRoute({ published: false })
    renderScreen(<ManagerDashboard />, { path: '/dashboard' })
    expect(await screen.findByText(/A published SANKET model run is not in this build/)).toBeInTheDocument()
  })
})

describe('ManagerDashboard — static mode', () => {
  it('derives the dashboard from the bundled export when no backend answered', async () => {
    renderScreen(<ManagerDashboard />, { path: '/dashboard', mode: 'static', user: null, pack: PACK })
    expect(await screen.findByTestId('headline')).toHaveTextContent('30')
    expect(screen.getByTestId('kpi-suppressed')).toHaveTextContent('83')
  })

  it('divides the suppressed count by the pool it was measured over, not by the bundled sample size', async () => {
    // Regression test for a real bug: PACK.metrics.suppression.suppressed_count (83) is a
    // full-pool figure, but PACK only bundles one bundled lead row. Dividing 83 by the
    // sample's `leads.length` (1) used to render "8300% of the book" here — in production,
    // with real numbers, that was the "560%" the Manager Dashboard actually shipped.
    // `funnelFromPack` now exposes the pool that count was measured over
    // (`metrics.suppression.pool_at_snapshot`, 830 in this fixture) as its own field, and
    // this is what the percentage must divide by instead: 83 / 830 = 10%.
    renderScreen(<ManagerDashboard />, { path: '/dashboard', mode: 'static', user: null, pack: PACK })
    const suppressedCard = await screen.findByTestId('kpi-suppressed')
    expect(suppressedCard).toHaveTextContent('83')
    expect(suppressedCard).toHaveTextContent('10% of the book')
    expect(suppressedCard).not.toHaveTextContent('560%')
    expect(suppressedCard).not.toHaveTextContent('8300%')
  })

  it('survives a pre-SM-1 export with none of the new keys', async () => {
    renderScreen(<ManagerDashboard />, { path: '/dashboard', mode: 'static', user: null, pack: LEGACY_PACK })
    await waitFor(() => expect(screen.getAllByTestId('not-in-build').length).toBeGreaterThan(0))
    // A missing suppressed count is an em dash, never a confident zero.
    expect(screen.getByTestId('kpi-suppressed')).toHaveTextContent('—')
  })
})
