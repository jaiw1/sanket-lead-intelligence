/**
 * The AA consent lifecycle, drawn.
 *
 * REQUESTED → PENDING → ACTIVE is the happy path; REJECTED, REVOKED, EXPIRED and FAILED
 * are the ends. The states are the ones the DATABASE can actually store — migration 0001's
 * `ck_aa_consent_status` — which is why PAUSED, present in contract 1.0.0, is not here: it
 * could never have been written, so drawing it would document a state that cannot exist.
 *
 * `may_transition_to` comes from the server per consent, so the diagram highlights the
 * moves this particular artefact can still make rather than a generic legend.
 */
const NODES = [
  { id: 'REQUESTED', label: 'Requested', hint: 'We asked. Nothing has been fetched.', col: 0, row: 1 },
  { id: 'PENDING', label: 'Pending', hint: 'The customer has the request in their AA app.', col: 1, row: 1 },
  { id: 'ACTIVE', label: 'Active', hint: 'Approved. Statements may now be fetched.', col: 2, row: 1, good: true },
  { id: 'REJECTED', label: 'Rejected', hint: 'The customer declined.', col: 1, row: 2, bad: true },
  { id: 'REVOKED', label: 'Revoked', hint: 'Withdrawn after approval. We stop.', col: 3, row: 0, bad: true },
  { id: 'EXPIRED', label: 'Expired', hint: 'Validity lapsed.', col: 3, row: 1, bad: true },
  { id: 'FAILED', label: 'Failed', hint: 'The AA could not complete it.', col: 3, row: 2, bad: true },
]

export const CONSENT_NODES = NODES

export default function ConsentStateMachine({ current, mayTransitionTo = [], terminal = false }) {
  const next = new Set(mayTransitionTo || [])

  return (
    <div>
      <ol className="grid gap-2 sm:grid-cols-4" data-testid="consent-state-machine">
        {NODES.map((node) => {
          const isCurrent = node.id === current
          const isNext = next.has(node.id)
          const tone = isCurrent
            ? 'border-signal-amber bg-signal-amber/15 text-signal-amber'
            : isNext
              ? 'border-line-strong bg-ink-800 text-txt-mid'
              : 'border-line bg-ink-800/50 text-txt-lo'
          return (
            <li
              key={node.id}
              className={`rounded-lg border p-2.5 ${tone}`}
              data-state={node.id}
              data-current={isCurrent ? 'true' : 'false'}
              aria-current={isCurrent ? 'step' : undefined}
            >
              <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide">
                {node.label}
                {isCurrent && <span className="rounded bg-signal-amber px-1 text-[9px] font-extrabold text-ink-900">NOW</span>}
                {!isCurrent && isNext && <span className="text-[9px] font-semibold normal-case text-txt-lo">can move here</span>}
              </p>
              <p className="mt-0.5 text-[11px] font-normal normal-case leading-relaxed text-txt-mid">{node.hint}</p>
            </li>
          )
        })}
      </ol>
      <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
        {terminal
          ? 'This consent is in a terminal state: nothing further can move it, and no data can be fetched under it.'
          : next.size > 0
            ? `From ${current} it can still move to ${[...next].join(', ')}. Only a webhook from the Account Aggregator (497/498) moves it — this screen never sets a state.`
            : 'The server did not report which transitions remain for this consent.'}
      </p>
    </div>
  )
}
