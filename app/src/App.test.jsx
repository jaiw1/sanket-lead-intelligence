import { useEffect } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { vi } from 'vitest'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { mockFetchRoutes } from './test/http'
import { session } from './test/render'

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

describe('App shell — the routes a role may open', () => {
  /** Every link the signed-in role is offered. Each carries the wide and the narrow
   *  label, so the text is matched rather than compared whole. */
  const navText = () => {
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    return [...toolbar.querySelectorAll('a')].map((a) => a.textContent.trim())
  }

  // The two screens whose audience narrowed. The server refuses metaSync/metaProvenance
  // independently; the radar has no platform route at all, so the guard here is the whole
  // of its access control — which is why it is asserted per role rather than once.
  describe.each([
    ['/sources', 'relationship_manager', 'Relationship manager'],
    ['/sources', 'credit_officer', 'Credit officer'],
    ['/radar', 'relationship_manager', 'Relationship manager'],
    ['/radar', 'manager', 'Manager'],
    ['/radar', 'credit_officer', 'Credit officer'],
  ])('a direct visit to %s as a %s', (path, role, label) => {
    it('is refused, by name, inside the shell', async () => {
      mockFetchRoutes({})
      renderApp(path, { user: session(role) })
      expect(await screen.findByTestId('state-denied')).toHaveTextContent(label)
      expect(screen.getByTestId('session-bar')).toBeInTheDocument()
    })
  })

  it('opens the radar for an administrator, with the out-of-scope label on it', async () => {
    mockFetchRoutes({})
    renderApp('/radar', { user: session('admin') })
    expect(await screen.findByTestId('radar-scope-note')).toHaveTextContent(
      'Exploratory exhibit on public company data — outside this track’s scope (existing-customer prospects); kept for reference.',
    )
    expect(screen.queryByTestId('state-denied')).not.toBeInTheDocument()
  })

  it('offers a relationship manager neither the radar nor data sources', async () => {
    mockFetchRoutes({})
    renderApp('/queue', { user: session('relationship_manager') })
    await screen.findByRole('toolbar', { name: 'Screens' })
    const labels = navText().join(' | ')
    expect(labels).not.toMatch(/Business radar/)
    expect(labels).not.toMatch(/Data sources/)
    expect(labels).toMatch(/Lead queue/)
  })

  it('offers a credit officer nothing at all, and says why on the screen', async () => {
    mockFetchRoutes({})
    renderApp('/queue', { user: session('credit_officer') })
    expect(await screen.findByTestId('state-denied')).toHaveTextContent('Credit officer')
    expect(navText()).toEqual([])
  })
})
