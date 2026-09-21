import { useMemo } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  CircleSlash, Clock, Gauge, PhoneOutgoing, ShieldOff, TrendingUp, Users,
} from 'lucide-react'
import AppShell from '../components/AppShell'
import Card, { Stat } from '../components/Card'
import ChartFrame, { AXIS, COLOR, GRID, TOOLTIP } from '../components/ChartFrame'
import NotInBuild from '../components/NotInBuild'
import ErrorState from '../components/states/ErrorState'
import Loading from '../components/states/Loading'
import PermissionDenied from '../components/states/PermissionDenied'
import { useAuth } from '../auth/AuthContext'
import useResource from '../data/useResource'
import { usePack } from '../data/PackContext'
import { getFunnel } from '../lib/sanket'
import { funnelFromPack, readMetrics } from '../lib/pack'
import { PRODUCTS, STAGES, STAGE_LABEL, num, pct, productLabel, suppressionLabel } from '../lib/fmt'

/**
 * The manager's one screen: where the drop-off book is, who is working it, and what the
 * model is actually worth on it.
 *
 * Live it is one call — `GET /sanket/funnel` (x-roles M, A). In the static bundle there is
 * no backend, so the same panels are derived from `app/public/sanket_data.json` and every
 * panel the pack cannot support says so instead of drawing an empty chart.
 */
export default function ManagerDashboard() {
  const { isStatic, role } = useAuth()
  const pack = usePack()
  const live = useResource(({ signal }) => getFunnel({ signal }), [], { enabled: !isStatic })

  const data = isStatic ? funnelFromPack(pack.data) : live.data
  const loading = isStatic ? pack.loading : live.loading
  const error = isStatic ? pack.error : live.error
  const metrics = useMemo(() => readMetrics(data?.published_metrics), [data])
  const headline = metrics?.headline || null
  // See the Suppressed `Stat`'s hint below: the denominator for "share of the book
  // suppressed" has to be the same population `data.suppressed` was counted over.
  const suppressedPoolTotal = data?.pool ?? data?.leads ?? null

  const sourceBadge = isStatic ? 'SIMULATED' : (live.meta?.provenance_mode === 'fixture' ? 'FIXTURE' : 'SIMULATED')
  const sourceDetail = isStatic
    ? 'The bundled export from src/score_and_pack.py. No backend answered this page load.'
    : `Published model_run ${live.meta?.model_run_id || 'unknown'}, provenance ${live.meta?.provenance_mode || 'unknown'}.`

  if (loading) return <AppShell title="Manager dashboard" help="dashboard"><Loading label="Loading the drop-off book…" /></AppShell>
  if (error?.isForbidden) {
    return (
      <AppShell title="Manager dashboard" help="dashboard">
        <PermissionDenied role={role} allowed={['M', 'A']} />
      </AppShell>
    )
  }
  if (error) {
    return (
      <AppShell title="Manager dashboard" help="dashboard">
        <ErrorState title="The dashboard could not be loaded" error={error} onRetry={isStatic ? pack.reload : live.reload} />
      </AppShell>
    )
  }
  if (!data?.published) {
    return (
      <AppShell title="Manager dashboard" help="dashboard">
        <NotInBuild
          what="A published SANKET model run"
          keys={['model_run']}
          hint="Nothing has been published yet. `python -m app.fixtures load --product sanket` publishes a run; the batch runner publishes a real one."
        />
      </AppShell>
    )
  }

  return (
    <AppShell title="Manager dashboard" help="dashboard">
      <div className="space-y-5">
        {/* Every screen carries a visible h2 under AppShell's (screen-reader-only) h1, so
            the Card headings at h3 never skip a level. Lighthouse caught this one. */}
        <header>
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <Gauge size={18} className="text-signal-amber" aria-hidden="true" /> Manager dashboard
          </h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-txt-lo">
            The drop-off book: who abandoned an application, where they stopped, who is working
            them, how many are still inside their contact window, and how many the bank held back.
          </p>
        </header>

        <Headline headline={headline} metrics={metrics} source={sourceBadge} detail={sourceDetail} />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat icon={Users} label="Leads in the book" value={num(data.leads)} hint="drop-off population at this run" testId="kpi-leads" />
          <Stat
            icon={ShieldOff}
            label="Suppressed"
            value={data.suppressed == null ? '—' : num(data.suppressed)}
            // `data.suppressed` is always a full-pool count (live: `lead` rows for this
            // run; static: `metrics.suppression.suppressed_count`, both counted over the
            // whole drop-off population). The percentage has to divide by that same
            // population, not by `data.leads` — in live mode `data.leads` already is that
            // population (one SQL query counts both), but in static mode `data.leads` is
            // only the bundled sample's row count (a few hundred, out of thousands), which
            // used to read a nonsense >100% ("560% suppressed"). `data.pool`, present only
            // on the static path, carries the real denominator; live mode falls back to
            // `data.leads`, which is already correct there.
            hint={suppressedPoolTotal ? `${pct((data.suppressed || 0) / suppressedPoolTotal, 0)} of the book — never queued` : 'never queued'}
            tone="text-signal-rose"
            testId="kpi-suppressed"
          />
          <Stat
            icon={Clock}
            label="Window still open"
            value={data.sla ? num(data.sla.window_open) : '—'}
            hint={data.sla ? `${num(data.sla.window_expired)} have run out` : 'not computed in this build'}
            tone="text-signal-teal"
            testId="kpi-window-open"
          />
          <Stat
            icon={PhoneOutgoing}
            label="Unassigned"
            value={data.unassigned == null ? '—' : num(data.unassigned)}
            hint="waiting for a round-robin run"
            testId="kpi-unassigned"
          />
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <FunnelPanel data={data} source={sourceBadge} detail={sourceDetail} />
          <ProductMix mix={data.product_mix} source={sourceBadge} detail={sourceDetail} />
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <RmLoad rows={data.rm_load} dispositions={data.dispositions} source={sourceBadge} detail={sourceDetail} />
          <SlaVsWindow sla={data.sla} source={sourceBadge} detail={sourceDetail} />
        </div>

        {/*
          `book` is the same denominator as the KPI hint above. `data.leads` is only the
          bundled sample in static mode, so "N suppressed of {leads}" could print a count
          larger than the book it claims to be a part of.
        */}
        <Suppression
          byReason={data.suppression_by_reason}
          total={data.suppressed}
          book={suppressedPoolTotal}
          source={sourceBadge}
          detail={sourceDetail}
        />
      </div>
    </AppShell>
  )
}

