// The one way this app talks to the RR Squad platform API.
//
// Contract: rrsquad-platform/contracts/openapi.json.
//   * success  -> { data, meta: { request_id, model_run_id, generated_at, provenance_mode } }
//   * failure  -> { error: { code, message, request_id, fields?, reason? } }
//   * session  -> HttpOnly cookie `rrsq_session` + JS-readable `rrsq_csrf`; every
//                 mutating request echoes the CSRF token in the `X-CSRF-Token` header.
//
// Nothing else in the app may call `fetch` against /api/v1 directly: the auth-event
// dispatch below is what makes session expiry, forced password changes and CSRF
// rotation visible to <AuthProvider>, and a bypass would silently lose them.

export const DEFAULT_API_BASE = '/api/v1'

/** Base path for every API call. `VITE_API_BASE` is how the deploy points at nginx. */
export const API_BASE = String(import.meta.env?.VITE_API_BASE || DEFAULT_API_BASE).replace(/\/+$/, '')

export const SESSION_COOKIE = 'rrsq_session' // HttpOnly — never readable here, listed for documentation
export const CSRF_COOKIE = 'rrsq_csrf'
export const CSRF_HEADER = 'X-CSRF-Token'

/** Methods that carry no side effect: safe to retry, exempt from CSRF. */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/** Events <AuthProvider> listens to. Anything may listen; only api.js emits them. */
export const AUTH_EVENT = {
  UNAUTHENTICATED: 'auth:unauthenticated',
  EXPIRED: 'auth:expired',
  PASSWORD_CHANGE: 'auth:password-change',
  CSRF_FAILED: 'auth:csrf-failed',
}

/** Reasons the backend puts alongside `code` (the contract's `code` enum is closed). */
export const REASON = {
  PASSWORD_CHANGE_REQUIRED: 'PASSWORD_CHANGE_REQUIRED',
  CSRF_FAILED: 'CSRF_FAILED',
  SESSION_IDLE: 'SESSION_IDLE',
  SESSION_ABSOLUTE: 'SESSION_ABSOLUTE',
  SESSION_INACTIVE: 'SESSION_INACTIVE',
}

const GENERIC_MESSAGE = {
  0: 'Could not reach the server. Check your connection and try again.',
  400: 'The request was rejected. Please check the values and try again.',
  401: 'Please sign in to continue.',
  403: 'You do not have permission to do that.',
  404: 'Not found.',
  409: 'That conflicts with something that already exists.',
  423: 'This account is temporarily locked after repeated failed sign-ins.',
  429: 'Too many requests. Please wait a moment and try again.',
  500: 'Something went wrong on the server.',
  503: 'The service is temporarily unavailable.',
}

/** A failure that is safe to render to a user. Never carries a stack trace from the server. */
export class ApiError extends Error {
  constructor(status, options = {}) {
    const message = options.message || GENERIC_MESSAGE[status] || 'Request failed.'
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = options.code || null
    this.reason = options.reason || null
    this.requestId = options.requestId || null
    this.fields = options.fields || null
    this.retryAfter = options.retryAfter ?? null // seconds, when the server said
    this.lockedUntil = options.lockedUntil || null // ISO timestamp, when the server said
    this.path = options.path || null
    if (options.cause) this.cause = options.cause
  }

  get isNetwork() { return this.status === 0 }
  get isUnauthenticated() { return this.status === 401 }
  get isForbidden() { return this.status === 403 }
  get isLocked() { return this.status === 423 }
  get isRateLimited() { return this.status === 429 }
  get isServer() { return this.status >= 500 }
  /** True when the session itself ended (idle, absolute, or revoked), at 401 or 403. */
  get isSessionExpiry() { return typeof this.reason === 'string' && this.reason.startsWith('SESSION_') }
  get needsPasswordChange() { return this.reason === REASON.PASSWORD_CHANGE_REQUIRED }
}

/** Read a JS-readable cookie. Returns null when absent (HttpOnly cookies always read null). */
export function readCookie(name) {
  if (typeof document === 'undefined') return null
  const jar = document.cookie || ''
  for (const part of jar.split(';')) {
    const eq = part.indexOf('=')
    if (eq < 0) continue
    if (part.slice(0, eq).trim() !== name) continue
    try {
      return decodeURIComponent(part.slice(eq + 1).trim())
    } catch {
      return part.slice(eq + 1).trim()
    }
  }
  return null
}

export const readCsrfToken = () => readCookie(CSRF_COOKIE)

export function emitAuthEvent(name, detail) {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return
  window.dispatchEvent(new CustomEvent(name, { detail }))
}

function parseRetryAfter(headerValue) {
  if (!headerValue) return null
  const seconds = Number(headerValue)
  if (Number.isFinite(seconds)) return Math.max(0, Math.round(seconds))
  const when = Date.parse(headerValue)
  if (Number.isNaN(when)) return null
  return Math.max(0, Math.round((when - Date.now()) / 1000))
}

