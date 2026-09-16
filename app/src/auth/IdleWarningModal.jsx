import { useRef } from 'react'
import { Clock, LogOut } from 'lucide-react'
import useFocusTrap from '../lib/useFocusTrap'

const mmss = (seconds) => {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

const spoken = (seconds) => {
  const s = Math.max(0, Math.floor(seconds))
  const m = Math.floor(s / 60)
  const rest = s % 60
  if (m && rest) return `${m} minute${m === 1 ? '' : 's'} and ${rest} seconds`
  if (m) return `${m} minute${m === 1 ? '' : 's'}`
  return `${rest} seconds`
}

/**
 * The 2-minute warning before an idle session ends.
 * Modal, focus-trapped, and deliberately not dismissable by clicking away: the choice is
 * "stay signed in" or "sign out", because ignoring it ends the session either way.
 */
export default function IdleWarningModal({ open, secondsLeft, pinging, onStayAlive, onSignOut }) {
  const dialogRef = useRef(null)
  const stayRef = useRef(null)
  useFocusTrap(dialogRef, { active: open, initialFocusRef: stayRef })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-slate-900/50 px-4" data-testid="idle-overlay">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="idle-title"
        aria-describedby="idle-body"
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-rag-amber/10 text-rag-amber">
            <Clock size={20} aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="idle-title" className="text-base font-extrabold text-slate-900">
              Still there?
            </h2>
            <p id="idle-body" className="mt-1 text-sm leading-relaxed text-slate-600">
              For security, this session ends after 30 minutes without activity. You will be signed out in{' '}
              <span className="font-bold tabular-nums text-slate-900">{mmss(secondsLeft)}</span>.
            </p>
          </div>
        </div>

        {/* Announced every 30s rather than every tick, so a screen reader is not flooded. */}
        <p aria-live="assertive" className="sr-only">
          {secondsLeft % 30 === 0 ? `Signing out in ${spoken(secondsLeft)}.` : ''}
        </p>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onSignOut}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <LogOut size={15} aria-hidden="true" /> Sign out now
          </button>
          <button
            ref={stayRef}
            type="button"
            onClick={onStayAlive}
            disabled={pinging}
            className="rounded-lg bg-idbi-green px-4 py-2 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2 disabled:opacity-60"
          >
            {pinging ? 'Keeping you signed in…' : 'Stay signed in'}
          </button>
        </div>
      </div>
    </div>
  )
}
