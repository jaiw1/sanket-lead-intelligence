// One view model for a lead, whichever side of the wire it came from — and one place that
// decides a field is ABSENT rather than inventing a value for it.
//
// Two sources, deliberately not merged upstream:
//
//   LIVE   `GET /sanket/queue` and `/sanket/lead/{id}` — the contract's shapes, listed in
//          `x-response-shapes`. Decimal columns arrive as STRINGS ("219800.00"), the menu
//          calls its probability `prob`, and the window is already resolved server-side.
//   STATIC `app/public/sanket_data.json` — what `src/score_and_pack.py` packs. SM-1 is
//          rewriting it as this lane is built, so every key it adds (`product_menu`,
//          `negative_chips`, `suppressed`, `suppression_reason`, `contact_by`,
//          `window_days`, `provenance`, six products, the headline parts) is read
//          DEFENSIVELY: present -> render it, absent -> the panel hides itself behind a
//          "not in this build" note. Never a placeholder that reads like a real number.
//
// The rule the whole file exists for: `undefined` and `null` mean "this build does not
// carry it". They are never coerced to 0, to "—" inside a computation, or to `false`.

import { publicPath } from './basepath'
import { WINDOW_DAYS, productLabel } from './fmt'
import { WINDOW_STATE, windowStatus } from './window'

/** Decimal columns cross the wire as strings. Returns null for anything non-numeric. */
export function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/** First key that is actually present. `null` when none is — never a default. */
export function pick(source, ...keys) {
  if (!source) return null
  for (const key of keys) {
    const value = source[key]
    if (value !== undefined && value !== null) return value
  }
  return null
}

/** An array, or null when the key is absent. An EMPTY array is a real answer and is kept. */
export function pickArray(source, ...keys) {
  const value = pick(source, ...keys)
  return Array.isArray(value) ? value : null
}

// --------------------------------------------------------------------------- //
// leads
// --------------------------------------------------------------------------- //

function normaliseMenu(raw) {
  if (!Array.isArray(raw) || raw.length === 0) return null
  return raw.map((entry) => ({
    product: entry.product,
    label: entry.label || productLabel(entry.product),
    // live: `prob`; packed: `p`
    prob: toNumber(pick(entry, 'prob', 'p', 'probability')),
    reason: entry.reason || null,
    windowDays: toNumber(pick(entry, 'window_days')) ?? WINDOW_DAYS[entry.product] ?? null,
    contactBy: pick(entry, 'contact_by', 'due_by'),
    // live: `safe_emi`; packed: `emi`
    emi: toNumber(pick(entry, 'safe_emi', 'emi')),
    emiSource: pick(entry, 'emi_source') || (entry.amortisation_ref ? 'amortisation' : null),
    amortisationRef: pick(entry, 'amortisation_ref'),
  }))
}

/**
 * Negative window-shopper chips, from either spelling.
 *   live   `negative_signals: [{signal, label, severity}]`
 *   packed `negative_chips:   [{signal, text, impact, mentor_signal}]`
 * Returns null when NEITHER key is present (the field is not in this build); returns []
 * when the key is present and empty (this lead genuinely has no negative signal).
 */
function normaliseChips(raw) {
  const value = pick(raw, 'negative_signals', 'negative_chips')
  if (!Array.isArray(value)) return null
  return value.map((entry) => {
    if (typeof entry === 'string') return { signal: null, label: entry, severity: null, impact: null, mentorSignal: false }
    return {
      signal: entry.signal ?? null,
      label: entry.label || entry.text || entry.signal || 'Signal',
      severity: entry.severity ?? null,
      impact: toNumber(entry.impact),
      mentorSignal: Boolean(entry.mentor_signal),
    }
  })
}

/**
 * Suppression, from either spelling.
 *   live   `suppressed: bool` + `suppression_reasons: string[]`
 *   packed `suppressed: bool` + `suppression_reason: string` (singular, "none" when not)
 */
