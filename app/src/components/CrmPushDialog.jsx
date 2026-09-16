import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleSlash, Send, ShieldQuestion } from 'lucide-react'
import Modal, { PrimaryButton, SecondaryButton } from './Modal'
import ErrorState from './states/ErrorState'
import Loading from './states/Loading'
import { crmPushConfirm, crmPushDryRun } from '../lib/sanket'
import { productLabel } from '../lib/fmt'

/**
 * Push a lead into the bank's CRM (API 428 createLead) — the only WRITE this platform
 * makes into a bank system, and therefore the most deliberate thing in the product.
 *
 * The contract makes it take two flags: `dry_run: false` AND `confirm: true`, so a client
 * that forgets a default cannot write by omission. This dialog mirrors that exactly:
 *
 *   step 1  dry run    -> the 456 dedupe verdict and the exact 428 payload that WOULD go
 *   step 2  confirm    -> an explicit second act, on a screen showing what step 1 returned
 *   step 3  result     -> whatever came back, including NOT_SENT, said plainly
 *
 * `NOT_SENT` at HTTP 200 is not an error and is not hidden. It is what the backend answers
 * when there is no Atlas client or writes are disabled: nothing reached the bank, the
 * attempt is recorded, and blaming the bank with a 502 would be a lie about whose decision
 * it was. The result panel says exactly that.
 */

const VERDICT = {
  clear: {
    tone: 'border-signal-teal/40 bg-signal-teal/10 text-signal-teal',
    icon: CheckCircle2,
    label: 'Clear — no duplicate found',
    hint: 'API 456 found no existing master record that matches this customer.',
  },
  duplicate: {
    tone: 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose',
    icon: AlertTriangle,
    label: 'Duplicate — the bank already holds this customer',
    hint: 'Pushing would create a second lead against the same person. The push is refused.',
  },
  unknown: {
    tone: 'border-signal-amber/40 bg-signal-amber/10 text-signal-amber',
    icon: ShieldQuestion,
    label: 'Unknown — no dedupe check was made',
    hint: 'Nothing was asked of API 456, so nothing is claimed about duplicates. This is not a pass.',
  },
}

const STATUS = {
  OK: { tone: 'border-signal-teal/40 bg-signal-teal/10 text-signal-teal', icon: CheckCircle2, label: 'Sent to the bank CRM' },
  NOT_SENT: { tone: 'border-signal-amber/40 bg-signal-amber/10 text-signal-amber', icon: CircleSlash, label: 'NOT SENT — nothing reached the bank' },
  NOT_COLLECTED: { tone: 'border-line-strong bg-ink-700 text-txt-mid', icon: CircleSlash, label: 'NOT COLLECTED — the call was never made' },
  ERROR: { tone: 'border-signal-rose/40 bg-signal-rose/10 text-signal-rose', icon: AlertTriangle, label: 'ERROR — the bank refused it' },
}

function Payload({ payload }) {
  if (!payload) return null
  return (
    <details className="rounded-lg border border-line bg-ink-900">
      <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-txt-mid focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber">
        The exact API 428 payload ({Object.keys(payload.lead || payload).length} fields)
      </summary>
      <pre className="scroll-thin max-h-56 overflow-auto px-3 pb-3 font-mono text-[11px] leading-relaxed text-txt-mid">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  )
}

function Dedupe({ dedupe }) {
  if (!dedupe) return null
  const spec = VERDICT[dedupe.verdict] || VERDICT.unknown
  const Icon = spec.icon
  return (
    <div className={`rounded-lg border p-3 ${spec.tone}`} data-testid="crm-dedupe" data-verdict={dedupe.verdict}>
      <p className="flex items-center gap-2 text-sm font-bold">
        <Icon size={15} aria-hidden="true" /> {spec.label}
      </p>
      {dedupe.detail && <p className="mt-1 text-xs leading-relaxed text-txt-mid">{dedupe.detail}</p>}
      {/* Our own framing always shows, so a reassuring server sentence cannot stand in for
          it. "unknown" in particular must never read like a pass. */}
      <p className="mt-1 text-xs leading-relaxed text-txt-mid">{spec.hint}</p>
      <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-[11px] text-txt-lo">
        <dt>Checked with</dt><dd className="text-txt-mid">API {dedupe.api_id || '456'}</dd>
        {dedupe.customer_count != null && (<><dt>Matching records</dt><dd className="text-txt-mid">{dedupe.customer_count}</dd></>)}
        {dedupe.dedupe_match_score != null && (<><dt>Match score</dt><dd className="text-txt-mid">{dedupe.dedupe_match_score}</dd></>)}
        {dedupe.already_pushed_as && (<><dt>Already pushed as</dt><dd className="font-mono text-txt-mid">{dedupe.already_pushed_as}</dd></>)}
      </dl>
    </div>
  )
}

