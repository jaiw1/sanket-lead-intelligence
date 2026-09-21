import { useCallback, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronRight, ListOrdered, Search, ShieldOff, Shuffle, Users } from 'lucide-react'
import AppShell from '../components/AppShell'
import Card from '../components/Card'
import LeadDrawer from '../components/LeadDrawer'
import Modal, { PrimaryButton, SecondaryButton } from '../components/Modal'
import NotInBuild from '../components/NotInBuild'
import SourceBadge from '../components/SourceBadge'
import WindowBadge from '../components/WindowBadge'
import Empty from '../components/states/Empty'
import ErrorState from '../components/states/ErrorState'
import Loading from '../components/states/Loading'
import PermissionDenied from '../components/states/PermissionDenied'
import { useAuth } from '../auth/AuthContext'
import { roleMatches } from '../auth/roles'
import useResource from '../data/useResource'
import { usePack } from '../data/PackContext'
import { getQueue, postAssign } from '../lib/sanket'
import { normaliseLead } from '../lib/pack'
import {
  PRODUCTS, SORT_KEYS, STATUSES, TIER, inr, num, productLabel, suppressionLabel,
} from '../lib/fmt'
import { WINDOW_FILTERS } from '../lib/window'

const PAGE = 50

/**
 * The calling queue.
 *
 * Scope is the backend's, not this screen's: `GET /sanket/queue` returns only the leads
 * whose `assigned_rm_id` is the caller's own EIN when the caller is an RM, and everything
 * when the caller is a manager or admin. This component renders whatever came back and
 * says which scope it was — it never filters for privacy itself, because a filter in a
 * browser is not an access control.
 *
 * Every filter is a QUERY PARAMETER, not a client-side array filter, for the same reason:
 * `include_suppressed` in particular decides what the server is willing to return, and
 * `window_due` is the server's own predicate over the abandonment timestamp.
 */
