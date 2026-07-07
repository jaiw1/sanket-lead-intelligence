import { useState, useMemo } from 'react'
import { pct, inr, TIER, PRODUCT } from '../lib/fmt'
import { Search, ArrowUpDown, ShieldOff, ChevronRight } from 'lucide-react'

const TIERS = ['all', 'hot', 'warm', 'cold']

export default function LeadQueue({ data, onSelect }) {
  const [tier, setTier] = useState('hot')
  const [product, setProduct] = useState('all')
  const [q, setQ] = useState('')
  const [showNoConsent, setShowNoConsent] = useState(true)
  const [sortKey, setSortKey] = useState('score')
  const [asc, setAsc] = useState(false)

  const view = useMemo(() => {
    let r = data.leads
    if (tier !== 'all') r = r.filter((x) => x.tier === tier)
    if (product !== 'all') r = r.filter((x) => x.product === product)
    if (q) r = r.filter((x) => x.id.toLowerCase().includes(q.toLowerCase()) || x.segment.toLowerCase().includes(q.toLowerCase()))
    if (!showNoConsent) r = r.filter((x) => x.consent)
    return [...r].sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey]
      const c = typeof va === 'string' ? va.localeCompare(vb) : va - vb
      return asc ? c : -c
    })
  }, [data, tier, product, q, showNoConsent, sortKey, asc])

  const noConsentCount = data.counts.no_consent
  const setSort = (k) => { if (k === sortKey) setAsc(!asc); else { setSortKey(k); setAsc(false) } }
  const Th = ({ k, children, right }) => (
    <th className={`px-3 py-2 font-semibold text-txt-lo ${right ? 'text-right' : 'text-left'} cursor-pointer select-none whitespace-nowrap`}
        onClick={() => setSort(k)}>
      <span className={`inline-flex items-center gap-1 ${right ? 'flex-row-reverse' : ''}`}>{children}<ArrowUpDown size={11} className="opacity-40" /></span>
    </th>
  )

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-bold">Lead Queue</h2>
          <p className="text-xs text-txt-lo">Ranked by blended intent × capacity. Click a lead for the full call briefing.</p>
        </div>
        <div className="flex items-center gap-2 text-xs bg-ink-700 border border-line rounded-lg px-3 py-2">
          <ShieldOff size={13} className="text-txt-lo" />
          <span className="text-txt-mid"><b className="text-txt-hi">{noConsentCount.toLocaleString('en-IN')}</b> customers excluded — no marketing consent</span>
        </div>
      </div>

      <div className="bg-ink-700 border border-line rounded-xl overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 p-3 border-b border-line">
          <div className="flex gap-1 bg-ink-800 rounded-lg p-1">
            {TIERS.map((t) => (
              <button key={t} onClick={() => setTier(t)}
                className={`px-3 py-1 text-sm rounded-md font-medium capitalize transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber ${tier === t ? 'bg-ink-600 text-txt-hi' : 'text-txt-lo hover:text-txt-mid'}`}>
                {t}
              </button>
            ))}
          </div>
          <select value={product} onChange={(e) => setProduct(e.target.value)}
            className="text-sm bg-ink-800 border border-line rounded-lg px-2.5 py-1.5 text-txt-mid cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
            <option value="all">All products</option>
            {Object.entries(PRODUCT).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-txt-mid cursor-pointer select-none">
            <input type="checkbox" checked={showNoConsent} onChange={(e) => setShowNoConsent(e.target.checked)} className="accent-signal-amber" />
            show excluded rows
          </label>
          <div className="text-xs text-txt-lo">{view.length} leads</div>
          <div className="ml-auto relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-txt-lo" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search id / segment"
              className="pl-8 pr-3 py-1.5 text-sm bg-ink-800 border border-line rounded-lg w-52 text-txt-hi placeholder:text-txt-lo focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber" />
          </div>
        </div>

        <div className="max-h-[560px] overflow-auto scroll-thin">
          <table className="w-full text-sm">
            <thead className="bg-ink-800 sticky top-0 z-10 text-xs">
              <tr>
                <Th k="id">Customer</Th>
                <Th k="segment">Segment</Th>
                <Th k="product">Next-best product</Th>
                <Th k="intent" right>Intent</Th>
                <Th k="capacity" right>Capacity</Th>
                <Th k="score" right>Blended</Th>
                <th className="px-3 py-2 text-left font-semibold text-txt-lo">Top signal</th>
                <th className="w-6" />
              </tr>
            </thead>
            <tbody>
              {view.map((r) => {
                const t = TIER[r.tier]
                if (!r.consent) return (
                  <tr key={r.id} className="border-t border-ink-600/40 opacity-45 select-none">
                    <td className="px-3 py-2.5 font-semibold text-txt-mid">{r.id}</td>
                    <td className="px-3 py-2.5 text-txt-lo capitalize">{r.segment}</td>
                    <td className="px-3 py-2.5 text-txt-lo italic" colSpan={5}>not queued — no marketing consent (DPDP)</td>
                    <td />
                  </tr>
                )
                return (
                  <tr key={r.id} onClick={() => onSelect(r.id)}
                      className="border-t border-ink-600/40 hover:bg-ink-600/30 cursor-pointer">
                    <td className="px-3 py-2.5">
                      <span className={`inline-block w-1.5 h-4 rounded-sm mr-2 align-middle ${r.tier === 'hot' ? 'bg-signal-teal' : r.tier === 'warm' ? 'bg-signal-amber' : 'bg-ink-500'}`} />
                      <span className="font-semibold text-txt-hi">{r.id}</span>
                    </td>
                    <td className="px-3 py-2.5 text-txt-mid capitalize">{r.segment}{r.segment === 'gig' ? ' worker' : ''}</td>
                    <td className="px-3 py-2.5">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${t.chip}`}>{PRODUCT[r.product].label}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-txt-hi">{Math.round(r.intent * 100)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-txt-hi">{Math.round(r.capacity * 100)}</td>
                    <td className={`px-3 py-2.5 text-right font-bold tabular-nums ${t.text}`}>{Math.round(r.score * 100)}</td>
                    <td className="px-3 py-2.5 text-txt-mid max-w-[300px] truncate">{r.reasons?.[0] || '—'}</td>
                    <td className="py-2.5 text-txt-lo"><ChevronRight size={14} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
