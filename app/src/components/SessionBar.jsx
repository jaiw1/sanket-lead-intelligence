// Who am I, what may I do, how long have I got, and how do I leave.
//
// The time remaining is the *absolute* 8-hour session limit from the session envelope, not
// the idle window — the idle window has its own warning modal. Showing it is not decoration:
// a credit officer half-way through a memo should be able to see that the session is about
// to end before it does.

import { useEffect, useState } from 'react'
import { LogOut, ShieldCheck, TriangleAlert, UserRound } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'

export function timeLeftLabel(expiresAt, now = Date.now()) {
  if (!expiresAt) return null
  const ms = Date.parse(expiresAt) - now
  if (Number.isNaN(ms)) return null
  if (ms <= 0) return 'expired'
  const minutes = Math.floor(ms / 60000)
  if (minutes < 60) return `${Math.max(1, minutes)}m left`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${rest}m left` : `${hours}h left`
}

export default function SessionBar({ className = '' }) {
  const { isStatic, isAuthenticated, fullName, username, roleLabel: role, scope, expiresAt, logout } = useAuth()
  const [, tick] = useState(0)
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    if (!expiresAt) return undefined
    const id = setInterval(() => tick((n) => n + 1), 30000)
    return () => clearInterval(id)
  }, [expiresAt])

  if (isStatic) {
    return (
      <div className={`flex items-center gap-2 text-xs text-slate-500 ${className}`} data-testid="session-bar">
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 font-semibold">
          <ShieldCheck size={13} aria-hidden="true" /> Static demo — no sign-in
        </span>
      </div>
    )
  }

  if (!isAuthenticated) return null

  const left = timeLeftLabel(expiresAt)
  const soon = left && (left === 'expired' || /^(\d|[1-9])m left$/.test(left))

  return (
    <div className={`flex items-center gap-2 ${className}`} data-testid="session-bar">
      <div className="hidden items-center gap-2 rounded-lg bg-slate-100 px-3 py-1.5 text-xs sm:flex">
        <UserRound size={13} className="text-slate-400" aria-hidden="true" />
        <span className="font-semibold text-slate-700">{fullName || username}</span>
        {role && <span className="text-slate-400">·</span>}
        {role && <span className="text-slate-500">{role}</span>}
        {scope?.length > 0 && (
          <span className="text-slate-400" title={`Scoped to: ${scope.join(', ')}`}>
            · {scope.length} portfolio{scope.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {left && (
        <span
          className={`hidden items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold md:inline-flex ${
            soon ? 'bg-rag-amber/10 text-rag-amber' : 'text-slate-400'
          }`}
          title="Time remaining on this sign-in session"
        >
          {soon && <TriangleAlert size={12} aria-hidden="true" />}
          <span className="sr-only">Session </span>
          {left}
        </span>
      )}

      <button
        type="button"
        disabled={signingOut}
        onClick={async () => { setSigningOut(true); try { await logout() } finally { setSigningOut(false) } }}
        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green disabled:opacity-60"
      >
        <LogOut size={13} aria-hidden="true" /> {signingOut ? 'Signing out…' : 'Sign out'}
      </button>
    </div>
  )
}
