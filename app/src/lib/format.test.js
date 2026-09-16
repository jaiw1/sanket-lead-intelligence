import { describe, expect, it } from 'vitest'
import { RAG, inr, pct } from './format'

/**
 * `lib/format.js` came over with the shared kit, where DRISHTi's screens use it. SANKET's
 * own screens use `lib/fmt.js`. Both are here, so both are tested — an untested formatter
 * that two products share is the kind of thing that quietly disagrees about a lakh.
 */
describe('format (the shared kit formatter)', () => {
  it('scales rupees the same way fmt.js does', () => {
    expect(inr(4200)).toBe('₹4,200')
    expect(inr(250000)).toBe('₹2.5 L')
    expect(inr(32500000)).toBe('₹3.25 Cr')
  })

  it('returns an em dash for null', () => {
    expect(inr(null)).toBe('—')
    expect(inr(undefined)).toBe('—')
  })

  it('differs from fmt.inr on NEGATIVE amounts, deliberately unfixed here', () => {
    // The kit version compares `n >= 1e5` rather than `Math.abs(n)`, so -250000 formats as
    // a plain number. DRISHTi never shows a negative rupee figure, SANKET's fmt.inr does
    // handle it, and changing a kit file would fork the kit for no SANKET-visible gain.
    expect(inr(-250000)).toBe('₹-2,50,000')
  })

  it('formats percentages at the requested precision', () => {
    expect(pct(0.3012, 1)).toBe('30.1%')
    expect(pct(0.09)).toBe('9%')
  })

  it('names the three RAG bands with classes for each', () => {
    for (const key of ['red', 'amber', 'green']) {
      expect(RAG[key].label).toBeTruthy()
      expect(RAG[key].text).toContain('rag-')
    }
  })
})