/**
 * The headline, computed — never typed.
 *
 * Both numbers are disbursement rates over the same drop-off population and the same
 * hundred calls: one calls at random, the other calls the model's top 10%. If either is
 * absent from the source, the panel says which key it wanted. If the random baseline is
 * genuinely zero (a small fixture with no disbursements at all), there is no lift to
 * quote and the panel says that too, rather than printing an infinity.
 */
function Headline({ headline, metrics, source, detail }) {
  if (!headline) {
    return (
      <Card title="The conversion claim" source="NOT_COLLECTED" labelledBy="headline-title">
        <NotInBuild
          what="The headline"
          keys={['published_metrics.baseline_dropoff_disbursement', 'published_metrics.precision_at.10', 'metrics.headline_parts']}
          hint="It is computed from two measured rates and is never hard-coded, so with neither rate present there is nothing honest to show."
        />
      </Card>
    )
  }
  const base = metrics?.precisionAt10
  return (
    <Card
      title="The conversion claim"
      subtitle="Both figures are disbursement rates over the same drop-off population and the same hundred calls."
      source={source}
      sourceDetail={detail}
      labelledBy="headline-title"
      className="bg-gradient-to-r from-ink-700 to-ink-800"
    >
      <p className="max-w-3xl text-xl font-bold leading-snug sm:text-2xl" data-testid="headline">
        <span className="text-signal-rose">{headline.basePer100}</span>
        <span className="mx-2 text-txt-lo" aria-hidden="true">→</span>
        <span className="sr-only">rises to</span>
        <span className="text-signal-teal">{headline.modelPer100}</span>{' '}
        disbursements per 100 RM calls
      </p>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-txt-mid">
        A random call into this population disburses at <b className="text-txt-hi">{pct(headline.baseline, 1)}</b>;
        calling the model's top <b className="text-txt-hi">{pct(headline.budget, 0)}</b> disburses
        at <b className="text-txt-hi">{pct(headline.precision, 1)}</b>
        {base?.lo != null && base?.hi != null && (
          <> (95% CI {pct(base.lo, 1)}–{pct(base.hi, 1)}{base.n ? `, n=${num(base.n)}` : ''})</>
        )}.
      </p>
      {headline.lift == null ? (
        <p className="mt-2 text-xs leading-relaxed text-txt-lo">
          The random baseline in this run is zero, so there is no multiple to quote. A lift needs a
          denominator; an "infinite" one is not a claim anybody should make.
        </p>
      ) : (
        <p className="mt-2 text-xs leading-relaxed text-txt-lo">
          That is {headline.lift.toFixed(1)}× the random call list — measured on held-out customers,
          not asserted. {headline.note || ''}
        </p>
      )}
      {metrics?.note && <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">{metrics.note}</p>}
    </Card>
  )
}

/** Where the abandoned applications stopped. */
function FunnelPanel({ data, source, detail }) {
  const published = data.published_metrics?.funnel
  // `published_metrics.funnel` is a real funnel (each stage's survivors, with drop rates).
  // `stage_reached` is not: it counts applications by the stage they STOPPED at, so its
  // bars legitimately go up as well as down. Drawing the second under the first's wording
  // makes an honest histogram look like a broken funnel.
  const isFunnel = Array.isArray(published) && published.length > 0
  const rows = useMemo(() => {
    if (Array.isArray(published) && published.length) {
      return published.map((r) => ({
        stage: r.stage,
        name: STAGE_LABEL[r.stage] || r.stage,
        n: r.n,
        dropPct: r.drop_rate == null ? null : +(r.drop_rate * 100).toFixed(1),
      }))
    }
    const reached = data.stage_reached
    if (!reached) return null
    const known = STAGES.filter((s) => s in reached)
    const rest = Object.keys(reached).filter((s) => !STAGES.includes(s))
    return [...known, ...rest].map((stage) => ({
      stage, name: STAGE_LABEL[stage] || stage, n: reached[stage], dropPct: null,
    }))
  }, [published, data.stage_reached])

  return (
    <Card
      title="Where the application stopped"
      subtitle={isFunnel
        ? 'Start → Eligibility → KYC → Documents → ₹1,000 fee → Offer → Accept → Disburse, with the drop at each step.'
        : 'How many abandoned applications stopped at each stage. Not a cumulative funnel — a stage with more applications than the one before it simply lost more people.'}
      source={source}
      sourceDetail={detail}
      labelledBy="funnel-title"
    >
      {!rows ? (
        <NotInBuild what="The stage funnel" keys={['published_metrics.funnel', 'stage_reached']} />
      ) : (
        <>
          <ChartFrame
            title={isFunnel ? 'Applications surviving each stage' : 'Applications by the stage they stopped at'}
            summary={`${isFunnel ? 'Applications surviving each stage' : 'Applications by the stage they stopped at'}: ${rows.map((r) => `${r.name} ${r.n}`).join(', ')}.`}
            height={240}
            rows={rows}
            columns={[
              { key: 'name', label: 'Stage' },
              { key: 'n', label: isFunnel ? 'Reached this stage' : 'Stopped here' },
              { key: 'dropPct', label: 'Drop rate %', format: (v) => (v == null ? 'not measured' : `${v}%`) },
            ]}
          >
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
              <XAxis type="number" tick={AXIS} />
              <YAxis type="category" dataKey="name" tick={AXIS} width={92} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#1D2549' }} formatter={(v) => [num(v), isFunnel ? 'reached this stage' : 'stopped here']} />
              <Bar dataKey="n" radius={[0, 5, 5, 0]} isAnimationActive={false}>
                <LabelList dataKey="n" position="right" style={{ fontSize: 11, fill: '#EAEDFB', fontWeight: 700 }} />
                {rows.map((r) => (
                  <Cell key={r.stage} fill={r.stage === 'fee' ? COLOR.rose : COLOR.amber} />
                ))}
              </Bar>
            </BarChart>
          </ChartFrame>
          <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
            The ₹1,000 processing fee is drawn in rose because it is the stage the mentors singled out:
            a customer who walks away there is the clearest window-shopper signal in the journey.
          </p>
        </>
      )}
    </Card>
  )
}

/** Six products, not three. */
function ProductMix({ mix, source, detail }) {
  const rows = useMemo(() => {
    if (!Array.isArray(mix) || mix.length === 0) return null
    const order = new Map(PRODUCTS.map((p, i) => [p, i]))
    return [...mix]
      .sort((a, b) => (order.get(a.product) ?? 99) - (order.get(b.product) ?? 99))
      .map((r) => ({
        product: r.product,
        name: productLabel(r.product),
        leads: r.leads,
        suppressed: r.suppressed ?? 0,
        queueable: Math.max(0, (r.leads || 0) - (r.suppressed || 0)),
        meanScore: r.mean_score == null ? null : +(r.mean_score * 100).toFixed(1),
      }))
  }, [mix])

  return (
    <Card
      title="Product mix"
      subtitle="All six products the single model ranks — queueable versus suppressed."
      source={source}
      sourceDetail={detail}
      labelledBy="mix-title"
    >
      {!rows ? (
        <NotInBuild what="The product mix" keys={['product_mix']} />
      ) : (
        <>
          <ChartFrame
            title="Leads by product"
            summary={`Leads by product: ${rows.map((r) => `${r.name} ${r.leads}, of which ${r.suppressed} suppressed`).join('; ')}.`}
            height={240}
            rows={rows}
            columns={[
              { key: 'name', label: 'Product' },
              { key: 'queueable', label: 'Queueable' },
              { key: 'suppressed', label: 'Suppressed' },
              { key: 'meanScore', label: 'Mean score %', format: (v) => (v == null ? 'not measured' : `${v}%`) },
            ]}
          >
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 30, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
              <XAxis type="number" tick={AXIS} />
              <YAxis type="category" dataKey="name" tick={AXIS} width={132} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#1D2549' }} />
              <Bar dataKey="queueable" name="Queueable" stackId="p" fill={COLOR.teal} isAnimationActive={false} />
              <Bar dataKey="suppressed" name="Suppressed" stackId="p" fill={COLOR.rose} radius={[0, 5, 5, 0]} isAnimationActive={false} />
            </BarChart>
          </ChartFrame>
          <ul className="mt-2 flex flex-wrap gap-3 text-[11px] text-txt-mid">
            <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-signal-teal" aria-hidden="true" /> Queueable</li>
            <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-signal-rose" aria-hidden="true" /> Suppressed</li>
          </ul>
        </>
      )}
    </Card>
  )
}

/** Who is carrying the book, and what came back from the calls. */
function RmLoad({ rows, dispositions, source, detail }) {
  const list = Array.isArray(rows) ? [...rows].sort((a, b) => (b.leads || 0) - (a.leads || 0)) : null
  const dispEntries = dispositions && typeof dispositions === 'object' ? Object.entries(dispositions) : null
  const dispTotal = dispEntries?.reduce((sum, [, v]) => sum + (Number(v) || 0), 0) ?? 0

  return (
    <Card
      title="RM load and conversion"
      subtitle="Round-robin assigns across the seeded roster; conversion is what the dispositions say came back."
      source={source}
      sourceDetail={detail}
      labelledBy="rm-title"
    >
      {!list || list.length === 0 ? (
        <NotInBuild what="RM load" keys={['rm_load']} hint="Nothing has been assigned yet. Assign from the lead queue." />
      ) : (
        // A scrollable region that cannot be focused is unreachable by keyboard, which axe
        // reports as a serious failure (scrollable-region-focusable). The fix is exactly
        // tabindex="0" plus a labelled role; jsx-a11y's rule allows tabIndex only on
        // `tabpanel` by default and does not know about this pattern, so it is silenced
        // here rather than the keyboard user being left without a way in.
        <div
          className="scroll-thin max-h-64 overflow-auto rounded-lg border border-line"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
          role="region"
          aria-label="Leads assigned to each relationship manager, scrollable"
        >
          <table className="w-full text-sm">
            <caption className="sr-only">Leads assigned to each relationship manager</caption>
            <thead className="sticky top-0 bg-ink-800 text-xs">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Relationship manager</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Assigned</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Still open</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.rm_ein} className="border-t border-ink-600/40">
                  <th scope="row" className="px-3 py-2 text-left font-mono text-xs font-normal text-txt-mid">{r.rm_ein}</th>
                  <td className="px-3 py-2 text-right tabular-nums text-txt-hi">{num(r.leads)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-txt-mid">{num(r.open)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3">
        <h4 className="mb-1.5 text-xs font-bold uppercase tracking-wider text-txt-lo">Call outcomes</h4>
        {!dispEntries || dispEntries.length === 0 ? (
          <NotInBuild what="Conversion by outcome" keys={['dispositions']} hint="No call has been dispositioned yet, so there is no conversion to report." compact />
        ) : (
          <ul className="space-y-1">
            {dispEntries.sort((a, b) => b[1] - a[1]).map(([outcome, n]) => (
              <li key={outcome} className="flex items-center gap-2 text-xs">
                <span className="w-56 shrink-0 text-txt-mid">{outcome.replace(/_/g, ' ')}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-900">
                  <div className="h-full rounded-full bg-signal-teal" style={{ width: `${dispTotal ? (n / dispTotal) * 100 : 0}%` }} />
                </div>
                <span className="w-10 text-right font-bold tabular-nums text-txt-hi">{num(n)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

/** The mentors' per-product window, as an SLA a manager can be held to. */
function SlaVsWindow({ sla, source, detail }) {
  if (!sla) {
    return (
      <Card title="SLA against the contact window" source="NOT_COLLECTED" labelledBy="sla-title">
        <NotInBuild
          what="The window split"
          keys={['sla']}
          hint="The window runs from the abandonment timestamp for the number of days the product allows. It is resolved server-side; the bundled export has no server."
        />
      </Card>
    )
  }
  const total = (sla.window_open || 0) + (sla.window_expired || 0) + (sla.no_window || 0)
  const days = sla.windows_days || {}
  const rows = PRODUCTS.filter((p) => p in days).map((p) => ({ product: p, name: productLabel(p), days: days[p] }))

  return (
    <Card
      title="SLA against the contact window"
      subtitle="A lead outside its window is not a lead — it is a customer who has moved on."
      source={source}
      sourceDetail={detail}
      labelledBy="sla-title"
    >
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-lg border border-signal-teal/40 bg-signal-teal/10 p-3">
          <div className="text-xl font-bold tabular-nums text-signal-teal">{num(sla.window_open)}</div>
          <div className="text-[11px] text-txt-mid">window open — call now</div>
        </div>
        <div className="rounded-lg border border-signal-rose/40 bg-signal-rose/10 p-3">
          <div className="text-xl font-bold tabular-nums text-signal-rose">{num(sla.window_expired)}</div>
          <div className="text-[11px] text-txt-mid">window closed</div>
        </div>
        <div className="rounded-lg border border-line-strong bg-ink-800 p-3">
          <div className="text-xl font-bold tabular-nums text-txt-mid">{num(sla.no_window)}</div>
          <div className="text-[11px] text-txt-mid">no window — no abandonment timestamp</div>
        </div>
      </div>
      {total > 0 && (
        <p className="mt-2 text-xs text-txt-mid">
          <TrendingUp size={13} className="mr-1 inline text-signal-amber" aria-hidden="true" />
          {pct((sla.window_open || 0) / total, 0)} of the book is still inside its window.
        </p>
      )}
      {rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <caption className="sr-only">Contact window length in days, by product</caption>
            <thead>
              <tr>
                <th scope="col" className="py-1 text-left font-semibold text-txt-lo">Product</th>
                {rows.map((r) => <th key={r.product} scope="col" className="py-1 text-right font-semibold text-txt-lo">{r.name}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row" className="py-1 text-left font-normal text-txt-mid">Window</th>
                {rows.map((r) => (
                  <td key={r.product} className="py-1 text-right tabular-nums text-txt-hi">{r.days}d</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/** Who was held back, and why — the count is a KPI precisely because it is a cost. */
function Suppression({ byReason, total, book, source, detail }) {
  const rows = byReason && typeof byReason === 'object'
    ? Object.entries(byReason).map(([reason, n]) => ({ reason, name: suppressionLabel(reason), n: Number(n) || 0 })).sort((a, b) => b.n - a.n)
    : null
  const max = rows?.reduce((m, r) => Math.max(m, r.n), 0) || 1

  return (
    <Card
      title="Suppressed, and why"
      subtitle="Scored, then held back before the queue. The count is shown because it is a real cost of doing this properly."
      source={rows ? source : 'NOT_COLLECTED'}
      sourceDetail={detail}
      labelledBy="supp-title"
      actions={total != null && (
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-signal-rose/40 bg-signal-rose/10 px-3 py-1.5 text-xs font-bold text-signal-rose">
          <CircleSlash size={13} aria-hidden="true" /> {num(total)} suppressed
          {book ? <span className="font-normal text-txt-mid">of {num(book)}</span> : null}
        </span>
      )}
    >
      {!rows || rows.length === 0 ? (
        <NotInBuild what="The suppression histogram" keys={['suppression_by_reason']} />
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.reason} className="flex items-center gap-3 text-sm">
              <span className="w-56 shrink-0 text-txt-mid">{r.name}</span>
              <div className="h-3 flex-1 overflow-hidden rounded-full bg-ink-900">
                <div className="h-full rounded-full bg-signal-rose/70" style={{ width: `${(r.n / max) * 100}%` }} />
              </div>
              <span className="w-12 text-right font-bold tabular-nums text-txt-hi">{num(r.n)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
        A suppressed lead is never quietly dropped: it is returned with its reasons when the queue is
        asked for it, so an RM can see that the bank chose not to call, and why.
      </p>
    </Card>
  )
}