function secondsUntil(iso) {
  if (!iso) return null
  const when = Date.parse(iso)
  if (Number.isNaN(when)) return null
  return Math.max(0, Math.round((when - Date.now()) / 1000))
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Turn an auth-shaped failure into the event <AuthProvider> reacts to.
 * `silent` suppresses this — <AuthProvider> uses it for the calls that *are* the reaction
 * (bootstrap /auth/me, the login POST) so a failed sign-in cannot loop.
 */
function dispatchAuthEvent(error) {
  const detail = { status: error.status, reason: error.reason, requestId: error.requestId }
  if (error.isSessionExpiry) {
    emitAuthEvent(AUTH_EVENT.EXPIRED, detail)
    return
  }
  if (error.status === 401) {
    emitAuthEvent(AUTH_EVENT.UNAUTHENTICATED, detail)
    return
  }
  if (error.status === 403 && error.reason === REASON.PASSWORD_CHANGE_REQUIRED) {
    emitAuthEvent(AUTH_EVENT.PASSWORD_CHANGE, detail)
    return
  }
  if (error.status === 403 && error.reason === REASON.CSRF_FAILED) {
    emitAuthEvent(AUTH_EVENT.CSRF_FAILED, detail)
  }
}

async function readBody(response) {
  const type = response.headers?.get?.('content-type') || ''
  if (response.status === 204 || response.status === 205) return null
  if (!type.includes('json')) {
    try {
      const text = await response.text()
      return text ? { _text: text } : null
    } catch {
      return null
    }
  }
  try {
    return await response.json()
  } catch {
    return null
  }
}

function errorFromResponse(response, body, path) {
  const envelope = (body && typeof body === 'object' && body.error) || {}
  const retryAfter =
    parseRetryAfter(response.headers?.get?.('retry-after')) ??
    (Number.isFinite(Number(envelope.retry_after)) ? Number(envelope.retry_after) : null) ??
    secondsUntil(envelope.locked_until)
  return new ApiError(response.status, {
    code: envelope.code || null,
    reason: envelope.reason || null,
    message: envelope.message || undefined,
    requestId: envelope.request_id || response.headers?.get?.('x-request-id') || null,
    fields: envelope.fields || null,
    retryAfter,
    lockedUntil: envelope.locked_until || null,
    path,
  })
}

/**
 * Call the platform API.
 *
 * @param {string} path      route below the API base, e.g. `/auth/me`
 * @param {object} [options]
 * @param {string} [options.method='GET']
 * @param {object} [options.body]          serialised as JSON
 * @param {AbortSignal} [options.signal]   caller cancellation; aborts rethrow as-is
 * @param {object} [options.headers]
 * @param {boolean} [options.silent=false] do not dispatch auth events for this call
 * @param {boolean} [options.retry]        default: true for GET/HEAD, false otherwise
 * @param {number} [options.retryDelayMs=300]
 * @param {number} [options.timeoutMs=20000]
 * @returns {Promise<{data: any, meta: object}>} the contract envelope (204 -> data null)
 * @throws {ApiError} on any non-2xx, network failure or timeout
 */
export async function apiFetch(path, options = {}) {
  const {
    method = 'GET',
    body,
    signal,
    headers = {},
    silent = false,
    retryDelayMs = 300,
    timeoutMs = 20000,
    credentials = 'include',
  } = options
  const verb = String(method).toUpperCase()
  const idempotent = SAFE_METHODS.has(verb)
  const retry = options.retry ?? idempotent
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`

  const requestHeaders = { Accept: 'application/json', ...headers }
  if (body !== undefined && !requestHeaders['Content-Type']) {
    requestHeaders['Content-Type'] = 'application/json'
  }
  if (!idempotent) {
    // Double-submit: the cookie is readable, so the header can echo it. A cross-site
    // form post cannot read the cookie, so it cannot produce the header.
    const token = readCsrfToken()
    if (token && !requestHeaders[CSRF_HEADER]) requestHeaders[CSRF_HEADER] = token
  }

  const attempt = async () => {
    const controller = typeof AbortController === 'function' ? new AbortController() : null
    let timedOut = false
    let timer = null
    if (controller) {
      if (signal) {
        if (signal.aborted) controller.abort(signal.reason)
        else signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true })
      }
      if (timeoutMs > 0) {
        timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
      }
    }
    try {
      const response = await fetch(url, {
        method: verb,
        credentials,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller ? controller.signal : signal,
      })
      const parsed = await readBody(response)
      if (!response.ok) throw errorFromResponse(response, parsed, path)
      if (parsed && typeof parsed === 'object' && 'data' in parsed) {
        return { data: parsed.data, meta: parsed.meta || {} }
      }
      return { data: parsed === null ? null : parsed, meta: {} }
    } catch (error) {
      if (error instanceof ApiError) throw error
      if (error && error.name === 'AbortError') {
        if (!timedOut) throw error // the caller cancelled — let them recognise their own abort
        throw new ApiError(0, { code: 'timeout', message: 'The server took too long to respond.', path, cause: error })
      }
      throw new ApiError(0, { code: 'network_error', path, cause: error })
    } finally {
      if (timer) clearTimeout(timer)
    }
  }

  let error
  try {
    return await attempt()
  } catch (first) {
    if (first && first.name === 'AbortError') throw first
    error = first
    const retryable = first instanceof ApiError && (first.isNetwork || first.isServer)
    if (!retry || !retryable) {
      if (!silent && first instanceof ApiError) dispatchAuthEvent(first)
      throw first
    }
  }

  if (retryDelayMs > 0) await sleep(retryDelayMs)
  try {
    return await attempt()
  } catch (second) {
    if (second && second.name === 'AbortError') throw second
    if (!silent && second instanceof ApiError) dispatchAuthEvent(second)
    throw second instanceof ApiError ? second : error
  }
}

/** `apiFetch` when the caller only wants the payload. */
export async function apiData(path, options) {
  const { data } = await apiFetch(path, options)
  return data
}