function normaliseSuppression(raw) {
  const flagged = pick(raw, 'suppressed')
  const many = pickArray(raw, 'suppression_reasons')
  const one = pick(raw, 'suppression_reason')
  const reasons = many ?? (one && one !== 'none' ? [one] : one ? [] : null)
  if (flagged === null && reasons === null) return { known: false, suppressed: false, reasons: [] }
  const suppressed = flagged !== null ? Boolean(flagged) : Boolean(reasons && reasons.length)
  return { known: true, suppressed, reasons: reasons || [] }
}

/**
 * Bilingual call material.
 *   live   `pitch: {en: {...}, hi: {...}}`, `objection: {en: {q,a}, hi: {q,a}}`
 *   packed `pitch: {opener, why_now, proof}` in the lead's own language only
 * Returns `{en, hi, single, bilingual}`; `single` is set when only one language shipped.
 */
function normaliseBilingual(raw, lang) {
  if (!raw || typeof raw !== 'object') return { en: null, hi: null, single: null, bilingual: false }
  if (raw.en || raw.hi) return { en: raw.en || null, hi: raw.hi || null, single: null, bilingual: Boolean(raw.en && raw.hi) }
  return { en: lang === 'hi' ? null : raw, hi: lang === 'hi' ? raw : null, single: raw, bilingual: false }
}

/** Turn a queue row, a lead detail or a packed lead into the one shape every screen reads. */
export function normaliseLead(raw) {
  if (!raw) return null
  const lang = raw.lang === 'hi' ? 'hi' : 'en'
  const suppression = normaliseSuppression(raw)

  return {
    raw,
    id: String(pick(raw, 'lead_id', 'id') ?? ''),
    cifId: pick(raw, 'cif_id'),
    segment: pick(raw, 'segment'),
    age: toNumber(pick(raw, 'age')),
    cityTier: toNumber(pick(raw, 'city_tier')),
    tenureM: toNumber(pick(raw, 'tenure_m')),

    product: pick(raw, 'product'),
    productMenu: normaliseMenu(pick(raw, 'product_menu')),
    tier: pick(raw, 'tier'),
    lang,

    score: toNumber(pick(raw, 'score')),
    intent: toNumber(pick(raw, 'intent')),
    capacity: toNumber(pick(raw, 'capacity')),
    probability: toNumber(pick(raw, 'probability')),
    upliftTag: pick(raw, 'uplift_tag'),
    upliftPct: toNumber(pick(raw, 'uplift_pct')),
    shopperScore: toNumber(pick(raw, 'shopper_score')),
    windowShopper: pick(raw, 'window_shopper'),

    salaryM: toNumber(pick(raw, 'salary_m')),
    retainedIncome: toNumber(pick(raw, 'retained_income')),
    safeEmi: toNumber(pick(raw, 'safe_emi')),

    reasons: pickArray(raw, 'reasons') || [],
    negativeChips: normaliseChips(raw),
    nba: pick(raw, 'nba'),

    suppressionKnown: suppression.known,
    suppressed: suppression.suppressed,
    suppressionReasons: suppression.reasons,

    consent: pick(raw, 'consent'),
    consentMarketing: pick(raw, 'consent_marketing'),
    // The platform's own call-eligibility verdict: whether this customer may be contacted,
    // on what consent, and what is blocking the call. It reached the client on every queue
    // row and lead and was read by nothing.
    contactability: pick(raw, 'contactability'),
    contactable: pick(raw, 'contactable'),
    assignedRmId: pick(raw, 'assigned_rm_id', 'rm_id'),
    status: pick(raw, 'status'),

    stageReached: pick(raw, 'stage_reached', 'dropoff_stage'),
    journeyRef: pick(raw, 'journey_ref'),
    abandonTs: pick(raw, 'abandon_ts'),
    daysSinceAbandon: toNumber(pick(raw, 'days_since_abandon')),
    contactBy: pick(raw, 'contact_by'),
    windowDays: toNumber(pick(raw, 'window_days')),
    window: pick(raw, 'window'),
    // The instant this lead's window state was decided at. Live it rides inside `window`;
    // a packed lead has no `window` object at all, so the pack's own anchor is attached
    // here by `withAsOf` below. Flattened either way, so one field answers for both lanes.
    windowAsOf: pick(raw, 'window_as_of') ?? (raw?.window ? pick(raw.window, 'as_of') : null),

    pitch: normaliseBilingual(pick(raw, 'pitch'), lang),
    objection: normaliseBilingual(pick(raw, 'objection'), lang),

    amortisation: pick(raw, 'amortisation'),
    amortisationRef: pick(raw, 'amortisation_ref'),
    emiSource: pick(raw, 'emi_source'),
    journey: pick(raw, 'journey'),
    dispositions: pickArray(raw, 'dispositions'),
    consents: pickArray(raw, 'consents'),
    customer: pick(raw, 'customer'),
    provenance: pick(raw, 'provenance'),
    spark: pickArray(raw, 'spark'),
  }
}

