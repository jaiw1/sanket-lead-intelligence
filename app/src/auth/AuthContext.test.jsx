import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AUTH_EVENT, API_BASE } from '../lib/api'
import { AuthProvider, useAuth } from './AuthContext'
import { emptyResponse, errorResponse, jsonResponse, mockFetchRoutes, networkFailure } from '../test/http'

const SESSION = {
  username: 'co.demo',
  full_name: 'Demo Credit Officer',
  role: 'credit_officer',
  ein: 'E1001',
  scope: ['MSME-CC', 'MSME-TL'],
  must_change_password: false,
  csrf_token: 'csrf-1',
  expires_at: new Date(Date.now() + 8 * 3600 * 1000).toISOString(),
}

const meEnvelope = (overrides = {}) => jsonResponse(200, { data: { ...SESSION, ...overrides }, meta: { request_id: 'r' } })

function Probe() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="mode">{auth.mode ?? ''}</span>
      <span data-testid="user">{auth.fullName ?? ''}</span>
      <span data-testid="role">{auth.role ?? ''}</span>
      <span data-testid="rolecode">{auth.roleCode ?? ''}</span>
      <span data-testid="scope">{auth.scope.join(',')}</span>
      <span data-testid="must">{String(auth.mustChangePassword)}</span>
      <span data-testid="ended">{auth.endedReason ?? ''}</span>
      <button type="button" onClick={() => auth.login('co.demo', 'hunter22characters')}>sign in</button>
      <button type="button" onClick={() => auth.logout()}>sign out</button>
      <button type="button" onClick={() => auth.changePassword('old-password', 'a-much-longer-one')}>change</button>
    </div>
  )
}

const renderAuth = (props = {}) => render(<AuthProvider {...props}><Probe /></AuthProvider>)

afterEach(() => vi.unstubAllGlobals())

describe('AuthProvider bootstrap', () => {
  it('probes health, then restores an existing session from /auth/me', async () => {
    const fetchMock = mockFetchRoutes({
      [`${API_BASE}/meta/health`]: jsonResponse(200, { data: { status: 'ok' }, meta: {} }),
      [`${API_BASE}/auth/me`]: meEnvelope(),
    })
    renderAuth()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('mode')).toHaveTextContent('live')
    expect(screen.getByTestId('user')).toHaveTextContent('Demo Credit Officer')
    expect(screen.getByTestId('role')).toHaveTextContent('credit_officer')
    expect(screen.getByTestId('rolecode')).toHaveTextContent('CO')
    expect(screen.getByTestId('scope')).toHaveTextContent('MSME-CC,MSME-TL')
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([`${API_BASE}/meta/health`, `${API_BASE}/auth/me`])
  })

  it('treats an unreachable health endpoint as the static demo, without calling /auth/me', async () => {
    const fetchMock = mockFetchRoutes({ [`${API_BASE}/meta/health`]: () => { throw networkFailure() } })
    renderAuth()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('static'))
    expect(screen.getByTestId('mode')).toHaveTextContent('static')
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([`${API_BASE}/meta/health`])
  })

  it('lands on anonymous when the backend is up but nobody is signed in', async () => {
    mockFetchRoutes({
      [`${API_BASE}/meta/health`]: jsonResponse(200, { data: {}, meta: {} }),
      [`${API_BASE}/auth/me`]: errorResponse(401, { code: 'unauthorized', message: 'Authentication required.' }),
    })
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
  })

  it('reports the forced password change from the session envelope', async () => {
    mockFetchRoutes({
      [`${API_BASE}/meta/health`]: jsonResponse(200, { data: {}, meta: {} }),
      [`${API_BASE}/auth/me`]: meEnvelope({ must_change_password: true }),
    })
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('must')).toHaveTextContent('true'))
  })
})

describe('AuthProvider actions', () => {
  it('signs in and holds the session the server returned', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/login`]: jsonResponse(200, { data: SESSION, meta: {} }),
    })
    renderAuth({ initialMode: 'live' })

    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    await user.click(screen.getByRole('button', { name: 'sign in' }))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent('Demo Credit Officer')
  })

  it('signs out locally even when the logout call fails', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({ [`POST ${API_BASE}/auth/logout`]: () => { throw networkFailure() } })
    renderAuth({ initialMode: 'live', initialUser: SESSION })

    await user.click(screen.getByRole('button', { name: 'sign out' }))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(screen.getByTestId('ended')).toHaveTextContent('SIGNED_OUT')
  })

  it('re-reads /auth/me after a password change so the gate lifts', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/password`]: emptyResponse(204),
      [`${API_BASE}/auth/me`]: meEnvelope({ must_change_password: false, csrf_token: 'csrf-2' }),
    })
    renderAuth({ initialMode: 'live', initialUser: { ...SESSION, must_change_password: true } })

    expect(screen.getByTestId('must')).toHaveTextContent('true')
    await user.click(screen.getByRole('button', { name: 'change' }))
    await waitFor(() => expect(screen.getByTestId('must')).toHaveTextContent('false'))
  })
})

describe('AuthProvider reacts to the auth events from lib/api.js', () => {
  it('ends the session on auth:expired and remembers why', async () => {
    renderAuth({ initialMode: 'live', initialUser: SESSION })
    expect(screen.getByTestId('status')).toHaveTextContent('authenticated')

    act(() => {
      window.dispatchEvent(new CustomEvent(AUTH_EVENT.EXPIRED, { detail: { reason: 'SESSION_IDLE' } }))
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(screen.getByTestId('ended')).toHaveTextContent('SESSION_IDLE')
  })

  it('ends the session on auth:unauthenticated', async () => {
    renderAuth({ initialMode: 'live', initialUser: SESSION })
    act(() => { window.dispatchEvent(new CustomEvent(AUTH_EVENT.UNAUTHENTICATED, { detail: {} })) })
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
  })

  it('raises the password-change gate on auth:password-change', async () => {
    renderAuth({ initialMode: 'live', initialUser: SESSION })
    expect(screen.getByTestId('must')).toHaveTextContent('false')
    act(() => { window.dispatchEvent(new CustomEvent(AUTH_EVENT.PASSWORD_CHANGE, { detail: {} })) })
    await waitFor(() => expect(screen.getByTestId('must')).toHaveTextContent('true'))
  })

  it('re-reads the session on auth:csrf-failed, to pick up a rotated token', async () => {
    const fetchMock = mockFetchRoutes({ [`${API_BASE}/auth/me`]: meEnvelope({ csrf_token: 'csrf-rotated' }) })
    renderAuth({ initialMode: 'live', initialUser: SESSION })
    act(() => { window.dispatchEvent(new CustomEvent(AUTH_EVENT.CSRF_FAILED, { detail: {} })) })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/auth/me`, expect.anything()))
  })
})
