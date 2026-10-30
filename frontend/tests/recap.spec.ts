import { describe, expect, it } from 'vitest'
import { addDays, weekLabel } from '../src/composables/useRecap'

describe('weekly recap', () => {
  it('labels a week within a month and across months', () => {
    expect(weekLabel('2026-10-18', '2026-10-24')).toBe('Oct 18 – 24, 2026')
    expect(weekLabel('2026-09-27', '2026-10-03')).toBe('Sep 27 – Oct 3, 2026')
    expect(addDays('2026-10-24', 1)).toBe('2026-10-25')
  })
})
