import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  API_BASE, AUTH_EVENT, ApiError, CSRF_HEADER, apiFetch, readCookie,
} from './api'
import { emptyResponse, errorResponse, jsonResponse, mockFetchSequence, networkFailure } from '../test/http'

const ENVELOPE = { data: { ok: true }, meta: { request_id: 'req-1', provenance_mode: 'fixture' } }

function listen(...names) {
  const seen = []
  const handlers = names.map((name) => {
    const handler = (event) => seen.push({ name, detail: event.detail })
    window.addEventListener(name, handler)
    return [name, handler]
  })
  return {
    seen,
    stop: () => handlers.forEach(([name, handler]) => window.removeEventListener(name, handler)),
  }
}

describe('apiFetch', () => {
  let events
  beforeEach(() => {
    events = listen(
      AUTH_EVENT.UNAUTHENTICATED, AUTH_EVENT.EXPIRED,
      AUTH_EVENT.PASSWORD_CHANGE, AUTH_EVENT.CSRF_FAILED,
    )
  })
  afterEach(() => { events.stop(); vi.unstubAllGlobals() })

  it('calls the contract base path and returns the envelope', async () => {
    const fetchMock = mockFetchSequence(jsonResponse(200, ENVELOPE))
    const result = await apiFetch('/drishti/portfolio')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE}/drishti/portfolio`)
    expect(init.method).toBe('GET')
    expect(init.credentials).toBe('include')
    expect(result).toEqual({ data: { ok: true }, meta: ENVELOPE.meta })
  })

  it('sends no CSRF header on a GET', async () => {
    document.cookie = 'rrsq_csrf=token-abc; path=/'
    const fetchMock = mockFetchSequence(jsonResponse(200, ENVELOPE))
    await apiFetch('/auth/me')
    expect(fetchMock.mock.calls[0][1].headers[CSRF_HEADER]).toBeUndefined()
  })

  it('echoes the rrsq_csrf cookie in X-CSRF-Token on every mutating request', async () => {
    document.cookie = 'rrsq_csrf=token-abc; path=/'
    expect(readCookie('rrsq_csrf')).toBe('token-abc')

    const fetchMock = mockFetchSequence(emptyResponse(204))
    const result = await apiFetch('/auth/logout', { method: 'POST' })

    const init = fetchMock.mock.calls[0][1]
    expect(init.headers[CSRF_HEADER]).toBe('token-abc')
    expect(init.method).toBe('POST')
    expect(result).toEqual({ data: null, meta: {} })
  })

  it('serialises a JSON body and sets the content type', async () => {
    const fetchMock = mockFetchSequence(jsonResponse(200, ENVELOPE))
    await apiFetch('/auth/login', { method: 'POST', body: { username: 'co.demo', password: 'x' } })
    const init = fetchMock.mock.calls[0][1]
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ username: 'co.demo', password: 'x' })
  })

  it('maps a plain 401 to ApiError and dispatches auth:unauthenticated', async () => {
    mockFetchSequence(errorResponse(401, { code: 'unauthorized', message: 'Authentication required.' }))
    const error = await apiFetch('/drishti/portfolio', { retry: false }).catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(401)
    expect(error.code).toBe('unauthorized')
    expect(error.requestId).toBe('req-test')
    expect(events.seen.map((e) => e.name)).toEqual([AUTH_EVENT.UNAUTHENTICATED])
  })

  it.each(['SESSION_IDLE', 'SESSION_ABSOLUTE'])('maps a 401 with reason %s to auth:expired', async (reason) => {
    mockFetchSequence(errorResponse(401, { code: 'unauthorized', message: 'Your session has ended.', reason }))
    const error = await apiFetch('/drishti/portfolio', { retry: false }).catch((e) => e)

    expect(error.isSessionExpiry).toBe(true)
    expect(events.seen).toEqual([{ name: AUTH_EVENT.EXPIRED, detail: { status: 401, reason, requestId: 'req-test' } }])
  })

  it('maps 403 PASSWORD_CHANGE_REQUIRED to auth:password-change', async () => {
    mockFetchSequence(errorResponse(403, {
      code: 'forbidden', message: 'You must change your password.', reason: 'PASSWORD_CHANGE_REQUIRED',
    }))
    const error = await apiFetch('/drishti/portfolio', { retry: false }).catch((e) => e)

    expect(error.status).toBe(403)
    expect(error.needsPasswordChange).toBe(true)
    expect(events.seen.map((e) => e.name)).toEqual([AUTH_EVENT.PASSWORD_CHANGE])
  })

  it('maps 403 CSRF_FAILED to auth:csrf-failed', async () => {
    mockFetchSequence(errorResponse(403, { code: 'forbidden', message: 'CSRF token missing or invalid.', reason: 'CSRF_FAILED' }))
    await apiFetch('/drishti/threshold', { method: 'PUT', body: {} }).catch((e) => e)
    expect(events.seen.map((e) => e.name)).toEqual([AUTH_EVENT.CSRF_FAILED])
  })

  it('maps a plain 403 to an error with no auth event', async () => {
    mockFetchSequence(errorResponse(403, { code: 'forbidden', message: 'Your role does not permit this.' }))
    const error = await apiFetch('/admin/users', { retry: false }).catch((e) => e)
    expect(error.isForbidden).toBe(true)
    expect(events.seen).toEqual([])
  })

  it('reads Retry-After off a 423 lockout', async () => {
    mockFetchSequence(errorResponse(423, { code: 'locked', message: 'Locked.' }, { 'retry-after': '900' }))
    const error = await apiFetch('/auth/login', { method: 'POST', body: {} }).catch((e) => e)

    expect(error.status).toBe(423)
    expect(error.isLocked).toBe(true)
    expect(error.retryAfter).toBe(900)
  })

  it('derives retry-after from locked_until when the header is absent', async () => {
    const lockedUntil = new Date(Date.now() + 120_000).toISOString()
    mockFetchSequence(errorResponse(423, { code: 'locked', message: 'Locked.', locked_until: lockedUntil }))
    const error = await apiFetch('/auth/login', { method: 'POST', body: {} }).catch((e) => e)

    expect(error.retryAfter).toBeGreaterThan(110)
    expect(error.retryAfter).toBeLessThanOrEqual(120)
    expect(error.lockedUntil).toBe(lockedUntil)
  })

  it('surfaces 5xx as a server error for the boundary, after one retry', async () => {
    const fetchMock = mockFetchSequence(
      errorResponse(500, { code: 'internal_error', message: 'Something went wrong.' }),
      errorResponse(500, { code: 'internal_error', message: 'Something went wrong.' }),
    )
    const error = await apiFetch('/drishti/metrics', { retryDelayMs: 0 }).catch((e) => e)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(error.isServer).toBe(true)
    expect(events.seen).toEqual([])
  })

  it('returns the retry when the second attempt succeeds', async () => {
    const fetchMock = mockFetchSequence(errorResponse(503, { code: 'upstream_error', message: 'Degraded.' }), jsonResponse(200, ENVELOPE))
    const result = await apiFetch('/meta/health', { retryDelayMs: 0 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.data).toEqual({ ok: true })
  })

  it('never retries a mutating request', async () => {
    const fetchMock = mockFetchSequence(errorResponse(500, { code: 'internal_error', message: 'boom' }))
    await apiFetch('/drishti/account/A1/action', { method: 'POST', body: {}, retryDelayMs: 0 }).catch(() => {})
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('retries a network failure once and then reports it as a network error', async () => {
    const fetchMock = mockFetchSequence(networkFailure(), networkFailure())
    const error = await apiFetch('/meta/health', { retryDelayMs: 0 }).catch((e) => e)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(error.isNetwork).toBe(true)
    expect(error.code).toBe('network_error')
  })

  it('suppresses auth events when asked (the bootstrap and login paths)', async () => {
    mockFetchSequence(errorResponse(401, { code: 'unauthorized', message: 'nope' }))
    await apiFetch('/auth/me', { silent: true, retry: false }).catch(() => {})
    expect(events.seen).toEqual([])
  })

  it('rethrows the caller’s AbortError unchanged so a cancelled request can be ignored', async () => {
    vi.stubGlobal('fetch', vi.fn((url, init) => new Promise((_, reject) => {
      init.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
    })))
    const controller = new AbortController()
    const pending = apiFetch('/drishti/portfolio', { signal: controller.signal })
    controller.abort()
    const error = await pending.catch((e) => e)
    expect(error.name).toBe('AbortError')
    expect(error).not.toBeInstanceOf(ApiError)
  })
})
