import type { RSUGrantDetail, UpcomingVest } from '../types'

/** The ticker the page works with: whatever the grants carry; never a hard-coded symbol. */
export function deriveSymbol(grants: Pick<RSUGrantDetail, 'symbol'>[], responseSymbol?: string | null): string | null {
  const fromGrants = grants.map(g => g.symbol).find(s => !!s)
  return fromGrants || responseSymbol || null
}

/** Vests on or after `today` (the API returns every non-actual event, including stale past-dated ones). */
export function upcomingVests(vests: UpcomingVest[], today: Date = new Date()): UpcomingVest[] {
  const cutoff = today.toISOString().slice(0, 10)
  return vests.filter(v => v.vest_date >= cutoff).sort((a, b) => a.vest_date.localeCompare(b.vest_date))
}

export function groupByYear<T extends { vest_date: string }>(vests: T[]): Record<string, T[]> {
  const grouped: Record<string, T[]> = {}
  for (const v of vests) (grouped[v.vest_date.slice(0, 4)] ??= []).push(v)
  return grouped
}

export function daysUntil(dateStr: string, today: Date = new Date()): number {
  // Whole calendar days, computed in UTC so a DST change between the two dates cannot add an hour.
  const [y, m, d] = dateStr.split('-').map(Number)
  const target = Date.UTC(y, m - 1, d)
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((target - now) / 86_400_000)
}

export function useRsuHelpers() {
  return { deriveSymbol, upcomingVests, groupByYear, daysUntil }
}
