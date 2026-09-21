import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CalendarClock, Check, Copy, Lightbulb, MessageSquareQuote, PhoneCall, PhoneOff, Quote, Send,
  ShieldCheck, ShieldOff, Wallet, X,
} from 'lucide-react'
import Amortisation from './Amortisation'
import { NegativeChips, ReasonChips } from './Chips'
import CrmPushDialog from './CrmPushDialog'
import DispositionDialog from './DispositionDialog'
import NotInBuild from './NotInBuild'
import SourceBadge from './SourceBadge'
import WindowBadge from './WindowBadge'
import { PrimaryButton, SecondaryButton } from './Modal'
import ErrorState from './states/ErrorState'
import Loading from './states/Loading'
import { useAuth } from '../auth/AuthContext'
import { roleMatches } from '../auth/roles'
import useFocusTrap from '../lib/useFocusTrap'
import useResource from '../data/useResource'
import { usePack } from '../data/PackContext'
import { getLead } from '../lib/sanket'
import { normaliseLead } from '../lib/pack'
import {
  LANG_LABEL, STAGE_LABEL, TIER, dispositionLabel, fallbackPitch, inr, num, pct,
  productLabel, suppressionLabel,
} from '../lib/fmt'

/**
 * The call briefing: everything an RM needs in the sixty seconds before the phone rings,
 * and nothing they would have to take on trust.
 *
 * The order is deliberate. The menu of four comes first (which product, and how sure),
 * then the evidence FOR, then the evidence AGAINST — the window-shopper chips are not
 * buried below the fold, because a lead that will not close is worth knowing about while
 * the RM can still choose a different call. The script comes after the evidence, so it
 * reads as a consequence of it rather than a brochure.
 */
