/**
 * Cash page range logic: pure functions so the 1M/3M/6M/1Y/All control can be unit-tested
 * (tests/cash-range.spec.ts). The range scopes every section of the page: the balance chart,
 * the change badge, average monthly spend, runway and notable transactions.
 */
import { daysAgo } from './useDatePresets'
import type { MonthlySpending } from '../types'

export type CashRange = '30' | '90' | '180' | '365' | 'all'

export const CASH_RANGES: { key: CashRange; label: string; desc: string; days: number | null }[] = [
  { key: '30', label: '1M', desc: 'Last month', days: 30 },
  { key: '90', label: '3M', desc: 'Last 3 months', days: 90 },
  { key: '180', label: '6M', desc: 'Last 6 months', days: 180 },
  { key: '365', label: '1Y', desc: 'Last year', days: 365 },
  { key: 'all', label: 'All', desc: 'All time', days: null },
]

export function rangeDays(range: CashRange): number | null {
  return CASH_RANGES.find(r => r.key === range)?.days ?? null
}

/** From-date (YYYY-MM-DD) for the range, or null for "all". */
export function rangeFromDate(range: CashRange, now: Date = new Date()): string | null {
  const days = rangeDays(range)
  return days == null ? null : daysAgo(days, now)
}

/**
 * Keep only the points on/after `fromDate`. Returns empty arrays when nothing falls in the
 * range: the caller must show an empty state rather than fall back to the whole history.
 */
export function filterSeries(dates: string[], values: number[], fromDate: string | null): { dates: string[]; values: number[] } {
  if (fromDate == null) return { dates: [...dates], values: [...values] }
  const start = dates.findIndex(d => d >= fromDate)
  if (start < 0) return { dates: [], values: [] }
  return { dates: dates.slice(start), values: values.slice(start) }
}

export function changeOver(values: number[]): { change: number; pct: number } | null {
  if (values.length < 2) return null
  const first = values[0]
  const last = values[values.length - 1]
  const change = last - first
  return { change, pct: first !== 0 ? (change / Math.abs(first)) * 100 : 0 }
}

/** Mean of the monthly spending totals (absolute), or null when there are none. */
export function averageMonthlySpend(months: MonthlySpending[]): number | null {
  if (!months.length) return null
  return months.reduce((s, m) => s + Math.abs(m.total || 0), 0) / months.length
}

/** Whole months of runway, or null when there is no spend to divide by. */
export function runwayMonths(totalCash: number, avgMonthlySpend: number | null): number | null {
  if (!avgMonthlySpend || avgMonthlySpend <= 0) return null
  return Math.round(totalCash / avgMonthlySpend)
}

/** Index of the snapshot date nearest to `date` (for placing transaction markers). */
export function nearestIndex(dates: string[], date: string): number {
  if (!dates.length) return -1
  let idx = dates.findIndex(d => d >= date)
  if (idx < 0) return dates.length - 1
  if (idx > 0 && date < dates[idx]) {
    const t = new Date(date).getTime()
    const prev = Math.abs(t - new Date(dates[idx - 1]).getTime())
    const next = Math.abs(t - new Date(dates[idx]).getTime())
    if (prev < next) idx--
  }
  return idx
}
