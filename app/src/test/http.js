// Minimal Response stand-in. Deliberately not undici's Response: these tests are about
// what lib/api.js does with a response, not about the platform's fetch implementation.
import { vi } from 'vitest'

export function headers(map = {}) {
  const lower = Object.fromEntries(Object.entries(map).map(([k, v]) => [k.toLowerCase(), String(v)]))
  return { get: (name) => lower[String(name).toLowerCase()] ?? null }
}

export function jsonResponse(status, body, extraHeaders = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: headers({ 'content-type': 'application/json', ...extraHeaders }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

export function emptyResponse(status = 204, extraHeaders = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: headers(extraHeaders),
    json: async () => { throw new Error('no body') },
    text: async () => '',
  }
}

export function errorResponse(status, error, extraHeaders = {}) {
  return jsonResponse(status, { error: { request_id: 'req-test', ...error } }, extraHeaders)
}

/** Queue of responses (or thrown errors), consumed one per fetch call. */
export function mockFetchSequence(...entries) {
  const fetchMock = vi.fn(async () => {
    const next = entries.shift()
    if (next === undefined) throw new Error('fetch called more times than the test queued')
    if (next instanceof Error) throw next
    return next
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Route table keyed by "METHOD /path" or "/path". */
export function mockFetchRoutes(routes) {
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase()
    const key = `${method} ${url}`
    const handler = routes[key] ?? routes[url]
    if (!handler) throw new Error(`no mock route for ${key}`)
    return typeof handler === 'function' ? handler(url, init) : handler
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export const networkFailure = () => Object.assign(new TypeError('Failed to fetch'), { name: 'TypeError' })
