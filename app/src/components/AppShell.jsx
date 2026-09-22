import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Antenna, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { roleMatches } from '../auth/roles'
import ScreenHelp from './ScreenHelp'
import SessionBar from './SessionBar'

/**
 * Every route a signed-in user can reach, with the `x-roles` that gate it, straight from
 * contracts/openapi.json. A link is not rendered at all when the role cannot use it — but
 * the guard on the route is what actually enforces it, and the backend enforces it again.
 * Hiding a link is tidiness; it is never the access control.
 */
export const NAV = [
  { to: '/dashboard', label: 'Manager dashboard', short: 'Dashboard', roles: ['M', 'A'] },
  { to: '/queue', label: 'Lead queue', short: 'Queue', roles: ['A', 'M', 'RM'] },
  { to: '/consent', label: 'Consent & AA', short: 'Consent', roles: ['A', 'M', 'RM'] },
  { to: '/trust', label: 'Model & trust', short: 'Trust', roles: ['M', 'A'] },
  // Business radar screens public company filings. It is an appendix exhibit outside this
  // track's scope — the track is existing-customer prospects — so it is kept for reference
  // and shown to administrators only, with a label on the screen saying as much.
  { to: '/radar', label: 'Business radar', short: 'Radar', roles: ['A'], badge: 'REAL' },
  // metaSync / metaProvenance narrowed to A and M: Data sources is a disclosure surface
  // about the platform's own plumbing, not a screen an RM works from.
  { to: '/sources', label: 'Data sources', short: 'Sources', roles: ['A', 'M'] },
  { to: '/admin', label: 'Administration', short: 'Admin', roles: ['A'] },
]

/**
 * What the frozen bundle does not show.
 *
 * Static mode has no session and therefore no role, so it needs a rule of its own: it
 * shows **what a manager sees, minus the screens that are an administrator's alone**.
 * Administration needs a session and a backend; Business radar is admin-only.
 *
 * `RequireRole` reads the same set, so a typed URL and the menu agree.
 */
export const STATIC_HIDDEN = new Set(['/admin', '/radar'])

/** The landing route for a role: an RM has no dashboard, so they start on their queue. */
export function homeFor(role, isStatic = false) {
  if (isStatic) return '/dashboard'
  if (roleMatches(role, ['M', 'A'])) return '/dashboard'
  if (roleMatches(role, ['RM'])) return '/queue'
  // A credit officer is DRISHTi's role, not SANKET's: the contract gives CO no sanket/*
  // operation, and Data sources — the one screen that used to be theirs here — is now a
  // manager's. They land on the queue and are told plainly that it is not their screen,
  // which is the truth; there is no door left to point them at.
  return '/queue'
}

/**
 * Roving tabindex over the primary navigation.
 *
 * A tab list of eight links is eight tab stops otherwise, which is eight presses before a
 * keyboard user reaches the screen they navigated to. One stop enters the bar; the arrow
 * keys move within it; Home and End jump to the ends. This is the pattern WAI-ARIA
 * prescribes for a navigation toolbar, and `role="toolbar"` is what tells a screen reader
 * the arrow keys are live.
 */
function useRovingTabindex(count) {
  const [active, setActive] = useState(0)
  const refs = useRef([])

  const onKeyDown = useCallback((event) => {
    // A role with no screen of its own in SANKET (a credit officer) renders an empty bar.
    // `% 0` is NaN, so the wrap-around needs a floor of one.
    const span = Math.max(count, 1)
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
    let next = null
    if (event.key in keys) next = (active + keys[event.key] + span) % span
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = span - 1
    if (next === null) return
    event.preventDefault()
    setActive(next)
    refs.current[next]?.focus()
  }, [active, count])

  return { active, setActive, refs, onKeyDown }
}

export default function AppShell({ title, help, children, wide = false }) {
  const { role, isStatic, fullName, roleLabel } = useAuth()
  const location = useLocation()
  // The frozen bundle has no session and no backend, so it shows what it can actually
  // render: Administration would open a user table and an audit log with nothing behind
  // them. DRISHTi's shell already drops it (and Thresholds) in static mode; this is the
  // same rule on this side.
  const items = NAV.filter((item) => (
    isStatic ? !STATIC_HIDDEN.has(item.to) : roleMatches(role, item.roles)
  ))
  const roving = useRovingTabindex(items.length)

  // Keep the roving index on whatever screen is actually open, so tabbing into the bar and
  // pressing an arrow moves relative to where you are, not to where you last clicked.
  useEffect(() => {
    const i = items.findIndex((item) => location.pathname.startsWith(item.to))
    if (i >= 0) roving.setActive(i)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, items.length])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-ink-800/95 backdrop-blur">
        <div className={`mx-auto flex h-14 items-center gap-3 px-4 sm:px-6 ${wide ? '' : 'max-w-[1400px]'}`}>
          <div className="flex h-full shrink-0 items-center gap-2.5 border-r border-line pr-3 sm:pr-4">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-signal-amber text-ink-900" aria-hidden="true">
              <Antenna size={17} />
            </div>
            {/* The wordmark is the only part that has to survive a narrow screen. */}
            <div className="hidden leading-tight xs:block sm:block">
              <div className="font-bold tracking-wide">SANKET</div>
              <div className="-mt-0.5 hidden text-[10px] text-txt-lo sm:block">prospect assist</div>
            </div>
          </div>

          <nav aria-label="Primary" className="min-w-0 flex-1">
            <div
              role="toolbar"
              aria-label="Screens"
              aria-orientation="horizontal"
              onKeyDown={roving.onKeyDown}
              className="scroll-thin flex items-center gap-1 overflow-x-auto"
            >
              {items.map((item, i) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  ref={(el) => { roving.refs.current[i] = el }}
                  tabIndex={roving.active === i ? 0 : -1}
                  onFocus={() => roving.setActive(i)}
                  className={({ isActive }) => `flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive ? 'bg-ink-600 text-txt-hi' : 'text-txt-mid hover:bg-ink-700 hover:text-txt-hi'
                  }`}
                >
                  <span className="hidden sm:inline">{item.label}</span>
                  <span className="sm:hidden">{item.short}</span>
                  {item.badge && (
                    <span className="rounded bg-signal-teal/20 px-1.5 py-0.5 text-[9px] font-extrabold text-signal-teal">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          </nav>

          {/* Shrinkable, not fixed: on a phone the session chip has to give way rather than
              push the whole header past the viewport and make the page scroll sideways. */}
          <div className="ml-auto flex min-w-0 items-center gap-2 overflow-hidden">
            {help && <ScreenHelp screen={help} compact />}
            <SessionBar />
          </div>
        </div>
      </header>

      <main
        id="main-content"
        className={`mx-auto w-full flex-1 px-4 py-5 sm:px-6 ${wide ? '' : 'max-w-[1400px]'}`}
      >
        {title && <h1 className="sr-only">{title}</h1>}
        {children}
      </main>

      <footer className="border-t border-line px-4 py-3 text-center text-[11px] text-txt-lo">
        <ShieldCheck size={12} className="mr-1 inline text-signal-teal" aria-hidden="true" />
        SANKET advises — the relationship manager decides.
        {fullName && <> Signed in as {fullName}{roleLabel ? ` (${roleLabel})` : ''}.</>}
      </footer>
    </div>
  )
}
