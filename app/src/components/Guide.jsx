import { useState } from 'react'
import { X, ChevronRight, ChevronLeft, Compass } from 'lucide-react'

// 60-second guided tour: each step can switch tab / open a lead so a first-time
// judge sees every screen without hunting.
const STEPS = [
  {
    tab: 'mission', lead: null, title: 'Welcome to SANKET',
    body: 'Banks cold-call their own customers at ~1% conversion. SANKET reads the liability book — every transaction is a signal — and ranks who is ready for which loan. The headline is measured, not promised: the top-2% queue converts ~36%.',
  },
  {
    tab: 'mission', lead: null, title: 'Choose your calling capacity',
    body: 'Drag the slider: precision, lift and expected conversions recompute live from held-out customers. Calling deeper honestly converts less — that trade-off IS the product.',
  },
  {
    tab: 'queue', lead: null, title: 'The ranked queue — with consent built in',
    body: 'Two separate scores: INTENT (is the need real right now?) and CAPACITY (can they repay comfortably?). Greyed rows are customers without marketing consent — they are never scored at all. DPDP lives in the product, not on a slide.',
  },
  {
    tab: 'queue', lead: 'auto-hindi', title: 'The call briefing',
    body: 'Every lead opens into a full briefing: the signals month-by-month, plain-English reasons, a retained-income → safe-EMI check, and a pitch script — about 40% surface in Hindi, matched to the customer. Every claim traces to a signal chip.',
  },
  {
    tab: 'trust', lead: null, title: 'Persuadable, not just probable',
    body: 'The uplift model separates customers who convert BECAUSE you call from those who would convert anyway — and flags the few where a pushy call kills the sale. Top-uplift calling nearly triples incremental conversions per 1,000 calls.',
  },
  {
    tab: 'radar', lead: null, title: 'Proven on real businesses',
    body: 'The same engine ran over 26,000+ real Indian businesses: the prospects it ranked highest actually raised borrowings the next year at twice the rate of the rest. Explore freely — SANKET advises, the RM decides.',
  },
]

export default function Guide({ setTab, setLead, hindiLeadId, onClose }) {
  const [i, setI] = useState(0)
  const step = STEPS[i]

  const go = (n) => {
    const s = STEPS[n]
    if (!s) return
    setTab(s.tab)
    setLead(s.lead === 'auto-hindi' ? hindiLeadId : null)
    setI(n)
  }

  return (
    <div className="fixed inset-x-0 bottom-16 md:bottom-6 z-50 px-4 pointer-events-none">
      <div className="max-w-xl mx-auto bg-ink-700 border border-signal-amber/50 rounded-2xl shadow-2xl p-4 pointer-events-auto">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-signal-amber grid place-items-center text-ink-900 shrink-0"><Compass size={16} /></div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-sm">{step.title}</h3>
              <span className="text-[10px] text-txt-lo">{i + 1}/{STEPS.length}</span>
            </div>
            <p className="text-xs text-txt-mid leading-relaxed mt-1">{step.body}</p>
          </div>
          <button onClick={onClose} aria-label="Close tour"
            className="text-txt-lo hover:text-txt-hi rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"><X size={16} /></button>
        </div>
        <div className="flex items-center gap-2 mt-3 pl-11">
          {STEPS.map((_, k) => (
            <span key={k} className={`h-1 rounded-full transition-all ${k === i ? 'w-5 bg-signal-amber' : 'w-2 bg-ink-500'}`} />
          ))}
          <div className="ml-auto flex gap-2">
            {i > 0 && (
              <button onClick={() => go(i - 1)}
                className="flex items-center gap-1 text-xs text-txt-mid hover:text-txt-hi px-2 py-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
                <ChevronLeft size={13} /> Back
              </button>
            )}
            {i < STEPS.length - 1 ? (
              <button onClick={() => go(i + 1)}
                className="flex items-center gap-1 text-xs font-bold bg-signal-amber text-ink-900 px-3 py-1 rounded-lg hover:bg-signal-amber/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
                Next <ChevronRight size={13} />
              </button>
            ) : (
              <button onClick={onClose}
                className="text-xs font-bold bg-signal-teal text-ink-900 px-3 py-1 rounded-lg hover:bg-signal-teal/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-teal">
                Explore on your own
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
