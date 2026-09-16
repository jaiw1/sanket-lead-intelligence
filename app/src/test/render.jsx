import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AuthProvider from '../auth/AuthContext'
import { PackProvider } from '../data/PackContext'

export const ROUTER_FLAGS = { v7_startTransition: true, v7_relativeSplatPath: true }

/** A signed-in session envelope, shaped like `GET /auth/me`'s `data`. */
export function session(role = 'manager', extra = {}) {
  return {
    username: `demo.${role}`,
    full_name: `Demo ${role}`,
    role,
    ein: 'EIN-100237',
    branch_code: 'BR-0412',
    scope: [],
    must_change_password: false,
    csrf_token: 'csrf-test',
    expires_at: new Date(Date.now() + 8 * 3600_000).toISOString(),
    ...extra,
  }
}

/**
 * Render a screen the way the app renders it: inside the router, the auth provider and the
 * bundled-export provider. `pack` is handed to <PackProvider> directly so a screen test
 * never has to mock the public/ fetch.
 */
export function renderScreen(ui, {
  path = '/', route = '*', user = session('manager'), mode = 'live', pack = null, ...options
} = {}) {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FLAGS}>
      <AuthProvider initialMode={mode} initialUser={user}>
        <PackProvider enabled={false} value={pack}>
          <Routes>
            <Route path={route} element={ui} />
          </Routes>
        </PackProvider>
      </AuthProvider>
    </MemoryRouter>,
    options,
  )
}
