import { useState } from 'react'
import { Landmark, TriangleAlert } from 'lucide-react'
import SourceBadge from './SourceBadge'
import NotInBuild from './NotInBuild'
import { inrExact, pct } from '../lib/fmt'

/**
 * What the loan would actually cost each month.
 *
 * Two very different things can be on this panel, and the badge is the whole point of it:
 *
 *   * A real schedule, when the lead resolves an `amortisation_ref` into a row set — rate,
 *     tenor and a per-instalment split whose provenance the payload states (API 433 rates
 *     and API 473 repayment schedules, or FIXTURE while the subscriptions are pending).
 *   * A typical EMI, when it does not. That is a table constant in the model package, not
 *     a bank rate, and a customer must never be quoted it. The badge says so in those
 *     words, beside the number, not in a footnote.
 */
export default function Amortisation({ amortisation, fallbackEmi, emiSource, product }) {
  const [openRows, setOpenRows] = useState(false)

  if (!amortisation) {
    if (fallbackEmi == null) {
      return (
        <NotInBuild
          what="The repayment schedule"
          keys={['amortisation', 'amortisation_ref', 'safe_emi']}
          hint="Resolved from API 473 repayment schedules and API 433 rates when those subscriptions are approved."
        />
      )
    }
    return (
      <div className="rounded-lg border border-signal-amber/40 bg-signal-amber/10 p-3.5" data-testid="typical-emi">
        <p className="flex items-center gap-2 text-sm font-bold text-signal-amber">
          <TriangleAlert size={15} aria-hidden="true" /> Typical EMI — not from bank rates
        </p>
        <p className="mt-1 text-2xl font-bold tabular-nums text-txt-hi">{inrExact(fallbackEmi)}<span className="text-sm font-normal text-txt-lo">/month</span></p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-txt-mid">
          This figure comes from <code className="font-mono">{emiSource || 'TYPICAL_EMI'}</code>, a table
          constant in the scoring package — not from API 433 (rates) or API 473 (repayment schedules).
          It is a planning number for the RM. <b className="text-txt-hi">Do not quote it to the customer</b> as a
          rate or an instalment.
        </p>
      </div>
    )
  }

  const rows = Array.isArray(amortisation.rows) ? amortisation.rows : []
  const prov = amortisation.provenance || {}
  const rateSource = prov.rate || 'NOT_COLLECTED'

  return (
    <div data-testid="amortisation">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SourceBadge source={rateSource} detail={`Rate from API 433, schedule from API 473 (${prov.schedule || 'unknown'}).`} />
        {rateSource !== 'BANK_API' && (
          <span className="text-[11px] text-txt-lo">
            Not a quotable rate until API 433 is live.
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="EMI" value={inrExact(amortisation.emi)} tone="text-signal-teal" />
        <Figure label="Principal" value={inrExact(amortisation.principal)} />
        <Figure label="Rate" value={amortisation.rate_pa == null ? '—' : `${pct(amortisation.rate_pa, 2)} p.a.`} />
        <Figure label="Tenor" value={amortisation.tenor_months == null ? '—' : `${amortisation.tenor_months} months`} />
      </div>
      {amortisation.total_interest != null && (
        <p className="mt-2 text-xs text-txt-mid">
          Total interest over the term: <b className="text-txt-hi">{inrExact(amortisation.total_interest)}</b>
          {product ? ` on the ${product} schedule.` : '.'}
        </p>
      )}

      {rows.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpenRows((v) => !v)}
            aria-expanded={openRows}
            className="mt-2 rounded text-xs font-semibold text-signal-amber underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            {openRows ? 'Hide' : 'Show'} the first {rows.length} instalments
          </button>
          {openRows && (
            <div className="scroll-thin mt-2 max-h-56 overflow-auto rounded-lg border border-line">
              <table className="w-full text-xs">
                <caption className="sr-only">Amortisation schedule: opening balance, instalment, interest, principal and closing balance</caption>
                <thead className="sticky top-0 bg-ink-800">
                  <tr>
                    <th scope="col" className="px-2 py-1.5 text-left font-semibold text-txt-lo">#</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-semibold text-txt-lo">Opening</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-semibold text-txt-lo">EMI</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-semibold text-txt-lo">Interest</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-semibold text-txt-lo">Principal</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-semibold text-txt-lo">Closing</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.n} className="border-t border-ink-600/40">
                      <th scope="row" className="px-2 py-1.5 text-left font-normal text-txt-lo">{r.n}</th>
                      <td className="px-2 py-1.5 text-right tabular-nums text-txt-mid">{inrExact(r.opening)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-txt-hi">{inrExact(r.emi)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-txt-mid">{inrExact(r.interest)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-txt-mid">{inrExact(r.principal)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-txt-mid">{inrExact(r.closing)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-txt-lo">
        <Landmark size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        Final eligibility, rate and instalment remain with credit policy. Nothing on this panel is a sanction.
      </p>
    </div>
  )
}

function Figure({ label, value, tone = 'text-txt-hi' }) {
  return (
    <div className="rounded-lg border border-line bg-ink-800 p-2.5 text-center">
      <div className={`text-base font-bold tabular-nums ${tone}`}>{value}</div>
      <div className="text-[10px] text-txt-lo">{label}</div>
    </div>
  )
}
