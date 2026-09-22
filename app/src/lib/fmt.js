// Shared vocabulary and formatters for the SANKET cockpit.
//
// The product list is the contract's: contracts/openapi.json spells the enum
// ["personal","gold","auto","education","home","lap"] on every SANKET operation that
// takes a product, and src/model/__init__.py packs the same six. Three products
// (home/auto/pl) was the pre-SM-1 shape and is gone; `pl` is spelled `personal`.

const blank = (n) => n === null || n === undefined || (typeof n === 'string' && n.trim() === '')

export const inr = (n) => {
  const v = Number(n)
  if (blank(n) || !Number.isFinite(v)) return '—'
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}

/** Exact rupees, for a figure that must reconcile (an EMI, an amortisation row). */
export const inrExact = (n) => {
  const v = Number(n)
  if (blank(n) || !Number.isFinite(v)) return '—'
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}

export const pct = (x, d = 0) => {
  const v = Number(x)
  return !blank(x) && Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : '—'
}

/**
 * A count, or an em dash. Never "0" for "we do not know".
 *
 * The empty string is excluded explicitly because `Number('')` is 0, which would turn a
 * blank field into a confident zero — the exact failure this whole file is built to avoid.
 */
export const num = (n) => {
  if (blank(n)) return '—'
  const v = Number(n)
  return Number.isFinite(v) ? v.toLocaleString('en-IN') : '—'
}

export const TIER = {
  hot: { label: 'Hot', text: 'text-signal-teal', chip: 'bg-signal-teal/15 text-signal-teal border-signal-teal/40', bar: 'bg-signal-teal' },
  warm: { label: 'Warm', text: 'text-signal-amber', chip: 'bg-signal-amber/15 text-signal-amber border-signal-amber/40', bar: 'bg-signal-amber' },
  cold: { label: 'Cold', text: 'text-txt-mid', chip: 'bg-ink-600 text-txt-mid border-line-strong', bar: 'bg-ink-500' },
}

/** The contract's product enum, in menu order. */
export const PRODUCTS = ['personal', 'gold', 'auto', 'education', 'home', 'lap']

export const PRODUCT = {
  personal: { label: 'Personal Loan', short: 'PL' },
  gold: { label: 'Gold Loan', short: 'GL' },
  auto: { label: 'Auto Loan', short: 'AL' },
  education: { label: 'Education Loan', short: 'EL' },
  home: { label: 'Home Loan', short: 'HL' },
  lap: { label: 'Loan Against Property', short: 'LAP' },
}

/** Never throws on a product the build has not seen; shows the raw code instead. */
export const productLabel = (p) => PRODUCT[p]?.label || (p ? String(p) : '—')
export const productShort = (p) => PRODUCT[p]?.short || (p ? String(p).slice(0, 3).toUpperCase() : '—')

/**
 * Contact windows in days, per product (plan SD-S4; the same table
 * validation/criteria.yaml registers and GET /sanket/funnel returns as
 * `sla.windows_days`). Used ONLY as a fallback label when a lead carries no window of
 * its own — a figure on screen always prefers the server's number.
 */
export const WINDOW_DAYS = { personal: 1, gold: 1, auto: 3, education: 7, home: 14, lap: 14 }

/** The contract's disposition enum, in the order an RM would reach for them. */
export const DISPOSITIONS = [
  { value: 'connected_interested', label: 'Connected — interested' },
  { value: 'callback_requested', label: 'Call-back requested', needsCallback: true },
  { value: 'application_started', label: 'Application started' },
  { value: 'disbursed', label: 'Disbursed' },
  { value: 'connected_not_interested', label: 'Connected — not interested' },
  { value: 'no_answer', label: 'No answer' },
  { value: 'wrong_number', label: 'Wrong number' },
  { value: 'do_not_call', label: 'Do not call again', destructive: true },
]

export const dispositionLabel = (v) => DISPOSITIONS.find((d) => d.value === v)?.label || v || '—'

/** Queue status enum from the contract. */
export const STATUSES = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'closed', label: 'Closed' },
]

