import { CircleSlash } from 'lucide-react'

/**
 * The honest absence.
 *
 * SM-1 is still moving keys in `app/public/sanket_data.json`, and the platform's fixture
 * runs carry less than a real model run will. When a figure's input is missing, the panel
 * says which key it wanted and where it comes from — it never renders a zero, a dash in a
 * chart, or a plausible-looking placeholder. A jury that sees "not in this build" learns
 * something true; a jury that sees a fabricated 0.83 does not.
 */
export default function NotInBuild({ what, keys, hint, compact = false }) {
  const list = (Array.isArray(keys) ? keys : keys ? [keys] : []).filter(Boolean)

  if (compact) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-txt-lo" data-testid="not-in-build">
        <CircleSlash size={11} aria-hidden="true" />
        {what ? `${what} — not in this build` : 'Not in this build'}
      </span>
    )
  }

  return (
    <div
      className="rounded-lg border border-dashed border-line-strong bg-ink-800/60 px-4 py-5 text-center"
      data-testid="not-in-build"
    >
      <CircleSlash size={18} className="mx-auto text-txt-lo" aria-hidden="true" />
      <p className="mt-2 text-sm font-semibold text-txt-mid">
        {what ? `${what} is not in this build` : 'Not in this build'}
      </p>
      {list.length > 0 && (
        <p className="mt-1 text-[11px] leading-relaxed text-txt-lo">
          The data source carries no{' '}
          {list.map((key, i) => (
            <span key={key}>
              {i > 0 && (i === list.length - 1 ? ' or ' : ', ')}
              <code className="rounded bg-ink-900 px-1 py-0.5 font-mono">{key}</code>
            </span>
          ))}
          .
        </p>
      )}
      {hint && <p className="mt-1.5 text-[11px] leading-relaxed text-txt-lo">{hint}</p>}
    </div>
  )
}
