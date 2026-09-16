// The shared shell every empty/loading/error/denied state sits in, so the four of them
// are visibly the same family and a screen can swap one for another without reflowing.

export default function Panel({ tone = 'neutral', icon: Icon, title, children, actions, role, live, testId }) {
  const tones = {
    neutral: 'bg-slate-100 text-slate-500',
    warn: 'bg-rag-amber/10 text-rag-amber',
    error: 'bg-rag-red/10 text-rag-red',
    brand: 'bg-idbi-green/10 text-idbi-green',
  }
  return (
    <div
      role={role}
      aria-live={live}
      data-testid={testId}
      className="grid place-items-center rounded-xl border border-slate-200 bg-white px-6 py-10 text-center"
    >
      <div className="max-w-sm space-y-3">
        {Icon && (
          <div className={`mx-auto grid h-11 w-11 place-items-center rounded-xl ${tones[tone] || tones.neutral}`}>
            <Icon size={22} aria-hidden="true" />
          </div>
        )}
        {title && <div className="font-bold text-slate-800">{title}</div>}
        {children && <div className="text-sm leading-relaxed text-slate-500">{children}</div>}
        {actions && <div className="flex items-center justify-center gap-2 pt-1">{actions}</div>}
      </div>
    </div>
  )
}
