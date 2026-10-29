import { describe, expect, it } from 'vitest'
import {
  averageMonthlySpend, changeOver, filterSeries, nearestIndex, rangeFromDate, runwayMonths,
} from '../src/composables/useCashRange'

const dates = ['2026-06-01', '2026-07-01', '2026-08-01', '2026-09-01', '2026-10-01']
const values = [100, 120, 110, 130, 125]
const now = new Date(2026, 9, 29)

describe('cash range', () => {
  it('filters the balance series to the range', () => {
    const r = filterSeries(dates, values, rangeFromDate('90', now))
    expect(r.dates).toEqual(['2026-08-01', '2026-09-01', '2026-10-01'])
    expect(r.values).toEqual([110, 130, 125])
    expect(filterSeries(dates, values, null).dates).toHaveLength(5)
  })

  it('returns an empty series (not all history) when nothing falls in the range', () => {
    const r = filterSeries(['2026-01-01', '2026-02-01'], [1, 2], rangeFromDate('30', now))
    expect(r.dates).toEqual([])
    expect(r.values).toEqual([])
  })

  it('computes the change badge over the filtered series only', () => {
    expect(changeOver([110, 130, 125])).toEqual({ change: 15, pct: (15 / 110) * 100 })
    expect(changeOver([5])).toBeNull()
  })

  it('averages monthly spend and derives runway', () => {
    const avg = averageMonthlySpend([{ month: '2026-08', total: -3000, count: 1 }, { month: '2026-09', total: -5000, count: 1 }])
    expect(avg).toBe(4000)
    expect(runwayMonths(30000, avg)).toBe(8)
    expect(runwayMonths(30000, null)).toBeNull()
    expect(averageMonthlySpend([])).toBeNull()
  })

  it('places markers on the nearest snapshot', () => {
    expect(nearestIndex(dates, '2026-08-20')).toBe(3) // closer to Sep 1 than Aug 1
    expect(nearestIndex(dates, '2026-08-05')).toBe(2)
    expect(nearestIndex(dates, '2027-01-01')).toBe(4)
  })
})
