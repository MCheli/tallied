import { describe, expect, it } from 'vitest'
import { pctChange, thirtyDayWindow, waterfallNetWorth, waterfallSteps } from '../src/composables/useDashboardTiles'

describe('dashboard tiles', () => {
  const layers = [
    { name: 'Cash', total: 29718.15, accounts: [] },
    { name: 'Investments', total: 50179.96, accounts: [] },
    { name: 'Home Equity', total: 157549.25, accounts: [] },
    { name: 'Credit Cards', total: -775.31, accounts: [] },
  ]

  it('sums the layer totals to the net worth bar', () => {
    const steps = waterfallSteps(layers)
    expect(steps[0]).toEqual({ name: 'Cash', total: 29718.15, start: 0 })
    expect(steps[3].start).toBeCloseTo(237447.36, 2)
    expect(waterfallNetWorth(layers)).toBeCloseTo(236672.05, 2)
  })

  it('queries a real 30-day window', () => {
    expect(thirtyDayWindow(new Date(2026, 9, 29))).toEqual({ from: '2026-09-29', to: '2026-10-29' })
  })

  it('computes the 12-month percent change', () => {
    expect(pctChange(110, 10)).toBeCloseTo(10)
    expect(pctChange(110, 0)).toBe(0)
    expect(pctChange(null, 10)).toBeUndefined()
  })
})
