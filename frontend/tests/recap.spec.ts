import { describe, expect, it } from 'vitest'
import { addDays, recapHeadline, weekLabel } from '../src/composables/useRecap'
import type { WeeklyRecap } from '../src/types'

const base: WeeklyRecap = {
  week_start: '2026-10-18', week_end: '2026-10-24', complete: true, previous_week: '2026-10-11', next_week: null,
  net_worth_start: 1000, net_worth_end: 1250, net_worth_change: 250, spending: 475, prior_weekly_avg: 115,
  transaction_count: 3, income: 3624.67, uncategorized: 1,
  categories: [{ category: 'Home Improvement', total: 300, prior_avg: 0 }], largest: [],
  upcoming_bills: [{ merchant: 'Phone Co', category: 'Phone', date: '2026-10-30', amount: 60 }],
  upcoming_vests: [{ date: '2026-10-27', shares: 10, est_value: 4000 }],
}

describe('weekly recap', () => {
  it('labels a week within a month and across months', () => {
    expect(weekLabel('2026-10-18', '2026-10-24')).toBe('Oct 18 – 24, 2026')
    expect(weekLabel('2026-09-27', '2026-10-03')).toBe('Sep 27 – Oct 3, 2026')
    expect(addDays('2026-10-24', 1)).toBe('2026-10-25')
  })

  it('writes the headline from the numbers', () => {
    expect(recapHeadline(base)).toBe(
      'You spent $475, 313% more than your 4-week average of $115; the most went to Home Improvement ($300). '
      + 'Net worth rose $250. Next week: 1 bill (~$60) and an RSU vest.')
    expect(recapHeadline({ ...base, spending: 0, categories: [], net_worth_change: null, upcoming_bills: [], upcoming_vests: [] }))
      .toBe('No spending this week.')
    expect(recapHeadline({ ...base, spending: 118, net_worth_change: -40, upcoming_bills: [], upcoming_vests: [] }))
      .toBe('You spent $118, about your usual week; the most went to Home Improvement ($300). Net worth fell $40.')
  })
})
