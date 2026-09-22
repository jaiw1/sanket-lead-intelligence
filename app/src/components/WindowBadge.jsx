import { Clock } from 'lucide-react'
import { asOfSuffix, windowPhrase, windowStatus, windowTone, WINDOW_STATE } from '../lib/window'
import { WINDOW_DAYS } from '../lib/fmt'

/**
 * How long this lead is still worth calling.
 *
 * The mentors' per-product window is the product's whole point, so it is a first-class
 * badge rather than a column of dates: `personal` and `gold` close in a day, `home` and
 * `lap` in a fortnight. The phrase is derived from the SERVER's `open`/`expired` whenever
 * the payload carries them (see lib/window.js) — this component never overrides a ruling
 * the queue filter already made.
 *
 * `asOf` is the instant that ruling was made at: the run's own scoring instant, which for
 * a published book is not today. The phrase ("3 days left", "closed 12 days ago") is
 * counted from it, and when it is a day or more from the wall clock the badge says so
 * rather than letting the reader assume today — an undated "closed 12 days ago" beside a
 * book scored in September is a claim about the calendar, not about the lead.
 */
export default function WindowBadge({ lead, now, asOf = null, showDays = true, className = '' }) {
  const status = windowStatus(lead, asOf ?? now)
  const phrase = windowPhrase(status)
  const days = status.days ?? WINDOW_DAYS[lead?.product] ?? null

  const asDate = (v) => (v ? new Date(v).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : null)
  // Both ends of the window, not just the far one: the due date only means something
  // beside the abandonment it is measured from.
  const detail = status.state === WINDOW_STATE.UNKNOWN
    ? 'No abandonment timestamp on this lead, so the contact window cannot be placed. Not the same as closed.'
    : [
      days != null ? `${days}-day window for ${lead?.product || 'this product'}` : 'Contact window',
      status.abandonedAt ? `abandoned ${asDate(status.abandonedAt)}` : null,
      status.dueBy ? `due by ${asDate(status.dueBy)}` : null,
    ].filter(Boolean).join(', ') + asOfSuffix(status.asOf) + '.'

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${windowTone(status)} ${className}`}
      title={detail}
      data-testid="window-badge"
      data-window-state={status.state}
      data-window-as-of={status.asOf || undefined}
    >
      <Clock size={10} aria-hidden="true" />
      {phrase}
      {showDays && days != null && <span className="font-normal normal-case">({days}d)</span>}
      <span className="sr-only">. {detail}</span>
    </span>
  )
}
