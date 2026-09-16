import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * One async read, with the four states every screen in this app owes the user:
 * loading, empty, error and denied. `error.isForbidden` is what a screen renders
 * <PermissionDenied/> for — the backend refuses independently of the route guard, and a
 * 403 from a data call is the honest way to find out.
 *
 * `deps` is an array like useEffect's. A change cancels the request in flight, so a fast
 * filter change cannot land an older response on top of a newer one.
 */
export default function useResource(loader, deps = [], { enabled = true, initial = null } = {}) {
  const [state, setState] = useState({ data: initial, meta: null, loading: enabled, error: null })
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    if (!enabled) {
      setState({ data: initial, meta: null, loading: false, error: null })
      return undefined
    }
    const controller = new AbortController()
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.resolve()
      .then(() => loaderRef.current({ signal: controller.signal }))
      .then((result) => {
        if (!live) return
        // A loader may return the envelope {data, meta} or just the payload.
        const isEnvelope = result && typeof result === 'object' && !Array.isArray(result)
          && 'data' in result && ('meta' in result)
        setState({
          data: isEnvelope ? result.data : result,
          meta: isEnvelope ? result.meta : null,
          loading: false,
          error: null,
        })
      })
      .catch((error) => {
        if (!live || error?.name === 'AbortError') return
        setState({ data: null, meta: null, loading: false, error })
      })
    return () => { live = false; controller.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, reload }
}
