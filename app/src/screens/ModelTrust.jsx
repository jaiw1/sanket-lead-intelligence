import { Fragment, useMemo } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Ban, ClipboardCheck, ScanEye, Scale, Target, Wallet } from 'lucide-react'
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
import { readMetrics } from '../lib/pack'
import { PRODUCTS, num, pct, suppressionLabel } from '../lib/fmt'

const ciText = (m) => (m?.lo != null && m?.hi != null ? `95% CI ${pct(m.lo, 1)}–${pct(m.hi, 1)}${m.n ? `, n=${num(m.n)}` : ''}` : m?.n ? `n=${num(m.n)}` : '')

/**
 * The scorecard a bank's model-risk function would ask for, shown before they ask.
 *
 * Its data source is `GET /sanket/funnel`, whose `x-roles` are M and A — the platform has
 * no `sanket/metrics` route (DRISHTi has one; SANKET does not), so this screen is
 * manager-and-admin only in live mode. That is a CONTRACT GAP, not a design choice, and it
 * is written down in the L11 report rather than worked around by widening a guard.
 *
 * The pre-registered validation table comes from the BUNDLED EXPORT rather than the API,
 * for the same reason, and its panel says so in its own words. Mixing two sources on one
 * screen is only acceptable because each panel names the one it used.
 */
export default function ModelTrust() {
  const { isStatic, role } = useAuth()
  const pack = usePack()
  const live = useResource(({ signal }) => getFunnel({ signal }), [], { enabled: !isStatic })

  const source = isStatic ? pack.data?.metrics : live.data?.published_metrics
  const metrics = useMemo(() => readMetrics(source), [source])
  // The bands live only in the packed export: `src/model/pack.py` writes `metrics.bands`
  // and no endpoint serves them.
  const packMetrics = useMemo(() => readMetrics(pack.data?.metrics), [pack.data])

  const loading = isStatic ? pack.loading : live.loading
  const error = isStatic ? pack.error : live.error
  const badge = isStatic ? 'SIMULATED' : (live.meta?.provenance_mode === 'fixture' ? 'FIXTURE' : 'SIMULATED')
  const detail = isStatic
    ? 'The bundled export from src/score_and_pack.py.'
    : `Published model_run ${live.meta?.model_run_id || 'unknown'}.`

  if (loading) return <AppShell title="Model and trust" help="trust"><Loading label="Loading the model scorecard…" /></AppShell>
  if (error?.isForbidden) {
    return (
      <AppShell title="Model and trust" help="trust">
        <PermissionDenied role={role} allowed={['M', 'A']} />
        <p className="mt-3 text-xs leading-relaxed text-txt-lo">
          The model scorecard is served by <code className="font-mono">GET /sanket/funnel</code>, which the
          contract restricts to managers and administrators. There is no SANKET metrics route with a wider
          role — that gap is recorded for the backend lane rather than papered over here.
        </p>
      </AppShell>
    )
  }
  if (error) {
    return (
      <AppShell title="Model and trust" help="trust">
        <ErrorState title="The scorecard could not be loaded" error={error} onRetry={isStatic ? pack.reload : live.reload} />
      </AppShell>
    )
  }

  return (
    <AppShell title="Model and trust" help="trust">
      <div className="space-y-5">
        <header>
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <ScanEye size={18} className="text-signal-amber" aria-hidden="true" /> Model and trust
          </h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-txt-lo">
            One model across all six products. Everything below is measured on held-out customers, with
            confidence intervals where the sample is small enough to need them — which, in this build, is
            most of them.
          </p>
        </header>

        {!metrics ? (
          <NotInBuild what="The model scorecard" keys={['published_metrics', 'metrics']} />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat
                icon={Target}
                label="Macro AUC"
                value={metrics.aucMacro == null ? '—' : metrics.aucMacro.toFixed(3)}
                hint="across the six products"
                tone="text-signal-teal"
              />
              <Stat
                icon={Target}
                label="Precision @ top 10%"
                value={metrics.precisionAt10?.value == null ? '—' : pct(metrics.precisionAt10.value, 1)}
                hint={ciText(metrics.precisionAt10) || 'disbursement inside the window'}
                tone="text-signal-amber"
              />
              <Stat
                icon={ClipboardCheck}
                label="Menu-of-4 hit rate"
                value={metrics.menuHitRate?.value == null ? '—' : pct(metrics.menuHitRate.value, 1)}
                hint={ciText(metrics.menuHitRate) || 'the product taken was on the menu'}
              />
              <Stat
                icon={ClipboardCheck}
                label="Window respect"
                value={metrics.windowRespect?.value == null ? '—' : pct(metrics.windowRespect.value, 1)}
                hint={ciText(metrics.windowRespect) || 'ranked inside the product window'}
              />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <PerProductAuc metrics={metrics} source={badge} detail={detail} />
              <Calibration metrics={metrics} source={badge} detail={detail} />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <ShopperPanel metrics={metrics} source={badge} detail={detail} />
              <SuppressionExhibit metrics={metrics} source={badge} detail={detail} />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <Fairness metrics={metrics} source={badge} detail={detail} />
              <IncomeAccuracy metrics={metrics} source={badge} detail={detail} />
            </div>

            <Excluded metrics={metrics} source={badge} detail={detail} />
            <ValidationTable metrics={packMetrics} live={!isStatic} packError={pack.error} packLoading={pack.loading} />
          </>
        )}
      </div>
    </AppShell>
  )
}

