import { describe, expect, it } from 'vitest'
import {
  bandSeries, changedLevers, cohortStats, deltaPts, eventSummary, formatLever, successTone, templateAges,
  whatMustBeTrue, yearRanges,
} from '../src/composables/usePlanningOutlook'
import type { EventTemplate, GoalSeekResult, MixStats } from '../src/types'

const mix: MixStats = {
  stock_share: 0.6, from_year: 1928, to_year: 2025, nominal_mean: 0.0904, real_mean: 0.059,
  nominal_cagr: 0.0834, real_cagr: 0.0515, volatility: 0.12, inflation_mean: 0.031,
}
const outlook = {
  retirement_age: 55,
  values: { retirement_spending: 90000, monthly_cash_savings: 1500, investment_return: 0.07, retirement_return: 0.05 },
  history_reference: { working: mix, retired: mix },
}
const goal = (over: Partial<GoalSeekResult> = {}): GoalSeekResult => ({
  target: 0.85, base_success: 0.6, max_spending: 58900, earliest_retirement_age: 61, extra_monthly_savings: 5150,
  required_return_shift: 0.018, required_investment_return: 0.088, required_retirement_return: 0.068,
  by_age: [], by_spending: [], ...over,
})

describe('planning outlook maths', () => {
  it('turns percentile bands into stacked base + width series', () => {
    const s = bandSeries({ p10: [0, 10], p25: [5, 20], p50: [8, 30], p75: [12, 40], p90: [20, 60] })
    expect(s.outerBase).toEqual([0, 10])
    expect(s.outerWidth).toEqual([20, 50])           // p90 - p10
    expect(s.innerBase).toEqual([5, 20])
    expect(s.innerWidth).toEqual([7, 20])            // p75 - p25
    expect(s.median).toEqual([8, 30])
    // A collapsed band (every path ran out) never stacks a negative width.
    expect(bandSeries({ p10: [5], p25: [5], p50: [5], p75: [4], p90: [4] }).outerWidth).toEqual([0])
  })

  it('grades the chance of success against the target', () => {
    expect(successTone(0.9, 0.85)).toBe('good')
    expect(successTone(0.85, 0.85)).toBe('good')
    expect(successTone(0.72, 0.85)).toBe('warning')
    expect(successTone(0.6, 0.85)).toBe('critical')
  })

  it('says what would need to be true when the plan is short of the target', () => {
    const cards = whatMustBeTrue(outlook, goal())
    expect(cards.map((c) => c.key)).toEqual(['spending', 'age', 'savings', 'returns'])
    expect(cards[0].value).toBe('$58,900/yr')
    expect(cards[0].detail).toContain('$31,100 a year less')
    expect(cards[1]).toMatchObject({ title: 'Retire at', value: '61', met: false })
    expect(cards[2].value).toBe('+$5,150/mo')
    expect(cards[3].value).toBe('+1.8 points')
    expect(cards[3].detail).toContain('8.8% while working and 6.8% retired')
    expect(cards[3].detail).toContain('9.0% a year (5.9% after inflation), 1928–2025')
  })

  it('says how much room there is when the plan already meets the target', () => {
    const cards = whatMustBeTrue(outlook, goal({
      base_success: 0.9, max_spending: 104000, earliest_retirement_age: 52, extra_monthly_savings: 0, required_return_shift: -0.012,
    }))
    expect(cards[0]).toMatchObject({ title: 'Spending headroom', met: true })
    expect(cards[0].detail).toContain('$14,000 a year more')
    expect(cards[1]).toMatchObject({ title: 'Could retire at', value: '52', met: true })
    expect(cards[2]).toMatchObject({ value: 'None needed', met: true })
    expect(cards[3]).toMatchObject({ title: 'Returns could fall', value: '1.2 points', met: true })
  })

  it('reports levers that cannot reach the target on their own', () => {
    const cards = whatMustBeTrue(outlook, goal({ max_spending: null, earliest_retirement_age: null, extra_monthly_savings: null, required_return_shift: null }))
    expect(cards.every((c) => c.value === 'Not reachable')).toBe(true)
  })

  it('places template events relative to the current and retirement ages', () => {
    const health: EventTemplate = { kind: 'healthcare', label: 'Healthcare', start: 'r', start_offset: 0, end: 'fixed', end_value: 64, amount: 15000, pct: 0, help: '' }
    expect(templateAges(health, 30, 55)).toEqual({ start_age: 55, end_age: 64 })
    expect(templateAges(health, 30, 66)).toEqual({ start_age: 66, end_age: 66 })  // retiring after 64: end never before start
    const college: EventTemplate = { kind: 'recurring_expense', label: 'College', start: 'c', start_offset: 20, end: 'c', end_offset: 23, amount: 35000, pct: 0, help: '' }
    expect(templateAges(college, 30, 55)).toEqual({ start_age: 50, end_age: 53 })
    const once: EventTemplate = { kind: 'one_off_expense', label: 'Car', start: 'c', start_offset: 3, amount: 60000, pct: 0, help: '' }
    expect(templateAges(once, 30, 55)).toEqual({ start_age: 33, end_age: null })
  })

  it('summarises events in words', () => {
    expect(eventSummary({ kind: 'healthcare', start_age: 55, end_age: 64, amount: 15000, pct: 0 })).toBe('Ages 55–64 · $15K/yr')
    expect(eventSummary({ kind: 'rsu_shock', start_age: 31, end_age: null, amount: 0, pct: -0.5 })).toBe('Age 31 · share price -50%')
    expect(eventSummary({ kind: 'spending_change', start_age: 55, end_age: null, amount: 25000, pct: -0.15 }))
      .toBe('From 55 · spending -15%, $25K to move')
  })

  it('finds the levers that differ from the saved plan', () => {
    expect(changedLevers({ a: 1, b: 0.07, c: 3 }, { a: 1, b: 0.07000000001, c: 4 })).toEqual({ c: 3 })
    expect(changedLevers({ a: 1 }, {})).toEqual({ a: 1 })
  })

  it('formats lever values by unit', () => {
    expect(formatLever(0.07, 'pct')).toBe('7%')
    expect(formatLever(0.045, 'pct')).toBe('4.5%')
    expect(formatLever(90000, 'usd')).toBe('$90,000')
    expect(formatLever(1500, 'usd_month')).toBe('$1,500/mo')
    expect(formatLever(2, 'count')).toBe('2')
    expect(formatLever(1, 'flag')).toBe('on')
    expect(formatLever(0, 'flag')).toBe('off')
    expect(formatLever(55, 'age')).toBe('55')
  })

  it('compresses failed cohort years and signs point changes', () => {
    expect(cohortStats([{ start_year: 1966, success: false }, { start_year: 1982, success: true }])).toEqual({ total: 2, lasted: 1, failed: [1966] })
    expect(yearRanges([1973, 1968, 1969, 1929])).toBe('1929, 1968–1969, 1973')
    expect(deltaPts(0.62, 0.59)).toBe('+3 pts')
    expect(deltaPts(0.55, 0.58)).toBe('−3 pts')
    expect(deltaPts(0.5, 0.5)).toBe('±0 pts')
  })
})
