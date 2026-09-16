// Idle-session watchdog: 30 minutes of inactivity ends the session, and the user is warned
// 2 minutes before it happens (plan section A; the backend enforces the same window and
// answers 401 with `reason: SESSION_IDLE` once it lapses).
//
// While the warning is on screen, ordinary activity deliberately does NOT extend the
// session: a mouse brushed across a trackpad should not silently keep a banking session
// alive. The user has to say "Stay signed in", which pings /auth/me and slides the
// server-side window forward too.

import { useCallback, useEffect, useRef, useState } from 'react'

export const DEFAULT_IDLE_MS = 30 * 60 * 1000
export const DEFAULT_WARNING_MS = 2 * 60 * 1000

/** Coarse, cheap signals. `mousemove` is deliberately absent — it fires on stray motion. */
export const ACTIVITY_EVENTS = ['mousedown', 'pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']

export function useIdleTimeout({
  enabled = true,
  idleMs = DEFAULT_IDLE_MS,
  warningMs = DEFAULT_WARNING_MS,
  tickMs = 1000,
  onExpire,
  onStayAlive,
} = {}) {
  const [warning, setWarning] = useState(false)
  const [msLeft, setMsLeft] = useState(idleMs)
  const [pinging, setPinging] = useState(false)
  const lastActivity = useRef(Date.now())
  const warningRef = useRef(false)
  const expiredRef = useRef(false)
  const onExpireRef = useRef(onExpire)
  const onStayAliveRef = useRef(onStayAlive)

  useEffect(() => { onExpireRef.current = onExpire }, [onExpire])
  useEffect(() => { onStayAliveRef.current = onStayAlive }, [onStayAlive])

  const reset = useCallback(() => {
    lastActivity.current = Date.now()
    expiredRef.current = false
    warningRef.current = false
    setWarning(false)
    setMsLeft(idleMs)
  }, [idleMs])

  const stayAlive = useCallback(async () => {
    setPinging(true)
    try {
      if (onStayAliveRef.current) await onStayAliveRef.current()
      reset()
    } finally {
      setPinging(false)
    }
  }, [reset])

  // Activity tracking. Suspended while the warning is up (see the note above).
  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return undefined
    const bump = () => {
      if (warningRef.current || expiredRef.current) return
      lastActivity.current = Date.now()
    }
    for (const name of ACTIVITY_EVENTS) {
      window.addEventListener(name, bump, { passive: true, capture: true })
    }
    return () => {
      for (const name of ACTIVITY_EVENTS) window.removeEventListener(name, bump, { capture: true })
    }
  }, [enabled])

  // The clock.
  useEffect(() => {
    if (!enabled) {
      warningRef.current = false
      expiredRef.current = false
      setWarning(false)
      return undefined
    }
    lastActivity.current = Date.now()
    expiredRef.current = false
    warningRef.current = false
    setWarning(false)
    setMsLeft(idleMs)

    const id = setInterval(() => {
      if (expiredRef.current) return
      const remaining = idleMs - (Date.now() - lastActivity.current)
      if (remaining <= 0) {
        expiredRef.current = true
        warningRef.current = false
        setWarning(false)
        setMsLeft(0)
        if (onExpireRef.current) onExpireRef.current()
        return
      }
      setMsLeft(remaining)
      if (remaining <= warningMs && !warningRef.current) {
        warningRef.current = true
        setWarning(true)
      }
    }, tickMs)
    return () => clearInterval(id)
  }, [enabled, idleMs, warningMs, tickMs])

  return {
    warning,
    msLeft,
    secondsLeft: Math.max(0, Math.ceil(msLeft / 1000)),
    pinging,
    stayAlive,
    reset,
  }
}

export default useIdleTimeout
