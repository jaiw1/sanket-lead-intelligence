import { Loader2 } from 'lucide-react'

/**
 * Busy state. The label is announced politely, so a screen-reader user hears that
 * something is happening rather than sitting in silence.
 */
export default function Loading({ label = 'Loading…', inline = false, testId = 'state-loading' }) {
  if (inline) {
    return (
      <span className="inline-flex items-center gap-2 text-sm text-slate-400" data-testid={testId}>
        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
        <span role="status" aria-live="polite">{label}</span>
      </span>
    )
  }
  return (
    <div
      className="grid place-items-center rounded-xl border border-slate-200 bg-white px-6 py-12"
      data-testid={testId}
    >
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Loader2 size={18} className="animate-spin" aria-hidden="true" />
        <span role="status" aria-live="polite">{label}</span>
      </div>
    </div>
  )
}
