// Administration — user roster, the append-only audit log, and the two admin-only
// mutations (hash-chain verify, batch run). The ROUTE is gated to role A by
// <RequireRole allow={['A']}>, but the backend refuses independently, so every data call
// here is read for `error.isForbidden` too — a stale or spoofed client role must not show
// a screen the server would not actually serve.
//
// contracts/openapi.json's `x-response-shapes` does not pin the row shape of
// `adminUsersList` or `adminAudit`, so both tables are read defensively: a short list of
// preferred keys is tried first (with the aliases the live backend is actually observed to
// use), any key absent from every row on the current page is dropped, and a table that
// matches none of the known keys falls back to the row's own keys rather than crashing.

import { useState } from 'react'
import {
  CheckCircle2, CircleSlash, Gavel, Loader2, ShieldCheck, TriangleAlert, Users as UsersIcon,
} from 'lucide-react'
import AppShell from '../components/AppShell'
import Card from '../components/Card'
import Loading from '../components/states/Loading'
import Empty from '../components/states/Empty'
import ErrorState from '../components/states/ErrorState'
import PermissionDenied from '../components/states/PermissionDenied'
import useResource from '../data/useResource'
import { getUsers, getAudit, verifyAudit, runBatch } from '../lib/sanket'
import { pick } from '../lib/pack'
import { num } from '../lib/fmt'
import { useAuth } from '../auth/AuthContext'
import { roleLabel } from '../auth/roles'

const AUDIT_LIMIT = 50

function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