export default function LeadDrawer({ leadId, onClose, onChanged }) {
  const { isStatic, role } = useAuth()
  const pack = usePack()
  const panelRef = useRef(null)
  const closeRef = useRef(null)
  const [pushOpen, setPushOpen] = useState(false)
  const [dispOpen, setDispOpen] = useState(false)

  useFocusTrap(panelRef, { active: true, onClose, initialFocusRef: closeRef })

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [])

  const live = useResource(({ signal }) => getLead(leadId, { signal }), [leadId], { enabled: !isStatic })
  const packed = useMemo(
    () => (isStatic ? (pack.data?.leads || []).find((l) => String(l.id) === String(leadId)) : null),
    [isStatic, pack.data, leadId],
  )
  const raw = isStatic ? packed : live.data
  const lead = useMemo(() => (raw ? normaliseLead(raw) : null), [raw])
  const loading = isStatic ? pack.loading : live.loading
  const error = isStatic ? pack.error : live.error

  const canPush = !isStatic && roleMatches(role, ['M', 'A'])
  const tier = TIER[lead?.tier] || TIER.cold

  return (
    <div className="fixed inset-0 z-40" data-testid="lead-drawer">
      <div className="absolute inset-0 bg-ink-900/70" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lead-drawer-title"
        tabIndex={-1}
        className="scroll-thin absolute right-0 top-0 h-full w-full max-w-[720px] overflow-y-auto border-l border-line bg-ink-800 shadow-2xl"
      >
        <div className="sticky top-0 z-10 flex items-start gap-3 border-b border-line bg-ink-700 px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="lead-drawer-title" className="text-lg font-bold">{leadId}</h2>
              {lead && (
                <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${tier.chip}`}>
                  {tier.label.toUpperCase()} · {productLabel(lead.product)}
                </span>
              )}
              {lead && <WindowBadge lead={lead} />}
            </div>
            {lead && (
              <p className="mt-0.5 text-xs capitalize text-txt-lo">
                {lead.segment || 'segment unknown'}
                {lead.age ? ` · age ${lead.age}` : ''}
                {lead.cityTier ? ` · tier-${lead.cityTier} city` : ''}
                {lead.tenureM ? ` · ${Math.round(lead.tenureM / 12)}y with the bank` : ''}
                {lead.stageReached ? ` · abandoned at ${STAGE_LABEL[lead.stageReached] || lead.stageReached}` : ''}
                {lead.abandonTs ? ` on ${new Date(lead.abandonTs).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
              </p>
            )}
          </div>
          {lead?.score != null && (
            <div className="text-right">
              <div className={`text-2xl font-bold leading-none ${tier.text}`}>{Math.round(lead.score * 100)}</div>
              <div className="mt-1 text-[10px] uppercase tracking-wide text-txt-lo">score</div>
            </div>
          )}
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded p-1 text-txt-lo transition hover:text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            <X size={20} aria-hidden="true" />
            <span className="sr-only">Close the briefing</span>
          </button>
        </div>

        <div className="space-y-4 p-5">
          {loading && <Loading label="Loading the briefing…" />}
          {!loading && error && <ErrorState title="This lead could not be loaded" error={error} onRetry={isStatic ? pack.reload : live.reload} />}
          {!loading && !error && !lead && (
            <NotInBuild what={`Lead ${leadId}`} hint="It is not in the data this page load has. It may belong to another relationship manager, or to an earlier model run." />
          )}

          {lead && (
            <>
              {lead.suppressed && <SuppressedNotice lead={lead} />}

              <Actions
                lead={lead}
                canPush={canPush}
                isStatic={isStatic}
                onPush={() => setPushOpen(true)}
                onDisposition={() => setDispOpen(true)}
              />

              <Contactability lead={lead} />

              <Section title="The menu of four" subtitle="One model ranks all six products for this customer; these are the four worth a conversation.">
                <ProductMenu lead={lead} />
              </Section>

              <div className="grid gap-4 md:grid-cols-2">
                <Section title="Why SANKET ranked this lead">
                  <ReasonChips reasons={lead.reasons} />
                </Section>
                <Section
                  title="Why it might not close"
                  subtitle="Window-shopper signals — the half of the briefing that argues against the call."
                >
                  <NegativeChips chips={lead.negativeChips} />
                </Section>
              </div>

              <Section
                title="Capacity, and what the loan would cost"
                icon={Wallet}
                subtitle="Behavioural income, not declared income: observed credits minus the outflows the account actually shows."
              >
                <div className="mb-3 grid grid-cols-3 gap-3 text-center">
                  <Figure label="median monthly credits" value={inr(lead.salaryM)} />
                  <Figure label="retained after committed outflows" value={inr(lead.retainedIncome)} />
                  <Figure label="comfortable EMI headroom" value={inr(lead.safeEmi)} tone="text-signal-teal" />
                </div>
                <Amortisation
                  amortisation={lead.amortisation}
                  fallbackEmi={lead.safeEmi}
                  emiSource={lead.emiSource}
                  product={productLabel(lead.product)}
                />
              </Section>

              <Pitch lead={lead} />

              <div className="grid gap-4 sm:grid-cols-2">
                <Section title="Likely objection" icon={Quote}>
                  <Objection lead={lead} />
                </Section>
                <Section title="Next best action" icon={CalendarClock}>
                  {lead.nba
                    ? <p className="text-sm leading-relaxed text-txt-mid">{lead.nba}</p>
                    : <NotInBuild what="The next-best action" keys="nba" compact />}
                </Section>
              </div>

              <Journey lead={lead} />
              <History lead={lead} />
              <Provenance lead={lead} />
            </>
          )}
        </div>
      </div>

      {lead && (
        <>
          <CrmPushDialog open={pushOpen} lead={lead} onClose={() => { setPushOpen(false); onChanged?.() }} />
          <DispositionDialog
            open={dispOpen}
            lead={lead}
            onClose={() => setDispOpen(false)}
            onRecorded={() => { onChanged?.(); if (!isStatic) live.reload() }}
          />
        </>
      )}
    </div>
  )
}

