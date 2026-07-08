import { useState } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { X, Copy, Check, MessageSquareQuote, Wallet, CalendarClock, Quote, Lightbulb } from 'lucide-react'
import { inr, pct, TIER, PRODUCT } from '../lib/fmt'

export default function LeadDrawer({ data, leadId, onClose }) {
  const [copied, setCopied] = useState(false)
  const rec = data.leads.find((r) => r.id === leadId)
  if (!rec) return null
  const t = TIER[rec.tier]
  const prod = PRODUCT[rec.product]

  const spark = rec.spark?.map((p, i) => ({ m: p.m, balance: p.bal, credits: p.cr }))

  const pitchText = [rec.pitch?.opener, rec.pitch?.why_now].filter(Boolean).join(' ')
  const copyPitch = () => {
    navigator.clipboard?.writeText(pitchText)
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-[680px] bg-ink-800 border-l border-line shadow-2xl overflow-y-auto scroll-thin">
        {/* header */}
        <div className="sticky top-0 z-10 bg-ink-700 border-b border-line px-5 py-4 flex items-start gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold">{rec.id}</h2>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${t.chip}`}>{t.label.toUpperCase()} · {prod.label}</span>
            </div>
            <div className="text-xs text-txt-lo mt-0.5 capitalize">
              {rec.segment}{rec.segment === 'gig' ? ' worker' : ''} · age {rec.age} · tier-{rec.city_tier} city · {Math.round(rec.tenure_m / 12)}y with the bank
            </div>
          </div>
          <div className="text-right">
            <div className={`text-2xl font-bold ${t.text} leading-none`}>{Math.round(rec.score * 100)}</div>
            <div className="text-[10px] text-txt-lo uppercase tracking-wide mt-1">blended score</div>
          </div>
          <button onClick={onClose} aria-label="Close briefing"
            className="text-txt-lo hover:text-txt-hi rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"><X size={20} /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* two scores */}
          <div className="grid grid-cols-2 gap-3">
            {[['Intent', rec.intent, 'does the need exist?'], ['Capacity', rec.capacity, 'can they repay comfortably?']].map(([label, v, hint]) => (
              <div key={label} className="bg-ink-700 border border-line rounded-xl p-3.5">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-txt-lo uppercase tracking-wide">{label}</span>
                  <span className="text-lg font-bold text-txt-hi">{Math.round(v * 100)}<span className="text-txt-lo text-xs">/100</span></span>
                </div>
                <div className="h-1.5 bg-ink-900 rounded-full mt-2 overflow-hidden">
                  <div className={`h-full rounded-full ${label === 'Intent' ? 'bg-signal-teal' : 'bg-signal-amber'}`} style={{ width: `${v * 100}%` }} />
                </div>
                <div className="text-[10px] text-txt-lo mt-1.5">{hint}</div>
              </div>
            ))}
          </div>

          {/* signal sparkline */}
          {spark?.length > 0 && (
            <section className="bg-ink-700 border border-line rounded-xl p-4">
              <h3 className="font-bold text-sm mb-1">The signals, month by month</h3>
              <p className="text-xs text-txt-lo mb-3">Average balance building while monthly credits hold steady — classic pre-purchase behaviour.</p>
              <ResponsiveContainer width="100%" height={170}>
                <ComposedChart data={spark} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" />
                  <XAxis dataKey="m" tick={{ fontSize: 9, fill: '#6B7399' }} interval={5} />
                  <YAxis tick={{ fontSize: 9, fill: '#6B7399' }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                  <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                           formatter={(v, n) => [inr(v), n]} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Area type="monotone" dataKey="balance" name="Avg balance" stroke="#2DD4BF" strokeWidth={2} fill="#2DD4BF" fillOpacity={0.08} isAnimationActive={false} />
                  <Line type="monotone" dataKey="credits" name="Monthly credits" stroke="#F5A623" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </section>
          )}

          {/* reasons */}
          <section className="bg-ink-700 border border-line rounded-xl p-4">
            <h3 className="font-bold text-sm mb-2.5">Why SANKET flagged this customer</h3>
            <div className="space-y-2">
              {rec.reasons.map((r, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm">
                  <span className="w-5 h-5 grid place-items-center rounded bg-signal-amber/15 text-signal-amber text-[11px] font-bold shrink-0 mt-0.5">{i + 1}</span>
                  <span className="text-txt-mid">{r}</span>
                </div>
              ))}
            </div>
          </section>

          {/* retained income / safe EMI */}
          <section className="bg-ink-700 border border-line rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2.5">
              <Wallet size={15} className="text-signal-teal" />
              <h3 className="font-bold text-sm">Retained-income check <span className="text-txt-lo font-normal">(supports prudent underwriting)</span></h3>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-ink-800 rounded-lg border border-line p-3">
                <div className="text-base font-bold">{inr(rec.salary_m)}</div>
                <div className="text-[10px] text-txt-lo">median monthly credits</div>
              </div>
              <div className="bg-ink-800 rounded-lg border border-line p-3">
                <div className="text-base font-bold">{inr(rec.retained_income)}</div>
                <div className="text-[10px] text-txt-lo">retained after committed outflows</div>
              </div>
              <div className="bg-ink-800 rounded-lg border border-line p-3">
                <div className="text-base font-bold text-signal-teal">{inr(rec.safe_emi)}</div>
                <div className="text-[10px] text-txt-lo">comfortable EMI headroom</div>
              </div>
            </div>
            <p className="text-[11px] text-txt-lo mt-2.5">
              Estimated from observed account behaviour (credit rhythm minus rent, EMIs, school fees and essential spend) —
              behavioural income, not just declared income. Final eligibility remains with credit policy.
            </p>
          </section>

          {/* pitch script */}
          <section className="bg-ink-700 border border-line rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2.5">
              <MessageSquareQuote size={15} className="text-signal-amber" />
              <h3 className="font-bold text-sm flex-1">Suggested opening — grounded in the data</h3>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-line text-txt-mid" title="Script language matched to the customer's preference">
                {rec.lang === 'hi' ? 'हिन्दी' : 'EN'}
              </span>
              <button onClick={copyPitch} className="flex items-center gap-1 text-xs text-txt-lo hover:text-signal-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber rounded">
                {copied ? <Check size={13} /> : <Copy size={13} />}{copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <div className="bg-ink-800 border border-line rounded-lg p-3.5 text-sm text-txt-mid leading-relaxed">
              “{rec.pitch.opener}” <br />
              <span className="text-txt-lo">then:</span> “{rec.pitch.why_now}”
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {rec.pitch.proof.map((p, i) => (
                <span key={i} className="text-[10px] bg-ink-600 border border-line text-txt-mid px-2 py-0.5 rounded-full">◈ {p}</span>
              ))}
            </div>
            <p className="text-[10px] text-txt-lo mt-2">Every claim in the script traces to a chip above — no generated facts.</p>
          </section>

          {/* objection + NBA */}
          <div className="grid sm:grid-cols-2 gap-3">
            <section className="bg-ink-700 border border-line rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2"><Quote size={14} className="text-signal-rose" /><h3 className="font-bold text-sm">Likely objection</h3></div>
              <div className="text-sm text-txt-mid italic">“{rec.objection.q}”</div>
              <div className="text-sm text-txt-mid mt-2 flex items-start gap-1.5"><Lightbulb size={14} className="text-signal-amber shrink-0 mt-0.5" />{rec.objection.a}</div>
            </section>
            <section className="bg-ink-700 border border-line rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2"><CalendarClock size={14} className="text-signal-teal" /><h3 className="font-bold text-sm">Next best action</h3></div>
              <div className="text-sm text-txt-mid leading-relaxed">{rec.nba}</div>
            </section>
          </div>

          <p className="text-[10px] text-txt-lo pb-2">
            SANKET advises; the relationship manager decides. This customer has active marketing consent on record.
          </p>
        </div>
      </div>
    </div>
  )
}
