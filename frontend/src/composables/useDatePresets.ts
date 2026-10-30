/**
 * Date presets shared by the Spending page (and anything else with a period picker).
 * Pure functions, no DOM: unit-tested in tests/spending-presets.spec.ts.
 *
 * Dates are built from local calendar fields and formatted as YYYY-MM-DD without going
 * through toISOString(), so the range never shifts a day in US time zones.
 */
export type DatePreset = 'month' | '3mo' | 'ytd' | '12mo'

export const PRESETS: { key: DatePreset; label: string }[] = [
  { key: 'month', label: 'This Month' },
  { key: '3mo', label: 'Last 3 Months' },
  { key: 'ytd', label: 'YTD' },
  { key: '12mo', label: 'Last 12 Months' },
]

export const DEFAULT_PRESET: DatePreset = '3mo'

export function localISO(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function daysAgo(n: number, now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  d.setDate(d.getDate() - n)
  return localISO(d)
}

export function presetRange(preset: DatePreset, now: Date = new Date()): { from: string; to: string } {
  const to = localISO(now)
  switch (preset) {
    case 'month':
      return { from: localISO(new Date(now.getFullYear(), now.getMonth(), 1)), to }
    // Whole calendar months (this one and the ones before), so a monthly chart never opens on a sliver.
    case '3mo':
      return { from: localISO(new Date(now.getFullYear(), now.getMonth() - 2, 1)), to }
    case 'ytd':
      return { from: `${now.getFullYear()}-01-01`, to }
    case '12mo':
      return { from: localISO(new Date(now.getFullYear(), now.getMonth() - 11, 1)), to }
  }
}

/** The wider preset to try when the current one has no data; null when there is nowhere wider to go. */
export function widerPreset(preset: DatePreset): DatePreset | null {
  switch (preset) {
    case 'month': return '3mo'
    case '3mo': return '12mo'
    case 'ytd': return '12mo'
    case '12mo': return null
  }
}

export function presetLabel(preset: DatePreset): string {
  return PRESETS.find(p => p.key === preset)?.label ?? preset
}

/** Number of calendar months touched by [from, to], at least 1. */
export function monthsInRange(from: string, to: string): number {
  const [fy, fm] = from.split('-').map(Number)
  const [ty, tm] = to.split('-').map(Number)
  return Math.max(1, (ty - fy) * 12 + (tm - fm) + 1)
}
