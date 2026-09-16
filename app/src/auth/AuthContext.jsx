// Who is signed in, and everything that can end that.
//
// One provider owns: the bootstrap probe (static demo vs live backend), the session
// itself, the forced password-change gate, the idle watchdog, and the four auth events
// lib/api.js emits when the server says the session is over. Screens never call
// /auth/* directly — they call these methods, so every path through sign-in and sign-out
// is the same path.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { AUTH_EVENT, apiFetch } from '../lib/api'
import { MODE, resolveMode } from '../lib/mode'
import { ROLE_CODE, normaliseRole, roleLabel } from './roles'
import useIdleTimeout, { DEFAULT_IDLE_MS, DEFAULT_WARNING_MS } from './useIdleTimeout'
import IdleWarningModal from './IdleWarningModal'

export const AUTH_STATUS = {
  BOOTSTRAPPING: 'bootstrapping',
  ANONYMOUS: 'anonymous',
  AUTHENTICATED: 'authenticated',
  STATIC: 'static',
}

/** Why a session ended, for the message shown on the login screen. */
export const ENDED = {
  IDLE: 'SESSION_IDLE',
  ABSOLUTE: 'SESSION_ABSOLUTE',
  INACTIVE: 'SESSION_INACTIVE',
  SIGNED_OUT: 'SIGNED_OUT',
}

const AuthContext = createContext(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth() must be used inside <AuthProvider>')
  return value
}

