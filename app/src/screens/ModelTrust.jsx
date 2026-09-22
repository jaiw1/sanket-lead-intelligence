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
import { getFunnel, getValidation } from '../lib/sanket'
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
 * The pre-registered validation table's rows still come from the BUNDLED EXPORT — the
 * SK-* verdicts `src/model/pack.py` writes, including the seed-mean disclosure — because
 * no route serves that pack's per-band detail. `GET /sanket/validation` (x-roles M, A,
 * same as `getFunnel`) does exist, and in live mode the table asks it for one thing only:
 * which of those failing criteria were named in advance and accepted on this model run,
 * and why. That acceptance overlay never changes a verdict — it can only mark an existing
 * failure as one somebody signed for. Mixing two sources on one screen is only acceptable
 * because each panel names the one it used, and the overlay fetch failing, or returning
 * nothing, leaves the table exactly as it renders without it.
 */
export default function ModelTrust() {
  const { isStatic, role } = useAuth()
  const pack = usePack()
  const live = useResource(({ signal }) => getFunnel({ signal }), [], { enabled: !isStatic })
  // Acceptance-only: no criteria/verdicts come from here, just which failing SK-* ids on
  // this run were accepted in advance, and their reasons. `useResource` degrades to
  // `data: null` on any error, which is exactly "no accepted failures" downstream.
  const validation = useResource(({ signal }) => getValidation({ signal }), [], { enabled: !isStatic })

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
            One model across all six products. Everything below is measured on held-out customers, on the
            list the calling policy would actually deliver — the same ranking, suppression and truncation
            the queue uses — with 95% confidence intervals around the packed seed's own numbers. The
            &ldquo;5-seed mean&rdquo; rows in the criteria table are a different thing: a spread across five
            training seeds, which measures training variability, not sampling error, and is never shown as
            a confidence interval.
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
                label="Conversion timing (SK-04)"
                value={metrics.windowRespect?.value == null ? '—' : pct(metrics.windowRespect.value, 1)}
                hint={`of the leads that disbursed, the share that disbursed inside the offered product's window${ciText(metrics.windowRespect) ? ` · ${ciText(metrics.windowRespect)}` : ''}`}
              />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <PerProductAuc metrics={metrics} source={badge} detail={detail} />
              <Calibration metrics={metrics} source={badge} detail={detail} />
            </div>

            <Uncertainty metrics={metrics} fallback={packMetrics} source={badge} detail={detail} />

            <div className="grid gap-5 lg:grid-cols-2">
              <MenuBaselines metrics={metrics} fallback={packMetrics} source={badge} detail={detail} />
              <ShopperPanel metrics={metrics} source={badge} detail={detail} />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <SuppressionExhibit metrics={metrics} source={badge} detail={detail} />
              <Fairness metrics={metrics} source={badge} detail={detail} />
            </div>

            <IncomeAccuracy metrics={metrics} source={badge} detail={detail} />

            <Excluded metrics={metrics} source={badge} detail={detail} />
            <ValidationTable
              metrics={packMetrics}
              live={!isStatic}
              packError={pack.error}
              packLoading={pack.loading}
              acceptance={isStatic ? null : validation.data}
            />
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
      // A fixed 2dp *string*, not a rounded number: `+(0.85).toFixed(3)` is `0.85`, so a
      // numeric column drifts between 2dp and 3dp row to row, and sat beside a CI that is
      // always 2dp. Both columns now read at the same precision, the one the published
      // Hanley–McNeil intervals are quoted at.
      .map((r) => ({ ...r, aucLabel: r.auc == null ? null : r.auc.toFixed(2) }))
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
              { key: 'aucLabel', label: 'AUC', format: (v) => (v == null ? 'not measured' : v) },
              { key: 'ci', label: '95% CI (Hanley–McNeil)', format: (v) => (v?.lo == null ? 'not measured' : `${v.lo.toFixed(2)}–${v.hi.toFixed(2)}`) },
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

/**
 * Three kinds of uncertainty, side by side and never added together.
 *
 * The review that prompted this panel found five-seed percentile spreads rendered as
 * "95% CI" beside seed-7 point estimates — which put several estimates outside their own
 * displayed interval, because a spread across five training splits is not a confidence
 * interval around any of them. The fix is not a better label on one number: it is showing
 * that there are three different questions and answering each separately.
 */
function Uncertainty({ metrics, fallback, source, detail }) {
  // `GET /sanket/funnel`'s `published_metrics` does not carry `uncertainty` — only the
  // bundled export does. Falling back to the pack keeps the panel on screen (it is the one
  // that enforces "spread, not a CI") and the footnote below says which source it used,
  // exactly as the validation table does.
  const fromPack = !metrics.uncertainty && Boolean(fallback?.uncertainty)
  const u = metrics.uncertainty || fallback?.uncertainty || null
  const budget = u?.sample?.['10'] ? '10' : null
  const sample = budget ? u.sample[budget] : null
  const seed = u?.training_seed?.precision_at_budget || null
  const gen = u?.generator || null
  const genSpread = gen?.spread?.precision_at_budget || null

  const rows = [
    {
      key: 'sample',
      name: 'Sampling — which customers landed in the book',
      method: u?.sample?.method,
      detail: sample ? `${num(u.sample.n_customers)} customers resampled with replacement, ${num(u.sample.n_resamples)} times; the queue is re-selected inside every resample` : null,
      lo: sample?.ci_low, hi: sample?.ci_high,
      isCi: true,
    },
    {
      key: 'seed',
      name: 'Training seed — which split the model drew',
      method: u?.training_seed?.method,
      detail: seed ? `${num(u.training_seed.n)} registered seeds; 2.5–97.5 percentile of their values` : null,
      lo: seed?.pct_low, hi: seed?.pct_high,
      isCi: false,
    },
    {
      key: 'generator',
      name: 'Generator — which synthetic world the book came from',
      method: gen?.method || gen?.estimand,
      detail: gen?.status === 'measured'
        ? `${num(gen.generator_seeds?.length)} worlds regenerated end to end, all scored at model seed ${gen.model_seed}`
        : (gen?.note || 'not measured in this run'),
      lo: genSpread?.min, hi: genSpread?.max,
      isCi: false,
    },
  ]

  return (
    <Card
      title="Uncertainty, three ways"
      subtitle="Precision at the 10% contact budget. Three different questions — they are not interchangeable and they do not combine into one interval."
      source={source}
      sourceDetail={detail}
      labelledBy="uncertainty-title"
    >
      {!u ? (
        <NotInBuild what="The uncertainty breakdown" keys={['metrics.uncertainty']} />
      ) : (
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full text-xs">
            <caption className="sr-only">Sampling, training-seed and generator uncertainty for precision at the 10% contact budget</caption>
            <thead>
              <tr className="text-left text-txt-lo">
                <th scope="col" className="py-1.5 pr-3 font-semibold">What varies</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">Interval</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">Kind</th>
                <th scope="col" className="py-1.5 font-semibold">How</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-t border-line align-top">
                  <th scope="row" className="py-2 pr-3 text-left font-medium text-txt-hi">{r.name}</th>
                  <td className="py-2 pr-3 font-mono tabular-nums text-txt-hi">
                    {r.lo == null || r.hi == null ? <span className="text-txt-lo">not measured</span> : `${pct(r.lo, 1)} – ${pct(r.hi, 1)}`}
                  </td>
                  <td className="py-2 pr-3 text-txt-mid">
                    {r.isCi
                      ? <span className="text-signal-teal">95% confidence interval</span>
                      : <span className="text-signal-amber">spread, not a CI</span>}
                  </td>
                  <td className="py-2 leading-relaxed text-txt-lo">{r.detail || r.method || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {u.sample?.headline?.interval_sentence && (
            <p className="mt-3 rounded-lg border border-line-strong bg-ink-800 px-3 py-2 text-[11px] leading-relaxed text-txt-mid">
              <b className="text-txt-hi">The headline with its own interval:</b>{' '}
              {u.sample.headline.interval_sentence}. Only the sampling row is a confidence
              interval; the other two say how much the answer would move if the experiment
              were re-run differently, which is a different thing and is why they are not
              added to it.
            </p>
          )}
          {fromPack && (
            <p className="mt-2 text-[11px] leading-relaxed text-signal-amber">
              These three intervals come from the bundled export
              (<code className="font-mono">app/public/sanket_data.json</code>), not from the published
              model run above: <code className="font-mono">GET /sanket/funnel</code> does not serve
              <code className="font-mono"> metrics.uncertainty</code>. If the run and the export are not the
              same build, read the intervals as the export&rsquo;s, not this run&rsquo;s.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}

/**
 * The menu of four against the two rules that need no model.
 *
 * Quoting a 96.5% menu-of-4 hit rate without these is a claim about the population: most
 * converters take the product they abandoned, so "offer them what they walked away from"
 * is already close to the ceiling. The column that matters is the switchers.
 */
function MenuBaselines({ metrics, fallback, source, detail }) {
  // Same contract gap as Uncertainty: `menu_baselines` lives only in the bundled export.
  const fromPack = !metrics.menuBaselines && Boolean(fallback?.menuBaselines)
  const b = metrics.menuBaselines || fallback?.menuBaselines || null
  const rows = b ? [
    { key: 'model', name: `SANKET — menu of ${b.k}`, v: b.model, strong: true },
    { key: 'abandoned', name: 'Abandoned product, then popularity', v: b.abandoned_product },
    { key: 'popular', name: `The ${b.k} most-taken products`, v: b.most_popular },
  ] : null

  return (
    <Card
      title="The menu against rules that need no model"
      subtitle="Hit rate on every converter, and on the converters who switched product — the only group where a menu can add anything."
      source={source}
      sourceDetail={detail}
      labelledBy="menu-baselines-title"
    >
      {!rows ? (
        <NotInBuild what="The menu baselines" keys={['metrics.menu_baselines']} />
      ) : (
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full text-xs">
            <caption className="sr-only">Menu hit rate for the model and for two baselines, on all converters and on switchers</caption>
            <thead>
              <tr className="text-left text-txt-lo">
                <th scope="col" className="py-1.5 pr-3 font-semibold">Rule</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-semibold">Hit rate</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-semibold">Top-1</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-semibold">Hit, switchers</th>
                <th scope="col" className="py-1.5 text-right font-semibold">Top-1, switchers</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-t border-line">
                  <th scope="row" className={`py-2 pr-3 text-left ${r.strong ? 'font-bold text-txt-hi' : 'font-medium text-txt-mid'}`}>{r.name}</th>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.v?.menu_hit_rate, 1)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.v?.top_1_accuracy, 1)}</td>
                  <td className={`py-2 pr-3 text-right tabular-nums ${r.strong ? 'font-bold text-signal-teal' : ''}`}>{pct(r.v?.menu_hit_rate_switchers, 1)}</td>
                  <td className="py-2 text-right tabular-nums">{pct(r.v?.top_1_accuracy_switchers, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {fromPack && (
            <p className="mt-3 text-[11px] leading-relaxed text-signal-amber">
              This table comes from the bundled export, not from the published run above:{' '}
              <code className="font-mono">GET /sanket/funnel</code> does not serve{' '}
              <code className="font-mono">metrics.menu_baselines</code>.
            </p>
          )}
          <p className="mt-3 text-[11px] leading-relaxed text-txt-lo">
            {num(b.model?.n_converters)} converters, of whom {num(b.model?.n_switchers)} took a
            different product from the one they abandoned. The most-popular baseline is built
            from training positives only, not from the held-out labels.
          </p>
        </div>
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
          {/* Name the population this count came out of. A bare "customers scored and then
              not queued" leaves the reader to guess whether the denominator is the whole
              scored pool or the handful of leads this build delivered. */}
          <p className="mb-3 text-xs text-txt-lo">
            {s?.pool_at_snapshot != null
              ? `of the ${num(s.pool_at_snapshot)} customers scored at this snapshot — held back, never queued`
              : 'customers scored and then not queued'}
          </p>
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
 *
 * `acceptance` is the *only* thing that ever comes from `GET /sanket/validation`, and only
 * in live mode — `acceptance.accepted_failure_ids` names which of these already-failing
 * criteria an operator recorded acceptance for in advance, and
 * `acceptance.accepted_failures.criteria[]` carries each one's pre-registered `reason`. It
 * never supplies a verdict: an accepted id still renders as a failure, just one somebody
 * signed for, never as a pass and never as a bare "accepted". A missing, errored or
 * `available: false` `acceptance` degrades to "no accepted failures" and changes nothing
 * else about the table.
 */
function ValidationTable({ metrics, live, packError, packLoading, acceptance }) {
  const bands = metrics?.bands
  const rows = useMemo(() => (bands ? Object.entries(bands).map(([id, v]) => ({ id, ...v })).sort((a, b) => a.id.localeCompare(b.id)) : null), [bands])

  const acceptedIds = useMemo(() => {
    const ids = acceptance?.available === false ? null : acceptance?.accepted_failure_ids
    return Array.isArray(ids) && ids.length ? new Set(ids) : null
  }, [acceptance])
  const acceptedReasons = useMemo(() => {
    const map = new Map()
    const criteria = acceptance?.accepted_failures?.criteria
    if (Array.isArray(criteria)) {
      for (const c of criteria) {
        if (c?.id && c.reason) map.set(c.id, c.reason)
      }
    }
    return map
  }, [acceptance])

  const tally = useMemo(() => {
    if (!rows) return null
    const acc = rows.reduce((acc, r) => {
      // An accepted failure is tallied on its own, never folded into `pass` (nor into
      // `fail`/`report`/anything else) — it is a distinct, disclosed thing, not a count
      // that happens to land in the same bucket a raw verdict would.
      if (acceptedIds?.has(r.id)) acc.accepted = (acc.accepted || 0) + 1
      else acc[r.verdict] = (acc[r.verdict] || 0) + 1
      return acc
    }, {})
    // A band can pass on the packed seed and fail on the 5-seed mean (SK-04 is the
    // pre-registered example) — `agrees_across_seeds: false` is the disclosure signal.
    // That is a second, separately-counted honest fail, not folded into `acc.fail`,
    // which only ever reflects the packed-seed verdict rendered in the main column.
    acc.seedMeanFail = rows.filter((r) => r.verdict_on_seed_mean && r.verdict_on_seed_mean !== r.verdict && r.verdict_on_seed_mean === 'fail').length
    return acc
  }, [rows, acceptedIds])

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
          {tally.accepted ? <> · <b className="text-signal-rose">{tally.accepted} accepted failure{tally.accepted === 1 ? '' : 's'}</b></> : null}
          {tally.seedMeanFail ? <> · <b className="text-signal-rose">{tally.seedMeanFail} fail{tally.seedMeanFail === 1 ? '' : 's'} on 5-seed mean</b></> : null}
          {tally.report ? <> · <b className="text-signal-amber">{tally.report} report-only</b></> : null}
          {tally.not_measured ? <> · {tally.not_measured} not measured</> : null}
          {/* `not_run` is a verdict the export really emits (SK-19 and SK-22 are reported
              with no band), and the reduce above has always counted it. Without a branch
              here the chip silently dropped two criteria and the numbers it did show did
              not add up to the table underneath it. */}
          {tally.not_run ? <> · {tally.not_run} not run</> : null}
        </span>
      )}
    >
      {live && (
        <p className="mb-3 rounded-lg border border-line-strong bg-ink-800 px-3 py-2 text-[11px] leading-relaxed text-txt-mid">
          <b className="text-txt-hi">This panel reads two sources.</b>{' '}
          The criteria and their verdicts are the bundled export's — <code className="font-mono">app/public/sanket_data.json</code>,
          the same pack the "5-seed mean" row below reads — because no route serves that per-band detail from
          the published model run. <code className="font-mono">GET /sanket/validation</code> now exists, and this
          table asks it for exactly one thing: which of these failures were accepted in advance on the run, and
          why. Everything above this panel comes from the run.
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
        <div className="scroll-thin max-h-96 overflow-auto rounded-lg border border-line" tabIndex={0} role="region" aria-label="Pre-registered validation criteria, scrollable">
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
                // Accepted failure: an operator named this id in advance and the acceptance
                // was recorded on the run. It still failed — the verdict cell must say so,
                // never "pass" and never a bare "accepted" — so this overrides only the
                // rendered label and tone, never `r.verdict` itself.
                const accepted = acceptedIds?.has(r.id)
                const acceptedReason = accepted ? acceptedReasons.get(r.id) : null
                return (
                  <Fragment key={r.id}>
                    <tr className="border-t border-ink-600/40">
                      <th scope="row" className="px-3 py-2 text-left font-mono font-normal text-txt-mid">{r.id}</th>
                      <td className="px-3 py-2 text-txt-lo">{r.band || r.criterion || r.description || '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-txt-hi">
                        {formatObserved(r.observed ?? r.value, r.verdict)}
                      </td>
                      <td className={`px-3 py-2 text-right text-[10px] font-bold uppercase ${accepted ? 'text-signal-rose' : (VERDICT_TONE[r.verdict] || 'text-txt-lo')}`}>
                        {accepted ? 'FAIL — ACCEPTED' : String(r.verdict || 'unknown').replace(/_/g, ' ')}
                        {seedMeanRow ? <span className="ml-1 normal-case text-txt-lo">(packed seed)</span> : null}
                      </td>
                    </tr>
                    {accepted && acceptedReason && (
                      <tr className="border-t border-ink-600/20 bg-ink-900/40">
                        <th scope="row" className="px-3 py-1.5 pl-7 text-left font-mono text-[10px] font-normal text-txt-lo">↳ accepted failure</th>
                        <td colSpan={3} className="px-3 py-1.5 text-[11px] text-txt-lo">{acceptedReason}</td>
                      </tr>
                    )}
                    {seedMeanRow && (
                      <tr className="border-t border-ink-600/20 bg-ink-900/40">
                        <th scope="row" className="px-3 py-1.5 pl-7 text-left font-mono text-[10px] font-normal text-txt-lo">↳ 5-seed mean</th>
                        <td className="px-3 py-1.5 text-[11px] text-txt-lo">
                          {r.agrees_across_seeds === false ? 'disagrees across seeds — disclosed, not smoothed over' : 'mean across the seeds actually run'} (training-seed spread, not a confidence interval)
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
