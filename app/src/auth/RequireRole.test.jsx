import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './AuthContext'
import RequireAuth from './RequireAuth'
import RequireRole from './RequireRole'

const SESSION = (role) => ({
  username: `${role}.demo`, full_name: `Demo ${role}`, role,
  scope: [], must_change_password: false, csrf_token: 'c',
  expires_at: new Date(Date.now() + 3600_000).toISOString(),
})

function renderAt(path, { user = null, mode = 'live' } = {}) {
  return render(
    <AuthProvider initialMode={mode} initialUser={user}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/login" element={<p>Sign-in screen</p>} />
          <Route path="/change-password" element={<p>Change your password</p>} />
          <Route path="/watchlist" element={<RequireAuth><p>Watch-list</p></RequireAuth>} />
          <Route path="/threshold" element={<RequireRole allow={['M', 'A']}><p>Threshold editor</p></RequireRole>} />
          <Route path="/admin" element={<RequireRole allow={['admin']}><p>Administration</p></RequireRole>} />
          <Route path="/any" element={<RequireRole allow={[]}><p>Any signed-in user</p></RequireRole>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('RequireAuth', () => {
  it('sends an unauthenticated visitor to login with a return-to', () => {
    renderAt('/watchlist')
    expect(screen.getByText('Sign-in screen')).toBeInTheDocument()
  })

  it('lets a signed-in user through', () => {
    renderAt('/watchlist', { user: SESSION('credit_officer') })
    expect(screen.getByText('Watch-list')).toBeInTheDocument()
  })

  it('traps a user who must change their password', () => {
    renderAt('/watchlist', { user: { ...SESSION('manager'), must_change_password: true } })
    expect(screen.getByText('Change your password')).toBeInTheDocument()
  })

  it('passes everything through in static-demo mode, where there is no backend', () => {
    renderAt('/watchlist', { mode: 'static' })
    expect(screen.getByText('Watch-list')).toBeInTheDocument()
  })
})

describe('RequireRole', () => {
  it('accepts the contract’s short codes from x-roles', () => {
    renderAt('/threshold', { user: SESSION('manager') })
    expect(screen.getByText('Threshold editor')).toBeInTheDocument()
  })

  it('accepts the long role names too', () => {
    renderAt('/admin', { user: SESSION('admin') })
    expect(screen.getByText('Administration')).toBeInTheDocument()
  })

  it('renders PermissionDenied for the wrong role instead of redirecting', () => {
    renderAt('/threshold', { user: SESSION('credit_officer') })
    expect(screen.queryByText('Threshold editor')).not.toBeInTheDocument()
    expect(screen.getByTestId('state-denied')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Credit officer')
  })

  it('names the roles that would be allowed', () => {
    renderAt('/admin', { user: SESSION('relationship_manager') })
    expect(screen.getByRole('alert')).toHaveTextContent('Administrator')
  })

  it('treats an empty allow-list as "any signed-in user"', () => {
    renderAt('/any', { user: SESSION('relationship_manager') })
    expect(screen.getByText('Any signed-in user')).toBeInTheDocument()
  })

  it('still requires a session', () => {
    renderAt('/admin')
    expect(screen.getByText('Sign-in screen')).toBeInTheDocument()
  })
})
