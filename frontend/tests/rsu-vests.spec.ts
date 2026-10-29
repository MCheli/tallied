import { describe, expect, it } from 'vitest'
import { deriveSymbol, upcomingVests, groupByYear, daysUntil } from '../src/composables/useRsuHelpers'

describe('useRsuHelpers', () => {
  it('derives the symbol from the grants, falling back to the response, never a hard-coded ticker', () => {
    expect(deriveSymbol([{ symbol: null }, { symbol: 'MSFT' }], 'XYZ')).toBe('MSFT')
    expect(deriveSymbol([{ symbol: null }], 'MSFT')).toBe('MSFT')
    expect(deriveSymbol([], null)).toBeNull()
  })

  it('keeps only vests dated today or later, sorted by date', () => {
    const today = new Date('2026-10-29T12:00:00')
    const vests = [
      { grant_id: 'A', grant_date: '2024-05-15', vest_date: '2026-11-15', shares: 50, est_value: 100 },
      { grant_id: 'B', grant_date: '2023-05-15', vest_date: '2025-11-15', shares: 60, est_value: 100 }, // stale non-actual event
      { grant_id: 'C', grant_date: '2025-05-15', vest_date: '2026-10-29', shares: 10, est_value: 100 },
    ]
    expect(upcomingVests(vests, today).map(v => v.grant_id)).toEqual(['C', 'A'])
    expect(Object.keys(groupByYear(upcomingVests(vests, today)))).toEqual(['2026'])
  })

  it('counts days until a vest from local midnight', () => {
    expect(daysUntil('2026-11-05', new Date('2026-10-29T18:00:00'))).toBe(7)
    expect(daysUntil('2026-10-29', new Date('2026-10-29T18:00:00'))).toBe(0)
  })
})
