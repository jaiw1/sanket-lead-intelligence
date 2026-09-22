import { useEffect } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { vi } from 'vitest'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { mockFetchRoutes } from './test/http'

const ROUTER_FLAGS = { v7_startTransition: true, v7_relativeSplatPath: true }

/** Reports every location the router settles on, so a test can assert on the URL itself. */
function LocationSpy({ onChange }) {
  const location = useLocation()
  useEffect(() => onChange(location), [location, onChange])
  return null
}

function renderApp(path, { mode = 'live', user = null, onLocation } = {}) {
  return render(
    <AuthProvider initialMode={mode} initialUser={user}>
      <MemoryRouter initialEntries={[path]} future={ROUTER_FLAGS}>
        {onLocation && <LocationSpy onChange={onLocation} />}
        <App />
      </MemoryRouter>
    </AuthProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('App shell — the root redirect', () => {
  // Regression: `/` used to run every visitor — signed in or not — through
  // `homeFor(role, isStatic)`. For a signed-out visitor that has no role, so it fell to
  // homeFor's own last-resort default (`/queue`) and landed them there, which then
  // bounced them to `/login?next=%2Fqueue` — a deep link nobody asked for. Mirrors the
  // same fix shipped for DRISHTi's `/` (App.jsx `LegacyViewRedirect`).
  it('sends an anonymous visitor at the root straight to sign-in, with no next fabricated', async () => {
    mockFetchRoutes({})
    let seen = null
    renderApp('/', { onLocation: (location) => { seen = location } })
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(seen).toMatchObject({ pathname: '/login', search: '' })
  })

  // An anonymous ?tab= is a genuine deep link (the pre-router build's own links, still in
  // the demo video and the deck) — unlike a bare `/`, it is honoured, and the route guard
  // downstream is what asks the visitor to sign in.
  it('still honours an anonymous ?tab= deep link, via a real login next', async () => {
    mockFetchRoutes({})
    let seen = null
    renderApp('/?tab=queue', { onLocation: (location) => { seen = location } })
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(seen).toMatchObject({ pathname: '/login', search: '?next=%2Fqueue' })
  })
})