function Section({ title, subtitle, icon: Icon, children }) {
  return (
    <section className="rounded-xl border border-line bg-ink-700 p-4">
      <h3 className="flex items-center gap-2 text-sm font-bold text-txt-hi">
        {Icon && <Icon size={15} className="text-signal-amber" aria-hidden="true" />}
        {title}
      </h3>
      {subtitle && <p className="mb-2.5 mt-0.5 text-xs leading-relaxed text-txt-lo">{subtitle}</p>}
      <div className={subtitle ? '' : 'mt-2.5'}>{children}</div>
    </section>
  )
}

function Figure({ label, value, tone = 'text-txt-hi' }) {
  return (
    <div className="rounded-lg border border-line bg-ink-800 p-3">
      <div className={`text-base font-bold tabular-nums ${tone}`}>{value}</div>
      <div className="text-[10px] leading-tight text-txt-lo">{label}</div>
    </div>
  )
}

function SuppressedNotice({ lead }) {
  return (
    <div role="note" className="rounded-xl border border-signal-rose/40 bg-signal-rose/10 p-4">
      <p className="flex items-center gap-2 text-sm font-bold text-signal-rose">
        <ShieldOff size={16} aria-hidden="true" /> This lead is suppressed — do not call
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-txt-mid">
        It was scored and then held back:{' '}
        <b className="text-txt-hi">{lead.suppressionReasons.map(suppressionLabel).join('; ') || 'reason not recorded'}</b>.
        It is shown rather than silently dropped so the exclusion is visible — but the briefing below
        is for review, not for a call.
      </p>
    </div>
  )
}

/**
 * May we call this person at all, and on what basis?
 *
 * The platform computes this for every lead — `contactability` carries the consent state it
 * read, whether the customer is eligible and queueable, and the blockers standing in the
 * way — and nothing in the app read it, so the "do not call" judgement the product claims
 * to support was never on the RM's screen. Suppression already had a notice; consent and
 * the non-suppression blockers (an expired window, for instance) did not.
 */
function Contactability({ lead }) {
  const c = lead.contactability
  if (!c || typeof c !== 'object') return null
  const consent = c.consent && typeof c.consent === 'object' ? c.consent : null
  const blockers = Array.isArray(c.blockers) ? c.blockers : []
  const ok = c.contactable === true && blockers.length === 0
  const Icon = c.contactable === false ? PhoneOff : ok ? ShieldCheck : PhoneCall
  const tone = c.contactable === false
    ? 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose'
    : ok
      ? 'border-signal-teal/40 bg-signal-teal/10 text-signal-teal'
      : 'border-signal-amber/40 bg-signal-amber/10 text-signal-amber'

  return (
    <section className={`rounded-xl border p-4 ${tone}`} data-testid="contactability">
      <h3 className="flex items-center gap-2 text-sm font-bold">
        <Icon size={15} aria-hidden="true" />
        {c.contactable === false ? 'Not contactable' : ok ? 'Contactable' : 'Contactable, with conditions'}
      </h3>
      <ul className="mt-2 space-y-1 text-xs leading-relaxed text-txt-mid">
        {consent && (
          <li>
            <span className="text-txt-lo">Marketing consent</span>{' '}
            <b className="text-txt-hi">
              {consent.granted === true ? 'granted' : consent.granted === false ? 'not granted' : consent.state || 'unknown'}
            </b>
            {consent.state && consent.state !== (consent.granted === true ? 'granted' : consent.granted === false ? 'not granted' : consent.state)
              ? ` (${consent.state})` : ''}
            {consent.source ? ` · recorded by ${consent.source}` : ''}
            {consent.expires_at ? ` · expires ${new Date(consent.expires_at).toLocaleDateString('en-IN')}` : ''}
          </li>
        )}
        <li>
          <span className="text-txt-lo">Eligible to be offered</span>{' '}
          <b className="text-txt-hi">{c.eligible === false ? 'no' : c.eligible === true ? 'yes' : 'not stated'}</b>
          <span className="text-txt-lo"> · queued for calling</span>{' '}
          <b className="text-txt-hi">{c.queueable === false ? 'no' : c.queueable === true ? 'yes' : 'not stated'}</b>
        </li>
        {blockers.length > 0 && (
          <li>
            <span className="text-txt-lo">In the way</span>{' '}
            <b className="text-txt-hi">{blockers.map(suppressionLabel).join('; ')}</b>
          </li>
        )}
      </ul>
      <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
        This is the platform&rsquo;s own verdict on whether the call may be made, shown beside the
        briefing rather than behind it. A blocker is a reason to stop, not a score.
      </p>
    </section>
  )
}

