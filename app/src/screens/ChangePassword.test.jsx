import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { API_BASE } from '../lib/api'
import { AuthProvider } from '../auth/AuthContext'
import ChangePassword, { MIN_PASSWORD_LENGTH, validateNewPassword } from './ChangePassword'
import { emptyResponse, errorResponse, jsonResponse, mockFetchRoutes } from '../test/http'

const ROUTER_FLAGS = { v7_startTransition: true, v7_relativeSplatPath: true }

const SESSION = (overrides = {}) => ({
  username: 'co.demo', full_name: 'Demo Credit Officer', role: 'credit_officer',
  scope: [], must_change_password: true, csrf_token: 'c',
  expires_at: new Date(Date.now() + 3600_000).toISOString(),
  ...overrides,
})

function renderScreen(user = SESSION()) {
  return render(
    <AuthProvider initialMode="live" initialUser={user}>
      <MemoryRouter initialEntries={['/change-password?next=%2Fwatchlist']} future={ROUTER_FLAGS}>
        <Routes>
          <Route path="/change-password" element={<ChangePassword />} />
          <Route path="/watchlist" element={<p>Watch-list</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

const fill = async (user, { current = 'old-password-1', next = 'a-brand-new-password', confirm = next } = {}) => {
  await user.type(screen.getByLabelText('Current password'), current)
  await user.type(screen.getByLabelText(`New password (at least ${MIN_PASSWORD_LENGTH} characters)`), next)
  await user.type(screen.getByLabelText('Confirm new password'), confirm)
  await user.click(screen.getByRole('button', { name: 'Change password' }))
}

afterEach(() => vi.unstubAllGlobals())

describe('validateNewPassword', () => {
  it('enforces the contract’s 12-character minimum', () => {
    expect(validateNewPassword({ current: 'a', next: 'short', confirm: 'short' }).new_password)
      .toMatch(/at least 12/)
  })
  it('refuses a no-op change', () => {
    const same = 'same-password-12'
    expect(validateNewPassword({ current: same, next: same, confirm: same }).new_password)
      .toMatch(/different/)
  })
  it('catches a mistyped confirmation', () => {
    expect(validateNewPassword({ current: 'a', next: 'aaaaaaaaaaaaaa', confirm: 'bbbbbbbbbbbbbb' }).confirm)
      .toMatch(/do not match/)
  })
  it('passes a good change', () => {
    expect(validateNewPassword({ current: 'old-one', next: 'a-brand-new-password', confirm: 'a-brand-new-password' }))
      .toEqual({})
  })
})

describe('ChangePassword', () => {
  it('explains why a seeded account is trapped here', () => {
    mockFetchRoutes({})
    renderScreen()
    expect(screen.getByRole('status')).toHaveTextContent('Choose a new password to continue')
  })

  it('validates in the browser before touching the network', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchRoutes({})
    renderScreen()

    await fill(user, { next: 'tooshort', confirm: 'tooshort' })
    expect(screen.getByText(`Use at least ${MIN_PASSWORD_LENGTH} characters.`)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('changes the password and returns the user to where they were going', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/password`]: emptyResponse(204),
      [`${API_BASE}/auth/me`]: jsonResponse(200, { data: SESSION({ must_change_password: false }), meta: {} }),
    })
    renderScreen()

    await fill(user)
    await waitFor(() => expect(screen.getByText('Watch-list')).toBeInTheDocument())
  })

  it('reports a wrong current password without losing the session', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/password`]: errorResponse(400, {
        code: 'bad_request', message: 'Please correct the fields below.',
        fields: { current_password: 'That is not your current password.' },
      }),
    })
    renderScreen()

    await fill(user)
    expect(await screen.findByTestId('change-password-error')).toBeInTheDocument()
    expect(screen.getByText('That is not your current password.')).toBeInTheDocument()
    expect(screen.getByLabelText('Current password')).toHaveAttribute('aria-invalid', 'true')
  })
})