/** Six products, each with its own AUC and its own interval. */
function PerProductAuc({ metrics, source, detail }) {
  const rows = useMemo(() => {
    if (!metrics.perProduct) return null
    const order = new Map(PRODUCTS.map((p, i) => [p, i]))
    return [...metrics.perProduct]
      .sort((a, b) => (order.get(a.product) ?? 99) - (order.get(b.product) ?? 99))
      .map((r) => ({ ...r, aucRounded: r.auc == null ? null : +r.auc.toFixed(3) }))
  }, [metrics.perProduct])

  return (
    <Card
      title="Ranking quality, per product"
      subtitle="AUC 0.5 is a coin flip. The pre-registered floor is 0.75 per product and 0.78 macro (SK-08, SK-09)."
      source={source}
      sourceDetail={detail}
      labelledBy="auc-title"
    >
      {!rows || rows.length === 0 ? (
        <NotInBuild what="Per-product AUC" keys={['published_metrics.per_product_auc', 'metrics.per_product']} />
      ) : (
        <>
          <ChartFrame
            title="AUC by product"
            summary={`Area under the ROC curve by product: ${rows.map((r) => `${r.label} ${r.auc?.toFixed(2) ?? 'not measured'}`).join(', ')}. The pre-registered floor is 0.75.`}
            height={210}
            rows={rows}
            columns={[
              { key: 'label', label: 'Product' },
              { key: 'aucRounded', label: 'AUC', format: (v) => (v == null ? 'not measured' : v) },
              { key: 'ci', label: '95% CI', format: (v) => (v?.lo == null ? 'not measured' : `${v.lo.toFixed(2)}–${v.hi.toFixed(2)}`) },
              { key: 'nPos', label: 'Positives in test', format: (v) => (v == null ? 'not reported' : v) },
            ]}
          >
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
              <XAxis type="number" domain={[0, 1]} tick={AXIS} />
              <YAxis type="category" dataKey="label" tick={AXIS} width={132} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#1D2549' }} formatter={(v) => [v, 'AUC']} />
              <ReferenceLine x={0.75} stroke={COLOR.rose} strokeDasharray="5 4" label={{ value: 'floor 0.75', fontSize: 9, fill: COLOR.rose, position: 'top' }} />
              <Bar dataKey="auc" radius={[0, 5, 5, 0]} isAnimationActive={false}>
                <LabelList dataKey="auc" position="right" formatter={(v) => (v == null ? '—' : v.toFixed(2))} style={{ fontSize: 11, fill: '#EAEDFB', fontWeight: 700 }} />
                {rows.map((r) => <Cell key={r.product} fill={r.auc >= 0.75 ? COLOR.teal : COLOR.rose} />)}
              </Bar>
            </BarChart>
          </ChartFrame>
          <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
            Bars below the floor are drawn in rose and are not explained away. With this few positives
            per product the interval is wide enough that a bar below the line is not yet evidence the
            model is bad — which is exactly why the interval is in the table beside it.
          </p>
        </>
      )}
    </Card>
  )
}

