import { describe, expect, it } from 'vitest'
import {
  DISPOSITIONS, PITCH_EN, PITCH_HI, PRODUCTS, SORT_KEYS, TIER, WINDOW_DAYS,
  dispositionLabel, fallbackPitch, inr, inrExact, num, pct, productLabel, productShort,
  suppressionLabel,
} from './fmt'

describe('fmt — the six-product vocabulary', () => {
  it('carries all six products from the contract enum, not the retired three', () => {
    expect(PRODUCTS).toEqual(['personal', 'gold', 'auto', 'education', 'home', 'lap'])
    // `pl` was the pre-SM-1 spelling and must not come back: the contract says `personal`.
    expect(PRODUCTS).not.toContain('pl')
  })

  it('labels every product, and degrades to the raw code for one it has never seen', () => {
    for (const p of PRODUCTS) expect(productLabel(p)).toMatch(/\w/)
    expect(productLabel('lap')).toBe('Loan Against Property')
    expect(productLabel('crypto')).toBe('crypto')
    expect(productLabel(null)).toBe('—')
    expect(productShort('education')).toBe('EL')
  })

  it('has a contact window for every product, and the mentors’ own numbers', () => {
    for (const p of PRODUCTS) expect(WINDOW_DAYS[p]).toBeGreaterThan(0)
    expect(WINDOW_DAYS).toEqual({ personal: 1, gold: 1, auto: 3, education: 7, home: 14, lap: 14 })
  })

  it('offers only the sort keys the backend allowlists', () => {
    expect(SORT_KEYS.map((s) => s.value)).toEqual(['score', 'intent', 'capacity', 'uplift_pct', 'safe_emi'])
  })

  it('offers exactly the contract’s eight disposition outcomes', () => {
    expect(DISPOSITIONS).toHaveLength(8)
    expect(DISPOSITIONS.map((d) => d.value).sort()).toEqual([
      'application_started', 'callback_requested', 'connected_interested',
      'connected_not_interested', 'disbursed', 'do_not_call', 'no_answer', 'wrong_number',
    ])
    expect(dispositionLabel('do_not_call')).toBe('Do not call again')
    expect(dispositionLabel('something_else')).toBe('something_else')
  })

  it('names three tiers with a class for each', () => {
    for (const key of ['hot', 'warm', 'cold']) {
      expect(TIER[key].label).toBeTruthy()
      expect(TIER[key].chip).toContain('border')
    }
  })
})

describe('fmt — money and percentages', () => {
  it('scales rupees to lakh and crore', () => {
    expect(inr(4200)).toBe('₹4,200')
    expect(inr(250000)).toBe('₹2.5 L')
    expect(inr(32500000)).toBe('₹3.25 Cr')
    expect(inr(-250000)).toBe('₹-2.5 L')
  })

  it('accepts the string decimals the API actually sends', () => {
    expect(inr('219800.00')).toBe('₹2.2 L')
    expect(inrExact('32200.00')).toBe('₹32,200')
  })

  it('returns an em dash rather than NaN for an absent value', () => {
    for (const bad of [null, undefined, '', 'not a number']) {
      expect(inr(bad)).toBe('—')
      expect(inrExact(bad)).toBe('—')
      expect(num(bad)).toBe('—')
    }
    expect(pct(null)).toBe('—')
    // Zero is a real answer and must survive.
    expect(inr(0)).toBe('₹0')
    expect(num(0)).toBe('0')
    expect(pct(0)).toBe('0%')
  })

  it('formats percentages at the requested precision', () => {
    expect(pct(0.3012, 1)).toBe('30.1%')
    expect(pct(0.09)).toBe('9%')
  })
})

describe('fmt — call material', () => {
  it('ships both languages for all six products', () => {
    for (const p of PRODUCTS) {
      for (const table of [PITCH_EN, PITCH_HI]) {
        expect(table[p]).toBeTruthy()
        expect(table[p].opener.length).toBeGreaterThan(10)
        expect(table[p].why_now.length).toBeGreaterThan(10)
      }
    }
  })

  it('promises nothing about approval, in either language', () => {
    // The model ranks a conversation; it does not underwrite a loan. Copy that says
    // "pre-approved" turns a ranking into a commitment the bank has not made.
    const forbidden = /pre-approved|pre-qualified|guaranteed|sanctioned|approved amount|मंज़ूर|स्वीकृत राशि|गारंटी/i
    for (const p of PRODUCTS) {
      for (const table of [PITCH_EN, PITCH_HI]) {
        const all = Object.values(table[p]).join(' ')
        expect(all, `${p} pitch promises approval`).not.toMatch(forbidden)
      }
    }
  })

  it('keeps the Hindi respectful and readable: आप, no Devanagari digits', () => {
    for (const p of PRODUCTS) {
      const all = Object.values(PITCH_HI[p]).join(' ')
      // तू / तुम would be wrong register for a bank calling a customer.
      expect(all).not.toMatch(/\bतुम\b|\bतू\b/)
      // Devanagari digits are read unreliably by screen readers on Indian locales.
      expect(all).not.toMatch(/[०-९]/)
    }
  })

  it('falls back to a real script for any product and language', () => {
    expect(fallbackPitch('gold', 'hi').opener).toBe(PITCH_HI.gold.opener)
    expect(fallbackPitch('gold', 'en').opener).toBe(PITCH_EN.gold.opener)
    // An unknown product still yields something an RM can read aloud.
    expect(fallbackPitch('unknown', 'en')).toBe(PITCH_EN.personal)
  })
})

describe('fmt — suppression', () => {
  it('names every reason the generator can emit', () => {
    expect(suppressionLabel('no_marketing_consent')).toMatch(/DPDP/)
    expect(suppressionLabel('dnd_registry')).toMatch(/DND/)
    // An unknown reason is shown, de-underscored — never swallowed.
    expect(suppressionLabel('some_new_rule')).toBe('some new rule')
    expect(suppressionLabel(null)).toBe('Suppressed')
  })
})
