import { AlertTriangle, Check } from 'lucide-react'
import NotInBuild from './NotInBuild'
import { NEGATIVE_SIGNAL } from '../lib/fmt'

/** Why SANKET ranked this lead — the positive evidence, numbered so a script can cite it. */
export function ReasonChips({ reasons }) {
  if (!Array.isArray(reasons) || reasons.length === 0) {
    return <NotInBuild what="The reason list" keys="reasons" compact />
  }
  return (
    <ol className="space-y-2">
      {reasons.map((reason, i) => (
        <li key={`${i}-${reason}`} className="flex items-start gap-2.5 text-sm">
          <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded bg-signal-teal/15 text-[11px] font-bold text-signal-teal">
            {i + 1}
          </span>
          <span className="text-txt-mid">{reason}</span>
        </li>
      ))}
    </ol>
  )
}

const SEVERITY = {
  high: 'bg-signal-rose/10 text-signal-rose border-signal-rose/40',
  medium: 'bg-signal-amber/10 text-signal-amber border-signal-amber/40',
  low: 'bg-ink-600 text-txt-mid border-line-strong',
}

/**
 * The window-shopper chips — the half of the briefing that argues AGAINST the call.
 *
 * The mentors named four signals: vague answers, refusing to share income, balking at the
 * ₹1,000 fee, refusing to upload documents. They are shown to the RM before the pitch,
 * not buried, because a lead that will not close is worth knowing about while the phone is
 * still on the hook. A lead with no negative signal shows that too — an empty list is a
 * finding, a missing key is not.
 */
export function NegativeChips({ chips }) {
  if (chips === null || chips === undefined) {
    return (
      <NotInBuild
        what="Window-shopper signals"
        keys={['negative_signals', 'negative_chips']}
        hint="SM-1 adds these to the packed export; the platform returns them on every queue row."
      />
    )
  }
  if (chips.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-signal-teal">
        <Check size={15} aria-hidden="true" />
        No window-shopper signal on this application.
      </p>
    )
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {chips.map((chip, i) => (
        <li key={`${chip.signal || 'chip'}-${i}`}>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${SEVERITY[chip.severity] || SEVERITY.low}`}
            title={chip.impact != null ? `Costs ${chip.impact.toFixed(2)} in log-odds at this lead` : undefined}
          >
            <AlertTriangle size={11} aria-hidden="true" />
            {chip.label || NEGATIVE_SIGNAL[chip.signal] || chip.signal}
            {chip.severity && <span className="sr-only"> — {chip.severity} severity</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}