function Calibration({ metrics, source, detail }) {
  const rows = useMemo(() => {
    if (!metrics.calibration) return null
    return metrics.calibration.map((r, i) => ({
      key: i,
      pred: +(r.pred * 100).toFixed(1),
      obs: +(r.obs * 100).toFixed(1),
      n: r.n,
    }))
  }, [metrics.calibration])
  const max = rows ? Math.max(1, Math.ceil(Math.max(...rows.flatMap((r) => [r.pred, r.obs])))) : 1

  return (
    <Card
      title="Calibration — does the score mean what it says?"
      subtitle="Predicted probability against what actually happened, by decile. On the dashed line is trustworthy."
      source={source}
      sourceDetail={detail}
      labelledBy="cal-title"
    >
      {!rows ? (
        <NotInBuild what="The calibration curve" keys="calibration" />
      ) : (
        <ChartFrame
          title="Calibration"
          summary={`Predicted against observed disbursement rate by decile: ${rows.map((r) => `predicted ${r.pred}% observed ${r.obs}%`).join('; ')}.`}
          height={230}
          rows={rows}
          columns={[
            { key: 'pred', label: 'Predicted %' },
            { key: 'obs', label: 'Observed %' },
            { key: 'n', label: 'Customers' },
          ]}
        >
          <LineChart data={rows} margin={{ top: 6, right: 14, left: -8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
            <XAxis dataKey="pred" type="number" domain={[0, max]} tick={AXIS} unit="%" />
            <YAxis domain={[0, max]} tick={AXIS} unit="%" />
            <Tooltip contentStyle={TOOLTIP} formatter={(v) => [`${v}%`, 'observed']} labelFormatter={(l) => `predicted ${l}%`} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: max, y: max }]} stroke={COLOR.lo} strokeDasharray="5 4" />
            <Line type="linear" dataKey="obs" stroke={COLOR.teal} strokeWidth={2} dot={{ r: 3.5, fill: COLOR.teal, stroke: '#0B1026' }} isAnimationActive={false} />
          </LineChart>
        </ChartFrame>
      )}
    </Card>
  )
}

/** The window-shopper detector, and the honest caveat on its target. */
function ShopperPanel({ metrics, source, detail }) {
  const s = metrics.shopperAuc
  return (
    <Card
      title="Window-shopper detection"
      subtitle="Vague answers, refused income, the ₹1,000 fee balk and a document refusal — the four signals the mentors named."
      source={source}
      sourceDetail={detail}
      labelledBy="shopper-title"
    >
      {s?.value == null ? (
        <NotInBuild what="The shopper AUC" keys={['published_metrics.shopper_signal_auc', 'metrics.shopper.auc']} />
      ) : (
        <>
          <p className="text-3xl font-bold tabular-nums text-signal-amber">{s.value.toFixed(3)}</p>
          <p className="text-xs text-txt-lo">AUC against the generator's own window-shopper flag. {ciText(s)}</p>
          <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
            This is an <b className="text-txt-mid">upper bound</b>, and saying so matters: the target here is a
            latent flag the generator knows and production never will. In production the target is the
            observable proxy — two or more abandonments and no disbursement in twelve months — which is
            noisier, so the real number will be lower.
          </p>
        </>
      )}
    </Card>
  )
}

