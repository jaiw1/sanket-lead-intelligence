import { useCallback, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Download, Eye, FileKey, Plus, RotateCcw, ShieldCheck,
} from 'lucide-react'
import AppShell from '../components/AppShell'
import Card from '../components/Card'
import ConsentStateMachine from '../components/ConsentStateMachine'
import Modal, { PrimaryButton, SecondaryButton } from '../components/Modal'
import NotInBuild from '../components/NotInBuild'
import Empty from '../components/states/Empty'
import ErrorState from '../components/states/ErrorState'
import Loading from '../components/states/Loading'
import PermissionDenied from '../components/states/PermissionDenied'
import { useAuth } from '../auth/AuthContext'
import { roleMatches } from '../auth/roles'
import useResource from '../data/useResource'
import {
  CONSENT_STATES, REPLAY_EVENTS, getConsent, getConsents,
  postConsentFetch, postConsentRequest, postConsentReplay,
} from '../lib/sanket'
import { num } from '../lib/fmt'

const STATE_TONE = {
  ACTIVE: 'border-signal-teal/40 bg-signal-teal/10 text-signal-teal',
  REQUESTED: 'border-signal-amber/40 bg-signal-amber/10 text-signal-amber',
  PENDING: 'border-signal-amber/40 bg-signal-amber/10 text-signal-amber',
  REJECTED: 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose',
  REVOKED: 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose',
  EXPIRED: 'border-line-strong bg-ink-600 text-txt-mid',
  FAILED: 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose',
}

const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—')

/**
 * Account Aggregator consent: the screen that proves the product asks before it looks.
 *
 * The flow the plan names is 590 → 592 → 593 with 497/498 as the webhooks and 595/739 as
 * the fetch. Nothing on this screen sets a state: a consent moves because the customer
 * acted in their AA app and the aggregator called our webhook. The one exception is the
 * admin-only replay, which re-injects a STORED delivery through the same state machine and
 * is audited under its own action name — it exists because the IDBI sandbox may not be able
 * to reach a box with no public address, not because a state should ever be settable here.
 */
export default function Consent() {
  const { isStatic, role } = useAuth()
  const [params, setParams] = useSearchParams()
  const selected = params.get('id')
  const statusFilter = params.get('status') || ''

  const list = useResource(
    ({ signal }) => getConsents({ status: statusFilter || undefined, limit: 100, signal }),
    [statusFilter],
    { enabled: !isStatic },
  )

  const select = useCallback((id) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id) next.set('id', id); else next.delete('id')
      return next
    }, { replace: true })
  }, [setParams])

  if (isStatic) {
    return (
      <AppShell title="Consent and Account Aggregator" help="consent">
        <NotInBuild
          what="Consent"
          keys={['GET /sanket/consent/list']}
          hint="A consent artefact is platform state, not model output, so the bundled export carries none. This screen needs the backend."
        />
      </AppShell>
    )
  }

  return (
    <AppShell title="Consent and Account Aggregator" help="consent">
      <div className="space-y-4">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold">
              <FileKey size={18} className="text-signal-amber" aria-hidden="true" /> Consent and Account Aggregator
            </h2>
            <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-txt-lo">
              Cross-bank statements fill the two gaps this product cannot see from its own book —
              EMIs paid elsewhere and salary credited elsewhere. Nothing is fetched until the customer
              approves in their own Account Aggregator app.
            </p>
          </div>
          <RequestConsentButton onDone={list.reload} />
        </header>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,420px),1fr]">
          <ConsentList
            resource={list}
            statusFilter={statusFilter}
            onFilter={(value) => setParams((prev) => {
              const next = new URLSearchParams(prev)
              if (value) next.set('status', value); else next.delete('status')
              return next
            }, { replace: true })}
            selected={selected}
            onSelect={select}
            role={role}
          />
          {selected
            ? <ConsentDetail consentId={selected} onChanged={list.reload} role={role} />
            : <WhatTheCustomerSeesPlaceholder />}
        </div>
      </div>
    </AppShell>
  )
}

