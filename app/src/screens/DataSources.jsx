// "Data sources and sync" — every screen in SANKET shows a number; this is the one screen
// that shows where each number came from. GET /meta/sync is the per-API call ledger, GET
// /meta/provenance is the same claim made at the family level for the two published model
// runs, and GET /meta/version ties both to a build. Nothing here is guessed: an API that
// has never been called says so, and a family that is FIXTURE or SIMULATED is never
// quietly rounded up to "real".
//
// A row can also be `served_from_cache`: the call tonight failed, so the platform served
// the last good response the same request got on an earlier night
// (`app/atlas/lastgood.py`). That row reads **Bank API · last good pull** — the bytes are
// still the bank's, `last_success_at` says when they really arrived, and it is never
// counted as a live pull. `last_success_at` and `records` are untouched by any of this.

import { useMemo } from 'react'
import {
  Antenna, CircleSlash, Database, History, Landmark, RefreshCw, ShieldAlert, Tag, TriangleAlert,
} from 'lucide-react'
import AppShell from '../components/AppShell'
import Card, { Stat } from '../components/Card'
import SourceBadge from '../components/SourceBadge'
import NotInBuild from '../components/NotInBuild'
import Loading from '../components/states/Loading'
import Empty from '../components/states/Empty'
import ErrorState from '../components/states/ErrorState'
import useResource from '../data/useResource'
import { getSync, getProvenance, getVersion } from '../lib/sanket'
import { num } from '../lib/fmt'

const PRODUCT_TITLE = { sanket: 'SANKET', drishti: 'DRISHTi' }
const PRODUCT_ORDER = ['sanket', 'drishti']
const USED_BY_LABEL = { drishti: 'DRISHTi', sanket: 'SANKET' }

function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

/** `provenance_mode` ("fixture"/"simulated"/"live"/…) onto the badge's closed enum. */
function runSource(mode) {
  const m = String(mode || '').toLowerCase()
  if (m === 'live' || m === 'bank_api') return 'BANK_API'
  if (m === 'simulated') return 'SIMULATED'
  if (m === 'fixture') return 'FIXTURE'
  return 'NOT_COLLECTED'
}

