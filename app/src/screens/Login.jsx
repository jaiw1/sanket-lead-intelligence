import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, LockKeyhole, Radar, ShieldCheck, TriangleAlert } from 'lucide-react'
import { AUTH_STATUS, ENDED, useAuth } from '../auth/AuthContext'
import InsecureContextNotice, { isInsecureContext } from '../components/InsecureContextNotice'
import ScreenHelp from '../components/ScreenHelp'

/** Only ever return to a path inside this app. `//evil.example` is not a path. */
export function safeReturnTo(value) {
  if (!value || typeof value !== 'string') return '/'
  if (!value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

/** One message for every credential failure: the screen must not reveal which half was wrong. */
const GENERIC_FAILURE = 'Sign-in failed. Check your username and password, then try again.'

const ENDED_MESSAGE = {
  [ENDED.IDLE]: 'You were signed out after 30 minutes without activity.',
  [ENDED.ABSOLUTE]: 'Your 8-hour session reached its limit. Please sign in again.',
  [ENDED.INACTIVE]: 'That session is no longer valid. Please sign in again.',
  [ENDED.SIGNED_OUT]: 'You have been signed out.',
}

const countdownLabel = (seconds) => {
  const s = Math.max(0, Math.ceil(seconds))
  const m = Math.floor(s / 60)
  const rest = s % 60
  if (m) return `${m}:${String(rest).padStart(2, '0')}`
  return `${rest}s`
}

export default function Login() {
  const { login, status, isStatic, endedReason, mustChangePassword } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const usernameRef = useRef(null)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const [lockSeconds, setLockSeconds] = useState(0)

  const returnTo = safeReturnTo(params.get('next') || location.state?.from || '/')
  const insecure = isInsecureContext()

  useEffect(() => { usernameRef.current?.focus() }, [])

  // Lockout / rate-limit countdown.
  useEffect(() => {
    if (lockSeconds <= 0) return undefined
    const id = setTimeout(() => setLockSeconds((n) => Math.max(0, n - 1)), 1000)
    return () => clearTimeout(id)
  }, [lockSeconds])

  if (insecure) return <InsecureContextNotice />
  if (isStatic) return <Navigate to="/" replace />
  if (status === AUTH_STATUS.AUTHENTICATED) {
    return <Navigate to={mustChangePassword ? '/change-password' : returnTo} replace />
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    if (pending || lockSeconds > 0) return
    setError(null)
    setPending(true)
    try {
      const session = await login(username.trim(), password)
      setPassword('')
      navigate(session?.must_change_password ? '/change-password' : returnTo, { replace: true })
    } catch (failure) {
      setPassword('')
      if (failure?.isLocked || failure?.isRateLimited) {
        setLockSeconds(failure.retryAfter ?? 0)
        setError({
          kind: failure.isLocked ? 'locked' : 'throttled',
          message: failure.isLocked
            ? 'This account is temporarily locked after repeated failed sign-ins.'
            : 'Too many sign-in attempts from this address.',
        })
      } else if (failure?.isNetwork) {
        setError({ kind: 'network', message: 'Could not reach the server. Check your connection and try again.' })
      } else if (failure?.status === 400) {
        setError({ kind: 'validation', message: failure.message || 'Please fill in both fields.' })
      } else {
        setError({ kind: 'credentials', message: GENERIC_FAILURE })
      }
    } finally {
      setPending(false)
    }
  }

  const locked = lockSeconds > 0
  const notice = !error && endedReason ? ENDED_MESSAGE[endedReason] : null

  return (
    <main id="main-content" className="grid min-h-screen place-items-center bg-slate-100 px-6 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-idbi-green text-white">
            <Radar size={22} aria-hidden="true" />
          </div>
          <div>
            <div className="text-lg font-extrabold leading-tight tracking-wide text-slate-900">SANKET</div>
            <div className="text-xs leading-tight text-slate-500">Prospect Assist AI · IDBI Bank</div>
          </div>
          <div className="ml-auto"><ScreenHelp screen="login" label="Help" /></div>
        </div>

        <form
          onSubmit={onSubmit}
          noValidate
          className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          aria-labelledby="login-heading"
        >
          <h1 id="login-heading" className="text-base font-extrabold text-slate-900">Sign in</h1>

          {notice && (
            <p className="rounded-lg bg-slate-100 px-3 py-2 text-xs leading-relaxed text-slate-600" role="status">
              {notice}
            </p>
          )}

          {/* One assertive region: a failure must be announced, not just coloured red. */}
          <div aria-live="assertive" role="alert">
            {error && (
              <p
                data-testid="login-error"
                className="flex items-start gap-2 rounded-lg border border-rag-red/30 bg-red-50 px-3 py-2 text-xs leading-relaxed text-rag-red"
              >
                <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>
                  {error.message}
                  {locked && (
                    <>
                      {' '}Try again in <b className="tabular-nums">{countdownLabel(lockSeconds)}</b>.
                    </>
                  )}
                  {error.kind === 'locked' && !locked && ' Please wait a few minutes before trying again.'}
                </span>
              </p>
            )}
          </div>

          <div>
            <label htmlFor="login-username" className="block text-xs font-semibold text-slate-600">
              Username
            </label>
            <input
              ref={usernameRef}
              id="login-username"
              name="username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck="false"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-describedby={error ? 'login-error-hint' : undefined}
              aria-invalid={error?.kind === 'credentials' ? 'true' : undefined}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-idbi-green focus:ring-2 focus:ring-idbi-green/30"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-xs font-semibold text-slate-600">
              Password
            </label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error?.kind === 'credentials' ? 'true' : undefined}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-idbi-green focus:ring-2 focus:ring-idbi-green/30"
            />
          </div>

          <button
            type="submit"
            disabled={pending || locked}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-idbi-green px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <LockKeyhole size={15} aria-hidden="true" />}
            {pending ? 'Signing in…' : locked ? `Locked — ${countdownLabel(lockSeconds)}` : 'Sign in'}
          </button>

          <p id="login-error-hint" className="text-[11px] leading-relaxed text-slate-400">
            Accounts are issued by the bank. Five failed attempts in fifteen minutes locks an account for
            fifteen minutes.
          </p>
        </form>

        <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
          <ShieldCheck size={12} aria-hidden="true" />
          Sessions end after 8 hours, or 30 minutes idle.
        </p>
      </div>
    </main>
  )
}
