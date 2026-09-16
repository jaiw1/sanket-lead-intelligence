import { Navigate, useLocation } from 'react-router-dom'
import { AUTH_STATUS, useAuth } from './AuthContext'
import Loading from '../components/states/Loading'

/** Where to send someone back to after they sign in. */
export function returnToFrom(location) {
  return `${location.pathname}${location.search}` || '/'
}

/**
 * Gate for "must be signed in". Unauthenticated users go to the login screen with a
 * return-to, so a deep link survives an expired session instead of dumping them at the
 * dashboard. A user who must change their password is trapped on /change-password —
 * the same rule the backend enforces with 403 PASSWORD_CHANGE_REQUIRED.
 */
export default function RequireAuth({ children }) {
  const { ready, status, isStatic, mustChangePassword } = useAuth()
  const location = useLocation()

  if (!ready) return <Loading label="Checking your session…" />
  if (isStatic) return children // static demo: there is no backend to authenticate against

  if (status !== AUTH_STATUS.AUTHENTICATED) {
    const next = returnToFrom(location)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(next)}`}
        replace
        state={{ from: next }}
      />
    )
  }

  if (mustChangePassword && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace state={{ from: returnToFrom(location) }} />
  }

  return children
}
