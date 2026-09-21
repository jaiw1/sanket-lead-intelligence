import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList, Cell,
} from 'recharts'
import { Radar as RadarIcon, BadgeCheck, TrendingUp } from 'lucide-react'


export default function BusinessRadar({ radar }) {
  if (!radar) return (
    <div className="bg-ink-700 border border-line rounded-xl p-6 text-sm text-txt-mid">
      Business Radar data not loaded.
    </div>
  )

  const sectors = radar.sectors.map((s) => ({ ...s, headroomPct: Math.round(s.share_headroom * 100) }))

  return (
    <div className="space-y-5">
      <section className="bg-signal-amber/5 border border-signal-amber/30 rounded-xl p-5">
        <div className="flex items-center gap-2 text-signal-amber mb-2">
          <BadgeCheck size={18} /><h3 className="font-bold text-lg">Business Radar — an illustrative exhibit on real filings</h3>
        </div>
        <p className="text-sm text-txt-mid leading-relaxed max-w-4xl">
          A hand-weighted financial-ratio screen over <b>{radar.meta.n_companies_str} real Indian businesses'</b> annual
          financials: growing income, comfortable interest cover and unused borrowing headroom mark a business that may be
          <b> ready for working capital</b>. It is <b>not</b> SANKET's model and does not validate it — different features,
          different label, different population.
        </p>
        <p className="text-xs text-signal-amber/90 mt-2 leading-relaxed max-w-4xl">{radar.meta.caveat}</p>
        <p className="text-xs text-txt-lo mt-2">{radar.meta.desc}</p>
      </section>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-ink-700 border border-line rounded-xl p-4">
          <div className="text-2xl font-bold text-signal-teal">{radar.meta.n_companies_str}</div>
          <div className="text-sm font-semibold mt-0.5">Real businesses screened</div>
          <div className="text-xs text-txt-lo">real published financial statements</div>
        </div>
        <div className="bg-ink-700 border border-line rounded-xl p-4">
          <div className="text-2xl font-bold text-txt-hi">{radar.meta.n_prospects.toLocaleString('en-IN')}</div>
          <div className="text-sm font-semibold mt-0.5">Radar prospects</div>
          <div className="text-xs text-txt-lo">clean history + credit headroom</div>
        </div>
        <div className="bg-ink-700 border border-line rounded-xl p-4">
          <div className="text-2xl font-bold text-signal-amber">{radar.backtest.top_multiple.toFixed(2)}×</div>
          <div className="text-sm font-semibold mt-0.5">Backtest lift, point-in-time</div>
          <div className="text-xs text-txt-lo">
            top-decile companies raised borrowings from some lender the following year at this multiple of the rest
            {radar.backtest.company_clustered_ci
              ? ` (95% company-clustered ${radar.backtest.company_clustered_ci.ci_low}–${radar.backtest.company_clustered_ci.ci_high}×)`
              : ''}
            {radar.backtest.lookahead_top_multiple
              ? `. The same calculation with the look-ahead this exhibit used to carry reads ${radar.backtest.lookahead_top_multiple.toFixed(2)}×.`
              : ''}
          </div>
        </div>
        <div className="bg-ink-700 border border-line rounded-xl p-4">
          <div className="text-2xl font-bold text-txt-hi">{radar.meta.years}</div>
          <div className="text-sm font-semibold mt-0.5">Evaluation years</div>
          <div className="text-xs text-txt-lo">each scored using only the filings that existed at the time</div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <h3 className="font-bold text-sm">Where the headroom sits, by sector</h3>
          <p className="text-xs text-txt-lo mt-1 mb-4">Share of each sector's screened businesses with genuine borrowing headroom — where a business-banking RM should hunt.</p>
          <div
            role="img"
            aria-label={`Share of each sector's screened businesses with borrowing headroom: ${sectors.map((d) => `${d.sector} ${d.headroomPct}%`).join(', ')}.`}
          >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={sectors} layout="vertical" margin={{ top: 0, right: 36, left: 30, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6B7399' }} unit="%" />
              <YAxis type="category" dataKey="sector" tick={{ fontSize: 11, fill: '#A7AFD4' }} width={110} />
              <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                       formatter={(v) => [`${v}%`, 'with headroom']} />
              <Bar dataKey="headroomPct" radius={[0, 5, 5, 0]} isAnimationActive={false}>
                <LabelList dataKey="headroomPct" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: '#EAEDFB' }} />
                {sectors.map((d, i) => <Cell key={i} fill={i % 2 ? '#2DD4BF' : '#F5A623'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
        </section>

        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <div className="flex items-center gap-2 mb-1"><TrendingUp size={15} className="text-signal-amber" /><h3 className="font-bold text-sm">Did the radar predict borrowing, point-in-time?</h3></div>
          <p className="text-xs text-txt-lo mt-1 mb-4">
            Each year is scored using only filings up to that year, and only companies with no default dated on or
            before it; deciles are cut within the year. Businesses in the top decile raised borrowings the following
            year more often than the rest.
          </p>
          <div
            role="img"
            aria-label={`Share raising borrowings the following financial year, by score decile: ${radar.backtest.deciles.map((d) => `decile ${d.decile} ${d.jump_rate_pct}%`).join(', ')}.`}
          >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={radar.backtest.deciles} margin={{ top: 18, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" />
              <XAxis dataKey="decile" tick={{ fontSize: 10, fill: '#6B7399' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6B7399' }} unit="%" />
              <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                       formatter={(v) => [`${v}%`, 'raised borrowings next FY']} />
              <Bar dataKey="jump_rate_pct" radius={[5, 5, 0, 0]} isAnimationActive={false}>
                <LabelList dataKey="jump_rate_pct" position="top" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: '#EAEDFB' }} />
                {radar.backtest.deciles.map((d, i) => <Cell key={i} fill={i >= 8 ? '#2DD4BF' : '#3A466F'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="bg-ink-700 border border-line rounded-xl overflow-hidden">
        <div className="p-4 border-b border-line flex items-center gap-2">
          <RadarIcon size={15} className="text-signal-teal" />
          <h3 className="font-bold text-sm">Radar picks — real businesses, anonymised</h3>
          <span className="text-xs text-txt-lo">(real financial ratios & real next-year outcomes)</span>
        </div>
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full text-sm">
            <thead className="bg-ink-800 text-xs text-txt-lo">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Prospect</th>
                <th className="text-left px-4 py-2 font-semibold">Sector</th>
                <th className="text-right px-4 py-2 font-semibold">Income growth</th>
                <th className="text-right px-4 py-2 font-semibold">Interest cover</th>
                <th className="text-right px-4 py-2 font-semibold">Borrowings ÷ income</th>
                <th className="text-right px-4 py-2 font-semibold">Radar score</th>
                <th className="text-left px-4 py-2 font-semibold">Why</th>
              </tr>
            </thead>
            <tbody>
              {radar.prospects.map((e) => (
                <tr key={e.id} className="border-t border-ink-600/40">
                  <td className="px-4 py-2.5 font-semibold text-txt-hi">{e.id}</td>
                  <td className="px-4 py-2.5 text-txt-mid">{e.sector}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-signal-teal">+{Math.round(e.income_cagr * 100)}%/yr</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{e.interest_cover ?? '—'}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{e.borrow_to_income}</td>
                  <td className="px-4 py-2.5 text-right font-bold text-signal-amber tabular-nums">{Math.round(e.score * 100)}</td>
                  <td className="px-4 py-2.5 text-txt-mid max-w-[260px] truncate">{e.reasons?.[0]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {Array.isArray(radar.backtest.by_year) && radar.backtest.by_year.length > 0 && (
        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <h3 className="font-bold text-sm">Year by year, and the trend</h3>
          <p className="text-xs text-txt-lo mt-1 mb-3">
            An expanding window: every year is ranked against the filings that preceded it. A pooled number can hide a
            drift, so each year is published.
          </p>
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full text-xs">
              <caption className="sr-only">Top-decile borrowing lift by evaluation year</caption>
              <thead>
                <tr className="text-left text-txt-lo">
                  <th scope="col" className="py-1.5 pr-3 font-semibold">Year scored</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">Companies</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">Top decile</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">The rest</th>
                  <th scope="col" className="py-1.5 text-right font-semibold">Lift</th>
                </tr>
              </thead>
              <tbody>
                {radar.backtest.by_year.map((r) => (
                  <tr key={r.year} className="border-t border-line">
                    <th scope="row" className="py-1.5 pr-3 text-left font-medium text-txt-mid">{r.year}</th>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-txt-lo">{r.n.toLocaleString('en-IN')}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{Math.round(r.top_decile_rate * 100)}%</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{Math.round(r.rest_rate * 100)}%</td>
                    <td className="py-1.5 text-right font-bold tabular-nums text-signal-amber">{r.multiple.toFixed(2)}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="text-[11px] text-txt-lo">
        Sector-level aggregates and anonymised exemplars from real Indian companies' published annual financials and credit-rating histories; only derived aggregates ship with this app.
        Businesses are screened out of a given year only if they had already defaulted by that year — a company that defaults later is still a prospect at the earlier date, which is what makes this a backtest rather than a hindsight ranking.
      </p>
    </div>
  )
}
