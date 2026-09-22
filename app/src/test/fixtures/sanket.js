// Fixtures shaped like the two real sources, so a test that passes here would pass
// against the running backend. Values are trimmed, not invented: the key names and the
// string-typed decimals are what `GET /sanket/queue` actually returns.

export const QUEUE_ROW = {
  lead_id: 'LB-2000002',
  id: 'LB-2000002',
  cif_id: '978411994',
  segment: 'self-employed',
  product: 'personal',
  product_menu: [
    { prob: 0.5976, reason: 'We can fold the EMIs you pay elsewhere into one at a lower rate.', product: 'personal', safe_emi: 32200, window_days: 1, amortisation_ref: 'AMT-PERSONAL' },
    { prob: 0.1018, reason: 'A short-tenor gold loan covers the gap before salary day.', product: 'gold', safe_emi: 32200, window_days: 1, amortisation_ref: 'AMT-GOLD' },
    { prob: 0.1018, reason: 'Your cab and fuel spend is close to an EMI on a vehicle of your own.', product: 'auto', safe_emi: 32200, window_days: 3, amortisation_ref: 'AMT-AUTO' },
    { prob: 0.1018, reason: 'School and college debits are rising.', product: 'education', safe_emi: 32200, window_days: 7, amortisation_ref: 'AMT-EDUCATION' },
  ],
  tier: 'hot',
  lang: 'en',
  score: 0.5976,
  intent: 0.9225,
  capacity: 0.4196,
  uplift_tag: 'persuadable',
  uplift_pct: 0.3586,
  salary_m: '219800.00',
  retained_income: '64400.00',
  safe_emi: '32200.00',
  reasons: ['53 min on personal-loan pages in 90 days'],
  negative_signals: [
    { label: 'Dropped at the Rs 1,000 processing fee', signal: 'fee_balk', severity: 'high' },
  ],
  nba: 'Call within 1 day(s).',
  suppressed: false,
  suppression_reasons: [],
  assigned_rm_id: 'EIN-100471',
  status: 'open',
  journey_ref: 'JRN-000002',
  consent: true,
  provenance: { model: 'FIXTURE', journey: 'SIMULATED' },
  abandon_ts: '2026-09-10T18:59:28+00:00',
  window_shopper: true,
  stage_reached: 'fee',
  // `as_of` is what the server says it judged this window at — the run's scoring
  // instant, not the reader's clock. The row travels without the envelope, so it carries
  // its own anchor.
  window: { days: 1, due_by: '2026-09-11T18:59:28+00:00', open: false, expired: true, as_of: '2026-09-12T00:00:00+00:00' },
}

// A suppressed lead keeps the tier its probability earned — `tier` is a band on the
// score, `suppressed` is whether the bank may ring them, and the backend sends both.
// Until 2026-09-21 every suppressed row arrived as `cold`, which made the tier column
// a restatement of the suppression flag; this fixture is deliberately a suppressed HOT
// lead so a screen that conflates the two fails here.
export const SUPPRESSED_ROW = {
  ...QUEUE_ROW,
  lead_id: 'LB-2000099',
  id: 'LB-2000099',
  tier: 'hot',
  suppressed: true,
  suppression_reasons: ['no_marketing_consent'],
  assigned_rm_id: null,
}

export const LEAD_DETAIL = {
  ...QUEUE_ROW,
  age: 52,
  city_tier: 1,
  tenure_m: 213,
  window_days: 1,
  pitch: {
    en: { opener: 'I look after personal banking for your branch.', why_now: 'One EMI instead of several.', proof: ['Retained income about Rs 64,400 a month'] },
    hi: { opener: 'मैं आपकी शाखा की व्यक्तिगत बैंकिंग देखता हूँ।', why_now: 'कई EMI की जगह एक EMI।', proof: ['मासिक बचत लगभग Rs 64,400'] },
  },
  objection: {
    en: { q: 'Another loan sounds like more stress.', a: 'It replaces costlier debt you already service.' },
    hi: { q: 'एक और लोन तो और तनाव जैसा लगता है।', a: 'यह महँगे कर्ज़ की जगह लेता है।' },
  },
  amortisation: {
    emi: 16428.62, principal: 500000, rate_pa: 0.1125, tenor_months: 36, total_interest: 91430.32,
    product: 'personal', provenance: { rate: 'FIXTURE', schedule: 'FIXTURE' },
    rows: [{ n: 1, emi: 16428.62, opening: 500000, closing: 488258.88, interest: 4687.5, principal: 11741.12 }],
  },
  journey: {
    journey_id: 'JRN-000002', product: 'personal', channel: 'branch', stage_reached: 'fee',
    abandon_reason: 'fee_balk', window_shopper: true,
    shopper_signals: { fee_balk: true, doc_refusal: false, refused_income: false, blank_field_ratio: 0.033, vague_answer_count: 0, multi_product_revisits: 4 },
    stages: [{ stage: 'start', outcome: 'advanced', dwell_seconds: 219, blank_fields: 0 }],
  },
  dispositions: [],
  consents: [],
  customer: { cust_id: 'LB-2000002', segment: 'self-employed' },
}