export default function CrmPushDialog({ open, lead, onClose }) {
  const [step, setStep] = useState('dry')
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [product, setProduct] = useState('')
  const [note, setNote] = useState('')
  const confirmRef = useRef(null)

  useEffect(() => {
    if (!open || !lead) return undefined
    let live = true
    setStep('dry'); setPreview(null); setResult(null); setError(null); setBusy(true)
    setProduct(lead.product || '')
    crmPushDryRun(lead.id)
      .then((data) => { if (live) { setPreview(data); setBusy(false) } })
      .catch((e) => { if (live) { setError(e); setBusy(false) } })
    return () => { live = false }
  }, [open, lead])

  const rerunDryRun = async () => {
    setBusy(true); setError(null)
    try {
      setPreview(await crmPushDryRun(lead.id, { product: product || undefined, note: note.trim() || undefined }))
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const confirm = async () => {
    setBusy(true); setError(null)
    try {
      const data = await crmPushConfirm(lead.id, { product: product || undefined, note: note.trim() || undefined })
      setResult(data)
      setStep('result')
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const duplicate = preview?.dedupe?.verdict === 'duplicate'
  const statusSpec = result ? (STATUS[result.status] || STATUS.NOT_SENT) : null
  const StatusIcon = statusSpec?.icon

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Push ${lead?.id || 'this lead'} to the bank CRM`}
      description="API 428 createLead. This is the only write this platform makes into a bank system, so it takes two deliberate steps and every attempt is audited."
      size="lg"
      testId="crm-push-dialog"
      initialFocusRef={step === 'confirm' ? confirmRef : undefined}
      footer={
        step === 'result' ? (
          <PrimaryButton onClick={onClose}>Close</PrimaryButton>
        ) : step === 'confirm' ? (
          <>
            <SecondaryButton onClick={() => setStep('dry')} disabled={busy}>Back to the preview</SecondaryButton>
            <PrimaryButton ref={confirmRef} onClick={confirm} disabled={busy || duplicate} data-testid="crm-confirm">
              <Send size={15} aria-hidden="true" />
              {busy ? 'Sending…' : 'Yes — send it to the bank'}
            </PrimaryButton>
          </>
        ) : (
          <>
            <SecondaryButton onClick={onClose} disabled={busy}>Cancel</SecondaryButton>
            <SecondaryButton onClick={rerunDryRun} disabled={busy}>Re-run the dry run</SecondaryButton>
            <PrimaryButton onClick={() => setStep('confirm')} disabled={busy || !preview || duplicate} data-testid="crm-continue">
              Continue
            </PrimaryButton>
          </>
        )
      }
    >
      <div aria-live="polite" className="sr-only">
        {busy ? 'Working.' : result ? `Result: ${result.status}. ${result.sent ? 'The lead reached the bank.' : 'Nothing reached the bank.'}` : preview ? `Dry run complete. Dedupe verdict ${preview.dedupe?.verdict}.` : ''}
      </div>

      {error && <ErrorState title="The CRM push failed" error={error} onRetry={step === 'dry' ? rerunDryRun : undefined} />}

      {step === 'dry' && (
        <div className="space-y-4">
          <p className="rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-xs leading-relaxed text-txt-mid">
            <b className="text-txt-hi">Step 1 of 2 — dry run.</b> Nothing has been sent. `dry_run` defaults to
            true in the contract, so this is what happens when a client forgets to say otherwise.
          </p>
          {busy && !preview && <Loading label="Running the dedupe check…" />}
          {preview && (
            <>
              <Dedupe dedupe={preview.dedupe} />
              <Payload payload={preview.would_send} />
              {preview.gateway && (
                <p className="text-[11px] leading-relaxed text-txt-lo">
                  Gateway: mode <code className="font-mono text-txt-mid">{preview.gateway.mode}</code>,
                  client {preview.gateway.client_available ? 'available' : 'unavailable'},
                  writes {preview.gateway.writes_allowed ? 'allowed' : 'disabled'}.
                  {preview.gateway.reason ? ` ${preview.gateway.reason}` : ''}
                </p>
              )}
              {preview.note && <p className="text-[11px] leading-relaxed text-txt-lo">{preview.note}</p>}
              {duplicate && (
                <p className="rounded-lg border border-signal-rose/40 bg-signal-rose/10 px-3 py-2 text-xs font-semibold text-signal-rose">
                  The push is blocked: the bank already holds a matching record. A dedupe refusal is
                  audited out of band and writes no `crm_push` row — that table records attempts
                  against the bank, and this one never became an attempt.
                </p>
              )}
            </>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="crm-product" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Product on the lead</label>
              <select
                id="crm-product"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
              >
                <option value="">Use the ranked product</option>
                {(lead?.productMenu || []).map((m) => (
                  <option key={m.product} value={m.product}>{productLabel(m.product)}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="crm-note" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">Remark for the CRM</label>
              <input
                id="crm-note"
                type="text"
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi placeholder:text-txt-lo focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
                placeholder="Optional"
              />
            </div>
          </div>
        </div>
      )}

      {step === 'confirm' && (
        <div className="space-y-4">
          <div className="rounded-lg border border-signal-amber/40 bg-signal-amber/10 p-4">
            <p className="flex items-center gap-2 text-sm font-bold text-signal-amber">
              <AlertTriangle size={16} aria-hidden="true" /> Step 2 of 2 — this writes into a bank system
            </p>
            <p className="mt-1.5 text-xs leading-relaxed text-txt-mid">
              Confirming sends <code className="font-mono">dry_run: false</code> together
              with <code className="font-mono">confirm: true</code>. The returned lead id is written
              to <code className="font-mono">crm_push</code> and to the audit log against your user id.
              There is no undo from this screen.
            </p>
          </div>
          <Dedupe dedupe={preview?.dedupe} />
          <Payload payload={preview?.would_send} />
        </div>
      )}

      {step === 'result' && result && (
        <div className="space-y-4" data-testid="crm-result" data-status={result.status}>
          <div className={`rounded-lg border p-4 ${statusSpec.tone}`}>
            <p className="flex items-center gap-2 text-sm font-bold">
              <StatusIcon size={16} aria-hidden="true" /> {statusSpec.label}
            </p>
            {result.reason && <p className="mt-1.5 text-xs leading-relaxed text-txt-mid">{result.reason}</p>}
            {result.status === 'NOT_SENT' && (
              <p className="mt-2 text-[11px] leading-relaxed text-txt-lo">
                This came back as HTTP 200, not an error, and that is deliberate: nothing reached the
                bank because <i>we</i> have writes switched off, not because the bank refused. A 502
                here would blame the bank for our own decision. The attempt is still recorded.
              </p>
            )}
            <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-[11px] text-txt-lo">
              <dt>Reached the bank</dt><dd className="text-txt-mid">{result.sent ? 'yes' : 'no'}</dd>
              {result.crm_lead_id && (<><dt>CRM lead id</dt><dd className="font-mono text-txt-hi">{result.crm_lead_id}</dd></>)}
              {result.crm_push_id != null && (<><dt>crm_push row</dt><dd className="font-mono text-txt-mid">#{result.crm_push_id}</dd></>)}
            </dl>
          </div>
          <Dedupe dedupe={result.dedupe} />
          <Payload payload={result.sent_payload} />
        </div>
      )}
    </Modal>
  )
}
