import { describe, expect, it } from 'vitest'
import { funnelFromPack, headlineFrom, normaliseLead, packAsOf, pick, pickArray, readMetrics, toNumber } from './pack'
import { LEAD_DETAIL, LEGACY_PACK, PACK, QUEUE_ROW, SUPPRESSED_ROW } from '../test/fixtures/sanket'
// The bundle the static demo actually serves, read from disk rather than mocked: the
// numbers on that dashboard are the point of this fix, and a fixture cannot vouch for them.
import COMMITTED_PACK from '../../public/sanket_data.json'

describe('toNumber / pick — absence is a value', () => {
  it('turns the API’s string decimals into numbers', () => {
    expect(toNumber('219800.00')).toBe(219800)
    expect(toNumber(0.5976)).toBe(0.5976)
  })

  it('returns null — never 0 — for anything that is not a number', () => {
    for (const bad of [null, undefined, '', 'abc', NaN, Infinity]) expect(toNumber(bad)).toBeNull()
    expect(toNumber(0)).toBe(0) // a real zero survives
  })

  it('picks the first key that is actually present, and null when none is', () => {
    expect(pick({ b: 2 }, 'a', 'b')).toBe(2)
    expect(pick({ a: null, b: 0 }, 'a', 'b')).toBe(0)
    expect(pick({}, 'a', 'b')).toBeNull()
    expect(pick(null, 'a')).toBeNull()
  })

  it('distinguishes an empty list from a missing one', () => {
    expect(pickArray({ xs: [] }, 'xs')).toEqual([])
    expect(pickArray({}, 'xs')).toBeNull()
  })
})

describe('normaliseLead — one shape from two sources', () => {
  it('reads a live queue row, coercing the string decimals', () => {
    const lead = normaliseLead(QUEUE_ROW)
    expect(lead.id).toBe('LB-2000002')
    expect(lead.salaryM).toBe(219800)
    expect(lead.retainedIncome).toBe(64400)
    expect(lead.safeEmi).toBe(32200)
    expect(lead.productMenu).toHaveLength(4)
    // live spells the probability `prob`; the packed export spells it `p`
    expect(lead.productMenu[0].prob).toBe(0.5976)
    expect(lead.productMenu[0].label).toBe('Personal Loan')
  })

  it('reads a packed lead, whose menu uses `p` and `emi`', () => {
    const lead = normaliseLead(PACK.leads[0])
    expect(lead.productMenu[0].prob).toBe(0.41)
    expect(lead.productMenu[0].emi).toBe(15500)
    expect(lead.productMenu[0].emiSource).toBe('TYPICAL_EMI')
    expect(lead.productMenu[0].windowDays).toBe(14)
  })

  it('reads negative chips under either key, preserving the label', () => {
    expect(normaliseLead(QUEUE_ROW).negativeChips).toEqual([
      { signal: 'fee_balk', label: 'Dropped at the Rs 1,000 processing fee', severity: 'high', impact: null, mentorSignal: false },
    ])
    const packed = normaliseLead(PACK.leads[0]).negativeChips
    expect(packed[0].label).toBe('Left 44% of optional fields blank')
    expect(packed[0].impact).toBe(-0.31)
    expect(packed[0].mentorSignal).toBe(true)
  })

  it('returns null chips — not [] — when NEITHER key is in the build', () => {
    // This is the whole point: `[]` means "this lead has no negative signal", which is a
    // finding. `null` means "this build does not carry the field", which is not.
    expect(normaliseLead(LEGACY_PACK.leads[0]).negativeChips).toBeNull()
    expect(normaliseLead({ ...QUEUE_ROW, negative_signals: [] }).negativeChips).toEqual([])
  })

  it('reads suppression from the plural live key and the singular packed key', () => {
    const live = normaliseLead(SUPPRESSED_ROW)
    expect(live.suppressed).toBe(true)
    expect(live.suppressionReasons).toEqual(['no_marketing_consent'])
    expect(live.suppressionKnown).toBe(true)

    const packed = normaliseLead({ ...PACK.leads[0], suppressed: true, suppression_reason: 'dnd' })
    expect(packed.suppressionReasons).toEqual(['dnd'])

    // "none" is the packed sentinel for not suppressed, not a reason to display.
    expect(normaliseLead(PACK.leads[0]).suppressionReasons).toEqual([])
    expect(normaliseLead(PACK.leads[0]).suppressed).toBe(false)
  })

  it('says suppression is UNKNOWN when a legacy build carries neither key', () => {
    const legacy = normaliseLead(LEGACY_PACK.leads[0])
    expect(legacy.suppressionKnown).toBe(false)
    expect(legacy.suppressed).toBe(false)
  })

  it('normalises a bilingual pitch and a single-language one', () => {
    const live = normaliseLead(LEAD_DETAIL)
    expect(live.pitch.bilingual).toBe(true)
    expect(live.pitch.en.opener).toMatch(/personal banking/)
    expect(live.pitch.hi.opener).toMatch(/शाखा/)

    const packed = normaliseLead(PACK.leads[0]) // lang: 'hi', single-language pitch
    expect(packed.pitch.bilingual).toBe(false)
    expect(packed.pitch.hi.opener).toBe('नमस्ते!')
    expect(packed.pitch.en).toBeNull()
  })

  it('survives a lead with almost nothing on it', () => {
    const lead = normaliseLead({ id: 'LB-1' })
    expect(lead.id).toBe('LB-1')
    expect(lead.productMenu).toBeNull()
    expect(lead.reasons).toEqual([])
    expect(lead.score).toBeNull()
    expect(lead.pitch.single).toBeNull()
  })
})

