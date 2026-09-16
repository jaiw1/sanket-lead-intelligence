import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import ModelTrust from './ModelTrust'
import { renderScreen } from '../test/render'
import { PACK } from '../test/fixtures/sanket'
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
