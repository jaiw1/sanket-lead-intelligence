import { createContext, useContext, useMemo } from 'react'
import { loadPack } from '../lib/pack'
import useResource from './useResource'

/**
 * The bundled export, `app/public/sanket_data.json`.
 *
 * Two screens want it for two different reasons:
 *   * In STATIC mode it is the only data there is — no backend answered, so the queue, the
 *     dashboard and Model & Trust all read it, behind the static-demo banner.
 *   * In LIVE mode, Model & Trust additionally reads it for the pre-registered validation
 *     table, because the platform API has no SANKET validation route (the contract has
 *     `drishti/validation` and no counterpart). That panel is labelled with its own source
 *     so the two are never confused on screen.
 *
 * It is fetched at most once per page load, and a failure is not fatal: every consumer
 * renders an empty or error state of its own.
 */
const PackContext = createContext(null)

export function PackProvider({ children, enabled = true, value: override = null }) {
  const resource = useResource(({ signal }) => loadPack({ signal }), [], { enabled: enabled && !override })
  const value = useMemo(
    () => (override ? { data: override, loading: false, error: null, reload: () => {} } : resource),
    [override, resource],
  )
  return <PackContext.Provider value={value}>{children}</PackContext.Provider>
}

export function usePack() {
  return useContext(PackContext) || { data: null, loading: false, error: null, reload: () => {} }
}

export default PackContext
