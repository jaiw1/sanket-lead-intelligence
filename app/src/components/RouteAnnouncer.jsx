import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Focus and announcement management on navigation.
 *
 * A single-page app changes the whole screen without moving focus, which leaves a
 * keyboard user stranded where they were and tells a screen reader nothing. On every
 * pathname change this moves focus to the main region and announces the new screen.
 */
export default function RouteAnnouncer({ title, targetId = 'main-content' }) {
  const location = useLocation()
  const liveRef = useRef(null)
  const first = useRef(true)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    const main = document.getElementById(targetId)
    if (main) {
      main.setAttribute('tabindex', '-1')
      main.focus({ preventScroll: true })
      window.scrollTo({ top: 0 })
    }
    if (liveRef.current) liveRef.current.textContent = title ? `${title} — page loaded` : 'Page loaded'
  }, [location.pathname, title, targetId])

  return <p ref={liveRef} aria-live="polite" aria-atomic="true" className="sr-only" />
}
