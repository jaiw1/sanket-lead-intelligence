// Per-screen help drawer.
//
// The original Guide.jsx was one linear product tour shown once. This generalises it: any
// screen declares `<ScreenHelp screen="watchlist" />` and gets a help button plus a drawer
// of copy from src/help/screens.json — so the explanation lives beside the screen it
// explains, and stays reachable after the tour has been dismissed forever.

import { useEffect, useRef, useState } from 'react'
import { CircleHelp, X } from 'lucide-react'
import useFocusTrap from '../lib/useFocusTrap'
import { HELP, helpFor } from '../help'

export default function ScreenHelp({ screen, map = HELP, label = 'Help', compact = false }) {
  const [open, setOpen] = useState(false)
  const panelRef = useRef(null)
  const closeRef = useRef(null)
  const entry = helpFor(screen, map)

  useFocusTrap(panelRef, { active: open, onClose: () => setOpen(false), initialFocusRef: closeRef })

  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [open])

  if (!entry) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-lg bg-idbi-green/10 px-3 py-1.5 text-xs font-semibold text-idbi-green transition hover:bg-idbi-green/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green"
      >
        <CircleHelp size={14} aria-hidden="true" />
        {compact ? <span className="sr-only">{`${label}: ${entry.title}`}</span> : label}
      </button>

      {open && (
        <div className="fixed inset-0 z-[90] flex justify-end" data-testid="screen-help-overlay">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="screen-help-title"
            tabIndex={-1}
            className="scroll-thin relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-2xl"
          >
            <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-idbi-green/10 text-idbi-green">
                <CircleHelp size={18} aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="screen-help-title" className="font-extrabold text-slate-900">{entry.title}</h2>
                <p className="mt-0.5 text-sm leading-relaxed text-slate-600">{entry.summary}</p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close help"
                className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="flex-1 space-y-5 px-5 py-5">
              {(entry.sections || []).map((section) => (
                <section key={section.heading}>
                  <h3 className="text-xs font-extrabold uppercase tracking-wide text-idbi-green">{section.heading}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{section.body}</p>
                </section>
              ))}
              {entry.bullets?.length > 0 && (
                <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-600">
                  {entry.bullets.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </div>

            {entry.caveat && (
              <p className="border-t border-slate-200 bg-slate-50 px-5 py-4 text-xs leading-relaxed text-slate-500">
                {entry.caveat}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  )
}
