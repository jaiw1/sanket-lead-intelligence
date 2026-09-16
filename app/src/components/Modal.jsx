import { forwardRef, useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import useFocusTrap from '../lib/useFocusTrap'

/**
 * A modal dialog that behaves like one: focus moves in, is trapped while open, and returns
 * to whatever opened it; Escape and the backdrop both close it; the page behind cannot
 * scroll. Every confirmation in this product goes through it, so there is one focus
 * behaviour to get right rather than five.
 *
 * The backdrop is a plain <div> with a click handler and `aria-hidden` — not a button.
 * Escape is the keyboard route out, and the close button is in the dialog, so a second
 * tab stop on the backdrop would only add noise for a keyboard user.
 */
export default function Modal({
  open, onClose, title, description, children, footer, initialFocusRef, size = 'md', testId,
}) {
  const panelRef = useRef(null)
  const closeRef = useRef(null)
  const titleId = useId()
  const descId = useId()

  useFocusTrap(panelRef, { active: open, onClose, initialFocusRef: initialFocusRef || closeRef })

  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [open])

  if (!open) return null

  const width = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl' }[size] || 'max-w-xl'

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center p-4" data-testid={testId}>
      <div className="absolute inset-0 bg-ink-900/80" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={`scroll-thin relative max-h-[90vh] w-full ${width} overflow-y-auto rounded-xl border border-line-strong bg-ink-800 shadow-2xl`}
      >
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-bold text-txt-hi">{title}</h2>
            {description && <p id={descId} className="mt-1 text-xs leading-relaxed text-txt-mid">{description}</p>}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded p-1 text-txt-lo transition hover:text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            <X size={18} aria-hidden="true" />
            <span className="sr-only">Close</span>
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

// The buttons every dialog in this product ends with, styled once. They forward refs
// because useFocusTrap's `initialFocusRef` has to be able to land on one of them.
const button = (base, displayName) => {
  const Component = forwardRef(function Button({ children, className = '', ...props }, ref) {
    return (
      <button ref={ref} type="button" className={`${base} ${className}`} {...props}>
        {children}
      </button>
    )
  })
  Component.displayName = displayName
  return Component
}

export const PrimaryButton = button(
  'inline-flex items-center gap-2 rounded-lg bg-signal-amber px-4 py-2 text-sm font-bold text-ink-900 transition hover:bg-signal-amber/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber focus-visible:ring-offset-2 focus-visible:ring-offset-ink-800 disabled:cursor-not-allowed disabled:opacity-50',
  'PrimaryButton',
)

export const SecondaryButton = button(
  'inline-flex items-center gap-2 rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold text-txt-mid transition hover:bg-ink-700 hover:text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber disabled:cursor-not-allowed disabled:opacity-50',
  'SecondaryButton',
)

export const DangerButton = button(
  'inline-flex items-center gap-2 rounded-lg bg-signal-rose px-4 py-2 text-sm font-bold text-ink-900 transition hover:bg-signal-rose/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-rose focus-visible:ring-offset-2 focus-visible:ring-offset-ink-800 disabled:cursor-not-allowed disabled:opacity-50',
  'DangerButton',
)