export function AuthProvider({
  children,
  idleMs = DEFAULT_IDLE_MS,
  warningMs = DEFAULT_WARNING_MS,
  // Tests and Storybook can skip the network probe entirely.
  initialMode = null,
  initialUser = null,
}) {
  const [mode, setMode] = useState(initialMode)
  const [status, setStatus] = useState(
    initialMode === MODE.STATIC
      ? AUTH_STATUS.STATIC
      : initialUser
        ? AUTH_STATUS.AUTHENTICATED
        : initialMode
          ? AUTH_STATUS.ANONYMOUS
          : AUTH_STATUS.BOOTSTRAPPING,
  )
  const [user, setUser] = useState(initialUser)
  const [endedReason, setEndedReason] = useState(null)
  const [bootstrapError, setBootstrapError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const applySession = useCallback((data) => {
    setUser(data)
    setStatus(AUTH_STATUS.AUTHENTICATED)
    setEndedReason(null)
    setBootstrapError(null)
  }, [])

  const clearSession = useCallback((reason = null) => {
    setUser(null)
    setStatus(AUTH_STATUS.ANONYMOUS)
    if (reason) setEndedReason(reason)
  }, [])

  // ---- bootstrap -----------------------------------------------------------------
  useEffect(() => {
    if (initialMode) return undefined
    const controller = new AbortController()
    let live = true
    ;(async () => {
      let resolved = MODE.LIVE
      try {
        resolved = await resolveMode({ signal: controller.signal })
      } catch (error) {
        if (error?.name === 'AbortError') return
      }
      if (!live) return
      setMode(resolved)
      if (resolved === MODE.STATIC) {
        setStatus(AUTH_STATUS.STATIC)
        return
      }
      try {
        const { data } = await apiFetch('/auth/me', { silent: true, retry: false, signal: controller.signal })
        if (!live) return
        applySession(data)
      } catch (error) {
        if (error?.name === 'AbortError' || !live) return
        // A 401 here is the normal "not signed in yet" answer, not a failure.
        if (error?.isNetwork) setBootstrapError(error)
        setUser(null)
        setStatus(AUTH_STATUS.ANONYMOUS)
      }
    })()
    return () => { live = false; controller.abort() }
  }, [initialMode, applySession])

  // ---- actions -------------------------------------------------------------------
  const refresh = useCallback(async () => {
    const { data } = await apiFetch('/auth/me', { silent: true, retry: false })
    applySession(data)
    return data
  }, [applySession])

  const login = useCallback(async (username, password) => {
    const { data } = await apiFetch('/auth/login', {
      method: 'POST',
      body: { username, password },
      silent: true,
      retry: false,
    })
    applySession(data)
    return data
  }, [applySession])

  const logout = useCallback(async (reason = ENDED.SIGNED_OUT) => {
    try {
      await apiFetch('/auth/logout', { method: 'POST', silent: true, retry: false })
    } catch {
      // The cookie may already be dead server-side; local sign-out still has to happen.
    }
    clearSession(reason)
  }, [clearSession])

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    await apiFetch('/auth/password', {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword },
      silent: true,
      retry: false,
    })
    // The backend keeps this session and revokes the user's others; re-read so the
    // must_change_password gate lifts and the CSRF token in state is current.
    return refresh()
  }, [refresh])

  // ---- the four auth events from lib/api.js --------------------------------------
  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const onExpired = (event) => clearSession(event?.detail?.reason || ENDED.ABSOLUTE)
    const onUnauthenticated = () => clearSession(null)
    const onPasswordChange = () => setUser((u) => (u ? { ...u, must_change_password: true } : u))
    const onCsrfFailed = () => { refresh().catch(() => clearSession(null)) }

    window.addEventListener(AUTH_EVENT.EXPIRED, onExpired)
    window.addEventListener(AUTH_EVENT.UNAUTHENTICATED, onUnauthenticated)
    window.addEventListener(AUTH_EVENT.PASSWORD_CHANGE, onPasswordChange)
    window.addEventListener(AUTH_EVENT.CSRF_FAILED, onCsrfFailed)
    return () => {
      window.removeEventListener(AUTH_EVENT.EXPIRED, onExpired)
      window.removeEventListener(AUTH_EVENT.UNAUTHENTICATED, onUnauthenticated)
      window.removeEventListener(AUTH_EVENT.PASSWORD_CHANGE, onPasswordChange)
      window.removeEventListener(AUTH_EVENT.CSRF_FAILED, onCsrfFailed)
    }
  }, [clearSession, refresh])

  // ---- idle watchdog --------------------------------------------------------------
  const idle = useIdleTimeout({
    enabled: status === AUTH_STATUS.AUTHENTICATED,
    idleMs,
    warningMs,
    onExpire: () => { logout(ENDED.IDLE) },
    onStayAlive: () => apiFetch('/auth/me', { silent: true, retry: false }).then(({ data }) => applySession(data)),
  })

  const value = useMemo(() => {
    const role = normaliseRole(user?.role)
    return {
      mode,
      status,
      ready: status !== AUTH_STATUS.BOOTSTRAPPING,
      isStatic: status === AUTH_STATUS.STATIC,
      isAuthenticated: status === AUTH_STATUS.AUTHENTICATED,
      user,
      username: user?.username || null,
      fullName: user?.full_name || user?.username || null,
      role,
      roleCode: role ? ROLE_CODE[role] : null,
      roleLabel: role ? roleLabel(role) : null,
      roles: role ? [role] : [],
      scope: user?.scope || [],
      mustChangePassword: Boolean(user?.must_change_password),
      expiresAt: user?.expires_at || null,
      csrfToken: user?.csrf_token || null,
      endedReason,
      bootstrapError,
      login,
      logout,
      changePassword,
      refresh,
      idle,
    }
  }, [mode, status, user, endedReason, bootstrapError, login, logout, changePassword, refresh, idle])

  return (
    <AuthContext.Provider value={value}>
      {children}
      <IdleWarningModal
        open={status === AUTH_STATUS.AUTHENTICATED && idle.warning}
        secondsLeft={idle.secondsLeft}
        pinging={idle.pinging}
        onStayAlive={idle.stayAlive}
        onSignOut={() => logout(ENDED.SIGNED_OUT)}
      />
    </AuthContext.Provider>
  )
}

export default AuthProvider