/** Who the bank chose not to call. A count that is meant to be uncomfortable. */
function SuppressionExhibit({ metrics, source, detail }) {
  const s = metrics.suppression
  const reasons = s?.by_reason || s?.reasons || null
  const rows = reasons ? Object.entries(reasons).map(([k, v]) => ({ reason: k, name: suppressionLabel(k), n: Number(v) || 0 })).sort((a, b) => b.n - a.n) : null
  const total = s?.n_suppressed ?? s?.suppressed_count ?? (rows ? rows.reduce((t, r) => t + r.n, 0) : null)

  return (
    <Card
      title="The suppression exhibit"
      subtitle="Scored, then held back. Shown because the honest cost of consent-first prospecting is a smaller queue."
      source={source}
      sourceDetail={detail}
      labelledBy="supp-exhibit-title"
    >
      {!rows ? (
        <NotInBuild what="The suppression breakdown" keys={['published_metrics.suppression', 'metrics.suppression']} />
      ) : (
        <>
          <p className="text-3xl font-bold tabular-nums text-signal-rose">{num(total)}</p>
          <p className="mb-3 text-xs text-txt-lo">customers scored and then not queued</p>
          <ul className="space-y-1.5">
            {rows.map((r) => (
              <li key={r.reason} className="flex items-center gap-2 text-xs">
                <span className="w-52 shrink-0 text-txt-mid">{r.name}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-900">
                  <div className="h-full rounded-full bg-signal-rose/70" style={{ width: `${total ? (r.n / total) * 100 : 0}%` }} />
                </div>
                <span className="w-10 text-right font-bold tabular-nums text-txt-hi">{num(r.n)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

/** The fairness result, including the failure. */
function Fairness({ metrics, source, detail }) {
  const rows = metrics.fairness
  const failing = rows?.filter((f) => !f.passes) || []
  const gig = rows?.find((f) => String(f.group).toLowerCase() === 'gig')

  return (
    <Card
      title="Fairness — the 80% rule on the calling queue"
      subtitle="Each group's selection rate into the contacted budget, as a ratio of the most-selected group. Below 0.80 fails."
      source={source}
      sourceDetail={detail}
      labelledBy="fair-title"
    >
      {!rows || rows.length === 0 ? (
        <NotInBuild what="The fairness table" keys="fairness" />
      ) : (
        <>
          <table className="w-full text-xs">
            <caption className="sr-only">Adverse impact ratio by group, against the 80% rule</caption>
            <thead>
              <tr>
                <th scope="col" className="py-1 text-left font-semibold text-txt-lo">Dimension</th>
                <th scope="col" className="py-1 text-left font-semibold text-txt-lo">Group</th>
                <th scope="col" className="py-1 text-right font-semibold text-txt-lo">Selection rate</th>
                <th scope="col" className="py-1 text-right font-semibold text-txt-lo">Ratio</th>
                <th scope="col" className="py-1 text-right font-semibold text-txt-lo">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f, i) => (
                <tr key={`${f.dim}-${f.group}-${i}`} className="border-t border-line">
                  <th scope="row" className="py-1.5 text-left font-normal text-txt-lo">{f.dim}</th>
                  <td className="py-1.5 capitalize text-txt-mid">{f.group}{f.n ? <span className="text-txt-lo"> (n={num(f.n)})</span> : null}</td>
                  <td className="py-1.5 text-right tabular-nums text-txt-mid">{f.sel_rate == null ? '—' : pct(f.sel_rate, 1)}</td>
                  <td className={`py-1.5 text-right font-bold tabular-nums ${f.passes ? 'text-signal-teal' : 'text-signal-rose'}`}>{f.ratio?.toFixed(2)}</td>
                  <td className={`py-1.5 text-right text-[10px] font-bold ${f.passes ? 'text-signal-teal' : 'text-signal-rose'}`}>{f.passes ? 'PASS' : 'FAIL'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {failing.length > 0 ? (
            <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
              <b className="text-signal-rose">The failure is shown, not hidden.</b>{' '}
              {gig && !gig.passes
                ? <>Gig workers are under-selected at a ratio of {gig.ratio.toFixed(2)} because volatile income depresses the capacity score. Two mitigations are in the design and neither is a re-weighting of the label: capacity uses the behavioural <i>median</i> rather than a payslip, and production adds segment-aware calling quotas so the queue cannot quietly exclude gig earners.</>
                : <>{failing.length} group{failing.length === 1 ? '' : 's'} fall below the 0.80 ratio. They are reported rather than dropped from the table.</>}
            </p>
          ) : (
            <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
              Every group clears 0.80 in this run. With samples this small that is not yet a guarantee —
              it is one run's result, reported as one run's result.
            </p>
          )}
        </>
      )}
    </Card>
  )
}

function IncomeAccuracy({ metrics, source, detail }) {
  const a = metrics.incomeAcc
  return (
    <Card
      title="Income estimation — measured, not asserted"
      subtitle="The behavioural income estimate behind every safe-EMI figure, against each held-out customer's true income."
      source={source}
      sourceDetail={detail}
      labelledBy="income-title"
    >
      {!a ? (
        <NotInBuild what="Income accuracy" keys="income_acc" />
      ) : (
        <div className="grid grid-cols-2 gap-3 text-center">
          <Figure value={pct(a.within10, 0)} label="within ±10%" tone="text-signal-teal" />
          <Figure value={pct(a.within15, 0)} label="within ±15%" tone="text-signal-teal" />
          <Figure value={pct(a.gig_within15, 0)} label="gig workers within ±15% — the hardest segment, shown honestly" tone="text-signal-amber" />
          <Figure value={pct(a.median_err, 1)} label="median estimation error" />
        </div>
      )}
    </Card>
  )
}

function Figure({ value, label, tone = 'text-txt-hi' }) {
  return (
    <div className="rounded-lg border border-line bg-ink-800 p-4">
      <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
      <div className="mt-1 text-[11px] leading-tight text-txt-lo">{label}</div>
    </div>
  )
}

function Excluded({ metrics, source, detail }) {
  return (
    <Card
      title="Features we refused to use"
      subtitle="Anti-leakage and fairness by construction, rather than by correction afterwards."
      source={source}
      sourceDetail={detail}
      labelledBy="excluded-title"
    >
      {!metrics.excludedFeatures ? (
        <NotInBuild what="The exclusion list" keys="excluded_features" />
      ) : (
        <ul className="space-y-2">
          {metrics.excludedFeatures.map((f, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded bg-signal-rose/15 text-signal-rose">
                <Ban size={11} aria-hidden="true" />
              </span>
              <span className="text-txt-mid">{f}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

const VERDICT_TONE = {
  pass: 'text-signal-teal',
  fail: 'text-signal-rose',
  report: 'text-signal-amber',
  not_measured: 'text-txt-lo',
  pending: 'text-txt-lo',
}

/**
 * `bands[*].observed` (and its older sibling `value`) is a plain number for every gating
 * band, but three `op: "report"` bands ship a structured breakdown instead of one figure —
 * SK-03 (precision at two extra budgets), SK-06 (the headline's two per-100 counts) and
 * SK-10 (AUC/precision cut by seven dimensions). `src/model/pack.py` packs that shape on
 * purpose; the table just has to read it defensively rather than hand React an object as a
 * child (a hard crash) or hand the viewer raw JSON (unreadable, and it can run to a few KB
 * for SK-10). Anything recognised is summarised in one line; anything else is named as a
 * multi-part figure rather than either crashing or being rendered as if it were empty.
 */
function formatObserved(value, verdict) {
  if (value === null || value === undefined) {
    return verdict === 'not_measured' || verdict === 'not_run' ? 'not measured' : '—'
  }
  if (typeof value !== 'object') return value
  if (value.at_5pct && value.at_20pct) {
    return `${pct(value.at_5pct.precision, 1)} @5% · ${pct(value.at_20pct.precision, 1)} @20%`
  }
  if (value.baseline_per_100 != null && value.model_per_100 != null) {
    return `${value.baseline_per_100} → ${value.model_per_100} / 100`
  }
  if (Array.isArray(value)) return `${value.length} row${value.length === 1 ? '' : 's'} reported`
  const keys = Object.keys(value)
  return keys.length ? `reported, ${keys.length} part${keys.length === 1 ? '' : 's'} — see MODEL_CARD.md` : 'reported'
}

/**
 * The pre-registered criteria, with their verdicts as recorded.
 *
 * `validation/criteria.yaml` is committed before the first result, so the git timestamp is
 * the pre-registration. `src/model/pack.py` writes each SK-* band's verdict into the packed
 * export. Nothing is re-graded here: a `fail` renders as a fail, and a `not_measured`
 * renders as not measured rather than being quietly omitted to make the table look better.
 */
function ValidationTable({ metrics, live, packError, packLoading }) {
  const bands = metrics?.bands
  const rows = useMemo(() => (bands ? Object.entries(bands).map(([id, v]) => ({ id, ...v })).sort((a, b) => a.id.localeCompare(b.id)) : null), [bands])
  const tally = useMemo(() => {
    if (!rows) return null
    const acc = rows.reduce((acc, r) => { acc[r.verdict] = (acc[r.verdict] || 0) + 1; return acc }, {})
    // A band can pass on the packed seed and fail on the 5-seed mean (SK-04 is the
    // pre-registered example) — `agrees_across_seeds: false` is the disclosure signal.
    // That is a second, separately-counted honest fail, not folded into `acc.fail`,
    // which only ever reflects the packed-seed verdict rendered in the main column.
    acc.seedMeanFail = rows.filter((r) => r.verdict_on_seed_mean && r.verdict_on_seed_mean !== r.verdict && r.verdict_on_seed_mean === 'fail').length
    return acc
  }, [rows])

  return (
    <Card
      title="Pre-registered validation criteria"
      subtitle="Committed to validation/criteria.yaml before the first result — the git timestamp is the pre-registration."
      source="SIMULATED"
      sourceDetail="Read from the bundled export, app/public/sanket_data.json."
      labelledBy="validation-title"
      actions={tally && (
        <span className="text-xs text-txt-mid">
          <b className="text-signal-teal">{tally.pass || 0} pass</b>
          {tally.fail ? <> · <b className="text-signal-rose">{tally.fail} fail</b></> : null}
          {tally.seedMeanFail ? <> · <b className="text-signal-rose">{tally.seedMeanFail} fail{tally.seedMeanFail === 1 ? '' : 's'} on 5-seed mean</b></> : null}
          {tally.report ? <> · <b className="text-signal-amber">{tally.report} report-only</b></> : null}
          {tally.not_measured ? <> · {tally.not_measured} not measured</> : null}
        </span>
      )}
    >
      {live && (
        <p className="mb-3 rounded-lg border border-line-strong bg-ink-800 px-3 py-2 text-[11px] leading-relaxed text-txt-mid">
          <b className="text-txt-hi">This panel reads a different source from the rest of the screen.</b>{' '}
          The platform API has a <code className="font-mono">drishti/validation</code> route and no SANKET
          counterpart, so the pre-registered table comes from the bundled export rather than the published
          model run. Everything above comes from the run.
        </p>
      )}
      {packLoading && <Loading label="Loading the bundled export…" />}
      {!packLoading && packError && (
        <NotInBuild
          what="The validation table"
          keys={['metrics.bands']}
          hint="The bundled export could not be read on this page load."
        />
      )}
      {!packLoading && !packError && !rows && (
        <NotInBuild
          what="The validation table"
          keys={['metrics.bands']}
          hint="SM-1's rewrite of src/score_and_pack.py writes a verdict per SK-* criterion. A pre-SM-1 export carries none."
        />
      )}
      {rows && (
        <div className="scroll-thin max-h-96 overflow-auto rounded-lg border border-line">
          <table className="w-full text-xs">
            <caption className="sr-only">Pre-registered validation criteria and their verdicts</caption>
            <thead className="sticky top-0 bg-ink-800">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Criterion</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-txt-lo">Band</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Observed</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-txt-lo">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                // Disclosed dual verdict: a band can clear its threshold on the seed the
                // export packs and still miss it on the mean across seeds (SK-04 is the
                // pre-registered example — see README "The two honest fails"). Whenever
                // the pack carries both verdicts and they disagree, the seed-mean verdict
                // gets its own row directly under the packed-seed one rather than being
                // silently dropped.
                const seedMeanRow = r.verdict_on_seed_mean && r.verdict_on_seed_mean !== r.verdict
                return (
                  <Fragment key={r.id}>
                    <tr className="border-t border-ink-600/40">
                      <th scope="row" className="px-3 py-2 text-left font-mono font-normal text-txt-mid">{r.id}</th>
                      <td className="px-3 py-2 text-txt-lo">{r.band || r.criterion || r.description || '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-txt-hi">
                        {formatObserved(r.observed ?? r.value, r.verdict)}
                      </td>
                      <td className={`px-3 py-2 text-right text-[10px] font-bold uppercase ${VERDICT_TONE[r.verdict] || 'text-txt-lo'}`}>
                        {String(r.verdict || 'unknown').replace(/_/g, ' ')}
                        {seedMeanRow ? <span className="ml-1 normal-case text-txt-lo">(packed seed)</span> : null}
                      </td>
                    </tr>
                    {seedMeanRow && (
                      <tr className="border-t border-ink-600/20 bg-ink-900/40">
                        <th scope="row" className="px-3 py-1.5 pl-7 text-left font-mono text-[10px] font-normal text-txt-lo">↳ 5-seed mean</th>
                        <td className="px-3 py-1.5 text-[11px] text-txt-lo">
                          {r.agrees_across_seeds === false ? 'disagrees across seeds — disclosed, not smoothed over' : 'mean across the seeds actually run'}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-[11px] text-txt-hi">
                          {formatObserved(r.seed_mean, r.verdict_on_seed_mean)}
                        </td>
                        <td className={`px-3 py-1.5 text-right text-[10px] font-bold uppercase ${VERDICT_TONE[r.verdict_on_seed_mean] || 'text-txt-lo'}`}>
                          {String(r.verdict_on_seed_mean).replace(/_/g, ' ')}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-txt-lo">
        <Scale size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        A failing criterion stays in the table as a failure. The claim this product makes is the
        machinery and the measurement, not a number that has been tuned until it is flattering.
      </p>
      <p className="mt-1 flex items-start gap-1.5 text-[11px] leading-relaxed text-txt-lo">
        <Wallet size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        Every rupee figure in this product is behavioural — estimated from account activity, not from a
        payslip — and final eligibility remains with credit policy.
      </p>
    </Card>
  )
}