function Actions({ lead, canPush, isStatic, onPush, onDisposition }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <PrimaryButton onClick={onDisposition} disabled={isStatic} data-testid="open-disposition">
        <PhoneCall size={15} aria-hidden="true" /> Record a call outcome
      </PrimaryButton>
      {canPush && (
        <SecondaryButton onClick={onPush} disabled={lead.suppressed} data-testid="open-crm-push">
          <Send size={15} aria-hidden="true" /> Push to CRM
        </SecondaryButton>
      )}
      {!canPush && !isStatic && (
        <p className="text-[11px] text-txt-lo">
          Pushing to the bank CRM is a manager action (<code className="font-mono">x-roles: M, A</code>).
        </p>
      )}
      {isStatic && (
        <p className="text-[11px] text-txt-lo">
          Actions need the backend. This page load is the frozen static demo.
        </p>
      )}
    </div>
  )
}

/** Four products, each with its probability, its reason and its own window. */
function ProductMenu({ lead }) {
  if (!lead.productMenu || lead.productMenu.length === 0) {
    return (
      <NotInBuild
        what="The menu of four"
        keys={['product_menu']}
        hint="The single model scores all six products for a customer-month and the top four become the menu. A build without it is the pre-SM-1 one-product-per-lead shape."
      />
    )
  }
  const top = lead.productMenu[0]?.prob ?? null
  return (
    <ol className="space-y-2">
      {lead.productMenu.map((item, i) => (
        <li
          key={item.product}
          className={`rounded-lg border p-3 ${i === 0 ? 'border-signal-teal/40 bg-signal-teal/5' : 'border-line bg-ink-800'}`}
          data-testid="menu-item"
          data-product={item.product}
        >
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-ink-600 text-[11px] font-bold text-txt-mid">{i + 1}</span>
            <span className="font-bold text-txt-hi">{item.label}</span>
            {item.prob != null && (
              <span className={`text-sm font-bold tabular-nums ${i === 0 ? 'text-signal-teal' : 'text-txt-mid'}`}>
                {pct(item.prob, 1)}
                <span className="sr-only"> probability of disbursement inside the window</span>
              </span>
            )}
            {item.windowDays != null && (
              <span className="ml-auto rounded-full border border-line-strong px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-txt-mid">
                {item.windowDays}-day window
              </span>
            )}
          </div>
          {item.reason && <p className="mt-1 text-xs leading-relaxed text-txt-mid">{item.reason}</p>}
          <p className="mt-1 text-[11px] text-txt-lo">
            {item.emi != null && <>EMI headroom {inr(item.emi)}</>}
            {item.contactBy && <> · contact by {new Date(item.contactBy).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</>}
            {top != null && i > 0 && item.prob != null && <> · {(item.prob / top * 100).toFixed(0)}% as likely as the top product</>}
          </p>
        </li>
      ))}
    </ol>
  )
}

/**
 * The script, in both languages.
 *
 * The payload carries a pitch for the lead's OWN product, built from that customer's
 * evidence. For any other product on the menu there is no such pitch, so the drawer falls
 * back to the neutral script in lib/fmt.js and labels it as generic. The two are never
 * blended: a sentence is either grounded in this customer's account or it is a template,
 * and the RM is told which.
 */
function Pitch({ lead }) {
  const [product, setProduct] = useState(lead.product)
  const [lang, setLang] = useState(lead.lang === 'hi' ? 'hi' : 'en')
  const [copied, setCopied] = useState(false)

  const grounded = product === lead.product
  const supplied = grounded ? (lead.pitch[lang] || (lead.pitch.single && lead.lang === lang ? lead.pitch.single : null)) : null
  const text = supplied || fallbackPitch(product, lang)
  const lines = [text.opener, text.why_now, text.ask].filter(Boolean)

  const copy = () => {
    navigator.clipboard?.writeText(lines.join(' '))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const menu = lead.productMenu || [{ product: lead.product, label: productLabel(lead.product) }]

  return (
    <section className="rounded-xl border border-line bg-ink-700 p-4">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-txt-hi">
          <MessageSquareQuote size={15} className="text-signal-amber" aria-hidden="true" /> Suggested opening
        </h3>
        <div className="ml-auto flex items-center gap-2">
          <label className="sr-only" htmlFor="pitch-product">Product for the script</label>
          <select
            id="pitch-product"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            className="rounded-lg border border-line-strong bg-ink-800 px-2 py-1 text-xs text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            {menu.map((m) => <option key={m.product} value={m.product}>{m.label || productLabel(m.product)}</option>)}
          </select>
          <div role="group" aria-label="Script language" className="flex overflow-hidden rounded-lg border border-line-strong">
            {['en', 'hi'].map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLang(code)}
                aria-pressed={lang === code}
                className={`px-2.5 py-1 text-xs font-bold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber ${
                  lang === code ? 'bg-signal-amber text-ink-900' : 'bg-ink-800 text-txt-mid hover:text-txt-hi'
                }`}
              >
                {LANG_LABEL[code]}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 rounded text-xs text-txt-lo transition hover:text-signal-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
          >
            {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>

      <div
        lang={lang}
        className="rounded-lg border border-line bg-ink-800 p-3.5 text-sm leading-relaxed text-txt-mid"
        data-testid="pitch-body"
      >
        {lines.map((line, i) => <p key={i} className={i ? 'mt-2' : ''}>“{line}”</p>)}
      </div>

      {supplied?.proof?.length > 0 && (
        <ul className="mt-2.5 flex flex-wrap gap-1.5">
          {supplied.proof.map((p, i) => (
            <li key={i} className="rounded-full border border-line bg-ink-600 px-2 py-0.5 text-[10px] text-txt-mid">◈ {p}</li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
        {grounded && supplied ? (
          <>Built from this customer's own evidence — every claim traces to a chip above. No generated facts.</>
        ) : (
          <>
            <b className="text-signal-amber">Generic script.</b> The payload carries a pitch only for the
            ranked product ({productLabel(lead.product)}); this one is the neutral template
            from <code className="font-mono">lib/fmt.js</code> and cites nothing about this customer.
          </>
        )}
        {' '}Nothing here promises approval — eligibility stays with credit policy.
      </p>
      {!lead.pitch.bilingual && grounded && (
        <p className="mt-1 text-[11px] text-txt-lo">
          This build shipped the script in {LANG_LABEL[lead.lang]} only; the other language is the neutral template.
        </p>
      )}
    </section>
  )
}

function Objection({ lead }) {
  const lang = lead.lang === 'hi' ? 'hi' : 'en'
  const o = lead.objection[lang] || lead.objection.single || lead.objection.en || lead.objection.hi
  if (!o?.q) return <NotInBuild what="The likely objection" keys="objection" compact />
  return (
    <div lang={lang}>
      <p className="text-sm italic text-txt-mid">“{o.q}”</p>
      {o.a && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-txt-mid">
          <Lightbulb size={14} className="mt-0.5 shrink-0 text-signal-amber" aria-hidden="true" />
          {o.a}
        </p>
      )}
    </div>
  )
}

/** The application they abandoned, stage by stage. */
function Journey({ lead }) {
  const j = lead.journey
  if (!j) {
    return (
      <Section title="The application they abandoned">
        <NotInBuild
          what="The journey"
          keys="journey"
          hint={lead.stageReached ? `The queue row says they reached ${STAGE_LABEL[lead.stageReached] || lead.stageReached}; the stage-by-stage detail comes with the lead endpoint.` : undefined}
        />
      </Section>
    )
  }
  const stages = Array.isArray(j.stages) ? j.stages : []
  const signals = j.shopper_signals || {}
  return (
    <Section
      title="The application they abandoned"
      subtitle={`${productLabel(j.product)} via ${j.channel || 'an unrecorded channel'} — stopped at ${STAGE_LABEL[j.stage_reached] || j.stage_reached}${j.abandon_reason ? ` (${j.abandon_reason.replace(/_/g, ' ')})` : ''}.`}
    >
      {stages.length > 0 && (
        <ol className="space-y-1.5">
          {stages.map((s) => (
            <li key={s.stage} className="flex items-center gap-2 text-xs">
              <span className={`h-2 w-2 shrink-0 rounded-full ${s.outcome === 'abandoned' ? 'bg-signal-rose' : 'bg-signal-teal'}`} aria-hidden="true" />
              <span className="w-28 shrink-0 font-semibold text-txt-mid">{STAGE_LABEL[s.stage] || s.stage}</span>
              <span className="text-txt-lo">{s.outcome}</span>
              {s.dwell_seconds != null && <span className="text-txt-lo">· {Math.round(s.dwell_seconds / 60)} min</span>}
              {s.blank_fields > 0 && <span className="text-signal-amber">· {s.blank_fields} fields left blank</span>}
            </li>
          ))}
        </ol>
      )}
      {Object.keys(signals).length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-3">
          {Object.entries(signals).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2">
              <dt className="text-txt-lo">{key.replace(/_/g, ' ')}</dt>
              <dd className="font-semibold text-txt-mid">
                {typeof value === 'boolean' ? (value ? 'yes' : 'no') : typeof value === 'number' ? (value < 1 && value > 0 ? pct(value, 0) : num(value)) : String(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Section>
  )
}

/** What has already been done to this customer, by us. */
function History({ lead }) {
  const disp = lead.dispositions
  const consents = lead.consents
  if (disp === null && consents === null) return null
  return (
    <Section title="What we have already done" subtitle="Calls recorded against this lead, and any Account Aggregator consent on file.">
      {disp && disp.length > 0 ? (
        <ul className="space-y-1.5">
          {disp.map((d, i) => (
            <li key={d.id ?? i} className="flex flex-wrap items-baseline gap-x-2 text-xs">
              <span className="font-semibold text-txt-mid">{dispositionLabel(d.outcome)}</span>
              {d.at && <span className="text-txt-lo">{new Date(d.at).toLocaleString('en-IN')}</span>}
              {d.note && <span className="w-full text-txt-lo">“{d.note}”</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-txt-lo">No call has been recorded against this lead yet.</p>
      )}
      {consents && consents.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {consents.map((c, i) => (
            <li key={c.consent_handle ?? i} className="flex items-center gap-2">
              <span className="font-mono text-txt-lo">{c.consent_handle}</span>
              <span className="font-semibold text-txt-mid">{c.status}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

/** Where every field on this briefing came from. */
function Provenance({ lead }) {
  const p = lead.provenance
  if (!p || typeof p !== 'object') return null
  return (
    <Section title="Where this briefing's data comes from">
      <ul className="flex flex-wrap gap-2">
        {Object.entries(p).map(([family, source]) => (
          <li key={family} className="flex items-center gap-1.5">
            <span className="text-[11px] text-txt-lo">{family.replace(/_/g, ' ')}</span>
            <SourceBadge source={String(source)} />
          </li>
        ))}
      </ul>
    </Section>
  )
}
