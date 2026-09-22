import { useLocation } from 'react-router-dom'
import RequireAuth from './RequireAuth'
import { useAuth } from './AuthContext'
import { roleMatches } from './roles'
import AppShell, { STATIC_HIDDEN } from '../components/AppShell'
import Empty from '../components/states/Empty'
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
 *
 * The refusal is rendered **inside the app shell**, not as a bare panel on an empty page.
 * A role with no screen of its own in this product (a credit officer, since SANKET's
 * screens narrowed to A/M/RM) would otherwise land on a panel with no header and no way to
 * sign out.
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
  const { pathname } = useLocation()

  // The frozen bundle has no session and therefore no role, so it cannot be gated by one.
  // It is gated by the same set the static navigation is built from, so a typed URL and
  // the menu agree about what this build contains.
  if (isStatic) {
    if (!STATIC_HIDDEN.has(pathname)) return children
    return (
      <AppShell title="Not in the static demo">
        <Empty
          title="This screen is not in the static demo"
          hint="It needs a signed-in administrator and a live backend. Everything else here works without one."
        />
      </AppShell>
    )
  }

  if (roleMatches(role, allow)) return children
  return fallback ?? (
    <AppShell title="You do not have access to this screen">
      <PermissionDenied role={role} allowed={allow} />
    </AppShell>
  )
}