export const FUNNEL = {
  published: true,
  leads: 120,
  suppressed: 83,
  unassigned: 0,
  stage_reached: { docs: 22, eligibility: 18, fee: 22, kyc: 19, offer: 20, start: 19 },
  product_mix: [
    { product: 'personal', leads: 19, suppressed: 11, mean_score: 0.152 },
    { product: 'gold', leads: 22, suppressed: 18, mean_score: 0.0657 },
    { product: 'auto', leads: 20, suppressed: 13, mean_score: 0.1098 },
    { product: 'education', leads: 17, suppressed: 11, mean_score: 0.1047 },
    { product: 'home', leads: 18, suppressed: 12, mean_score: 0.0988 },
    { product: 'lap', leads: 24, suppressed: 18, mean_score: 0.0722 },
  ],
  rm_load: [{ rm_ein: 'EIN-100471', leads: 12, open: 12 }],
  dispositions: {},
  // `as_of` is the instant the split was computed at — the run's own scoring instant,
  // deliberately well in the past here so the frozen-snapshot wording is exercised.
  sla: { window_open: 14, window_expired: 23, no_window: 0, windows_days: { personal: 1, gold: 1, auto: 3, education: 7, home: 14, lap: 14 }, as_of: '2026-09-01T00:00:00+00:00', as_of_source: 'export.leads[].scored_at' },
  suppression_by_reason: { contact_fatigue: 73, dnd_registry: 10, no_marketing_consent: 24 },
  counts: { hot: 5, warm: 25, cold: 90, no_consent: 24, suppressed: 83 },
  published_metrics: {
    note: 'Computed from data/bank/fixture.json by app.fixtures.',
    baseline_dropoff_disbursement: { n: 120, value: 0.09, ci_low: 0.05, ci_high: 0.15, method: 'wilson' },
    precision_at: { 5: { value: 0.34 }, 10: { n: 12, value: 0.30, ci_low: 0.15, ci_high: 0.50, method: 'wilson' }, 20: { value: 0.25 } },
    auc_macro: 0.812,
    per_product_auc: {
      personal: { auc: 0.84, ece: 0.02, n_pos_test: 21, auc_ci: { value: 0.84, ci_low: 0.78, ci_high: 0.9 } },
      gold: { auc: 0.71, ece: 0.03, n_pos_test: 9, auc_ci: { value: 0.71, ci_low: 0.6, ci_high: 0.82 } },
    },
    menu_hit_rate: { n: 16, value: 0.88, ci_low: 0.7, ci_high: 0.96 },
    window_respect: { n: 37, value: 0.93, ci_low: 0.8, ci_high: 0.98 },
    shopper_signal_auc: { n: 37, value: 0.7924, ci_low: 0.6459, ci_high: 0.9389 },
    calibration: [{ n: 7, pred: 0.16, obs: 0.14 }, { n: 8, pred: 0.3, obs: 0.33 }],
    fairness: [
      { n: 40, dim: 'Segment', group: 'salaried', ratio: 1.0, passes: true, sel_rate: 0.325 },
      { n: 45, dim: 'Segment', group: 'gig', ratio: 0.5471, passes: false, sel_rate: 0.1778 },
    ],
    income_acc: { within10: 0.65, within15: 0.9, median_err: 0.0654, gig_within15: 0.4 },
    suppression: { n_suppressed: 83, by_reason: { contact_fatigue: 73, dnd_registry: 10 } },
    excluded_features: ['Gender, religion, caste, marital status — excluded outright by policy.'],
  },
}

