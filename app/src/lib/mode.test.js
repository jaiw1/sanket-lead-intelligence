import { describe, expect, it } from 'vitest'
import { isFrozenBundle, modeOverride } from './mode'

/**
 * The frozen bundle is served from the same origin as the live platform, and `API_BASE`
 * falls back to `/api/v1`. Probing `/meta/health` therefore succeeded for the static
 * bundle too, so it decided it was live, called `/auth/me`, got a 401 and showed a
 * sign-in form — the fallback that exists for a backend outage was a login wall whenever
 * the backend was up. The build's own base path is the signal that settles it.
 */
describe('isFrozenBundle', () => {
  it('recognises the bundle deploy/export_static.py builds', () => {
    expect(isFrozenBundle('/static-demo/drishti/')).toBe(true)
    expect(isFrozenBundle('/static-demo/sanket/')).toBe(true)
  })

  it('leaves the live deployment alone', () => {
    expect(isFrozenBundle('/drishti/')).toBe(false)
    expect(isFrozenBundle('/sanket/')).toBe(false)
  })

  it('leaves the dev server alone', () => {
    expect(isFrozenBundle('./')).toBe(false)
    expect(isFrozenBundle('/')).toBe(false)
    expect(isFrozenBundle(undefined)).toBe(false)
  })
})

describe('modeOverride', () => {
  it('honours an explicit ?mode=, and nothing else', () => {
    expect(modeOverride('?mode=static')).toBe('static')
    expect(modeOverride('?mode=live')).toBe('live')
    expect(modeOverride('?mode=banana')).toBeNull()
    expect(modeOverride('')).toBeNull()
  })
})
