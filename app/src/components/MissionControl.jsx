import { useState, useMemo } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { pct, inr, TIER } from '../lib/fmt'
import { Flame, Users, PhoneOutgoing, ShieldCheck, ArrowRight } from 'lucide-react'

function Kpi({ icon: Icon, value, label, hint, tone = 'text-txt-hi' }) {
  return (
    <div className="bg-ink-700 border border-line rounded-xl p-4">
      <div className="flex items-center gap-2 text-txt-lo text-[11px] uppercase tracking-wider mb-1"><Icon size={14} /> {label}</div>
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-xs text-txt-lo mt-0.5">{hint}</div>
    </div>
  )
}

export default function MissionControl({ data, goQueue }) {
  const m = data.metrics.blended
  const meta = data.meta
  const counts = data.counts
  const [budget, setBudget] = useState(0.05)

  const point = useMemo(() => {
    let best = m.prec_curve[0]
    for (const p of m.prec_curve) if (Math.abs(p.budget - budget) < Math.abs(best.budget - budget)) best = p
    return best
  }, [m, budget])

  const curve = m.prec_curve.map((p) => ({ ...p, budgetPct: +(p.budget * 100).toFixed(1), precPct: +(p.precision * 100).toFixed(1) }))

  return (
    <div className="space-y-5">
      {/* headline */}
      <section className="bg-gradient-to-r from-ink-700 to-ink-800 border border-line rounded-2xl p-5 sm:p-6">
        <div className="text-[11px] uppercase tracking-widest text-signal-amber font-bold mb-2">the conversion problem</div>
        <h2 className="text-xl sm:text-2xl font-bold leading-snug max-w-3xl">
          Cold outreach converts <span className="text-signal-rose">~{pct(m.baseline, 1)}</span> of calls.
          SANKET's top-{pct(point.budget)} queue converts <span className="text-signal-teal">{pct(point.precision, 1)}</span> —
          a <span className="text-signal-amber">{point.lift.toFixed(0)}× lift</span>, measured on held-out customers.
        </h2>
        <p className="text-sm text-txt-mid mt-2 max-w-3xl">
          Every transaction on the liability book is a signal. SANKET reads them — salary rhythm, rent step-ups, fuel spend,
          balance build-ups — and ranks who is ready for which loan, with the reason in plain English.
        </p>
        <button onClick={goQueue} className="mt-4 inline-flex items-center gap-2 bg-signal-amber text-ink-900 font-bold text-sm rounded-lg px-4 py-2 hover:bg-signal-amber/90 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
          Open the lead queue <ArrowRight size={15} />
        </button>
      </section>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi icon={Users} value={meta.n_customers.toLocaleString('en-IN')} label="Liability customers" hint={`${meta.n_consented.toLocaleString('en-IN')} with marketing consent`} />
        <Kpi icon={Flame} value={counts.hot.toLocaleString('en-IN')} label="Hot leads" hint="ready-now conversations" tone="text-signal-teal" />
        <Kpi icon={PhoneOutgoing} value={pct(point.precision, 1)} label={`Precision @ top ${pct(point.budget)}`} hint={`vs ${pct(m.baseline, 1)} cold-call baseline`} tone="text-signal-amber" />
        <Kpi icon={ShieldCheck} value={counts.no_consent.toLocaleString('en-IN')} label="Excluded — no consent" hint="never queued, by design" />
      </div>

      {/* budget slider + curve */}
      <section className="bg-ink-700 border border-line rounded-xl p-5">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-1">
          <div>
            <h3 className="font-bold">Choose your calling capacity — see the conversion economics</h3>
            <p className="text-xs text-txt-lo mt-0.5">Precision falls as you call deeper into the book. That honest trade-off is the product.</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-signal-amber">{pct(point.precision, 1)}</div>
            <div className="text-[11px] text-txt-lo">expected conversion at top {pct(point.budget)}</div>
          </div>
        </div>
        <div className="flex items-center gap-4 my-4">
          <span className="text-xs text-txt-mid whitespace-nowrap">Contact top</span>
          <input type="range" min={1} max={30} step={1} value={Math.round(budget * 100)}
                 onChange={(e) => setBudget(+e.target.value / 100)} className="flex-1 cursor-pointer" />
          <span className="text-sm font-bold text-txt-hi w-12 text-right">{pct(budget)}</span>
        </div>
        <div className="grid sm:grid-cols-3 gap-3 mb-4 text-center">
          <div className="bg-ink-800 rounded-lg border border-line p-3">
            <div className="text-lg font-bold">{point.contacts.toLocaleString('en-IN')}</div>
            <div className="text-[11px] text-txt-lo">customers contacted / month</div>
          </div>
          <div className="bg-ink-800 rounded-lg border border-line p-3">
            <div className="text-lg font-bold text-signal-teal">{point.expected_conversions.toLocaleString('en-IN')}</div>
            <div className="text-[11px] text-txt-lo">expected loan conversations that land</div>
          </div>
          <div className="bg-ink-800 rounded-lg border border-line p-3">
            <div className="text-lg font-bold text-signal-amber">{point.lift.toFixed(1)}×</div>
            <div className="text-[11px] text-txt-lo">lift over random cold-calling</div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={230}>
          <ComposedChart data={curve} margin={{ top: 8, right: 10, left: -14, bottom: 2 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" />
            <XAxis dataKey="budgetPct" tick={{ fontSize: 10, fill: '#6B7399' }} unit="%" type="number" domain={[1, 30]} ticks={[1, 5, 10, 15, 20, 25, 30]} />
            <YAxis tick={{ fontSize: 10, fill: '#6B7399' }} unit="%" />
            <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                     labelFormatter={(l) => `top ${l}% of book`} formatter={(v, n) => [`${v}%`, n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={+(m.baseline * 100).toFixed(1)} stroke="#FB7185" strokeDasharray="4 4"
                           label={{ value: `cold-call baseline ${(m.baseline * 100).toFixed(1)}%`, fontSize: 10, fill: '#FB7185', position: 'insideBottomRight' }} />
            <ReferenceLine x={+(budget * 100).toFixed(0)} stroke="#F5A623" strokeDasharray="5 3" />
            <Area type="monotone" dataKey="precPct" name="Conversion rate at budget" stroke="#2DD4BF" strokeWidth={2.5}
                  fill="#2DD4BF" fillOpacity={0.08} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="text-[11px] text-txt-lo mt-2">
          Measured as precision@budget on a held-out test cohort of the synthetic book (engineered to the bank-stated ~1% cold baseline).
          Numbers recalibrate on real data in the sandbox phase — the machinery, not the exact figure, is the claim.
        </p>
      </section>

      {/* how it works strip */}
      <section className="grid sm:grid-cols-4 gap-3">
        {[
          ['1 · Signals', 'salary rhythm, rent & fuel spend, balance build-up, FD breaks, app dwell'],
          ['2 · Two scores', 'intent (does the need exist?) × capacity (can they repay comfortably?)'],
          ['3 · Ranked queue', 'hot / warm / cold per product, consent-screened before anything is queued'],
          ['4 · RM handoff', 'reasons, retained-income check, pitch script and next-best-action — one screen'],
        ].map(([t, d]) => (
          <div key={t} className="bg-ink-700 border border-line rounded-xl p-4">
            <div className="text-sm font-bold text-signal-amber mb-1">{t}</div>
            <div className="text-xs text-txt-mid leading-relaxed">{d}</div>
          </div>
        ))}
      </section>
    </div>
  )
}
