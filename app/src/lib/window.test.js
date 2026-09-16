import { describe, expect, it } from 'vitest'
import { WINDOW_FILTERS, WINDOW_STATE, windowPhrase, windowStatus, windowTone } from './window'

const NOW = Date.parse('2026-09-16T12:00:00Z')

describe('windowStatus — the server rules, this only presents', () => {
  it('trusts the server’s open/expired over its own arithmetic', () => {
    // due_by is in the past, but the server said open. A UI that recomputed `expired`
    // from a clock that may be minutes off would contradict the filter that fetched it.
    const lead = { product: 'home', window: { days: 14, due_by: '2026-09-15T00:00:00Z', open: true, expired: false } }
    const s = windowStatus(lead, NOW)
    expect(s.state).toBe(WINDOW_STATE.OPEN)
    expect(s.fromServer).toBe(true)
  })

  it('derives the state when the server sent only a due date', () => {
    const open = windowStatus({ product: 'home', window_days: 14, contact_by: '2026-09-20T00:00:00Z' }, NOW)
    expect(open.state).toBe(WINDOW_STATE.OPEN)
    expect(open.daysLeft).toBe(4)
    expect(open.fromServer).toBe(false)

    const shut = windowStatus({ product: 'personal', window_days: 1, contact_by: '2026-09-10T00:00:00Z' }, NOW)
    expect(shut.state).toBe(WINDOW_STATE.EXPIRED)
    expect(shut.daysOver).toBe(6)
  })

  it('derives the due date from the abandonment timestamp and the product window', () => {
    const s = windowStatus({ product: 'auto', abandon_ts: '2026-09-15T12:00:00Z' }, NOW)
    expect(s.days).toBe(3) // auto: 3 days, from the product table
    expect(s.state).toBe(WINDOW_STATE.OPEN)
    expect(s.daysLeft).toBe(2)
  })

  it('reports UNKNOWN — never EXPIRED — when it cannot place the window', () => {
    // "Expired" tells an RM not to call. Saying it about a lead whose timestamp we simply
    // do not have would suppress a real call for no reason.
    const s = windowStatus({ product: 'home' }, NOW)
    expect(s.state).toBe(WINDOW_STATE.UNKNOWN)
    expect(s.daysLeft).toBeNull()
    expect(s.daysOver).toBeNull()
    expect(windowStatus(null, NOW).state).toBe(WINDOW_STATE.UNKNOWN)
  })

  it('never reports a negative number of days left', () => {
    const s = windowStatus({ product: 'personal', window: { days: 1, due_by: '2026-09-16T11:00:00Z', open: true, expired: false } }, NOW)
    expect(s.daysLeft).toBeGreaterThanOrEqual(0)
  })
})

describe('windowPhrase and windowTone', () => {
  it('phrases each state in words an RM can act on', () => {
    expect(windowPhrase({ state: WINDOW_STATE.OPEN, daysLeft: 3 })).toBe('3 days left')
    expect(windowPhrase({ state: WINDOW_STATE.OPEN, daysLeft: 1 })).toBe('1 day left')
    expect(windowPhrase({ state: WINDOW_STATE.OPEN, daysLeft: 0 })).toBe('Window closes today')
    expect(windowPhrase({ state: WINDOW_STATE.EXPIRED, daysOver: 6 })).toBe('Closed 6 days ago')
    expect(windowPhrase({ state: WINDOW_STATE.UNKNOWN })).toBe('Window unknown')
    expect(windowPhrase(null)).toBe('Window unknown')
  })

  it('warns in amber on the last day and rose once closed', () => {
    expect(windowTone({ state: WINDOW_STATE.OPEN, daysLeft: 5 })).toContain('teal')
    expect(windowTone({ state: WINDOW_STATE.OPEN, daysLeft: 1 })).toContain('amber')
    expect(windowTone({ state: WINDOW_STATE.EXPIRED, daysOver: 2 })).toContain('rose')
    expect(windowTone({ state: WINDOW_STATE.UNKNOWN })).toContain('txt-mid')
  })
})

describe('WINDOW_FILTERS', () => {
  it('offers only the three values the query parameter has', () => {
    // The contract: true = open, false = run out, omitted = both. "Unknown" is not a
    // server bucket, and a filter that silently meant something else would be a lie.
    expect(WINDOW_FILTERS.map((f) => f.value)).toEqual(['', 'true', 'false'])
  })
})
