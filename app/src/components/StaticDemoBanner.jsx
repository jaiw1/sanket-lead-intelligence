import { Info } from 'lucide-react'

/**
 * Shown for the whole session when the app is running off the bundled snapshot because no
 * backend answered. Required by the plan's static fallback: the demo must keep working
 * without the API, and must say that it is doing so.
 */
export default function StaticDemoBanner({ className = '' }) {
  return (
    <div
      role="status"
      data-testid="static-demo-banner"
      className={`flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs leading-relaxed text-amber-900 ${className}`}
    >
      <Info size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
      <p>
        <b>Static demo.</b> No backend answered, so this page is reading a frozen snapshot bundled with
        the site. Sign-in, roles, audit and live bank data are part of the deployed build — none of them
        are active here.
      </p>
    </div>
  )
}