/** The sort keys the backend allows. Sending anything else is a 400, so the UI offers only these. */
export const SORT_KEYS = [
  { value: 'score', label: 'Score' },
  { value: 'intent', label: 'Intent' },
  { value: 'capacity', label: 'Capacity' },
  { value: 'uplift_pct', label: 'Uplift' },
  { value: 'safe_emi', label: 'Safe EMI' },
]

/** The journey stages, in order. Anything the API adds is appended, never dropped. */
export const STAGES = ['start', 'eligibility', 'kyc', 'docs', 'fee', 'offer', 'accept', 'disburse']

export const STAGE_LABEL = {
  start: 'Started',
  eligibility: 'Eligibility',
  kyc: 'KYC',
  docs: 'Documents',
  fee: 'Fee (₹1,000)',
  offer: 'Offer',
  accept: 'Accepted',
  disburse: 'Disbursed',
}

/** The four window-shopper signals the mentors named, plus the ones the generator emits. */
export const NEGATIVE_SIGNAL = {
  vague_answer_count: 'Vague answers',
  vague_answers: 'Vague answers',
  blank_field_ratio: 'Left fields blank',
  refused_income: 'Would not share income',
  fee_balk: 'Balked at the ₹1,000 fee',
  doc_refusal: 'Refused to upload documents',
  multi_product_revisits: 'Shopped several products',
  contact_fatigue: 'Contacted repeatedly — campaign fatigue',
}

// Both vocabularies, kept apart on purpose: the static pack carries the model's own
// reason codes (`account_dormant`, `recent_contact`), the API carries the export
// contract's (`dormant`, `contact_fatigue`). `deceased` and `dormant` used to reach
// this screen as `kyc_expired`, which told an RM to go and re-KYC someone who had died.
export const SUPPRESSION_REASON = {
  none: 'Not suppressed',
  deceased: 'Bereavement on record',
  no_marketing_consent: 'No marketing consent (DPDP)',
  dnd: 'On the DND registry',
  dnd_registry: 'On the DND registry',
  account_dormant: 'Account dormant',
  dormant: 'Account dormant',
  kyc_expired: 'KYC has expired',
  application_in_flight: 'Application already in flight',
  existing_application_open: 'Application already in flight',
  recent_decline: 'Declined recently',
  recent_contact: 'Called in the last 7 days',
  contact_fatigue: 'Called too often recently',
  window_closed: 'Contact window has closed',
  window_expired: 'Contact window has closed',
  negative_uplift: 'Calling would do harm',
  already_holds_product: 'Already holds this product',
  not_in_population: 'Not in the drop-off population',
}

export const suppressionLabel = (r) => SUPPRESSION_REASON[r] || (r ? String(r).replace(/_/g, ' ') : 'Suppressed')

// --------------------------------------------------------------------------- //
// Call material — six products, English and Hindi.
// --------------------------------------------------------------------------- //
//
// These are the FRONT END'S FALLBACK, used only when a lead carries no `pitch` of its
// own. The live payload's pitch (built from that customer's evidence in
// src/model/copy.py) always wins, and a rendered pitch says which one it is.
//
// Rules the copy obeys, and a review should re-check:
//   * No promise of approval. Not "pre-approved", not "pre-qualified", not "sanctioned" —
//     the model ranks a conversation, it does not underwrite a loan.
//   * No number that is not the customer's own. `{emi}` is their observed headroom.
//   * Short enough to be read aloud in one breath, because an RM reads it aloud.
//   * The Hindi is plain, gender-neutral in the verb where Hindi allows it, and uses the
//     respectful "आप" throughout. Digits stay Latin so a screen reader speaks the amount.

