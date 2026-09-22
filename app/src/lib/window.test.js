import { describe, expect, it } from 'vitest'
import { asOfLabel, asOfSuffix, isFrozen, WINDOW_FILTERS, WINDOW_STATE, windowPhrase, windowStatus, windowTone } from './window'

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

describe('windowStatus — the camelCase shape every caller actually passes', () => {
  // `pack.js` normaliseLead renames abandon_ts/contact_by/window_days and does NOT keep the
  // wire spelling, so the snake_case fallbacks were unreachable in the app: a lead with a
  // real abandonment timestamp could still render "Window unknown".
  it('derives the window from a normalised lead’s abandonTs and windowDays', () => {
    const s = windowStatus({ product: 'auto', abandonTs: '2026-09-15T12:00:00Z', windowDays: 3 }, NOW)
    expect(s.days).toBe(3)
    expect(s.abandonedAt).toBe('2026-09-15T12:00:00Z')
    expect(s.state).toBe(WINDOW_STATE.OPEN)
  })

  it('uses a normalised lead’s contactBy as the due date', () => {
    const s = windowStatus({ product: 'home', windowDays: 14, contactBy: '2026-09-20T00:00:00Z' }, NOW)
    expect(s.dueBy).toBe('2026-09-20T00:00:00Z')
    expect(s.daysLeft).toBe(4)
  })

  it('still reports unknown — never expired — when there is no timestamp at all', () => {
    expect(windowStatus({ product: 'home' }, NOW).state).toBe(WINDOW_STATE.UNKNOWN)
  })

  it('surfaces the abandonment the queue row carries when window{} has only due_by', () => {
    const s = windowStatus({
      product: 'home',
      abandonTs: '2026-07-29T07:59:56Z',
      window: { days: 14, due_by: '2026-08-12T07:59:56Z', open: false, expired: true },
    }, NOW)
    expect(s.abandonedAt).toBe('2026-07-29T07:59:56Z')
    expect(s.state).toBe(WINDOW_STATE.EXPIRED)
  })
})


describe('windowStatus — the answer is dated', () => {
  // A published book is a photograph. Its windows were measured at the instant it was
  // scored, and re-measuring them against Date.now() ages a fixed answer a day every day:
  // "3 days left" becomes "closed 372 days ago" without a number in the book changing.
  const SCORED = '2026-09-01T00:00:00+00:00'

  it('prefers the anchor the payload declares over the wall clock', () => {
    const lead = { product: 'education', windowDays: 7, contactBy: '2026-09-07T00:00:00Z', window: { as_of: SCORED } }
    const s = windowStatus(lead)
    expect(s.state).toBe(WINDOW_STATE.OPEN)
    expect(s.daysLeft).toBe(6)
    expect(s.asOf).toBe(SCORED)
    expect(s.asOfFrozen).toBe(true)
  })

  it('reads the same anchor off a normalised lead’s windowAsOf', () => {
    const s = windowStatus({ product: 'education', windowDays: 7, contactBy: '2026-09-07T00:00:00Z', windowAsOf: SCORED })
    expect(s.state).toBe(WINDOW_STATE.OPEN)
    expect(s.asOf).toBe(SCORED)
  })

  it('lets the caller override the payload’s anchor', () => {
    // The screens pass the run's anchor explicitly; tests pass an epoch. Either wins.
    const lead = { product: 'personal', windowDays: 1, contactBy: '2026-09-02T00:00:00Z', window: { as_of: SCORED } }
    expect(windowStatus(lead, NOW).state).toBe(WINDOW_STATE.EXPIRED)
    expect(windowStatus(lead, '2026-09-01T12:00:00Z').state).toBe(WINDOW_STATE.OPEN)
  })

  it('falls back to the wall clock, and claims no anchor when it does', () => {
    // Exactly today's behaviour for a payload that carries no as_of — the fix must not
    // invent a date for a lead that never declared one.
    const s = windowStatus({ product: 'home', windowDays: 14, contactBy: '2026-09-20T00:00:00Z' })
    expect(s.asOf).toBeNull()
    expect(s.asOfFrozen).toBe(false)
    expect(s.state).toBe(Date.parse('2026-09-20T00:00:00Z') >= Date.now() ? WINDOW_STATE.OPEN : WINDOW_STATE.EXPIRED)
  })

  it('calls an anchor frozen only once it is a day or more from now', () => {
    expect(isFrozen('2026-09-01T00:00:00Z', Date.parse('2026-12-01T00:00:00Z'))).toBe(true)
    expect(isFrozen('2026-09-01T00:00:00Z', Date.parse('2026-09-01T06:00:00Z'))).toBe(false)
    expect(isFrozen(null)).toBe(false)
  })

  it('writes the date the same way everywhere, whatever the browser thinks of en-IN', () => {
    expect(asOfLabel(SCORED)).toBe('1 Sep 2026')
    expect(asOfLabel(null)).toBeNull()
    expect(asOfSuffix(SCORED, { now: Date.parse('2026-12-01T00:00:00Z') }))
      .toBe(', as of 1 Sep 2026 (frozen snapshot)')
    expect(asOfSuffix(SCORED, { now: Date.parse('2026-09-01T06:00:00Z') })).toBe(', as of 1 Sep 2026')
    expect(asOfSuffix(null)).toBe('')
  })
})
