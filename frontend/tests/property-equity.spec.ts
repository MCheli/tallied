import { describe, expect, it } from 'vitest'
import { equityComposition, purchasePriceFromHistory } from '../src/composables/useEquityPosition'

describe('equityComposition', () => {
  it('splits equity into down payment, appreciation and principal when the purchase price is known', () => {
    const e = equityComposition({ value: 520000, mortgageBalance: 362450, originalAmount: 380000, purchasePrice: 450000 })!
    expect(e.needsPurchasePrice).toBe(false)
    expect(e.downPayment).toBe(70000)
    expect(e.appreciation).toBe(70000)
    expect(e.principalPaid).toBe(17550)
    expect(e.totalEquity).toBe(157550)
    expect(Math.round(e.widths.downPayment + e.widths.appreciation + e.widths.principalPaid + e.widths.remaining)).toBe(100)
  })

  it('never labels the loan-minus-value gap as appreciation without a purchase price', () => {
    const e = equityComposition({ value: 520000, mortgageBalance: 362450, originalAmount: 380000, purchasePrice: null })!
    expect(e.needsPurchasePrice).toBe(true)
    expect(e.downPayment).toBeNull()
    expect(e.appreciation).toBeNull()
    expect(e.principalPaid).toBe(17550)
    expect(e.widths.appreciation).toBe(0)
  })

  it('returns null without a value', () => {
    expect(equityComposition({ value: null, mortgageBalance: 1, originalAmount: 1, purchasePrice: 1 })).toBeNull()
  })
})

describe('purchasePriceFromHistory', () => {
  it('prefers the owner-entered purchase price, then a sale record', () => {
    expect(purchasePriceFromHistory([
      { source: 'sale', value: 440000 },
      { source: 'manual', value: 450000, details: { valuation_source: 'Purchase price' } },
    ])).toBe(450000)
    expect(purchasePriceFromHistory([{ source: 'sale', value: 440000 }])).toBe(440000)
    expect(purchasePriceFromHistory([{ source: 'manual', value: 1, details: { valuation_source: 'Zillow' } }])).toBeNull()
  })
})
