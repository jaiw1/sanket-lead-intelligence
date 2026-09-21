// Live backend, or the frozen static demo?
//
// The plan's static fallback: with no `VITE_API_BASE` configured and `/api/v1/meta/health`
// unreachable, the app still has to open and show the bundled snapshot — with a visible
// banner saying so, because a demo that silently looks live is a dishonest demo.

import { apiFetch } from './api'

export const MODE = { LIVE: 'live', STATIC: 'static', UNKNOWN: 'unknown' }

/** `?mode=static` / `?mode=live` forces a mode — for screenshots and the failover drill. */
export function modeOverride(search = typeof window === 'undefined' ? '' : window.location.search) {
  const value = new URLSearchParams(search).get('mode')
  return value === MODE.STATIC || value === MODE.LIVE ? value : null
}

export const hasConfiguredApi = () => Boolean(import.meta.env?.VITE_API_BASE)

/**
 * Is this page load the frozen bundle?
 *
 * `deploy/export_static.py` builds it with `VITE_API_BASE` unset and
 * `--base /static-demo/<product>/`, so those two facts together are the build's own
 * declaration that it has no backend — and the only signal available before any network
 * call is made.
 *
 * This matters because `API_BASE` falls back to `/api/v1`, and the frozen bundle is served
 * from the same origin as the live platform. `/api/v1/meta/health` therefore answered 200
 * for the static bundle too, so it decided it was LIVE, called `/auth/me`, got a 401 and
 * showed a sign-in form: the fallback that exists for a backend outage was a login wall
 * whenever the backend was healthy, with no "Static demo." banner anywhere.
 */
export function isFrozenBundle(base = import.meta.env?.BASE_URL) {
  if (hasConfiguredApi()) return false
  return String(base ?? '').includes('/static-demo/')
}

/**
 * Decide which mode this page load is in. Never throws.
 * @returns {Promise<'live'|'static'>}
 */
export async function resolveMode({ timeoutMs = 4000, signal } = {}) {
  const forced = modeOverride()
  if (forced) return forced
  // Decided before the probe: a bundle that declares no API must not be talked out of it
  // by an unrelated API answering on the same origin.
  if (isFrozenBundle()) return MODE.STATIC
  try {
    await apiFetch('/meta/health', { silent: true, retry: false, timeoutMs, signal })
    return MODE.LIVE
  } catch (error) {
    if (error && error.name === 'AbortError') throw error
    // A *configured* API that answers 503 is still the live deployment, degraded: say so
    // rather than quietly swapping in demo data underneath a real login.
    if (hasConfiguredApi()) return MODE.LIVE
    return MODE.STATIC
  }
}