/** A packed export, in SM-1's post-rewrite shape. */
export const PACK = {
  meta: { n_customers: 60000, n_consented: 41000, ref_month: '2026-09-01' },
  counts: { hot: 5, warm: 25, cold: 90, no_consent: 24, suppressed: 83 },
  provenance: { provenance_version: 1, product: 'sanket', mode: 'simulated', families: { journey: 'SIMULATED' } },
  metrics: {
    headline: '9 → 30 disbursements per 100 RM calls',
    headline_parts: { baseline: 0.09, precision: 0.30, budget: 0.10, baseline_per_100: 9, precision_per_100: 30 },
    bands: {
      'SK-01': { verdict: 'pass', band: 'baseline in [0.08, 0.10]', observed: 0.09 },
      'SK-02': { verdict: 'fail', band: 'precision@10% in [0.25, 0.35]', observed: 0.21 },
      'SK-03': { verdict: 'not_measured', band: 'precision at 5% and 20%' },
    },
    // `pool_at_snapshot` is the drop-off population `suppressed_count` was actually
    // counted over — always far bigger than this fixture's one bundled `leads` row, the
    // same way it is in a real export (a few hundred delivered rows against a
    // thousands-strong pool).
    suppression: { suppressed_count: 83, pool_at_snapshot: 830, reasons: { no_marketing_consent: 24 } },
    excluded_features: ['Credit-bureau score — pulled only at application stage.'],
  },
  leads: [
    {
      id: 'LB-3000001', segment: 'salaried', age: 34, city_tier: 2, tenure_m: 60,
      consent: true, queued: true, suppressed: false, suppression_reason: 'none',
      product: 'home', tier: 'warm', lang: 'hi', intent: 0.71, capacity: 0.66, score: 0.68,
      salary_m: 84000, retained_income: 31000, safe_emi: 15500,
      window_days: 14, contact_by: '2026-09-25', scored_at: '2026-09-01',
      reasons: ['Rent stepped up 18% over two quarters'],
      negative_chips: [{ signal: 'blank_field_ratio', text: 'Left 44% of optional fields blank', impact: -0.31, mentor_signal: true }],
      product_menu: [
        { product: 'home', label: 'Home Loan', p: 0.41, reason: 'the application they abandoned', window_days: 14, contact_by: '2026-09-25', emi: 15500, emi_source: 'TYPICAL_EMI' },
        { product: 'lap', label: 'Loan Against Property', p: 0.18, reason: 'their EMI headroom fits this ticket', window_days: 14, contact_by: '2026-09-25', emi: 15500, emi_source: 'TYPICAL_EMI' },
      ],
      pitch: { opener: 'नमस्ते!', why_now: 'किराया बढ़ा है।', proof: ['किराया +18%'] },
      objection: { q: 'क्या EMI किराए के बराबर होगी?', a: 'आपकी आय पर यह आरामदायक है।' },
      nba: 'Call within 14 days.',
      emi_source: 'TYPICAL_EMI',
      provenance: { features: 'SIMULATED', emi: 'TYPICAL_EMI' },
      spark: [],
    },
  ],
}

/** The pre-SM-1 packed export: none of the new keys. Static mode must survive it. */
export const LEGACY_PACK = {
  meta: { n_customers: 15000, n_consented: 9000 },
  counts: { hot: 2, warm: 5, cold: 9, no_consent: 3 },
  metrics: { blended: { baseline: 0.013, auc_macro: 0.88, prec_curve: [] }, per_product: {} },
  leads: [
    {
      id: 'LB-1000001', segment: 'gig', age: 29, city_tier: 3, tenure_m: 24, consent: true,
      product: 'pl', tier: 'hot', lang: 'en', intent: 0.8, capacity: 0.5, score: 0.7,
      salary_m: 32000, retained_income: 9000, safe_emi: 4200,
      reasons: ['Balance building for three months'],
      pitch: { opener: 'Hello.', why_now: 'Now is a good time.', proof: [] },
      objection: { q: 'Why now?', a: 'Because.' },
      nba: 'Call.',
      spark: [],
    },
  ],
}
