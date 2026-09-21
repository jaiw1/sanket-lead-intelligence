// Business radar — the one screen in SANKET that is not the synthetic retail lead book.
// It reuses the existing <BusinessRadar/> chart as-is and just gives it a shell, a loading
// state, and an honest empty state: `radar_data.json` is an optional bundled module (SM-1
// packs it offline, via src/make_radar.py, from real published company financials), so a
// missing file is "this build does not carry it", never a failed request.

import AppShell from '../components/AppShell'
import Card from '../components/Card'
import Loading from '../components/states/Loading'
import Empty from '../components/states/Empty'
import BusinessRadar from '../components/BusinessRadar'
import useResource from '../data/useResource'
import { loadRadar } from '../lib/pack'

export default function Radar() {
  const { data, loading, error } = useResource(({ signal }) => loadRadar({ signal }), [])

  return (
    <AppShell title="Business radar" help="radar">
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-bold text-txt-hi">Business radar</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-txt-mid">
            An appendix exhibit, not part of the SANKET model. It screens business-banking prospects on real
            published annual financials for thousands of Indian companies using four hand-weighted ratios —
            income growth, interest cover, borrowing headroom and net worth. The retail lead queue elsewhere in
            SANKET is a different thing entirely: a trained model over a drop-off population, predicting
            disbursement after an RM call. Nothing on this screen validates that model.
          </p>
        </div>

        <Card
          title="Where this comes from"
          source="FIXTURE"
          sourceDetail="Real published annual financials for Indian businesses, processed offline by src/make_radar.py and bundled with the site — not pulled from a bank API."
          labelledBy="radar-source-title"
        >
          <p className="text-sm leading-relaxed text-txt-mid">
            The retail queue is synthetic; these are real filings. What the filings support is narrower than it
            looks, and the three limits below are structural, not disclaimers:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-txt-mid">
            <li>
              <b className="text-txt-hi">Different model.</b> Four chosen weights over four ratios. It shares no
              code, features, label or population with SANKET&rsquo;s LightGBM.
            </li>
            <li>
              <b className="text-txt-hi">The backtest is point-in-time, since 21 September 2026.</b> Each year is
              scored using only filings up to that year, and a company is excluded only if it had already defaulted
              by then. It used to drop every company that ever defaulted and rank every year against every other,
              both of which read the future. Correcting it moved the lift from 1.96× to 1.88×, and that 1.96× is
              still published beside it so the size of the bias is a measurement rather than a claim.
            </li>
            <li>
              <b className="text-txt-hi">&ldquo;Raised borrowings&rdquo; is not a disbursement by this bank.</b> It
              means total borrowings from any lender rose on the next filing. Nobody called these companies, so
              no RM call caused any of it.
            </li>
          </ul>
        </Card>

        {loading && <Loading label="Loading business radar…" />}
        {!loading && error && (
          <Empty
            title="Business radar data is not bundled in this build"
            hint="radar_data.json was not found alongside this deploy. This is optional module data, not a failed request — the rest of SANKET works normally without it."
          />
        )}
        {!loading && !error && data && <BusinessRadar radar={data} />}
      </div>
    </AppShell>
  )
}
