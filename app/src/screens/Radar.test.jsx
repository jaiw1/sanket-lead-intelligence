import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import Radar from './Radar'
import { renderScreen } from '../test/render'
import { jsonResponse, mockFetchRoutes } from '../test/http'
import { publicPath } from '../lib/basepath'
import radarData from '../../public/radar_data.json'

const radarRoute = (data = radarData) =>
  mockFetchRoutes({ [publicPath('radar_data.json')]: jsonResponse(200, data) })

describe('Radar — what the backtest date means', () => {
  it('dates the rebuild, rather than dating point-in-time-ness itself', async () => {
    radarRoute()
    renderScreen(<Radar />, { path: '/radar' })
    // "point-in-time, since 21 September 2026" read as though the backtest only became
    // point-in-time on that date. 21 September is when the look-ahead was corrected.
    expect(await screen.findByText(/The backtest was rebuilt point-in-time on 21 September 2026\./)).toBeInTheDocument()
    expect(screen.queryByText(/point-in-time, since 21 September 2026/)).not.toBeInTheDocument()
  })
})

describe('Radar — one precision per column in the prospect table', () => {
  it('prints interest cover and borrowing ratio at a fixed number of places', async () => {
    radarRoute()
    renderScreen(<Radar />, { path: '/radar' })
    // The prospect table carries no caption, so it is found by a column only it has.
    const table = (await screen.findByRole('columnheader', { name: 'Interest cover' })).closest('table')
    const rows = [...table.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent))
    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      // Printed straight from JSON, 28.0 arrived as "28" beside "23.2" and 0.20 as "0.2"
      // beside "0.18" — one column, two precisions.
      expect(row[3]).toMatch(/^\d+\.\d$|^—$/)
      expect(row[4]).toMatch(/^\d+\.\d{2}$|^—$/)
    }
  })

  it('still shows an em dash for a prospect with no interest cover', async () => {
    radarRoute({
      ...radarData,
      prospects: [{ ...radarData.prospects[0], interest_cover: null, borrow_to_income: null }],
    })
    renderScreen(<Radar />, { path: '/radar' })
    const table = (await screen.findByRole('columnheader', { name: 'Interest cover' })).closest('table')
    const cells = [...table.querySelectorAll('tbody tr')[0].children].map((td) => td.textContent)
    expect(cells[3]).toBe('—')
    expect(cells[4]).toBe('—')
  })
})
