import { ShieldAlert } from 'lucide-react'
import Panel from './Panel'
import { roleLabel } from '../../auth/roles'

/**
 * Authenticated, but the role does not permit this screen. Deliberately says which role
 * the signed-in user holds — it is their own role, so it leaks nothing, and it is the
 * fact they need in order to ask the right person for access.
 */
export default function PermissionDenied({ role, allowed, action, testId = 'state-denied' }) {
  const allowedLabels = (Array.isArray(allowed) ? allowed : [allowed])
    .filter(Boolean)
    .map((entry) => roleLabel(entry))

  return (
    <Panel tone="warn" icon={ShieldAlert} title="You do not have access to this screen" role="alert" testId={testId} actions={action}>
      <p>
        {role
          ? <>You are signed in as a <b className="text-slate-700">{roleLabel(role)}</b>.</>
          : <>Your role does not permit this.</>}
        {allowedLabels.length > 0 && (
          <> This screen is for {allowedLabels.join(' and ')} accounts.</>
        )}
      </p>
      <p className="mt-2 text-xs text-slate-400">
        Nothing has been logged against you beyond the standard access record.
      </p>
    </Panel>
  )
}
