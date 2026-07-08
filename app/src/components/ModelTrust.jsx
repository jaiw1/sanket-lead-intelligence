import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, LabelList, Cell, Legend,
} from 'recharts'
import { pct, PRODUCT } from '../lib/fmt'
import { ScanEye, Ban } from 'lucide-react'

function Stat({ value, label, hint, tone = 'text-signal-teal' }) {
  return (
    <div className="bg-ink-700 border border-line rounded-xl p-4">
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-sm font-semibold text-txt-hi mt-0.5">{label}</div>
      <div className="text-xs text-txt-lo mt-0.5">{hint}</div>
    </div>
  )
}

export default function ModelTrust({ data }) {
  const m = data.metrics
  const per = m.per_product
  const cal = (m.calibration || []).map((r) => ({ pred: +(r.pred * 100).toFixed(1), obs: +(r.obs * 100).toFixed(1) }))
  const calMax = Math.max(1, Math.ceil(Math.max(...cal.flatMap((c) => [c.pred, c.obs]))))
  const aucBars = Object.entries(per).map(([k, v]) => ({ name: PRODUCT[k].label, auc: v.auc }))
  const lift = m.blended.prec_curve.filter((p) => [0.01, 0.02, 0.05, 0.1, 0.2, 0.3].includes(p.budget))
    .map((p) => ({ name: `top ${Math.round(p.budget * 100)}%`, lift: +p.lift.toFixed(1) }))

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold flex items-center gap-2"><ScanEye size={18} className="text-signal-amber" /> Model & Trust</h2>
        <p className="text-xs text-txt-lo">The scorecard a bank's model-risk team would ask for — shown before they ask.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat value={m.blended.auc_macro.toFixed(2)} label="Ranking quality (AUC)" hint="macro across the three product models" />
        <Stat value={`${m.blended.prec_curve.find((p) => p.budget === 0.02)?.lift.toFixed(0)}×`} label="Lift @ top 2%" hint="vs random cold-calling" tone="text-signal-amber" />
        <Stat value={pct(m.blended.baseline, 1)} label="Cold-call baseline" hint="random-contact conversion in the book" tone="text-signal-rose" />
        <Stat value="grouped + temporal" label="Leakage-safe testing" hint="no customer in both train & test; scored on future months" tone="text-txt-hi" />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <h3 className="font-bold text-sm">Calibration — does the score mean what it says?</h3>
          <p className="text-xs text-txt-lo mt-1 mb-4">Predicted conversion likelihood vs what actually happened, by score decile. Points on the dashed line = trustworthy probabilities.</p>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={cal} margin={{ top: 6, right: 14, left: -12, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" />
              <XAxis dataKey="pred" type="number" domain={[0, calMax]} tick={{ fontSize: 10, fill: '#6B7399' }} unit="%"
                     label={{ value: 'Predicted', fontSize: 10, fill: '#6B7399', position: 'insideBottom', dy: 12 }} />
              <YAxis domain={[0, calMax]} tick={{ fontSize: 10, fill: '#6B7399' }} unit="%"
                     label={{ value: 'Actual', fontSize: 10, fill: '#6B7399', angle: -90, position: 'insideLeft', dy: 20 }} />
              <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                       formatter={(v, n) => [`${v}%`, n === 'obs' ? 'Actual' : 'Predicted']} labelFormatter={(l) => `predicted ${l}%`} />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: calMax, y: calMax }]} stroke="#6B7399" strokeDasharray="5 4"
                             label={{ value: 'perfect', fontSize: 9, fill: '#6B7399', position: 'insideTopLeft' }} />
              <Line type="linear" dataKey="obs" name="Actual" stroke="#2DD4BF" strokeWidth={2} dot={{ r: 3.5, fill: '#2DD4BF', stroke: '#0B1026' }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <h3 className="font-bold text-sm">Lift over cold-calling, by calling depth</h3>
          <p className="text-xs text-txt-lo mt-1 mb-4">It honestly decays as you call deeper — that's what a real ranking looks like.</p>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={lift} margin={{ top: 18, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6B7399' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6B7399' }} />
              <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }}
                       formatter={(v) => [`${v}×`, 'lift']} />
              <Bar dataKey="lift" radius={[5, 5, 0, 0]} isAnimationActive={false}>
                <LabelList dataKey="lift" position="top" formatter={(v) => `${v}×`} style={{ fontSize: 11, fill: '#EAEDFB', fontWeight: 700 }} />
                {lift.map((d, i) => <Cell key={i} fill={i < 2 ? '#2DD4BF' : i < 4 ? '#F5A623' : '#6B7399'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <h3 className="font-bold text-sm mb-3">Per-product ranking quality</h3>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={aucBars} layout="vertical" margin={{ top: 0, right: 34, left: 20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232B4D" horizontal={false} />
              <XAxis type="number" domain={[0.5, 1]} tick={{ fontSize: 10, fill: '#6B7399' }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#A7AFD4' }} width={92} />
              <Tooltip contentStyle={{ background: '#151C3B', border: '1px solid #26304F', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="auc" fill="#F5A623" radius={[0, 5, 5, 0]} isAnimationActive={false}>
                <LabelList dataKey="auc" position="right" formatter={(v) => v.toFixed(2)} style={{ fontSize: 11, fill: '#EAEDFB', fontWeight: 700 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-[11px] text-txt-lo">AUC 0.5 = coin-flip, 1.0 = perfect. Scores from 0.80 to the mid-0.9s reflect how clearly each product telegraphs itself in account behaviour — personal-loan stress is the loudest signal.</p>
        </section>

        <section className="bg-ink-700 border border-line rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3"><Ban size={15} className="text-signal-rose" /><h3 className="font-bold text-sm">Features we refused to use</h3></div>
          <div className="space-y-2.5">
            {m.excluded_features.map((f, i) => (
              <div key={i} className="flex items-start gap-2.5 text-sm">
                <span className="w-5 h-5 grid place-items-center rounded bg-signal-rose/15 text-signal-rose shrink-0 mt-0.5"><Ban size={11} /></span>
                <span className="text-txt-mid">{f}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-txt-lo mt-3">
            Anti-leakage and fairness by construction: nothing that encodes the outcome, no protected attributes,
            nothing a customer hasn't consented to share.
          </p>
        </section>
      </div>

      <section className="bg-ink-600/40 border border-line rounded-xl p-5">
        <h3 className="font-bold text-signal-amber text-sm">Why we don't promise “30% conversion, guaranteed”</h3>
        <p className="text-sm text-txt-mid mt-2 leading-relaxed">
          The demo book is synthetic, engineered to the bank-stated ~1% cold-call baseline. What we claim is the <b>machinery</b>:
          a ranking measured at <b>{pct(m.blended.prec_curve.find((p) => p.budget === 0.02)?.precision ?? 0, 1)} precision at a top-2% calling budget</b> on
          held-out customers — a {m.blended.prec_curve.find((p) => p.budget === 0.02)?.lift.toFixed(0)}× lift. On real IDBI data in the sandbox,
          the numbers recalibrate; the queue, reasons, consent screening and measurement stay exactly as you see them.
        </p>
      </section>
    </div>
  )
}