function BoolChip({ value, trueLabel, falseLabel, unknownLabel = '—' }) {
  if (value === null || value === undefined) return <span className="text-txt-lo">{unknownLabel}</span>
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${
        value
          ? 'border-signal-teal/40 bg-signal-teal/15 text-signal-teal'
          : 'border-line-strong bg-ink-600 text-txt-mid'
      }`}
    >
      {value ? <CheckCircle2 size={10} aria-hidden="true" /> : <CircleSlash size={10} aria-hidden="true" />}
      {value ? trueLabel : falseLabel}
    </span>
  )
}

/** Key/value dump for a POST result whose shape isn't pinned — always safe, never crashes. */
function ResultGrid({ result }) {
  if (!result || typeof result !== 'object') return null
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border border-line bg-ink-800 p-3 text-xs sm:grid-cols-4">
      {Object.entries(result).map(([key, value]) => (
        <div key={key}>
          <dt className="text-txt-lo">{key}</dt>
          <dd className="mt-0.5 font-semibold text-txt-hi">
            {value === null || value === undefined ? '—' : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

// -------------------------------------------------------------------------------------- //
// Users
// -------------------------------------------------------------------------------------- //

const USER_FIELDS = [
  { label: 'Username', keys: ['username'] },
  { label: 'Full name', keys: ['full_name', 'fullName'] },
  { label: 'Role', keys: ['role'] },
  { label: 'EIN', keys: ['ein'] },
  { label: 'Branch', keys: ['branch_code', 'branchCode'] },
  { label: 'Scope', keys: ['scope'] },
  { label: 'Active', keys: ['is_active', 'isActive'] },
  { label: 'Must change password', keys: ['must_change_password', 'mustChangePassword'] },
  { label: 'Last login', keys: ['last_login_at', 'lastLoginAt'] },
]

function renderUserCell(field, row) {
  const value = pick(row, ...field.keys)
  if (field.label === 'Role') return value ? roleLabel(value) : '—'
  if (field.label === 'Active') return <BoolChip value={value} trueLabel="Active" falseLabel="Inactive" />
  if (field.label === 'Must change password') {
    return <BoolChip value={Boolean(value)} trueLabel="Must change" falseLabel="Current" />
  }
  if (field.label === 'Last login') return fmtDateTime(value)
  if (Array.isArray(value)) {
    if (value.length === 0) return '—'
    return (
      <div className="flex flex-wrap gap-1">
        {value.map((v) => (
          <span key={v} className="rounded-full border border-line-strong bg-ink-600 px-1.5 py-0.5 text-[10px] text-txt-mid">{v}</span>
        ))}
      </div>
    )
  }
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function UsersPanel({ users }) {
  const rows = Array.isArray(users.data) ? users.data : []
  const knownColumns = USER_FIELDS.filter((f) => rows.some((r) => pick(r, ...f.keys) !== null))
  const fallbackColumns = knownColumns.length === 0 && rows.length > 0
    ? Array.from(new Set(rows.flatMap((r) => Object.keys(r || {})))).map((k) => ({ label: k, keys: [k], raw: true }))
    : []
  const columns = knownColumns.length > 0 ? knownColumns : fallbackColumns

  return (
    <Card
      title="Users"
      subtitle={`${num(users.meta?.total ?? rows.length)} accounts on this platform`}
      source="NOT_COLLECTED"
      sourceDetail="Platform roster, not a bank figure."
      labelledBy="admin-users-title"
    >
      <p className="mb-3 text-[11px] leading-relaxed text-txt-lo">
        <code className="font-mono">adminUsersList</code>&apos;s row shape is not pinned by the contract&apos;s{' '}
        <code className="font-mono">x-response-shapes</code>. This table prefers username, full name, role, EIN,
        branch, scope, active, must-change-password and last-login, and quietly omits any of those that this
        response does not carry.
      </p>

      {users.loading && <Loading label="Loading users…" />}
      {!users.loading && users.error && (
        <ErrorState title="Could not load users" error={users.error} onRetry={users.reload} />
      )}
      {!users.loading && !users.error && rows.length === 0 && (
        <Empty title="No users found" hint="This platform has no user accounts yet." icon={UsersIcon} />
      )}
      {!users.loading && !users.error && rows.length > 0 && (
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Platform user accounts and their roles</caption>
            <thead className="text-[11px] uppercase tracking-wide text-txt-lo">
              <tr className="border-b border-line">
                {columns.map((c) => (
                  <th key={c.label} scope="col" className="py-2 pr-3 font-semibold">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={pick(row, 'id', 'username') ?? i} className="border-b border-line/60 last:border-b-0">
                  {columns.map((c) => (
                    <td key={c.label} className="py-2 pr-3 align-top text-txt-mid">
                      {c.raw ? String(row[c.keys[0]] ?? '—') : renderUserCell(c, row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// -------------------------------------------------------------------------------------- //
// Audit log
// -------------------------------------------------------------------------------------- //

const AUDIT_FIELDS = [
  { label: 'ID', keys: ['id'] },
  { label: 'Time', keys: ['at', 'ts', 'timestamp', 'created_at'], datetime: true },
  { label: 'Actor', keys: ['actor', 'actor_username', 'actor_user_id'] },
  { label: 'Actor role / EIN', keys: ['actor_ein', 'actor_role'] },
  { label: 'Action', keys: ['action'] },
  { label: 'Entity', keys: ['entity', 'target_type'] },
  { label: 'Entity key', keys: ['entity_key', 'target_id'] },
  { label: 'Request ID', keys: ['request_id'], code: true },
]

/**
 * `ok` when the row states it directly; otherwise the platform's own `payload.outcome` —
 * but only on a `request.*` row, where that key is the middleware's verdict on the HTTP
 * call itself ("ok", "denied", "not_found", "rejected", "error").
 *
 * A domain row (`sanket.disposition.callback_requested`, `admin.user.created`) carries
 * business words in the same key — "callback_requested" is a perfectly successful call —
 * and reading those as a verdict painted a red **Failed** chip on rows that had failed at
 * nothing. Those rows have no pass/fail of their own: they return `null`, and `BoolChip`
 * renders the honest em dash.
 */
export function auditOutcome(row) {
  const direct = pick(row, 'ok')
  if (typeof direct === 'boolean') return direct
  const action = pick(row, 'action')
  if (typeof action !== 'string' || !action.startsWith('request.')) return null
  const outcome = row?.payload && typeof row.payload === 'object' ? row.payload.outcome : null
  if (outcome === 'ok') return true
  if (outcome) return false
  return null
}

function renderAuditCell(field, row) {
  const value = pick(row, ...field.keys)
  if (field.datetime) return fmtDateTime(value)
  if (field.code) return value ? <code className="font-mono text-[11px]">{value}</code> : '—'
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function AuditPanel({ audit, offset, onPrev, onNext }) {
  const rows = Array.isArray(audit.data) ? audit.data : []
  const knownColumns = AUDIT_FIELDS.filter((f) => rows.some((r) => pick(r, ...f.keys) !== null))
  const hasOutcome = rows.some((r) => auditOutcome(r) !== null)
  const fallbackColumns = knownColumns.length === 0 && rows.length > 0
    ? Array.from(new Set(rows.flatMap((r) => Object.keys(r || {})))).slice(0, 10).map((k) => ({ label: k, keys: [k], raw: true }))
    : []
  const columns = knownColumns.length > 0 ? knownColumns : fallbackColumns

  const total = audit.meta?.total
  const atStart = offset === 0
  const atEnd = total != null ? offset + AUDIT_LIMIT >= total : rows.length < AUDIT_LIMIT
  const rangeLabel = total != null
    ? `${rows.length === 0 ? 0 : offset + 1}–${offset + rows.length} of ${num(total)}`
    : `${rows.length} rows`

  return (
    <Card
      title="Audit log"
      subtitle="Newest first. Append-only and DB-enforced: UPDATE and DELETE on this table raise at the database level, so nothing here can be edited or removed after the fact."
      source="NOT_COLLECTED"
      sourceDetail="Platform audit trail, not a bank figure."
      labelledBy="admin-audit-title"
    >
      <p className="mb-3 text-[11px] leading-relaxed text-txt-lo">
        <code className="font-mono">adminAudit</code>&apos;s row shape is not pinned by{' '}
        <code className="font-mono">x-response-shapes</code> either. This table prefers id, time, actor, action,
        entity and request id (and the aliases the live platform actually uses for them), and reads whatever
        this response actually carries.
      </p>

      {audit.loading && <Loading label="Loading audit log…" />}
      {!audit.loading && audit.error && (
        <ErrorState title="Could not load the audit log" error={audit.error} onRetry={audit.reload} />
      )}
      {!audit.loading && !audit.error && rows.length === 0 && (
        <Empty title="No audit entries" hint="Nothing has been recorded on this page of the log." icon={Gavel} />
      )}
      {!audit.loading && !audit.error && rows.length > 0 && (
        <>
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Audit log entries, newest first</caption>
              <thead className="text-[11px] uppercase tracking-wide text-txt-lo">
                <tr className="border-b border-line">
                  {columns.map((c) => (
                    <th key={c.label} scope="col" className="py-2 pr-3 font-semibold">{c.label}</th>
                  ))}
                  {hasOutcome && <th scope="col" className="py-2 pr-3 font-semibold">Outcome</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={pick(row, 'id') ?? i} className="border-b border-line/60 last:border-b-0">
                    {columns.map((c) => (
                      <td key={c.label} className="py-2 pr-3 align-top text-txt-mid">
                        {c.raw ? String(row[c.keys[0]] ?? '—') : renderAuditCell(c, row)}
                      </td>
                    ))}
                    {hasOutcome && (
                      <td className="py-2 pr-3 align-top">
                        <BoolChip value={auditOutcome(row)} trueLabel="OK" falseLabel="Failed" />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-txt-lo">
            <span>{rangeLabel}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={atStart || audit.loading}
                onClick={onPrev}
                className="rounded-lg border border-line-strong px-3 py-1.5 text-xs font-semibold text-txt-mid transition hover:bg-ink-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={atEnd || audit.loading}
                onClick={onNext}
                className="rounded-lg border border-line-strong px-3 py-1.5 text-xs font-semibold text-txt-mid transition hover:bg-ink-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}

// -------------------------------------------------------------------------------------- //
// Verify + batch
// -------------------------------------------------------------------------------------- //

function VerifyPanel() {
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const onVerify = async () => {
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const data = await verifyAudit()
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-bold text-txt-hi">Verify the hash chain</h3>
      <div className="flex items-start gap-2 text-xs leading-relaxed text-txt-lo">
        <ShieldCheck size={14} className="mt-0.5 shrink-0 text-signal-teal" aria-hidden="true" />
        <p>
          Walks the audit log&apos;s hash chain end to end. The log is append-only and DB-enforced — a row
          cannot be altered without breaking the chain from that point forward, which this check would catch.
        </p>
      </div>
      <button
        type="button"
        onClick={onVerify}
        disabled={pending}
        aria-busy={pending}
        className="inline-flex items-center gap-2 rounded-lg bg-signal-amber px-4 py-2 text-sm font-bold text-ink-900 transition hover:bg-signal-amber/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}
        {pending ? 'Verifying…' : 'Verify the hash chain'}
      </button>
      <div aria-live="polite" className="text-sm">
        {pending && <p className="text-txt-lo">Verifying the hash chain…</p>}
        {!pending && error && <ErrorState title="Verification failed to run" error={error} onRetry={onVerify} />}
        {!pending && !error && result && <ResultGrid result={result} />}
      </div>
    </div>
  )
}

function BatchPanel() {
  const [pending, setPending] = useState(false)
  const [outcome, setOutcome] = useState(null) // { kind: 'ok' | 'not_implemented' | 'error', data?, error? }

  const onRun = async () => {
    if (pending) return
    setPending(true)
    try {
      const data = await runBatch({})
      setOutcome({ kind: 'ok', data })
    } catch (err) {
      if (err?.status === 501 || err?.reason === 'NOT_IMPLEMENTED' || err?.code === 'NOT_IMPLEMENTED') {
        setOutcome({ kind: 'not_implemented' })
      } else {
        setOutcome({ kind: 'error', error: err })
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-bold text-txt-hi">Run the batch</h3>
      <div className="flex items-start gap-2 text-xs leading-relaxed text-txt-lo">
        <Gavel size={14} className="mt-0.5 shrink-0 text-signal-amber" aria-hidden="true" />
        <p>Runs the platform&apos;s batch scoring job.</p>
      </div>
      <button
        type="button"
        onClick={onRun}
        disabled={pending}
        aria-busy={pending}
        className="inline-flex items-center gap-2 rounded-lg bg-signal-amber px-4 py-2 text-sm font-bold text-ink-900 transition hover:bg-signal-amber/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Gavel size={15} aria-hidden="true" />}
        {pending ? 'Running…' : 'Run the batch'}
      </button>
      <div aria-live="polite" className="text-sm">
        {pending && <p className="text-txt-lo">Running the batch…</p>}
        {!pending && outcome?.kind === 'not_implemented' && (
          <div className="flex items-start gap-2 rounded-lg border border-line-strong bg-ink-800 px-3 py-2.5 text-xs leading-relaxed text-txt-mid">
            <TriangleAlert size={14} className="mt-0.5 shrink-0 text-signal-amber" aria-hidden="true" />
            <p>
              The batch runner is lane BE-8&apos;s and is not wired yet. The route exists and enforces its role,
              which is what lets the authorisation matrix be complete before the endpoint is.
            </p>
          </div>
        )}
        {!pending && outcome?.kind === 'error' && (
          <ErrorState title="The batch run failed" error={outcome.error} onRetry={onRun} />
        )}
        {!pending && outcome?.kind === 'ok' && <ResultGrid result={outcome.data} />}
      </div>
    </div>
  )
}

// -------------------------------------------------------------------------------------- //

export default function Admin() {
  const { role } = useAuth()
  const users = useResource(({ signal }) => getUsers({ signal }), [])
  const [offset, setOffset] = useState(0)
  const audit = useResource(({ signal }) => getAudit({ limit: AUDIT_LIMIT, offset, signal }), [offset])

  // The route is already gated to role A; this is the backend's independent refusal,
  // surfaced from a real data call rather than trusted from the client's own session state.
  const forbidden = users.error?.isForbidden || audit.error?.isForbidden

  if (forbidden) {
    return (
      <AppShell title="Administration" help="admin">
        <PermissionDenied role={role} allowed={['A']} />
      </AppShell>
    )
  }

  return (
    <AppShell title="Administration" help="admin">
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-bold text-txt-hi">Administration</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-txt-mid">
            The user roster, the append-only audit trail, and the two admin-only actions: verifying the audit
            log&apos;s hash chain, and running the batch scoring job.
          </p>
        </div>

        <UsersPanel users={users} />
        <AuditPanel
          audit={audit}
          offset={offset}
          onPrev={() => setOffset((o) => Math.max(0, o - AUDIT_LIMIT))}
          onNext={() => setOffset((o) => o + AUDIT_LIMIT)}
        />

        <Card
          title="Administrative actions"
          source="NOT_COLLECTED"
          sourceDetail="Platform actions, not a bank figure."
          labelledBy="admin-actions-title"
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <VerifyPanel />
            <BatchPanel />
          </div>
        </Card>
      </div>
    </AppShell>
  )
}
