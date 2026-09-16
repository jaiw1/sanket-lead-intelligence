import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { CheckCircle2, KeyRound, Loader2, TriangleAlert } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import InsecureContextNotice, { isInsecureContext } from '../components/InsecureContextNotice'
import { safeReturnTo } from './Login'

/** contracts/openapi.json: `new_password` has minLength 12. */
export const MIN_PASSWORD_LENGTH = 12

export function validateNewPassword({ current, next, confirm }) {
  const errors = {}
  if (!current) errors.current_password = 'Enter your current password.'
  if (!next) errors.new_password = 'Choose a new password.'
  else if (next.length < MIN_PASSWORD_LENGTH) {
    errors.new_password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`
  } else if (next === current) {
    errors.new_password = 'The new password must be different from the current one.'
  }
  if (next && confirm !== next) errors.confirm = 'The two new passwords do not match.'
  return errors
}

export default function ChangePassword() {
  const { changePassword, mustChangePassword, isStatic, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const currentRef = useRef(null)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [pending, setPending] = useState(false)

  const returnTo = safeReturnTo(params.get('next') || location.state?.from || '/')

  useEffect(() => { currentRef.current?.focus() }, [])

  if (isInsecureContext()) return <InsecureContextNotice />
  if (isStatic) return <Navigate to="/" replace />
  if (!isAuthenticated) return <Navigate to="/login" replace />

  const onSubmit = async (event) => {
    event.preventDefault()
    if (pending) return
    setFormError(null)
    const errors = validateNewPassword({ current, next, confirm })
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setPending(true)
    try {
      await changePassword(current, next)
      setCurrent(''); setNext(''); setConfirm('')
      navigate(returnTo, { replace: true })
    } catch (failure) {
      if (failure?.fields) {
        setFieldErrors(failure.fields)
        setFormError('Please correct the fields below.')
      } else if (failure?.status === 400 || failure?.status === 401) {
        // 401 here means the current password was wrong, not that the session died — the
        // session is what let us reach this route.
        setFormError(failure.message || 'That did not work. Check your current password and try again.')
      } else if (failure?.isNetwork) {
        setFormError('Could not reach the server. Check your connection and try again.')
      } else {
        setFormError(failure?.message || 'The password could not be changed.')
      }
    } finally {
      setPending(false)
    }
  }

  const field = (id, label, value, setValue, autoComplete, describedBy) => (
    <div>
      <label htmlFor={id} className="block text-xs font-semibold text-slate-600">{label}</label>
      <input
        ref={id === 'cp-current' ? currentRef : undefined}
        id={id}
        name={id}
        type="password"
        autoComplete={autoComplete}
        required
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-invalid={fieldErrors[describedBy] ? 'true' : undefined}
        aria-describedby={fieldErrors[describedBy] ? `${id}-error` : undefined}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-idbi-green focus:ring-2 focus:ring-idbi-green/30"
      />
      {fieldErrors[describedBy] && (
        <p id={`${id}-error`} className="mt-1 text-[11px] font-medium text-rag-red">{fieldErrors[describedBy]}</p>
      )}
    </div>
  )

  return (
    <main id="main-content" className="grid min-h-screen place-items-center bg-slate-100 px-6 py-10">
      <div className="w-full max-w-sm">
        {mustChangePassword && (
          <div
            className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900"
            role="status"
          >
            <TriangleAlert size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p>
              <b>Choose a new password to continue.</b> This account was issued with a temporary password,
              and nothing else will load until it is changed.
            </p>
          </div>
        )}

        <form
          onSubmit={onSubmit}
          noValidate
          className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          aria-labelledby="cp-heading"
        >
          <div className="flex items-center gap-2">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-idbi-green/10 text-idbi-green">
              <KeyRound size={18} aria-hidden="true" />
            </div>
            <h1 id="cp-heading" className="text-base font-extrabold text-slate-900">Change your password</h1>
          </div>

          <div aria-live="assertive" role="alert">
            {formError && (
              <p
                data-testid="change-password-error"
                className="flex items-start gap-2 rounded-lg border border-rag-red/30 bg-red-50 px-3 py-2 text-xs leading-relaxed text-rag-red"
              >
                <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>{formError}</span>
              </p>
            )}
          </div>

          {field('cp-current', 'Current password', current, setCurrent, 'current-password', 'current_password')}
          {field('cp-new', `New password (at least ${MIN_PASSWORD_LENGTH} characters)`, next, setNext, 'new-password', 'new_password')}
          {field('cp-confirm', 'Confirm new password', confirm, setConfirm, 'new-password', 'confirm')}

          <button
            type="submit"
            disabled={pending}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-idbi-green px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />}
            {pending ? 'Changing…' : 'Change password'}
          </button>

          <p className="text-[11px] leading-relaxed text-slate-400">
            Changing your password signs out every other session you have open. This one stays signed in.
          </p>
        </form>
      </div>
    </main>
  )
}
