import { Inbox } from 'lucide-react'
import Panel from './Panel'

/** Nothing to show — and why, which is the part that usually gets left out. */
export default function Empty({
  title = 'Nothing here yet',
  hint,
  icon = Inbox,
  action,
  testId = 'state-empty',
}) {
  return (
    <Panel icon={icon} title={title} actions={action} testId={testId}>
      {hint}
    </Panel>
  )
}