export default function Queue() {
  const { isStatic, role, user } = useAuth()
  const pack = usePack()
  const manager = isStatic || roleMatches(role, ['M', 'A'])

  const [params, setParams] = useSearchParams()
  const selected = params.get('lead')

  const filters = useMemo(() => ({
    product: params.get('product') || '',
    tier: params.get('tier') || '',
    status: params.get('status') || '',
    windowDue: params.get('window_due') || '',
    includeSuppressed: params.get('suppressed') === '1',
    sort: params.get('sort') || 'score',
    offset: Number(params.get('offset')) || 0,
    q: params.get('q') || '',
  }), [params])

  const setFilter = useCallback((key, value) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === '' || value === false || value === null) next.delete(key)
      else next.set(key, value === true ? '1' : String(value))
      if (key !== 'offset') next.delete('offset')
      return next
    }, { replace: true })
  }, [setParams])

  const live = useResource(({ signal }) => getQueue({
    product: filters.product || undefined,
    tier: filters.tier || undefined,
    status: filters.status || undefined,
    windowDue: filters.windowDue || undefined,
    includeSuppressed: filters.includeSuppressed,
    sort: filters.sort,
    limit: PAGE,
    offset: filters.offset,
    signal,
  }), [
    filters.product, filters.tier, filters.status, filters.windowDue,
    filters.includeSuppressed, filters.sort, filters.offset,
  ], { enabled: !isStatic })

  // The bundled export has no server to filter it, so the same predicates run here — and
  // the screen says so, rather than pretending the queue endpoint answered.
  const staticRows = useMemo(() => {
    if (!isStatic || !pack.data?.leads) return null
    let rows = pack.data.leads.map(normaliseLead)
    if (!filters.includeSuppressed) rows = rows.filter((r) => !r.suppressed)
    if (filters.product) rows = rows.filter((r) => r.product === filters.product)
    if (filters.tier) rows = rows.filter((r) => r.tier === filters.tier)
    if (filters.status) rows = rows.filter((r) => (r.status || 'open') === filters.status)
    const key = SORT_KEYS.some((s) => s.value === filters.sort) ? filters.sort : 'score'
    const value = (r) => (key === 'safe_emi' ? r.safeEmi : key === 'uplift_pct' ? r.upliftPct : r[key])
    return [...rows].sort((a, b) => (value(b) ?? -Infinity) - (value(a) ?? -Infinity))
  }, [isStatic, pack.data, filters])

  const rows = useMemo(
    () => (isStatic ? staticRows : (live.data || []).map(normaliseLead)),
    [isStatic, staticRows, live.data],
  )

  const searched = useMemo(() => {
    if (!rows || !filters.q) return rows
    const q = filters.q.toLowerCase()
    return rows.filter((r) => `${r.id} ${r.segment || ''} ${r.cifId || ''}`.toLowerCase().includes(q))
  }, [rows, filters.q])

  const loading = isStatic ? pack.loading : live.loading
  const error = isStatic ? pack.error : live.error
  const meta = live.meta
  const total = isStatic ? (staticRows?.length ?? 0) : (meta?.total ?? rows?.length ?? 0)
  const scope = isStatic ? 'bundled export' : (meta?.scope === 'all' ? 'the whole book' : `your own leads (${user?.ein || 'this EIN'})`)

  const reload = isStatic ? pack.reload : live.reload

  return (
    <AppShell title="Lead queue" help="queue">
      <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold">
              <ListOrdered size={18} className="text-signal-amber" aria-hidden="true" /> Lead queue
            </h2>
            {/*
              The queue is NOT filtered to open windows — `window_due` is an optional filter,
              and a frozen export can be delivered entirely after its windows have run out.
              Claiming every row is "still inside its window" beside a column of CLOSED
              badges is the first thing a reader notices.
            */}
            <p className="mt-0.5 text-xs text-txt-lo">
              Customers who abandoned an application, ranked by how likely a call is to end in a
              disbursement and by how soon their product&rsquo;s contact window closes. Use the
              contact-window filter to see only the ones still inside it. Showing{' '}
              <b className="text-txt-mid">{scope}</b>.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <SourceBadge
              source={isStatic ? 'SIMULATED' : (meta?.provenance_mode === 'fixture' ? 'FIXTURE' : 'SIMULATED')}
              detail={isStatic ? 'The bundled export; no backend answered.' : `Published model_run ${meta?.model_run_id || 'unknown'}.`}
            />
            {manager && <AssignButton rows={searched} onDone={reload} disabled={isStatic} />}
          </div>
        </div>

        <Filters filters={filters} setFilter={setFilter} isStatic={isStatic} />

        {loading && <Loading label="Loading the queue…" />}
        {!loading && error?.isForbidden && <PermissionDenied role={role} allowed={['A', 'M', 'RM']} />}
        {!loading && error && !error.isForbidden && (
          <ErrorState title="The queue could not be loaded" error={error} onRetry={reload} />
        )}

        {!loading && !error && searched && searched.length === 0 && (
          <Empty
            icon={Users}
            title="No leads match these filters"
            hint={
              roleMatches(role, ['RM']) && !isStatic
                ? 'An RM sees only leads assigned to their own EIN. If this is empty, nothing has been assigned to you yet — a manager assigns from this screen.'
                : 'Widen the filters, or tick "include suppressed" to see the leads the bank chose to hold back and why.'
            }
          />
        )}

        {!loading && !error && searched && searched.length > 0 && (
          <>
            <QueueTable rows={searched} onOpen={(id) => setFilter('lead', id)} />
            {!isStatic && (
              <Pager
                offset={filters.offset}
                shown={rows.length}
                total={total}
                onChange={(next) => setFilter('offset', next === 0 ? '' : next)}
              />
            )}
          </>
        )}
      </div>

      {selected && (
        <LeadDrawer
          leadId={selected}
          onClose={() => setFilter('lead', '')}
          onChanged={reload}
        />
      )}
    </AppShell>
  )
}

