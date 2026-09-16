import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { API_BASE } from '../lib/api'
import { AuthProvider } from '../auth/AuthContext'
import RequireAuth from '../auth/RequireAuth'
import Login, { safeReturnTo } from './Login'
import { isInsecureContext } from '../components/InsecureContextNotice'
import { errorResponse, jsonResponse, mockFetchRoutes } from '../test/http'

const SESSION = {
  username: 'co.demo', full_name: 'Demo Credit Officer', role: 'credit_officer',
  scope: [], must_change_password: false, csrf_token: 'c',
  expires_at: new Date(Date.now() + 3600_000).toISOString(),
}

function renderLogin(entries = ['/login']) {
  return render(
    <AuthProvider initialMode="live">
      <MemoryRouter initialEntries={entries} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/watchlist" element={<RequireAuth><p>Watch-list</p></RequireAuth>} />
          <Route path="/risk" element={<RequireAuth><p>Portfolio risk</p></RequireAuth>} />
          <Route path="/change-password" element={<p>Change your password</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

const signIn = async (user, password = 'correct-horse-battery') => {
  await user.type(screen.getByLabelText('Username'), 'co.demo')
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: /sign in/i }))
}

afterEach(() => vi.unstubAllGlobals())

describe('Login', () => {
  it('renders a labelled, autocompletable form', () => {
    mockFetchRoutes({})
    renderLogin()
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toHaveAttribute('autocomplete', 'username')
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password')
  })

  it('signs in and lands on the screen the user originally asked for', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({ [`POST ${API_BASE}/auth/login`]: jsonResponse(200, { data: SESSION, meta: {} }) })
    renderLogin(['/login?next=%2Frisk'])

    await signIn(user)
    await waitFor(() => expect(screen.getByText('Portfolio risk')).toBeInTheDocument())
  })

  it('sends a user with a temporary password to the change-password screen', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/login`]: jsonResponse(200, { data: { ...SESSION, must_change_password: true }, meta: {} }),
    })
    renderLogin()

    await signIn(user)
    await waitFor(() => expect(screen.getByText('Change your password')).toBeInTheDocument())
  })

  it('shows one generic failure that cannot be used to enumerate usernames', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/login`]: errorResponse(401, { code: 'unauthorized', message: 'Sign-in failed.' }),
    })
    renderLogin()

    await signIn(user, 'wrong-password')
    const alert = await screen.findByTestId('login-error')
    expect(alert).toHaveTextContent('Check your username and password')
    expect(alert.textContent).not.toMatch(/no such user|unknown user|does not exist|user not found/i)
    // and the password field is cleared, so a shoulder-surfer gains nothing from the retry
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('announces a lockout with a live countdown and disables the button', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/login`]: errorResponse(
        423, { code: 'locked', message: 'Locked.' }, { 'retry-after': '900' },
      ),
    })
    renderLogin()

    await signIn(user, 'wrong-password')
    const alert = await screen.findByTestId('login-error')
    expect(alert).toHaveTextContent('temporarily locked')
    expect(alert).toHaveTextContent('15:00')
    expect(screen.getByRole('alert')).toBe(alert.closest('[role="alert"]') || alert.parentElement)
    expect(screen.getByRole('button', { name: /locked/i })).toBeDisabled()
  })

  it('distinguishes a rate limit from a lockout', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({
      [`POST ${API_BASE}/auth/login`]: errorResponse(429, { code: 'rate_limited', message: 'Slow down.' }, { 'retry-after': '30' }),
    })
    renderLogin()

    await signIn(user)
    const alert = await screen.findByTestId('login-error')
    expect(alert).toHaveTextContent('Too many sign-in attempts')
    expect(alert).toHaveTextContent('30s')
  })

  it('says so plainly when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockFetchRoutes({ [`POST ${API_BASE}/auth/login`]: () => { throw new TypeError('Failed to fetch') } })
    renderLogin()

    await signIn(user)
    expect(await screen.findByTestId('login-error')).toHaveTextContent('Could not reach the server')
  })
})

describe('safeReturnTo', () => {
  it.each([
    ['/risk', '/risk'],
    ['/watchlist?account=A1', '/watchlist?account=A1'],
    ['//evil.example/phish', '/'],
    ['https://evil.example', '/'],
    ['', '/'],
    [null, '/'],
  ])('%s -> %s', (input, expected) => {
    expect(safeReturnTo(input)).toBe(expected)
  })
})

describe('isInsecureContext', () => {
  it.each([
    [{ protocol: 'https:', hostname: 'innobox.idbi.bank.in' }, false],
    [{ protocol: 'http:', hostname: 'localhost' }, false],
    [{ protocol: 'http:', hostname: '127.0.0.1' }, false],
    [{ protocol: 'http:', hostname: '192.0.2.10' }, true],
    [{ protocol: 'http:', hostname: 'drishti.example.com' }, true],
  ])('%o -> %s', (location, expected) => {
    expect(isInsecureContext(location)).toBe(expected)
  })
})
