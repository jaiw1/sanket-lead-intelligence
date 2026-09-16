import { useRef, useState } from 'react'
import { PhoneCall } from 'lucide-react'
import Modal, { PrimaryButton, SecondaryButton } from './Modal'
import ErrorState from './states/ErrorState'
import { DISPOSITIONS, dispositionLabel, productLabel } from '../lib/fmt'
import { postDisposition } from '../lib/sanket'

/**
 * Record what happened on the call.
 *
 * The outcome list is the contract's enum verbatim (`sanketDisposition`'s request body) —
 * eight values, no free text masquerading as one. `callback_requested` is the only outcome
 * that takes a time, so the field appears only for it; asking for a call-back time on
 * "wrong number" would be a form asking a question it cannot use.
 *
 * The write is append-only: it records what an RM observed. It never edits a score, and
 * the confirmation says so, because an RM who believes a disposition re-ranks the lead
 * will start dispositioning to game the queue.
 */
export default function DispositionDialog({ open, lead, onClose, onRecorded }) {
  const [outcome, setOutcome] = useState('')
  const [note, setNote] = useState('')
  const [callbackAt, setCallbackAt] = useState('')
  const [product, setProduct] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null)
  const firstRef = useRef(null)

  const needsCallback = DISPOSITIONS.find((d) => d.value === outcome)?.needsCallback
  const menu = lead?.productMenu || null

  const reset = () => {
    setOutcome(''); setNote(''); setCallbackAt(''); setProduct('')
    setBusy(false); setError(null); setDone(null)
  }

  const close = () => { reset(); onClose?.() }

  const submit = async () => {
    if (!outcome) return
    setBusy(true); setError(null)
    try {
      const body = { outcome }
      if (product) body.product = product
      if (note.trim()) body.note = note.trim()
      if (needsCallback && callbackAt) body.callback_at = new Date(callbackAt).toISOString()
      const result = await postDisposition(lead.id, body)
      setDone(result)
      onRecorded?.(result)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title={`Record a call outcome — ${lead?.id || ''}`}
      description="Append-only. This records what happened on the call; it does not change the lead's score or its position in tomorrow's ranking."
      initialFocusRef={firstRef}
      testId="disposition-dialog"
      footer={done ? (
        <PrimaryButton onClick={close}>Done</PrimaryButton>
      ) : (
        <>
          <SecondaryButton onClick={close} disabled={busy}>Cancel</SecondaryButton>
          <PrimaryButton onClick={submit} disabled={!outcome || busy}>
            <PhoneCall size={15} aria-hidden="true" />
            {busy ? 'Recording…' : 'Record outcome'}
          </PrimaryButton>
        </>
      )}
    >
      {/* The confirmation is announced, not just shown: an RM on a headset is not
          necessarily looking at the screen when the request comes back. */}
      <div aria-live="polite" className="sr-only">
        {busy ? 'Recording the call outcome.' : done ? `Recorded: ${dispositionLabel(done.outcome)}. The lead is now ${done.lead_status || 'updated'}.` : ''}
      </div>

      {done ? (
        <div
          className="rounded-lg border border-signal-teal/40 bg-signal-teal/10 p-4 text-sm text-txt-mid"
          data-testid="disposition-confirmed"
        >
          <p className="font-bold text-signal-teal">Recorded — {dispositionLabel(done.outcome)}</p>
          <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-txt-lo">Lead</dt><dd className="font-mono text-txt-hi">{done.lead_id}</dd>
            {done.lead_status && (<><dt className="text-txt-lo">Queue status</dt><dd className="text-txt-hi">{done.lead_status}</dd></>)}
            {done.product && (<><dt className="text-txt-lo">Product</dt><dd className="text-txt-hi">{productLabel(done.product)}</dd></>)}
            {done.callback_at && (<><dt className="text-txt-lo">Call back</dt><dd className="text-txt-hi">{new Date(done.callback_at).toLocaleString('en-IN')}</dd></>)}
            {done.at && (<><dt className="text-txt-lo">Recorded at</dt><dd className="text-txt-hi">{new Date(done.at).toLocaleString('en-IN')}</dd></>)}
          </dl>
          <p className="mt-2 text-[11px] text-txt-lo">Written to the append-only audit log against your user id.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {error && <ErrorState title="The outcome was not recorded" error={error} />}

          <fieldset>
            <legend className="mb-2 text-xs font-bold uppercase tracking-wider text-txt-lo">What happened?</legend>
            <div className="space-y-1.5">
              {DISPOSITIONS.map((d, i) => (
                <label
                  key={d.value}
                  className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm transition ${
                    outcome === d.value
                      ? 'border-signal-amber bg-signal-amber/10 text-txt-hi'
                      : 'border-line-strong text-txt-mid hover:bg-ink-700'
                  }`}
                >
                  <input
                    ref={i === 0 ? firstRef : undefined}
                    type="radio"
                    name="disposition-outcome"
                    value={d.value}
                    checked={outcome === d.value}
                    onChange={(e) => setOutcome(e.target.value)}
                    className="accent-signal-amber"
                  />
                  <span className={d.destructive ? 'text-signal-rose' : undefined}>{d.label}</span>
                  {d.destructive && <span className="ml-auto text-[10px] font-bold uppercase text-signal-rose">suppresses future calls</span>}
                </label>
              ))}
            </div>
          </fieldset>

          {menu && menu.length > 0 && (
            <div>
              <label htmlFor="disposition-product" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">
                Which product was discussed? <span className="font-normal normal-case text-txt-lo">(optional)</span>
              </label>
              <select
                id="disposition-product"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
              >
                <option value="">Not recorded</option>
                {menu.map((m) => <option key={m.product} value={m.product}>{m.label}</option>)}
              </select>
            </div>
          )}

          {needsCallback && (
            <div>
              <label htmlFor="disposition-callback" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">
                When should we call back?
              </label>
              <input
                id="disposition-callback"
                type="datetime-local"
                value={callbackAt}
                onChange={(e) => setCallbackAt(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
              />
            </div>
          )}

          <div>
            <label htmlFor="disposition-note" className="mb-1 block text-xs font-bold uppercase tracking-wider text-txt-lo">
              Note <span className="font-normal normal-case text-txt-lo">(optional, up to 2,000 characters)</span>
            </label>
            <textarea
              id="disposition-note"
              rows={3}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What the customer actually said."
              className="w-full rounded-lg border border-line-strong bg-ink-900 px-3 py-2 text-sm text-txt-hi placeholder:text-txt-lo focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-amber"
            />
            <p className="mt-1 text-[11px] text-txt-lo">{note.length} / 2000</p>
          </div>
        </div>
      )}
    </Modal>
  )
}