describe('headlineFrom — computed, never typed', () => {
  it('reads the packed headline_parts', () => {
    const h = headlineFrom(PACK.metrics)
    expect(h.basePer100).toBe(9)
    expect(h.modelPer100).toBe(30)
    expect(h.text).toBe('9 → 30 disbursements per 100 RM calls')
    expect(h.lift).toBeCloseTo(3.33, 1)
  })

  it('reads the live published_metrics spelling', () => {
    const h = headlineFrom({
      baseline_dropoff_disbursement: { value: 0.09 },
      precision_at: { 10: { value: 0.3 } },
    })
    expect(h.basePer100).toBe(9)
    expect(h.modelPer100).toBe(30)
  })

  it('reads the pre-registered spelling too', () => {
    const h = headlineFrom({
      registered: { random_contact_disbursement_rate: 0.08, precision_at_10pct_budget: 0.28 },
    })
    expect(h.basePer100).toBe(8)
    expect(h.modelPer100).toBe(28)
  })

  it('refuses to quote a lift when the baseline is zero', () => {
    // The fixture run really does have a 0% random baseline. "Infinite lift" is not a claim.
    const h = headlineFrom({ headline_parts: { baseline: 0, precision: 0.5 } })
    expect(h.basePer100).toBe(0)
    expect(h.modelPer100).toBe(50)
    expect(h.lift).toBeNull()
  })

  it('returns null when either rate is missing, rather than half a headline', () => {
    expect(headlineFrom({ headline_parts: { baseline: 0.09 } })).toBeNull()
    expect(headlineFrom({})).toBeNull()
    expect(headlineFrom(null)).toBeNull()
  })

  it('never hard-codes the deck’s numbers', () => {
    // Guard against a helpful default creeping in, and against the retired "1% -> 36%".
    // Whatever the source says is what the headline says.
    expect(headlineFrom({ headline_parts: { baseline: 0.02, precision: 0.11 } }).text)
      .toBe('2 → 11 disbursements per 100 RM calls')
    expect(headlineFrom({ headline_parts: { baseline: 0.5, precision: 0.5 } }).text)
      .toBe('50 → 50 disbursements per 100 RM calls')
    // And it reports the ready-made string the pack carries WITHOUT letting it override
    // the computed numbers, so a stale `metrics.headline` cannot contradict the rates.
    const h = headlineFrom({ headline: '9 → 30 disbursements per 100 RM calls', headline_parts: { baseline: 0.02, precision: 0.11 } })
    expect(h.text).toBe('2 → 11 disbursements per 100 RM calls')
    expect(h.ready).toBe('9 → 30 disbursements per 100 RM calls')
  })
})

describe('readMetrics — both metric shapes', () => {
  it('reads the live published_metrics', () => {
    const m = readMetrics(PACK.metrics)
    expect(m.headline.modelPer100).toBe(30)
    expect(m.bands['SK-02'].verdict).toBe('fail')
  })

  it('unwraps a Wilson interval into value/lo/hi/n', () => {
    const m = readMetrics({ menu_hit_rate: { n: 16, value: 0.88, ci_low: 0.7, ci_high: 0.96 } })
    expect(m.menuHitRate).toMatchObject({ value: 0.88, lo: 0.7, hi: 0.96, n: 16 })
  })

  it('lists per-product AUC for whatever products are present', () => {
    const m = readMetrics({
      per_product_auc: { personal: { auc: 0.84, ece: 0.02 }, gold: { auc: 0.71 } },
    })
    expect(m.perProduct.map((p) => p.product)).toEqual(['personal', 'gold'])
    expect(m.perProduct[0].label).toBe('Personal Loan')
  })

  it('returns nulls, not zeros, for everything a legacy export lacks', () => {
    const m = readMetrics(LEGACY_PACK.metrics)
    expect(m.perProduct).toEqual([])   // `per_product` present but empty
    expect(m.menuHitRate).toBeNull()
    expect(m.windowRespect).toBeNull()
    expect(m.bands).toBeNull()
    expect(m.suppression).toBeNull()
  })
})