function Filters({ filters, setFilter, isStatic }) {
  const select = 'rounded-lg border border-line-strong bg-ink-800 px-2.5 py-1.5 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber'
  const label = 'block text-[10px] font-bold uppercase tracking-wider text-txt-lo'

  return (
    <Card as="div" className="p-3 sm:p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className={label} htmlFor="f-product">Product</label>
          <select id="f-product" className={select} value={filters.product} onChange={(e) => setFilter('product', e.target.value)}>
            <option value="">All six products</option>
            {PRODUCTS.map((p) => <option key={p} value={p}>{productLabel(p)}</option>)}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="f-tier">Tier</label>
          <select id="f-tier" className={select} value={filters.tier} onChange={(e) => setFilter('tier', e.target.value)}>
            <option value="">Any tier</option>
            {['hot', 'warm', 'cold'].map((t) => <option key={t} value={t}>{TIER[t].label}</option>)}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="f-status">Status</label>
          <select id="f-status" className={select} value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">Any status</option>
            {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="f-window">Contact window</label>
          <select id="f-window" className={select} value={filters.windowDue} onChange={(e) => setFilter('window_due', e.target.value)} disabled={isStatic}>
            {WINDOW_FILTERS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="f-sort">Sort by</label>
          <select id="f-sort" className={select} value={filters.sort} onChange={(e) => setFilter('sort', e.target.value)}>
            {SORT_KEYS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <label className="flex cursor-pointer select-none items-center gap-1.5 pb-1.5 text-xs text-txt-mid">
          <input
            type="checkbox"
            checked={filters.includeSuppressed}
            onChange={(e) => setFilter('suppressed', e.target.checked)}
            className="accent-signal-amber"
          />
          Include suppressed
        </label>
        <div className="relative ml-auto">
          <label className="sr-only" htmlFor="f-search">Search by lead id, CIF or segment</label>
          <Search size={14} className="absolute left-2.5 top-2.5 text-txt-lo" aria-hidden="true" />
          <input
            id="f-search"
            type="search"
            value={filters.q}
            onChange={(e) => setFilter('q', e.target.value)}
            placeholder="Lead id / CIF / segment"
            className="w-56 rounded-lg border border-line-strong bg-ink-800 py-1.5 pl-8 pr-3 text-sm text-txt-hi placeholder:text-txt-lo focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          />
        </div>
      </div>
      <p className="mt-2 text-[11px] text-txt-lo">
        Sort keys are the allowlist the backend accepts (<code className="font-mono">score, intent,
        capacity, uplift_pct, safe_emi</code>); anything else is a 400, so the control offers nothing
        else. The search box filters the page you are looking at, client-side — it is not a server query.
        {isStatic && ' The window filter needs the server’s abandonment timestamps and is unavailable in the static bundle.'}
      </p>
    </Card>
  )
}

function QueueTable({ rows, onOpen }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-ink-700">
      <div className="scroll-thin max-h-[560px] overflow-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Ranked drop-off leads. Select a row to open the full call briefing.
          </caption>
          <thead className="sticky top-0 z-10 bg-ink-800 text-xs">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Lead</th>
              <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Segment</th>
              <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Ranked product</th>
              <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Contact window</th>
              <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Intent</th>
              <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Capacity</th>
              <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Score</th>
              <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Safe EMI</th>
              <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Top signal</th>
              <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Briefing</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((lead) => {
              const tier = TIER[lead.tier] || TIER.cold
              return (
                <tr
                  key={lead.id}
                  className={`border-t border-ink-600/40 ${lead.suppressed ? 'bg-ink-800/60' : 'hover:bg-ink-600/30'}`}
                  data-testid="queue-row"
                  data-lead-id={lead.id}
                  data-suppressed={lead.suppressed ? 'true' : 'false'}
                >
                  <th scope="row" className="px-3 py-2.5 text-left font-semibold text-txt-hi">
                    <span className={`mr-2 inline-block h-4 w-1.5 rounded-sm align-middle ${tier.bar}`} aria-hidden="true" />
                    {lead.id}
                    <span className="sr-only"> — {tier.label} tier</span>
                  </th>
                  <td className="px-3 py-2.5 capitalize text-txt-mid">{lead.segment || '—'}</td>
                  <td className="px-3 py-2.5">
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${tier.chip}`}>
                      {productLabel(lead.product)}
                    </span>
                  </td>
                  <td className="px-3 py-2.5"><WindowBadge lead={lead} showDays={false} /></td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-txt-hi">{lead.intent == null ? '—' : Math.round(lead.intent * 100)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-txt-hi">{lead.capacity == null ? '—' : Math.round(lead.capacity * 100)}</td>
                  <td className={`px-3 py-2.5 text-right font-bold tabular-nums ${tier.text}`}>{lead.score == null ? '—' : Math.round(lead.score * 100)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-txt-mid">{inr(lead.safeEmi)}</td>
                  <td className="max-w-[280px] truncate px-3 py-2.5 text-txt-mid">
                    {lead.suppressed ? (
                      <span className="inline-flex items-center gap-1.5 text-signal-rose">
                        <ShieldOff size={12} aria-hidden="true" />
                        Suppressed — {lead.suppressionReasons.map(suppressionLabel).join(', ') || 'reason not given'}
                      </span>
                    ) : (lead.reasons[0] || '—')}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      type="button"
                      onClick={() => onOpen(lead.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-line-strong px-2 py-1 text-xs font-semibold text-txt-mid transition hover:bg-ink-600 hover:text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
                    >
                      Open<span className="sr-only"> the call briefing for {lead.id}</span>
                      <ChevronRight size={13} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Pager({ offset, shown, total, onChange }) {
  const from = total === 0 ? 0 : offset + 1
  const to = offset + shown
  return (
    <nav className="flex items-center justify-between gap-3 text-xs text-txt-mid" aria-label="Queue pages">
      <p aria-live="polite">Showing {num(from)}–{num(to)} of {num(total)}</p>
      <div className="flex gap-2">
        <SecondaryButton onClick={() => onChange(Math.max(0, offset - PAGE))} disabled={offset === 0} className="px-3 py-1 text-xs">
          Previous
        </SecondaryButton>
        <SecondaryButton onClick={() => onChange(offset + PAGE)} disabled={to >= total} className="px-3 py-1 text-xs">
          Next
        </SecondaryButton>
      </div>
    </nav>
  )
}

/**
 * Round-robin assignment, manager or admin only.
 *
 * It takes a confirmation because it moves other people's work: an RM's queue changes
 * under them when this runs. The dialog names the count and shows the allocation that came
 * back, so the manager can see who got what rather than trusting a toast.
 */
function AssignButton({ rows, onDone, disabled }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const confirmRef = useRef(null)

  const unassigned = useMemo(() => (rows || []).filter((r) => !r.assignedRmId && !r.suppressed), [rows])

  const run = async () => {
    setBusy(true); setError(null)
    try {
      const body = { mode: 'round_robin' }
      if (unassigned.length) body.lead_ids = unassigned.map((r) => r.id)
      setResult(await postAssign(body))
      onDone?.()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const close = () => { setOpen(false); setResult(null); setError(null) }

  return (
    <>
      <PrimaryButton onClick={() => setOpen(true)} disabled={disabled} data-testid="assign-open" className="px-3 py-1.5 text-xs">
        <Shuffle size={14} aria-hidden="true" /> Assign round-robin
      </PrimaryButton>
      <Modal
        open={open}
        onClose={close}
        title="Assign leads round-robin"
        description="Manager or administrator only. Round-robin honours each RM's current load, so the busiest RM is not handed the next lead."
        initialFocusRef={confirmRef}
        testId="assign-dialog"
        footer={result ? (
          <PrimaryButton onClick={close}>Done</PrimaryButton>
        ) : (
          <>
            <SecondaryButton onClick={close} disabled={busy}>Cancel</SecondaryButton>
            <PrimaryButton ref={confirmRef} onClick={run} disabled={busy} data-testid="assign-confirm">
              {busy ? 'Assigning…' : `Assign ${unassigned.length ? num(unassigned.length) : 'the unassigned'} lead${unassigned.length === 1 ? '' : 's'}`}
            </PrimaryButton>
          </>
        )}
      >
        <div aria-live="polite" className="sr-only">
          {busy ? 'Assigning.' : result ? `Assigned ${result.assigned} leads across ${Object.keys(result.per_rm || {}).length} relationship managers.` : ''}
        </div>
        {error && <ErrorState title="Nothing was assigned" error={error} />}
        {result ? (
          <div className="space-y-3" data-testid="assign-result">
            <p className="text-sm font-bold text-signal-teal">
              Assigned {num(result.assigned)} lead{result.assigned === 1 ? '' : 's'} in {result.mode.replace('_', '-')} mode.
            </p>
            {result.roster && (
              <table className="w-full text-xs">
                <caption className="sr-only">Leads assigned to each relationship manager in this run</caption>
                <thead>
                  <tr>
                    <th scope="col" className="py-1 text-left font-semibold text-txt-lo">Relationship manager</th>
                    <th scope="col" className="py-1 text-left font-semibold text-txt-lo">EIN</th>
                    <th scope="col" className="py-1 text-right font-semibold text-txt-lo">Assigned now</th>
                  </tr>
                </thead>
                <tbody>
                  {result.roster.map((rm) => (
                    <tr key={rm.ein} className="border-t border-line">
                      <th scope="row" className="py-1.5 text-left font-normal text-txt-mid">{rm.name}</th>
                      <td className="py-1.5 font-mono text-txt-lo">{rm.ein}</td>
                      <td className="py-1.5 text-right tabular-nums text-txt-hi">{num(result.per_rm?.[rm.ein] || 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {result.roster && result.roster.length < 3 && (
              <NotInBuild
                what="A realistic RM roster"
                keys={['seeds/users.yaml']}
                hint={`Round-robin ran across ${result.roster.length} seeded relationship manager${result.roster.length === 1 ? '' : 's'}. The rotation is real, but with this few RMs it is not a demonstration of load balancing — seeding more RMs (or pulling the roster from API 442 accountManager / API 508 HRMS) is what makes the exhibit meaningful.`}
              />
            )}
            {result.note && <p className="text-[11px] text-txt-lo">{result.note}</p>}
          </div>
        ) : (
          <div className="space-y-3 text-sm text-txt-mid">
            <p>
              {unassigned.length > 0
                ? <>This will assign the <b className="text-txt-hi">{num(unassigned.length)}</b> lead{unassigned.length === 1 ? '' : 's'} currently on screen with no relationship manager.</>
                : <>Every lead on screen already has a relationship manager. Running this will rebalance nothing — cancel unless you meant to re-run the rotation.</>}
            </p>
            <p className="text-xs text-txt-lo">
              Suppressed leads are never assigned: the bank has already decided not to call them.
              Every assignment is written to the audit log against your user id.
            </p>
          </div>
        )}
      </Modal>
    </>
  )
}
