import { useEffect, useState } from 'react'
import { RefreshCw, WifiOff } from 'lucide-react'
import Panel from './Panel'

/** True while the browser believes it has no network. */
export function useOnlineStatus() {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine !== false))
  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

export default function Offline({ onRetry, testId = 'state-offline' }) {
  return (
    <Panel
      tone="warn"
      icon={WifiOff}
      title="You appear to be offline"
      role="alert"
      testId={testId}
      actions={
        onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-2 rounded-lg bg-idbi-green px-4 py-2 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2"
          >
            <RefreshCw size={15} aria-hidden="true" /> Retry
          </button>
        ) : null
      }
    >
      This screen needs the bank network. Nothing has been lost — reconnect and retry.
    </Panel>
  )
}
