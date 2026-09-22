// The contact window: how long a drop-off lead is still worth calling.
//
// Mentor mandate, via plan SD-S4: conversion is a DISBURSEMENT inside the abandoned
// product's decision window after an RM contact. The window runs from the moment the
// customer abandoned the application, for the number of days that product allows
// (personal 1, gold 1, auto 3, education 7, home 14, lap 14).
//
// Three rules this file exists to keep honest:
//
//  1. The SERVER decides. `GET /sanket/queue` and `/sanket/lead/{id}` both return a
//     `window` object with `open` and `expired` already computed, and the queue's
//     `window_due` filter is the server's own predicate. Everything here is either a
//     presentation detail (how many days are left, how to phrase it) or the fallback for
//     the static bundle, which has no server to ask.
//  2. `open` and `expired` are NOT each other's negation on the wire — a lead with no
//     `abandon_ts` has neither. A window we cannot compute is reported as unknown, never
//     as expired, because "expired" tells an RM not to call.
//  3. **The answer is dated.** A book is scored at an instant and its windows were
//     measured against that instant. `Date.now()` is the wrong anchor for a published
//     snapshot: it ages a fixed answer a day every day, and turns "3 days left" into
//     "closed 372 days ago" without a single number in the book having changed. So the
//     anchor is `window.as_of` — the instant the server says it answered as of — and the
//     wall clock is only the fallback for a payload that carries none.

import { WINDOW_DAYS } from './fmt'

export const WINDOW_STATE = { OPEN: 'open', EXPIRED: 'expired', UNKNOWN: 'unknown' }

const MS_PER_DAY = 86_400_000

const parse = (value) => {
  if (!value) return null
  const t = Date.parse(value)
  return Number.isNaN(t) ? null : t
}

/** The declared anchor among these, if any: a parseable instant, not a bare epoch. */
const declared = (...values) => values.find((v) => typeof v === 'string' && parse(v) != null) ?? null

/**
 * Is an answer dated to this anchor a frozen one?
 *
 * Only when the anchor is a day or more from the wall clock. A nightly run scoring last
 * night's book declares last night, and calling that "a frozen snapshot" would be noise;
 * a book cut on 1 September and read in December is exactly what the phrase is for. One
 * rule, so the queue, the drawer and the dashboard cannot disagree about the wording.
 */
export function isFrozen(asOf, now = Date.now()) {
  const t = parse(asOf)
  return t != null && Math.abs(now - t) >= MS_PER_DAY
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * "1 Sep 2026", the form every "as of" in this app is written in.
 *
 * Spelled out rather than handed to `toLocaleDateString`: the anchor is an instant the
 * server declared in UTC, and the label has to name the same day the data does, in every
 * browser and every reader's timezone. (Node and the browsers do not even agree on the
 * abbreviation — `en-IN` renders September as "Sept" in one and "Sep" in the other.)
 */
