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
 * Decide which mode this page load is in. Never throws.
 * @returns {Promise<'live'|'static'>}
 */
export async function resolveMode({ timeoutMs = 4000, signal } = {}) {
  const forced = modeOverride()
  if (forced) return forced
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
