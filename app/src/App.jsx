import { useState, useEffect } from 'react'
import MissionControl from './components/MissionControl'
import LeadQueue from './components/LeadQueue'
import BusinessRadar from './components/BusinessRadar'
import ModelTrust from './components/ModelTrust'
import LeadDrawer from './components/LeadDrawer'
import Guide from './components/Guide'
import { Antenna, Gauge, ListOrdered, Radar as RadarIcon, ScanEye, ShieldCheck, TriangleAlert, RefreshCw, Compass } from 'lucide-react'

const TABS = [
  { key: 'mission', label: 'Mission Control', short: 'Mission', icon: Gauge },
  { key: 'queue', label: 'Lead Queue', short: 'Queue', icon: ListOrdered },
  { key: 'radar', label: 'Business Radar', short: 'Radar', icon: RadarIcon, badge: 'REAL' },
  { key: 'trust', label: 'Model & Trust', short: 'Trust', icon: ScanEye },
]

export default function App() {
  const params = new URLSearchParams(window.location.search)
  const pv = params.get('tab')
  const [tab, setTab] = useState(TABS.some((t) => t.key === pv) ? pv : 'mission')
  const [data, setData] = useState(null)
  const [radar, setRadar] = useState(null)
  const [error, setError] = useState(false)
  const [lead, setLead] = useState(params.get('lead') || null)
  const [guide, setGuide] = useState(false)

  const load = () => {
    setError(false)
    const b = import.meta.env.BASE_URL
    fetch(`${b}sanket_data.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setData)
      .catch(() => setError(true))
    // radar module is optional — the app degrades gracefully without it
    fetch(`${b}radar_data.json`).then((r) => r.json()).then(setRadar).catch(() => {})
  }
  useEffect(() => {
    load()
    // auto-show tour on first visit; ?tour=0 suppresses (screenshots, deep-links)
    if (!localStorage.getItem('sanket_seen_tour') && params.get('tour') !== '0') setGuide(true)
  }, [])

  const closeGuide = () => { setGuide(false); setLead(null); localStorage.setItem('sanket_seen_tour', '1') }
  const hindiLeadId = data?.leads.find((l) => l.lang === 'hi' && l.consent && l.tier === 'hot')?.id

  if (error) return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="max-w-sm w-full bg-ink-700 border border-line rounded-xl p-6 text-center space-y-3">
        <TriangleAlert className="mx-auto text-signal-amber" size={30} />
        <div className="font-bold">Couldn't load the lead book</div>
        <p className="text-sm text-txt-mid">The connection may have dropped while downloading the demo dataset. Please retry.</p>
        <button onClick={load}
          className="inline-flex items-center gap-2 bg-signal-amber text-ink-900 text-sm font-bold rounded-lg px-4 py-2 hover:bg-signal-amber/90 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
          <RefreshCw size={15} /> Retry
        </button>
      </div>
    </div>
  )

  if (!data) return (
    <div className="min-h-screen grid place-items-center text-txt-mid">
      <div className="flex items-center gap-2 text-sm"><Antenna size={18} className="animate-pulse text-signal-amber" /> Tuning SANKET…</div>
    </div>
  )

  return (
    <div className="min-h-screen flex flex-col">
      {/* top command bar */}
      <header className="bg-ink-800/95 backdrop-blur border-b border-line sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 flex items-center gap-3 h-14">
          <div className="flex items-center gap-2.5 pr-4 border-r border-line h-full">
            <div className="w-8 h-8 rounded-lg bg-signal-amber grid place-items-center text-ink-900"><Antenna size={17} /></div>
            <div className="leading-tight">
              <div className="font-bold tracking-wide">SANKET</div>
              <div className="text-[10px] text-txt-lo -mt-0.5">every transaction is a signal</div>
            </div>
          </div>
          <nav className="flex items-center gap-1 overflow-x-auto scroll-thin">
            {TABS.map((t) => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber ${tab === t.key ? 'bg-ink-600 text-txt-hi' : 'text-txt-mid hover:text-txt-hi hover:bg-ink-700'}`}>
                <t.icon size={15} /> {t.label}
                {t.badge && <span className="text-[9px] font-extrabold bg-signal-teal/20 text-signal-teal px-1.5 py-0.5 rounded">{t.badge}</span>}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <button onClick={() => setGuide(true)}
              className="flex items-center gap-1.5 text-xs font-semibold text-signal-amber bg-signal-amber/10 hover:bg-signal-amber/20 rounded-lg px-3 py-1.5 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
              <Compass size={13} /> Tour
            </button>
            <div className="hidden lg:flex items-center gap-2 text-[11px] text-txt-lo">
              <ShieldCheck size={13} className="text-signal-teal" />
              consent-first · synthetic demo book · IDBI Innovate 2026 · Track 2
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-4 sm:px-6 py-5 space-y-5">
        {tab === 'mission' && <MissionControl data={data} goQueue={() => setTab('queue')} />}
        {tab === 'queue' && <LeadQueue data={data} onSelect={setLead} />}
        {tab === 'radar' && <BusinessRadar radar={radar} />}
        {tab === 'trust' && <ModelTrust data={data} />}
      </main>

      <footer className="border-t border-line py-3 pb-16 md:pb-3 text-center text-[11px] text-txt-lo">
        SANKET advises — the relationship manager decides. Demo runs on a synthetic liability book; bank data connects post-shortlisting.
      </footer>

      {/* mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-ink-800 border-t border-line flex pb-[env(safe-area-inset-bottom)]">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[10px] font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-signal-amber ${tab === t.key ? 'text-signal-amber bg-ink-600/60' : 'text-txt-lo'}`}>
            <t.icon size={17} /> {t.short}
          </button>
        ))}
      </nav>

      {lead && <LeadDrawer data={data} leadId={lead} onClose={() => setLead(null)} />}
      {guide && <Guide setTab={setTab} setLead={setLead} hindiLeadId={hindiLeadId} onClose={closeGuide} />}
    </div>
  )
}
