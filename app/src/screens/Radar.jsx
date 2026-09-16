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
            The retail lead queue elsewhere in SANKET runs on a synthetic demo book, by design, until sandbox
            access. This radar is different: it screens business-banking prospects on real published annual
            financials for thousands of Indian companies — the same signal-scoring approach, proven on reality.
          </p>
        </div>

        <Card
          title="Where this comes from"
          source="FIXTURE"
          sourceDetail="Real published annual financials for Indian businesses, processed offline by src/make_radar.py and bundled with the site — not pulled from a bank API."
          labelledBy="radar-source-title"
        >
          <p className="text-sm leading-relaxed text-txt-mid">
            The retail queue is synthetic; this radar is real filings — that is the point of this screen.
          </p>
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
