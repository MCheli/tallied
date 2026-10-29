import { describe, expect, it } from 'vitest'
import { useFormatters } from '../src/composables/useFormatters'

describe('useFormatters', () => {
  const f = useFormatters()

  it('formats money and compact values null-safely', () => {
    expect(f.money(1234.5)).toBe('$1,235')
    expect(f.compact(1_250_000)).toBe('$1.3M')
    expect(f.money(null)).toBe(f.dash)
  })

  it('formats percentages from ratios', () => {
    expect(f.percent(0.254)).toBe('25.4%')
    expect(f.percent(undefined)).toBe(f.dash)
  })

  it('parses date-only strings as local dates', () => {
    expect(f.date('2026-10-29')).toContain('2026')
    expect(f.monthYear('2026-10-01')).toMatch(/Oct/)
  })
})
