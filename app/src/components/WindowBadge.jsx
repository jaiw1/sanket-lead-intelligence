import { Clock } from 'lucide-react'
import { windowPhrase, windowStatus, windowTone, WINDOW_STATE } from '../lib/window'
import { WINDOW_DAYS } from '../lib/fmt'

/**
 * How long this lead is still worth calling.
 *
 * The mentors' per-product window is the product's whole point, so it is a first-class
 * badge rather than a column of dates: `personal` and `gold` close in a day, `home` and
 * `lap` in a fortnight. The phrase is derived from the SERVER's `open`/`expired` whenever
 * the payload carries them (see lib/window.js) — this component never overrides a ruling
 * the queue filter already made.
 */
export default function WindowBadge({ lead, now, showDays = true, className = '' }) {
  const status = windowStatus(lead, now)
  const phrase = windowPhrase(status)
  const days = status.days ?? WINDOW_DAYS[lead?.product] ?? null

  const detail = status.state === WINDOW_STATE.UNKNOWN
    ? 'No abandonment timestamp on this lead, so the contact window cannot be placed. Not the same as closed.'
    : `${days != null ? `${days}-day window for ${lead?.product || 'this product'}` : 'Contact window'}${status.dueBy ? `, due by ${new Date(status.dueBy).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}.`

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${windowTone(status)} ${className}`}
      title={detail}
      data-testid="window-badge"
      data-window-state={status.state}
    >
      <Clock size={10} aria-hidden="true" />
      {phrase}
      {showDays && days != null && <span className="font-normal normal-case">({days}d)</span>}
      <span className="sr-only">. {detail}</span>
    </span>
  )
}
