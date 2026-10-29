import { describe, expect, it } from 'vitest'
import { METRIC_GROUPS, isRetiredYear, orderedMetrics } from '../src/composables/usePlanningTable'

describe('planning table helpers', () => {
  it('has no Savings group and orders metrics by group', () => {
    expect(METRIC_GROUPS.map((g) => g.label)).toEqual(['Income', 'Tax & Take-home', 'Wealth'])
    const m = orderedMetrics(['net_worth', 'gross_income', 'expenses_annual', 'take_home'])
    expect(m).toEqual(['gross_income', 'take_home', 'net_worth'])
  })

  it('shades years from the retirement year on', () => {
    expect(isRetiredYear(2055, 2056)).toBe(false)
    expect(isRetiredYear(2056, 2056)).toBe(true)
    expect(isRetiredYear(2056, null)).toBe(false)
  })
})