export function asOfLabel(asOf) {
  const t = parse(asOf)
  if (t == null) return null
  const d = new Date(t)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** ", as of 1 Sep 2026 (frozen snapshot)" — or nothing at all. Appended, never standalone. */
export function asOfSuffix(asOf, { now = Date.now(), frozenNote = true } = {}) {
  const label = asOfLabel(asOf)
  if (!label) return ''
  if (!isFrozen(asOf, now)) return `, as of ${label}`
  return `, as of ${label}${frozenNote ? ' (frozen snapshot)' : ''}`
}

/**
 * Normalise whatever a lead carries into one shape the UI can render.
 *
 * @param {object} lead            a queue row or lead detail (live) or a packed lead (static)
 * @param {number|string} [now]    the instant to answer as of: epoch ms (tests inject a
 *   "today"), or an ISO instant (a screen passing the run's own anchor). Omitted, the
 *   lead's own `window.as_of` is used, and only then the wall clock.
 * @returns {{state: string, days: number|null, dueBy: string|null, abandonedAt: string|null,
 *            daysLeft: number|null, daysOver: number|null, fromServer: boolean,
 *            asOf: string|null, asOfFrozen: boolean}}
 */
export function windowStatus(lead, now) {
  if (!lead) return { state: WINDOW_STATE.UNKNOWN, days: null, dueBy: null, abandonedAt: null, daysLeft: null, daysOver: null, fromServer: false, asOf: null, asOfFrozen: false }

  const w = lead.window || null
  // The anchor, in precedence: what the caller asked for, what the payload says it was
  // answered as of, the wall clock. `asOf` is null in the last case on purpose — there is
  // no declared instant to name, and the UI must not claim one.
  const asOf = declared(now, w?.as_of, lead.windowAsOf, lead.window_as_of)
  const anchor = typeof now === 'number' && Number.isFinite(now) ? now : (parse(asOf) ?? Date.now())
  // Every caller passes a lead through `pack.js` `normaliseLead` first, which renames these
  // three to camelCase and does not keep the wire spelling — so the snake_case fallbacks
  // below were unreachable in the app and only ever fired in tests that build a raw row.
  // Both spellings are read now: a queue row's `window` carries no `abandoned_at`, and the
  // lead's own `abandonTs` is exactly what the fallback exists to use.
  const rawDays = w?.days ?? lead.windowDays ?? lead.window_days
  const days = Number.isFinite(Number(rawDays)) ? Number(rawDays) : WINDOW_DAYS[lead.product] ?? null

  const abandonedAt = w?.abandoned_at || lead.abandonTs || lead.abandon_ts || null
  // The static pack carries `contact_by` (a date) where the API carries `window.due_by`.
  const dueBy = w?.due_by || lead.contactBy || lead.contact_by || null

  // The server already ruled. Trust it — a UI that recomputes `expired` from a clock that
  // may be minutes off would contradict the filter the same screen just used.
  let state = WINDOW_STATE.UNKNOWN
  if (w && (w.open === true || w.expired === true)) {
    state = w.open === true ? WINDOW_STATE.OPEN : WINDOW_STATE.EXPIRED
  } else {
    const due = parse(dueBy) ?? (parse(abandonedAt) != null && days != null ? parse(abandonedAt) + days * MS_PER_DAY : null)
    if (due != null) state = due >= anchor ? WINDOW_STATE.OPEN : WINDOW_STATE.EXPIRED
  }

  const due = parse(dueBy) ?? (parse(abandonedAt) != null && days != null ? parse(abandonedAt) + days * MS_PER_DAY : null)
  const diffDays = due == null ? null : Math.ceil((due - anchor) / MS_PER_DAY)

  return {
    state,
    days,
    dueBy,
    abandonedAt,
    daysLeft: state === WINDOW_STATE.OPEN && diffDays != null ? Math.max(0, diffDays) : null,
    daysOver: state === WINDOW_STATE.EXPIRED && diffDays != null ? Math.max(0, -diffDays) : null,
    fromServer: Boolean(w && (w.open === true || w.expired === true)),
    asOf,
    asOfFrozen: isFrozen(asOf),
  }
}

/** One short phrase for a badge. Never invents urgency it cannot evidence. */
export function windowPhrase(status) {
  if (!status || status.state === WINDOW_STATE.UNKNOWN) return 'Window unknown'
  if (status.state === WINDOW_STATE.OPEN) {
    if (status.daysLeft == null) return 'Window open'
    if (status.daysLeft === 0) return 'Window closes today'
    return `${status.daysLeft} day${status.daysLeft === 1 ? '' : 's'} left`
  }
  if (status.daysOver == null) return 'Window closed'
  if (status.daysOver === 0) return 'Window closed today'
  return `Closed ${status.daysOver} day${status.daysOver === 1 ? '' : 's'} ago`
}

/** Tailwind classes for the badge, matched to the phrase. */
export function windowTone(status) {
  switch (status?.state) {
    case WINDOW_STATE.OPEN:
      return status.daysLeft != null && status.daysLeft <= 1
        ? 'bg-signal-amber/15 text-signal-amber border-signal-amber/40'
        : 'bg-signal-teal/15 text-signal-teal border-signal-teal/40'
    case WINDOW_STATE.EXPIRED:
      return 'bg-signal-rose/10 text-signal-rose border-signal-rose/40'
    default:
      return 'bg-ink-600 text-txt-mid border-line-strong'
  }
}

/**
 * The `window_due` query value for a UI filter.
 * The contract: true = the window is still OPEN, false = it has run out, omitted = both.
 * "unknown" is deliberately NOT expressible as a filter — the server has no such bucket,
 * and a UI filter that silently means something else is a lie about the data.
 */
export const WINDOW_FILTERS = [
  { value: '', label: 'Any window' },
  { value: 'true', label: 'Window open' },
  { value: 'false', label: 'Window closed' },
]
