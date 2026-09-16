import RequireAuth from './RequireAuth'
import { useAuth } from './AuthContext'
import { roleMatches } from './roles'
import PermissionDenied from '../components/states/PermissionDenied'

/**
 * Gate for "must be signed in AND hold one of these roles".
 *
 * `allow` takes either spelling from contracts/openapi.json — `['M','A']` straight out of
 * a route's `x-roles`, or `['manager','admin']`. An empty list means any signed-in user.
 *
 * A wrong role renders <PermissionDenied/> in place rather than redirecting: the user
 * asked for a real screen and deserves to be told why they cannot see it. The backend
 * refuses the data independently — this is UX, never the access control itself.
 */
export default function RequireRole({ allow, children, fallback }) {
  return (
    <RequireAuth>
      <RoleGate allow={allow} fallback={fallback}>{children}</RoleGate>
    </RequireAuth>
  )
}

function RoleGate({ allow, children, fallback }) {
  const { role, isStatic } = useAuth()
  if (isStatic) return children
  if (roleMatches(role, allow)) return children
  return fallback ?? <PermissionDenied role={role} allowed={allow} />
}