describe('funnelFromPack — the static dashboard', () => {
  it('derives product mix and stage counts from the leads', () => {
    const f = funnelFromPack(PACK)
    expect(f.leads).toBe(1)
    expect(f.product_mix[0].product).toBe('home')
    expect(f.suppressed).toBe(83) // from metrics.suppression, not recounted from one lead
  })

  it('exposes the pool the suppressed count was measured over, separate from the sample', () => {
    const f = funnelFromPack(PACK)
    // The bug this guards: `suppressed` (83) is always a full-pool count, never recounted
    // from the bundle's own `leads` (1 row here — a few hundred in a real export). A
    // screen that divided 83 by `f.leads` would get a share over 100%. `f.pool` is the
    // population that count actually came from, kept separate so `f.leads` stays right
    // for this bundle's own per-sample stats.
    expect(f.pool).toBe(830)
    expect(f.leads).toBe(1)
    expect(f.suppressed / f.pool).toBeLessThan(1)
  })

  it('reports null — not an empty chart — for what the pack cannot support', () => {
    const f = funnelFromPack(PACK)
    // Dispositions are platform state, not model output. The window split is not: the
    // pack carries every lead's contact_by and the instant the book was scored at.
    expect(f.dispositions).toBeNull()
  })

  it('splits the window against the pack’s own scoring instant, not today', () => {
    const f = funnelFromPack(PACK)
    // contact_by 2026-09-25, scored 2026-09-01: open then, and long shut by any wall
    // clock this test will ever run under. The static dashboard read "—" for this.
    expect(f.sla).toEqual(expect.objectContaining({
      window_open: 1, window_expired: 0, no_window: 0, as_of: '2026-09-01T00:00:00.000Z',
      as_of_source: 'pack.leads[].scored_at',
    }))
  })

  it('survives the legacy pack', () => {
    const f = funnelFromPack(LEGACY_PACK)
    expect(f.leads).toBe(1)
    expect(f.suppressed).toBeNull()
    expect(f.suppression_by_reason).toBeNull()
    expect(f.pool).toBeNull()
    // No scored_at and no ref_month: nothing to anchor to, so no split. "—" is the
    // honest answer here, and inventing a clock to fill it would not be.
    expect(f.sla).toBeNull()
  })

  it('returns null for no pack at all', () => {
    expect(funnelFromPack(null)).toBeNull()
  })
})

describe('packAsOf — when the bundled book was scored', () => {
  it('prefers the scored_at every lead agrees on', () => {
    expect(packAsOf(PACK)).toBe('2026-09-01T00:00:00.000Z')
  })

  it('falls back to the first of the reference month', () => {
    const noScoredAt = { ...PACK, leads: PACK.leads.map(({ scored_at: _drop, ...rest }) => rest) }
    expect(packAsOf(noScoredAt)).toBe('2026-09-01T00:00:00.000Z')
  })

  it('returns null when the leads disagree about when they were scored', () => {
    // An anchor a day out silently opens or shuts the one-day products. No anchor is the
    // honest state, and the reader falls back to the wall clock as it always did.
    const split = {
      ...PACK,
      leads: [{ ...PACK.leads[0], scored_at: '2026-09-01' }, { ...PACK.leads[0], id: 'LB-X', scored_at: '2026-08-01' }],
    }
    expect(packAsOf(split)).toBeNull()
    expect(funnelFromPack(split).sla).toBeNull()
  })

  it('returns null for a pack that says nothing about either', () => {
    expect(packAsOf(LEGACY_PACK)).toBeNull()
    expect(packAsOf(null)).toBeNull()
  })
})

describe('funnelFromPack — the committed bundle', () => {
  // The real numbers the static demo serves. Against the wall clock this reads 0 / 320:
  // every window in a book scored on 1 September has run out by the time anyone opens it,
  // which is a statement about the date and not about the book.
  it('splits the committed book 3 open / 317 closed as of 1 Sep 2026', () => {
    const f = funnelFromPack(COMMITTED_PACK)
    expect(f.sla.as_of).toBe('2026-09-01T00:00:00.000Z')
    expect(f.sla.window_open).toBe(3)
    expect(f.sla.window_expired).toBe(317)
    expect(f.sla.no_window).toBe(0)
  })
})