export const PITCH_EN = {
  personal: {
    opener: 'I look after personal banking for your branch.',
    why_now: 'You started an application with us and did not finish it. If the need is still there, we can look at one EMI in place of the ones you pay elsewhere.',
    ask: 'May I check what you would be eligible for? Nothing is committed at this stage.',
  },
  gold: {
    opener: 'I am calling from your branch about the application you began.',
    why_now: 'If what you needed was quick funds, a loan against household gold is the fastest route we have, and the jewellery stays insured in the branch vault.',
    ask: 'Would it help if I explained how the valuation works?',
  },
  auto: {
    opener: 'I handle vehicle loans at your branch.',
    why_now: 'Your travel spend has been rising for a few months, which is usually when customers start weighing a vehicle of their own.',
    ask: 'Shall I walk you through what the monthly outgo would look like?',
  },
  education: {
    opener: 'I look after education loans at your branch.',
    why_now: 'Fee payments from your account have been building, and an education loan spreads them across the course instead of the term.',
    ask: 'Would a short eligibility conversation be useful before the next fee date?',
  },
  home: {
    opener: 'I am calling from your bank about the home loan enquiry you started.',
    why_now: 'Your rent has stepped up over the last year. For many customers at that point the monthly outgo on a home loan is comparable.',
    ask: 'Would you like me to work out what that comparison looks like for you?',
  },
  lap: {
    opener: 'I am from your bank’s secured lending desk.',
    why_now: 'You hold property and had begun an enquiry with us. Borrowing against it is usually the least expensive option available to you, and the property stays yours.',
    ask: 'Shall I arrange a call with the valuation team?',
  },
}

export const PITCH_HI = {
  personal: {
    opener: 'मैं आपकी शाखा की व्यक्तिगत बैंकिंग देखता हूँ।',
    why_now: 'आपने हमारे साथ एक आवेदन शुरू किया था और पूरा नहीं किया। यदि ज़रूरत अब भी है, तो बाहर चल रही कई EMI की जगह एक EMI पर बात हो सकती है।',
    ask: 'क्या मैं देख लूँ कि आप किसके लिए पात्र होंगे? इस समय कोई प्रतिबद्धता नहीं है।',
  },
  gold: {
    opener: 'मैं आपकी शाखा से, आपके शुरू किए आवेदन के बारे में बात कर रहा हूँ।',
    why_now: 'यदि ज़रूरत जल्दी पैसों की थी, तो घर के सोने पर ऋण सबसे तेज़ रास्ता है, और गहने शाखा की तिजोरी में बीमित रहते हैं।',
    ask: 'क्या मैं बता दूँ कि मूल्यांकन कैसे होता है?',
  },
  auto: {
    opener: 'मैं आपकी शाखा में वाहन ऋण देखता हूँ।',
    why_now: 'पिछले कुछ महीनों से आपका आने-जाने का खर्च बढ़ रहा है। आमतौर पर इसी समय ग्राहक अपनी गाड़ी पर विचार करते हैं।',
    ask: 'क्या मैं बता दूँ कि हर महीने का खर्च कितना बैठेगा?',
  },
  education: {
    opener: 'मैं आपकी शाखा में शिक्षा ऋण देखता हूँ।',
    why_now: 'आपके खाते से फ़ीस के भुगतान बढ़ रहे हैं। शिक्षा ऋण इन्हें एक सत्र के बजाय पूरे कोर्स में फैला देता है।',
    ask: 'अगली फ़ीस तिथि से पहले क्या पात्रता पर थोड़ी बात कर लें?',
  },
  home: {
    opener: 'मैं आपके बैंक से, आपकी शुरू की गई गृह ऋण पूछताछ के बारे में बात कर रहा हूँ।',
    why_now: 'पिछले साल में आपका किराया बढ़ा है। ऐसे कई ग्राहकों के लिए गृह ऋण का मासिक खर्च इसके बराबर ही बैठता है।',
    ask: 'क्या मैं यह तुलना आपके लिए निकाल दूँ?',
  },
  lap: {
    opener: 'मैं आपके बैंक के सुरक्षित-ऋण डेस्क से हूँ।',
    why_now: 'आपके नाम संपत्ति है और आपने हमसे पूछताछ शुरू की थी। संपत्ति पर ऋण आम तौर पर सबसे कम खर्चीला विकल्प होता है, और संपत्ति आपकी ही रहती है।',
    ask: 'क्या मैं मूल्यांकन टीम से बात तय कर दूँ?',
  },
}

/** Fallback call material for a product, in the lead's language. Never undefined. */
export function fallbackPitch(product, lang = 'en') {
  const table = lang === 'hi' ? PITCH_HI : PITCH_EN
  return table[product] || table.personal
}

export const LANG_LABEL = { en: 'EN', hi: 'हिन्दी' }