function ConsentList({ resource, statusFilter, onFilter, selected, onSelect, role }) {
  const rows = resource.data || []
  return (
    <Card
      title="Consent artefacts"
      subtitle="API 591 — every consent this platform has asked for, and where it got to."
      source="FIXTURE"
      sourceDetail="Consent rows are platform state. With ATLAS_MODE off, no 590 call leaves the box, and the row says so."
      labelledBy="consent-list-title"
      actions={(
        <div>
          <label className="sr-only" htmlFor="consent-status">Filter by state</label>
          <select
            id="consent-status"
            value={statusFilter}
            onChange={(e) => onFilter(e.target.value)}
            className="rounded-lg border border-line-strong bg-ink-800 px-2 py-1 text-xs text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            <option value="">All states</option>
            {CONSENT_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      )}
    >
      {resource.loading && <Loading label="Loading consents…" />}
      {!resource.loading && resource.error?.isForbidden && <PermissionDenied role={role} allowed={['A', 'M', 'RM']} />}
      {!resource.loading && resource.error && !resource.error.isForbidden && (
        <ErrorState title="Consents could not be loaded" error={resource.error} onRetry={resource.reload} />
      )}
      {!resource.loading && !resource.error && rows.length === 0 && (
        <Empty
          icon={ShieldCheck}
          title="No consent has been requested yet"
          hint="Request one against a customer id to see the full lifecycle, including what the customer is shown before they decide."
        />
      )}
      {rows.length > 0 && (
        <>
          <ul className="scroll-thin max-h-[520px] space-y-1.5 overflow-auto" data-testid="consent-list">
            {rows.map((c) => (
              <li key={c.consent_handle}>
                <button
                  type="button"
                  onClick={() => onSelect(c.consent_handle)}
                  aria-current={selected === c.consent_handle ? 'true' : undefined}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber ${
                    selected === c.consent_handle ? 'border-signal-amber bg-signal-amber/10' : 'border-line bg-ink-800 hover:bg-ink-600'
                  }`}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-txt-hi">{c.consent_handle}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${STATE_TONE[c.status] || STATE_TONE.EXPIRED}`}>
                      {c.status}
                    </span>
                    {c.data_ready && (
                      <span className="rounded-full border border-signal-teal/40 bg-signal-teal/10 px-2 py-0.5 text-[10px] font-bold text-signal-teal">
                        DATA READY
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-txt-mid">
                    {c.cust_id} · requested {when(c.requested_at)} · {(c.fi_types || []).join(', ') || 'no FI types'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {resource.meta?.total != null && (
            <p className="mt-2 text-[11px] text-txt-lo">{num(rows.length)} of {num(resource.meta.total)} consents.</p>
          )}
        </>
      )}
    </Card>
  )
}

function WhatTheCustomerSeesPlaceholder() {
  return (
    <Card title="What the customer sees" source="NOT_COLLECTED" labelledBy="customer-sees-placeholder">
      <Empty
        icon={Eye}
        title="Select a consent"
        hint="Its detail shows the state machine, the transitions still available, and the exact screen the customer is shown in their Account Aggregator app before they decide."
      />
    </Card>
  )
}

function ConsentDetail({ consentId, onChanged, role }) {
  const resource = useResource(({ signal }) => getConsent(consentId, { signal }), [consentId])
  const c = resource.data
  const admin = roleMatches(role, ['A'])

  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  const act = async (kind, fn) => {
    setBusy(kind); setError(null); setMessage(null)
    try {
      const result = await fn()
      setMessage(result)
      resource.reload()
      onChanged?.()
    } catch (e) { setError(e) } finally { setBusy(null) }
  }

  if (resource.loading) return <Card title="Consent detail" source="FIXTURE"><Loading label="Loading the consent…" /></Card>
  if (resource.error) {
    return (
      <Card title="Consent detail" source="NOT_COLLECTED">
        {resource.error.isForbidden
          ? <PermissionDenied role={role} allowed={['A', 'M', 'RM']} />
          : <ErrorState title="This consent could not be loaded" error={resource.error} onRetry={resource.reload} />}
      </Card>
    )
  }
  if (!c) return null

  const sees = c.customer_sees

  return (
    <div className="space-y-4">
      <Card
        title={`Consent ${c.consent_handle}`}
        subtitle="The state machine, and what can still move it."
        source="FIXTURE"
        sourceDetail="Consent state is held by this platform and moved only by an Account Aggregator webhook (497/498)."
        labelledBy="consent-detail-title"
        actions={(
          <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${STATE_TONE[c.status] || STATE_TONE.EXPIRED}`}>
            {c.status}
          </span>
        )}
      >
        <ConsentStateMachine current={c.status} mayTransitionTo={c.may_transition_to} terminal={c.terminal} />

        <div aria-live="polite" className="sr-only">
          {busy ? 'Working.' : message ? 'The request was accepted.' : ''}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <PrimaryButton
            onClick={() => act('fetch', () => postConsentFetch(c.consent_handle))}
            disabled={busy != null || c.status !== 'ACTIVE'}
            data-testid="consent-fetch"
          >
            <Download size={15} aria-hidden="true" />
            {busy === 'fetch' ? 'Fetching…' : 'Fetch statements (595/739)'}
          </PrimaryButton>
          {c.status !== 'ACTIVE' && (
            <p className="text-[11px] text-txt-lo">
              A fetch is refused with 409 unless the consent is ACTIVE. That refusal is the product working.
            </p>
          )}
          {admin && <ReplayButton consent={c} busy={busy} onReplay={(body) => act('replay', () => postConsentReplay(c.consent_handle, body))} />}
        </div>

        {error && <div className="mt-3"><ErrorState title="The action did not complete" error={error} /></div>}
        {message && (
          <pre className="scroll-thin mt-3 max-h-48 overflow-auto rounded-lg border border-line bg-ink-900 p-3 font-mono text-[11px] leading-relaxed text-txt-mid">
            {JSON.stringify(message, null, 2)}
          </pre>
        )}

        <dl className="mt-4 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-xs">
          <dt className="text-txt-lo">Customer</dt><dd className="font-mono text-txt-hi">{c.cust_id || '—'}</dd>
          <dt className="text-txt-lo">VUA</dt><dd className="font-mono text-txt-mid">{c.vua || '—'}</dd>
          <dt className="text-txt-lo">Consent id (592)</dt><dd className="font-mono text-txt-mid">{c.consent_id || 'not issued yet'}</dd>
          <dt className="text-txt-lo">Requested</dt><dd className="text-txt-mid">{when(c.requested_at)}</dd>
          <dt className="text-txt-lo">Approved</dt><dd className="text-txt-mid">{when(c.approved_at)}</dd>
          <dt className="text-txt-lo">Expires</dt><dd className="text-txt-mid">{when(c.expires_at)}</dd>
          <dt className="text-txt-lo">Last fetch</dt><dd className="text-txt-mid">{when(c.last_fetch_at)}</dd>
          <dt className="text-txt-lo">Data ready</dt><dd className="text-txt-mid">{c.data_ready ? 'yes' : 'no'}</dd>
        </dl>
      </Card>

      <Card
        title="What the customer sees"
        subtitle="The consent screen shown in their own Account Aggregator app — the 592 redirect, in plain language."
        source="FIXTURE"
        labelledBy="customer-sees-title"
      >
        {!sees ? (
          <NotInBuild what="The customer's view" keys="customer_sees" />
        ) : (
          <div className="rounded-xl border border-line-strong bg-ink-900 p-4">
            <p className="text-xs uppercase tracking-wider text-txt-lo">Requested by</p>
            <p className="text-sm font-bold text-txt-hi">{sees.requested_by}</p>
            <dl className="mt-3 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
              <div><dt className="text-txt-lo">Purpose</dt><dd className="text-txt-mid">{sees.purpose} {sees.purpose_code ? `(code ${sees.purpose_code})` : ''}</dd></div>
              <div><dt className="text-txt-lo">Data requested</dt><dd className="text-txt-mid">{(sees.data_requested || []).join(', ')}</dd></div>
              <div><dt className="text-txt-lo">Period</dt><dd className="text-txt-mid">{sees.period}</dd></div>
              <div><dt className="text-txt-lo">Frequency</dt><dd className="text-txt-mid">{sees.frequency}</dd></div>
              <div><dt className="text-txt-lo">Valid until</dt><dd className="text-txt-mid">{when(sees.valid_until)}</dd></div>
            </dl>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-signal-teal/30 bg-signal-teal/5 p-3">
                <p className="text-xs font-bold text-signal-teal">You can</p>
                <ul className="mt-1 space-y-1 text-[11px] leading-relaxed text-txt-mid">
                  {(sees.you_can || []).map((t) => <li key={t}>· {t}</li>)}
                </ul>
              </div>
              <div className="rounded-lg border border-signal-rose/30 bg-signal-rose/5 p-3">
                <p className="text-xs font-bold text-signal-rose">We will not</p>
                <ul className="mt-1 space-y-1 text-[11px] leading-relaxed text-txt-mid">
                  {(sees.we_will_not || []).map((t) => <li key={t}>· {t}</li>)}
                </ul>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
              This is a rendering of the artefact we send to the Account Aggregator, not a screenshot of
              their app. The customer approves or declines there; this platform never sees their AA credentials.
            </p>
          </div>
        )}
      </Card>
    </div>
  )
}

/**
 * Admin-only replay.
 *
 * Deliberately NOT the webhook endpoint with the signature check removed: it is
 * authenticated, admin-only, and its audit action is `sanket.consent.replayed`, so nothing
 * in the trail can later be mistaken for a real delivery from the aggregator. The dialog
 * says that, because an admin clicking it should know what it will look like in the audit.
 */
function ReplayButton({ consent, busy, onReplay }) {
  const [open, setOpen] = useState(false)
  const [event, setEvent] = useState('ACTIVE')
  const [apiId, setApiId] = useState('497')
  const confirmRef = useRef(null)

  const allowed = useMemo(() => {
    const may = new Set(consent.may_transition_to || [])
    return REPLAY_EVENTS.filter((e) => may.size === 0 || may.has(e.value) || e.value === 'DATA_READY')
  }, [consent.may_transition_to])

  return (
    <>
      <SecondaryButton onClick={() => setOpen(true)} disabled={busy != null} data-testid="consent-replay-open">
        <RotateCcw size={15} aria-hidden="true" /> Replay a webhook
      </SecondaryButton>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Replay a stored Account Aggregator webhook"
        description="Administrator only. The IDBI sandbox cannot reach a box with no public address, so a stored 497/498 delivery is re-injected through the same state machine."
        initialFocusRef={confirmRef}
        testId="consent-replay-dialog"
        footer={(
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton
              ref={confirmRef}
              onClick={() => { onReplay({ event, apiId }); setOpen(false) }}
              data-testid="consent-replay-confirm"
            >
              Replay as {event}
            </PrimaryButton>
          </>
        )}
      >
        <div className="space-y-3">
          <p className="rounded-lg border border-signal-amber/40 bg-signal-amber/10 px-3 py-2 text-xs leading-relaxed text-txt-mid">
            This is <b className="text-txt-hi">not</b> the webhook endpoint with its signature check removed.
            It is authenticated, administrator-only, and audited as
            <code className="mx-1 font-mono">sanket.consent.replayed</code> — so no replayed
            delivery can later be mistaken for a real one from the aggregator.
          </p>
          <div>
            <label htmlFor="replay-event" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Event to synthesise</label>
            <select
              id="replay-event"
              value={event}
              onChange={(e) => setEvent(e.target.value)}
              className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
            >
              {allowed.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="replay-api" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Delivered as</label>
            <select
              id="replay-api"
              value={apiId}
              onChange={(e) => setApiId(e.target.value)}
              className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
            >
              <option value="497">API 497 — consent notification</option>
              <option value="498">API 498 — data notification</option>
            </select>
          </div>
        </div>
      </Modal>
    </>
  )
}

function RequestConsentButton({ onDone }) {
  const [open, setOpen] = useState(false)
  const [custId, setCustId] = useState('')
  const [purpose, setPurpose] = useState('Loan eligibility assessment')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const firstRef = useRef(null)

  const submit = async () => {
    setBusy(true); setError(null)
    try {
      setResult(await postConsentRequest({ custId: custId.trim(), purpose }))
      onDone?.()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const close = () => { setOpen(false); setResult(null); setError(null); setCustId('') }

  return (
    <>
      <PrimaryButton onClick={() => setOpen(true)} data-testid="consent-request-open">
        <Plus size={15} aria-hidden="true" /> Request consent
      </PrimaryButton>
      <Modal
        open={open}
        onClose={close}
        title="Request an Account Aggregator consent"
        description="API 590. This creates the request and returns what the customer will be shown. Nothing is fetched until they approve."
        initialFocusRef={firstRef}
        testId="consent-request-dialog"
        footer={result ? (
          <PrimaryButton onClick={close}>Done</PrimaryButton>
        ) : (
          <>
            <SecondaryButton onClick={close} disabled={busy}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} disabled={busy || !custId.trim()} data-testid="consent-request-submit">
              {busy ? 'Requesting…' : 'Request consent'}
            </PrimaryButton>
          </>
        )}
      >
        <div aria-live="polite" className="sr-only">{busy ? 'Requesting.' : result ? 'Consent requested.' : ''}</div>
        {error && <ErrorState title="The consent was not requested" error={error} />}
        {result ? (
          <div className="space-y-2 text-sm">
            <p className="font-bold text-signal-teal">Requested — {result.consent?.consent_handle}</p>
            <p className="text-xs leading-relaxed text-txt-mid">
              The consent is <b className="text-txt-hi">{result.consent?.status}</b>. It moves only when the
              customer acts and the aggregator calls our webhook.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label htmlFor="consent-cust" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Customer id</label>
              <input
                ref={firstRef}
                id="consent-cust"
                value={custId}
                onChange={(e) => setCustId(e.target.value)}
                placeholder="LB-2000002"
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi placeholder:text-txt-lo focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
              />
            </div>
            <div>
              <label htmlFor="consent-purpose" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Purpose shown to the customer</label>
              <input
                id="consent-purpose"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
              />
              <p className="mt-1 text-[11px] text-txt-lo">
                This wording is what the customer reads before deciding. Say what the data is for, not what you hope they agree to.
              </p>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
