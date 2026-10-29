import { describe, expect, it } from 'vitest'
import { daysAgo, localISO, monthsInRange, presetRange, widerPreset } from '../src/composables/useDatePresets'

const now = new Date(2026, 9, 29) // 2026-10-29 local

describe('date presets', () => {
  it('builds ranges from local calendar fields', () => {
    expect(presetRange('month', now)).toEqual({ from: '2026-10-01', to: '2026-10-29' })
    expect(presetRange('3mo', now)).toEqual({ from: '2026-07-29', to: '2026-10-29' })
    expect(presetRange('ytd', now)).toEqual({ from: '2026-01-01', to: '2026-10-29' })
    expect(presetRange('12mo', now)).toEqual({ from: '2025-10-29', to: '2026-10-29' })
  })

  it('never shifts a day through UTC conversion', () => {
    const lateEvening = new Date(2026, 9, 29, 23, 30)
    expect(localISO(lateEvening)).toBe('2026-10-29')
    expect(daysAgo(30, lateEvening)).toBe('2026-09-29')
  })

  it('falls back to a wider preset until there is nowhere wider', () => {
    expect(widerPreset('month')).toBe('3mo')
    expect(widerPreset('3mo')).toBe('12mo')
    expect(widerPreset('ytd')).toBe('12mo')
    expect(widerPreset('12mo')).toBeNull()
  })

  it('counts calendar months touched by a range', () => {
    expect(monthsInRange('2026-07-29', '2026-10-29')).toBe(4)
    expect(monthsInRange('2026-10-01', '2026-10-29')).toBe(1)
  })
})