// --------------------------------------------------------------------------- //
// the bundled export
// --------------------------------------------------------------------------- //

/** Fetch `public/sanket_data.json`, honouring the deployed base path. */
export async function loadPack({ signal } = {}) {
  const response = await fetch(publicPath('sanket_data.json'), { signal })
  if (!response.ok) throw new Error(`Could not load the bundled lead book (HTTP ${response.status})`)
  return response.json()
}

/** Fetch `public/radar_data.json`. Optional: the Radar degrades to an empty state. */
export async function loadRadar({ signal } = {}) {
  const response = await fetch(publicPath('radar_data.json'), { signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/**
 * The headline, as two measured rates — never typed, never hard-coded.
 *
 * The plan's wording is "{baseline} → {precision} disbursements per 100 RM calls", where
 * both numbers are disbursement rates over the SAME drop-off population and the same
 * hundred calls: one contacts at random, the other contacts the model's top 10%.
 *
 * Read in order of how directly the source states it. SM-1 is still moving these keys, so
 * every known spelling is tried and the last resort is `null` — which the screen renders
 * as "not in this build", not as a number.
 */
export function headlineFrom(metrics) {
  if (!metrics) return null
  const parts = metrics.headline_parts || null
  const registered = metrics.registered || null

  const baseline = toNumber(
    parts?.baseline
    ?? registered?.random_contact_disbursement_rate
    ?? metrics.baseline_dropoff_disbursement?.value
    ?? metrics.baseline_dropoff_disbursement
    ?? metrics.blended?.baseline,
  )
  const precision = toNumber(
    parts?.precision
    ?? registered?.precision_at_10pct_budget
    ?? metrics.precision_at_10pct?.value
    ?? metrics.precision_at_10pct
    ?? metrics.precision_at?.['10']?.value
    ?? metrics.blended?.precision_at_budget,
  )
  const budget = toNumber(parts?.budget ?? metrics.blended?.budget) ?? 0.10

  if (baseline === null || precision === null) return null

  const basePer100 = Math.round(baseline * 100)
  const modelPer100 = Math.round(precision * 100)
  return {
    baseline,
    precision,
    budget,
    basePer100,
    modelPer100,
    // A lift is only meaningful when the denominator is not zero. A fixture run with no
    // disbursements at all has a 0% baseline, and "infinite lift" is not a claim.
    lift: baseline > 0 ? precision / baseline : null,
    text: `${basePer100} → ${modelPer100} disbursements per 100 RM calls`,
    note: parts?.note || null,
    ready: metrics.headline || null,
  }
}

/**
 * Metrics, from whichever source this page load has.
 * Live: `GET /sanket/funnel` → `data.published_metrics`.
 * Static: the packed `metrics` block.
 * The shapes overlap but are not identical, so each reader below states both spellings.
 */
export function readMetrics(source) {
  if (!source) return null
  const m = source

  const ci = (v) => (v && typeof v === 'object' && 'value' in v
    ? { value: toNumber(v.value), lo: toNumber(v.ci_low), hi: toNumber(v.ci_high), n: toNumber(v.n), method: v.method || null }
    : v === null || v === undefined ? null : { value: toNumber(v), lo: null, hi: null, n: null, method: null })

  const perProduct = m.per_product_auc || m.per_product || null

  return {
    headline: headlineFrom(m),
    note: m.note || null,
    aucMacro: toNumber(m.auc_macro ?? m.blended?.auc_macro ?? m.macro_auc),
    perProduct: perProduct
      ? Object.entries(perProduct).map(([product, v]) => ({
        product,
        label: productLabel(product),
        auc: toNumber(v?.auc ?? v),
        ece: toNumber(v?.ece),
        ci: v?.auc_ci ? ci(v.auc_ci) : null,
        nPos: toNumber(v?.n_pos_test),
      }))
      : null,
    precisionAt: m.precision_at || null,
    precisionAt10: ci(m.precision_at?.['10'] ?? m.registered?.precision_at_10pct_budget ?? m.blended?.precision_at_budget),
    menuHitRate: ci(m.menu_hit_rate ?? m.menu?.menu_of_4_hit_rate ?? m.registered?.menu_of_4_hit_rate),
    windowRespect: ci(m.window_respect ?? m.windows?.window_respect_rate ?? m.registered?.window_respect_rate),
    shopperAuc: ci(m.shopper_signal_auc ?? m.shopper?.auc ?? m.registered?.window_shopper_auc),
    calibration: Array.isArray(m.calibration) ? m.calibration : null,
    precCurve: Array.isArray(m.prec_curve ?? m.blended?.prec_curve) ? (m.prec_curve ?? m.blended.prec_curve) : null,
    uplift: m.uplift || null,
    fairness: Array.isArray(m.fairness) ? m.fairness : null,
    incomeAcc: m.income_acc || null,
    excludedFeatures: Array.isArray(m.excluded_features) ? m.excluded_features : null,
    suppression: m.suppression || null,
    windowsPerProduct: m.windows?.per_product_days || null,
    bands: m.bands || null,
    seeds: m.seeds || null,
    byCut: m.by_cut || null,
    oot: m.oot || null,
    leakage: m.leakage || null,
    stability: m.stability || null,
    // Three estimands the pack keeps apart on purpose — sampling, training-seed and
    // generator variability. Passed through whole so a screen cannot merge them.
    uncertainty: m.uncertainty || null,
    menuBaselines: m.menu_baselines || null,
    deliveredQueue: m.delivered_queue || null,
    rankingComparison: m.ranking_comparison || null,
  }
}

/**
 * The instant the bundled book was scored at — the anchor every window in it was measured
 * against, and the one the static lane must answer as of.
 *
 * The static bundle is the worst case for a wall clock: it carries no server `window`
 * object, so with nothing else to go on every row was compared against `Date.now()` and
 * the whole book read "closed N days ago", N growing by one a day. The pack does carry
 * the answer — every lead's `scored_at`, and failing that the reference month.
 *
 * Leads that disagree about `scored_at` return null, deliberately: an anchor a day out
 * silently opens or shuts the one-day products, and no anchor at all is the honest state.
 */
export function packAsOf(pack) {
  if (!pack) return null
  const scored = new Set(
    (Array.isArray(pack.leads) ? pack.leads : []).map((l) => l?.scored_at).filter(Boolean),
  )
  if (scored.size > 1) return null
  if (scored.size === 1) {
    const only = String([...scored][0])
    const t = Date.parse(only)
    return Number.isNaN(t) ? null : new Date(t).toISOString()
  }
  // `ref_month` is the contract's `YYYY-MM`, but a producer that writes a full date means
  // the same month — take the first of it either way, which is where the scorer anchors.
  const refMonth = pack.meta?.ref_month
  const month = typeof refMonth === 'string' ? refMonth.slice(0, 7) : null
  if (month && /^\d{4}-\d{2}$/.test(month)) return new Date(`${month}-01T00:00:00Z`).toISOString()
  return null
}

/** Where `packAsOf` read the anchor from, for the `sla` block to declare. */
function packAsOfSource(pack) {
  const scored = new Set(
    (Array.isArray(pack?.leads) ? pack.leads : []).map((l) => l?.scored_at).filter(Boolean),
  )
  if (scored.size === 1) return 'pack.leads[].scored_at'
  if (scored.size === 0 && pack?.meta?.ref_month) return 'pack.meta.ref_month'
  return null
}

/** The window split over the non-suppressed book, as of the pack's own scoring instant. */
function slaFromPack(leads, asOf, pack) {
  if (!asOf) return null
  const counts = { window_open: 0, window_expired: 0, no_window: 0 }
  for (const lead of leads) {
    if (lead.suppressed) continue
    const state = windowStatus(lead, asOf).state
    if (state === WINDOW_STATE.OPEN) counts.window_open += 1
    else if (state === WINDOW_STATE.EXPIRED) counts.window_expired += 1
    else counts.no_window += 1
  }
  return {
    ...counts,
    windows_days: pack?.metrics?.windows?.per_product_days || { ...WINDOW_DAYS },
    as_of: asOf,
    as_of_source: packAsOfSource(pack),
  }
}

/**
 * The manager dashboard's numbers, derived from the bundled export when there is no
 * backend to ask. Only what the pack actually carries — anything absent stays null and
 * the corresponding panel says so.
 */
export function funnelFromPack(pack) {
  if (!pack) return null
  const leads = Array.isArray(pack.leads) ? pack.leads.map(normaliseLead) : []
  const counts = pack.counts || {}
  const suppression = pack.metrics?.suppression || null
  const asOf = packAsOf(pack)

  const byProduct = new Map()
  for (const lead of leads) {
    if (!lead.product) continue
    const row = byProduct.get(lead.product) || { product: lead.product, leads: 0, suppressed: 0, scoreSum: 0, scored: 0 }
    row.leads += 1
    if (lead.suppressed) row.suppressed += 1
    if (lead.score !== null) { row.scoreSum += lead.score; row.scored += 1 }
    byProduct.set(lead.product, row)
  }

  const byStage = new Map()
  for (const lead of leads) {
    if (!lead.stageReached) continue
    byStage.set(lead.stageReached, (byStage.get(lead.stageReached) || 0) + 1)
  }

  const byRm = new Map()
  for (const lead of leads) {
    if (!lead.assignedRmId) continue
    const row = byRm.get(lead.assignedRmId) || { rm_ein: lead.assignedRmId, leads: 0, open: 0 }
    row.leads += 1
    if (lead.status !== 'closed') row.open += 1
    byRm.set(lead.assignedRmId, row)
  }

  return {
    published: true,
    source: 'pack',
    leads: leads.length,
    suppressed: suppression?.suppressed_count ?? counts.suppressed ?? (leads.some((l) => l.suppressionKnown) ? leads.filter((l) => l.suppressed).length : null),
    // The drop-off population `suppressed` above was actually counted over — always the
    // full pool (`metrics.suppression.pool_at_snapshot`), never this bundle's own sample
    // of `leads`. A screen that divides `suppressed` by `leads.length` instead (a few
    // hundred delivered rows, not the thousands-strong pool) gets a share over 100%: the
    // pool's whole suppressed count against a denominator many times smaller than the
    // pool. Kept separate from `leads` rather than replacing it, because `leads.length`
    // is still the right count for this bundle's own per-sample stats (product mix, RM
    // load, stage funnel) — only a suppressed-of-pool share needs the pool figure.
    pool: suppression?.pool_at_snapshot ?? null,
    unassigned: byRm.size ? leads.filter((l) => !l.assignedRmId).length : null,
    stage_reached: byStage.size ? Object.fromEntries(byStage) : null,
    product_mix: byProduct.size
      ? [...byProduct.values()].map((r) => ({
        product: r.product, leads: r.leads, suppressed: r.suppressed,
        mean_score: r.scored ? r.scoreSum / r.scored : null,
      })).sort((a, b) => b.leads - a.leads)
      : null,
    rm_load: byRm.size ? [...byRm.values()].sort((a, b) => b.leads - a.leads) : null,
    // The pack has no RM dispositions: that is platform state, not model output. Saying
    // so beats rendering an empty chart.
    dispositions: null,
    // The window split, on the other hand, the pack CAN answer — it has every lead's
    // `contact_by` and the instant the book was scored at. What it could not do was
    // answer it against a defensible clock, and "—" was the honest placeholder for that.
    // With the anchor in hand the split is the same arithmetic the server does, over the
    // same non-suppressed population, and it agrees with the badges on the queue because
    // both go through `windowStatus`.
    sla: slaFromPack(leads, asOf, pack),
    suppression_by_reason: suppression?.reasons || null,
    counts,
    published_metrics: pack.metrics || null,
    leadRows: leads,
  }
}