function ProductRunCard({ product, run }) {
  const title = PRODUCT_TITLE[product] || product
  if (!run) {
    return (
      <Card title={title} source="NOT_COLLECTED" labelledBy={`ds-run-${product}`}>
        <NotInBuild what={`A published ${title} run`} keys={[`runs.${product}`]} compact={false} />
      </Card>
    )
  }
  if (!run.published) {
    return (
      <Card
        title={title}
        source={runSource(run.provenance_mode)}
        sourceDetail={run.generated_from}
        labelledBy={`ds-run-${product}`}
      >
        <p className="text-sm text-txt-mid">No {title} run has been published yet.</p>
      </Card>
    )
  }
  const families = run.provenance && typeof run.provenance === 'object' ? Object.entries(run.provenance) : []
  return (
    <Card
      title={title}
      subtitle={run.run_label ? `Run: ${run.run_label}` : undefined}
      source={runSource(run.provenance_mode)}
      sourceDetail={run.generated_from}
      labelledBy={`ds-run-${product}`}
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-txt-lo">Model run</dt>
          <dd className="mt-0.5"><code className="rounded bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-txt-hi">{run.model_run_id || '—'}</code></dd>
        </div>
        <div>
          <dt className="text-txt-lo">Published</dt>
          <dd className="mt-0.5 text-txt-mid">{fmtDateTime(run.published_at)}</dd>
        </div>
        <div>
          <dt className="text-txt-lo">Rows</dt>
          <dd className="mt-0.5 text-txt-mid">{num(run.n_rows)}</dd>
        </div>
        <div>
          <dt className="text-txt-lo">Source</dt>
          <dd className="mt-0.5 text-txt-mid">{run.source || '—'}</dd>
        </div>
        <div>
          <dt className="text-txt-lo">Run label</dt>
          <dd className="mt-0.5 text-txt-mid">{run.run_label || '—'}</dd>
        </div>
        <div>
          <dt className="text-txt-lo">Schema version</dt>
          <dd className="mt-0.5 text-txt-mid">{run.schema_version || '—'}</dd>
        </div>
      </dl>

      {families.length > 0 ? (
        <>
          <h4 className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-txt-lo">Families</h4>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-2">
            {families.map(([family, source]) => (
              <li key={family} className="flex items-center gap-1.5">
                <span className="text-xs text-txt-mid">{family}</span>
                <SourceBadge source={source} />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="mt-4">
          <NotInBuild what="The per-family provenance map" keys={[`runs.${product}.provenance`]} compact />
        </div>
      )}
    </Card>
  )
}

const DRIFT_TONE = {
  no_material_shift: 'text-signal-teal',
  moderate_shift: 'text-signal-amber',
  significant_shift: 'text-signal-rose',
}

const ageText = (h) => (h == null ? '—' : h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`)

/**
 * Two things `GET /meta/provenance` publishes and this screen used to drop: how old the
 * published run is against the platform's own staleness limit, and how far its score
 * distribution moved from the run it replaced. A significant shift is exactly the thing a
 * model-risk reviewer asks about, and it was visible only in the raw JSON.
 */
function FreshnessCard({ freshness, drift }) {
  const products = Array.from(new Set([...Object.keys(freshness || {}), ...Object.keys(drift || {})]))
  if (products.length === 0) return null
  return (
    <Card
      title="Freshness and drift"
      subtitle="How old each published run is against the platform's staleness limit, and how far its score distribution moved from the run it replaced. Drift is a flag to investigate, not a verdict."
      source="NOT_COLLECTED"
      sourceDetail="Operational metadata from GET /meta/provenance, not a bank figure."
      labelledBy="ds-freshness-title"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {products.map((product) => {
          const f = freshness?.[product]
          const d = drift?.[product]
          return (
            <div key={product} className="rounded-lg border border-line bg-ink-800 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-txt-hi">{PRODUCT_TITLE[product] || product}</span>
                {f && (
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${
                    f.stale
                      ? 'border-signal-rose/40 bg-signal-rose/15 text-signal-rose'
                      : 'border-signal-teal/40 bg-signal-teal/15 text-signal-teal'
                  }`}>
                    {f.stale ? 'stale' : 'fresh'}
                  </span>
                )}
              </div>
              {f ? (
                <p className="mt-1.5 text-xs leading-relaxed text-txt-mid">
                  Published <b className="text-txt-hi">{ageText(f.age_hours)}</b> ago
                  {f.threshold_hours != null && <> · limit {f.threshold_hours} h</>}
                  {f.n_rows != null && <> · {num(f.n_rows)} rows</>}
                  {f.reason && <> — {f.reason}</>}
                </p>
              ) : (
                <p className="mt-1.5 text-xs text-txt-lo">No freshness recorded for this product.</p>
              )}
              {d?.available ? (
                <p className="mt-1.5 text-xs leading-relaxed text-txt-mid">
                  Score drift (PSI) <b className={DRIFT_TONE[d.band] || 'text-txt-hi'}>{d.psi}</b>
                  {d.band && <> — {String(d.band).replace(/_/g, ' ')}</>}
                  {d.score_field && <> on <code className="font-mono text-[11px]">{d.score_field}</code></>}
                  {d.previous_model_run_id && (
                    <> · against run <code className="font-mono text-[11px]">{String(d.previous_model_run_id).slice(0, 8)}</code></>
                  )}
                </p>
              ) : (
                <p className="mt-1.5 text-xs leading-relaxed text-txt-lo">
                  No drift figure: {d?.reason || 'the platform published none for this product'}.
                </p>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function DataSources() {
  const sync = useResource(({ signal }) => getSync({ signal }), [])
  const provenance = useResource(({ signal }) => getProvenance({ signal }), [])
  const version = useResource(({ signal }) => getVersion({ signal }), [])

  const syncRows = useMemo(() => (Array.isArray(sync.data) ? sync.data : []), [sync.data])
  const totalRecords = useMemo(
    () => syncRows.reduce((sum, row) => sum + (Number.isFinite(row?.records) ? row.records : 0), 0),
    [syncRows],
  )
  const sortedRows = useMemo(() => (
    [...syncRows].sort((a, b) => {
      if (Boolean(a.live) !== Boolean(b.live)) return a.live ? -1 : 1
      return Number(a.api_id) - Number(b.api_id)
    })
  ), [syncRows])

  const realData = provenance.data ? Boolean(provenance.data.real_data) : sync.meta ? Boolean(sync.meta.real_data) : null

  return (
    <AppShell title="Data sources and sync" help="sources">
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-bold text-txt-hi">Data sources and sync</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-txt-mid">
            Every API SANKET is registered to call, whether it has actually been called, and the provenance
            of the two published model runs that feed the rest of this product — straight from the platform,
            not from documentation.
          </p>
          {version.data && (
            <p className="mt-1 text-[11px] text-txt-lo">
              Platform v{version.data.version || '—'} · {version.data.environment || 'unknown environment'}
              {version.data.git_sha ? ` · ${version.data.git_sha}` : ''}
            </p>
          )}
          {provenance.data?.cached?.apis?.length > 0 && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs leading-relaxed text-txt-mid">
              <History size={12} className="shrink-0 text-signal-teal" aria-hidden="true" />
              <span>
                <b className="text-txt-hi">{provenance.data.cached.apis.length}</b> API
                {provenance.data.cached.apis.length === 1 ? '' : 's'} answered tonight from a cached last-good pull
                {provenance.data.cached.last_reused_at && <>, most recently {fmtDateTime(provenance.data.cached.last_reused_at)}</>}.
                The bytes are the bank’s; they are not counted as live.
              </span>
            </p>
          )}
        </div>

        {sync.loading && <Loading label="Loading sync status…" />}
        {!sync.loading && sync.error && (
          <ErrorState title="Could not load sync status" error={sync.error} onRetry={sync.reload} />
        )}

        {!sync.loading && !sync.error && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat
                icon={Antenna}
                label="APIs called live"
                value={num(sync.meta?.live_apis?.length ?? 0)}
                hint={`of ${num(sync.meta?.total ?? syncRows.length)} registered`}
                tone={(sync.meta?.live_apis?.length ?? 0) > 0 ? 'text-signal-teal' : 'text-txt-hi'}
              />
              <Stat
                icon={Database}
                label="Records pulled"
                value={num(totalRecords)}
                hint="summed across every registered API"
              />
              <Stat
                icon={realData ? ShieldAlert : CircleSlash}
                label="Real bank data"
                value={realData ? 'Yes' : 'No'}
                tone={realData ? 'text-signal-teal' : 'text-signal-amber'}
                hint={realData ? undefined : 'every figure below is fixture or simulated'}
              />
              <Stat
                icon={Landmark}
                label="Gateway mode"
                value={String(sync.meta?.gateway?.mode ?? 'unknown').toUpperCase()}
                tone={sync.meta?.gateway?.mode === 'live' ? 'text-signal-teal' : 'text-signal-amber'}
                hint={sync.meta?.gateway?.reason || undefined}
              />
            </div>

            {provenance.data && !provenance.data.real_data && (
              <div
                role="status"
                className="flex items-start gap-3 rounded-xl border border-signal-amber/40 bg-signal-amber/10 px-4 py-3.5"
              >
                <TriangleAlert size={18} className="mt-0.5 shrink-0 text-signal-amber" aria-hidden="true" />
                <div className="text-sm leading-relaxed text-txt-hi">
                  <p className="font-bold">No family has been pulled from a bank API.</p>
                  <p className="mt-1 text-txt-mid">
                    Every number this product shows right now is FIXTURE or SIMULATED. Quoting{' '}
                    <code className="rounded bg-ink-900 px-1 py-0.5 font-mono text-[11px]">meta/provenance</code>{' '}
                    verbatim:
                  </p>
                  <p className="mt-1.5 italic text-txt-mid">&ldquo;{provenance.data.note}&rdquo;</p>
                </div>
              </div>
            )}
            {!provenance.loading && provenance.error && (
              <p className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-txt-lo">
                <TriangleAlert size={13} aria-hidden="true" />
                Could not confirm family-level provenance from <code className="font-mono">meta/provenance</code>.
                <button
                  type="button"
                  onClick={provenance.reload}
                  className="inline-flex items-center gap-1 font-semibold text-signal-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
                >
                  <RefreshCw size={12} aria-hidden="true" /> Retry
                </button>
              </p>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              {PRODUCT_ORDER.map((product) => (
                <ProductRunCard key={product} product={product} run={sync.meta?.runs?.[product]} />
              ))}
            </div>

            <FreshnessCard freshness={provenance.data?.freshness} drift={provenance.data?.drift} />

            <Card
              title="API calls"
              subtitle="One row per API this platform is registered to call. Live rows first, then by API id."
              source="NOT_COLLECTED"
              sourceDetail="This table is operational metadata about calls, not a bank figure — each row already states its own call status."
              labelledBy="ds-api-table-title"
            >
              {sortedRows.length === 0 ? (
                <Empty title="No APIs registered" hint="The platform has no APIs registered against this build." icon={Tag} />
              ) : (
                <div className="overflow-x-auto scroll-thin">
                  <table className="w-full text-left text-sm">
                    <caption className="sr-only">Registered bank APIs, their call status and last pull</caption>
                    <thead className="text-[11px] uppercase tracking-wide text-txt-lo">
                      <tr className="border-b border-line">
                        <th scope="col" className="py-2 pr-3 font-semibold">API</th>
                        <th scope="col" className="py-2 pr-3 font-semibold">Used by</th>
                        <th scope="col" className="py-2 pr-3 text-right font-semibold">Calls</th>
                        <th scope="col" className="py-2 pr-3 text-right font-semibold">Records</th>
                        <th scope="col" className="py-2 pr-3 font-semibold">Last status</th>
                        <th scope="col" className="py-2 pr-3 font-semibold">Last pulled</th>
                        <th scope="col" className="py-2 pr-3 font-semibold">Subscription</th>
                        <th scope="col" className="py-2 pr-3 font-semibold">Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row) => (
                        <tr key={row.api_id} className="border-b border-line/60 last:border-b-0">
                          <td className="py-2 pr-3">
                            <div className="font-semibold text-txt-hi">{row.label || row.api_id}</div>
                            <div className="text-[11px] text-txt-lo">
                              API <code className="font-mono">{row.api_id}</code>
                            </div>
                          </td>
                          <td className="py-2 pr-3">
                            <div className="flex flex-wrap gap-1">
                              {(row.used_by || []).map((p) => (
                                <span
                                  key={p}
                                  className="rounded-full border border-line-strong bg-ink-600 px-1.5 py-0.5 text-[10px] font-semibold text-txt-mid"
                                >
                                  {USED_BY_LABEL[p] || p}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-txt-mid">{num(row.calls)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums text-txt-mid">{num(row.records)}</td>
                          <td className="py-2 pr-3">
                            <div className="flex flex-wrap items-center gap-1.5">
                              {row.served_from_cache || row.last_mode === 'cached' ? (
                                <span className="inline-flex items-center gap-1 rounded-full border border-signal-teal/40 bg-signal-teal/15 px-2 py-0.5 text-[10px] font-bold uppercase text-signal-teal">
                                  <History size={10} aria-hidden="true" /> Bank API · last good pull
                                </span>
                              ) : row.live ? (
                                <span className="inline-flex items-center gap-1 rounded-full border border-signal-teal/40 bg-signal-teal/15 px-2 py-0.5 text-[10px] font-bold uppercase text-signal-teal">
                                  <Antenna size={10} aria-hidden="true" /> Live
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-ink-600 px-2 py-0.5 text-[10px] font-bold uppercase text-txt-mid">
                                  <CircleSlash size={10} aria-hidden="true" /> Not called
                                </span>
                              )}
                              {(row.served_from_cache || row.last_mode === 'cached') && row.last_success_at && (
                                <span className="text-[11px] text-txt-lo">({fmtDateTime(row.last_success_at)})</span>
                              )}
                              {row.last_status && <span className="text-xs text-txt-mid">{row.last_status}</span>}
                            </div>
                          </td>
                          <td className="py-2 pr-3 text-txt-mid">{fmtDateTime(row.last_pulled_at)}</td>
                          <td className="py-2 pr-3 text-txt-mid">{row.subscription_status || '—'}</td>
                          <td className="py-2 pr-3 text-txt-lo">{row.note || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </AppShell>
  )
}
