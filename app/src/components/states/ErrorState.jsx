import { RefreshCw, TriangleAlert } from 'lucide-react'
import Panel from './Panel'

/**
 * A failed request. Shows the server's own message (the contract guarantees it is safe to
 * display) and the request id, which is what makes a screenshot traceable to a log line.
 */
export default function ErrorState({
  title = 'Something went wrong',
  error,
  message,
  onRetry,
  retryLabel = 'Try again',
  testId = 'state-error',
}) {
  const text =
    message ||
    error?.message ||
    'The request could not be completed. Please try again.'
  const requestId = error?.requestId || null

  return (
    <Panel
      tone="error"
      icon={TriangleAlert}
      title={title}
      role="alert"
      testId={testId}
      actions={
        onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-2 rounded-lg bg-idbi-green px-4 py-2 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2"
          >
            <RefreshCw size={15} aria-hidden="true" /> {retryLabel}
          </button>
        ) : null
      }
    >
      <p>{text}</p>
      {requestId && (
        <p className="mt-2 text-xs text-slate-400">
          Reference <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px]">{requestId}</code>
        </p>
      )}
    </Panel>
  )
}
