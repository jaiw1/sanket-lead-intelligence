import SourceBadge from './SourceBadge'

/**
 * The frame every figure on this product sits in.
 *
 * `source` is not optional by accident: the plan requires a SourceBadge on every figure,
 * so the component that draws the frame is the component that draws the badge. A figure
 * whose provenance is genuinely unknown passes `source="NOT_COLLECTED"` and says so —
 * there is no way to render a chart here with no provenance at all.
 */
export default function Card({
  title, subtitle, source, sandbox, sourceDetail, actions, children, footnote,
  as: Tag = 'section', className = '', labelledBy, ...rest
}) {
  return (
    <Tag
      className={`rounded-xl border border-line bg-ink-700 p-4 sm:p-5 ${className}`}
      aria-labelledby={labelledBy}
      {...rest}
    >
      {(title || actions || source) && (
        <div className="mb-3 flex flex-wrap items-start gap-x-3 gap-y-1.5">
          <div className="min-w-0 flex-1">
            {title && <h3 id={labelledBy} className="text-sm font-bold text-txt-hi">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-txt-lo">{subtitle}</p>}
          </div>
          {/*
            `shrink-0` plus a long action (the validation tally reads "17 pass · 1 fail ·
            1 fail on 5-seed mean · 5 report-only") pushed the whole page 38px wider than
            a 390px phone. The actions may wrap; they must not widen the document.
          */}
          <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
            {actions}
            {source && <SourceBadge source={source} sandbox={sandbox} detail={sourceDetail} />}
          </div>
        </div>
      )}
      {children}
      {footnote && <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">{footnote}</p>}
    </Tag>
  )
}

/** A single number with its label — the KPI tile used across the dashboards. */
export function Stat({ value, label, hint, tone = 'text-txt-hi', icon: Icon, testId }) {
  return (
    <div className="rounded-xl border border-line bg-ink-700 p-4" data-testid={testId}>
      <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wider text-txt-lo">
        {Icon && <Icon size={14} aria-hidden="true" />} {label}
      </div>
      <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-txt-lo">{hint}</div>}
    </div>
  )
}
