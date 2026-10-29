/**
 * Dashboard arithmetic kept out of the view so it is unit-tested (tests/dashboard-tiles.spec.ts).
 */
import { ref, type Ref } from 'vue'
import { daysAgo, localISO } from './useDatePresets'
import type { LiquidityLayer } from '../types'

/** The 30-day window the "Last 30 Days Spending" tile really queries. */
export function thirtyDayWindow(now: Date = new Date()): { from: string; to: string } {
  return { from: daysAgo(30, now), to: localISO(now) }
}

/**
 * Waterfall steps from the layer totals the API returns (which already include only
 * include_in_nw accounts). The running total of the last step is the net worth tile.
 */
export function waterfallSteps(layers: LiquidityLayer[]): { name: string; total: number; start: number }[] {
  let running = 0
  return layers.map(l => {
    const step = { name: l.name, total: l.total, start: running }
    running += l.total
    return step
  })
}

export function waterfallNetWorth(layers: LiquidityLayer[]): number {
  return Math.round(layers.reduce((s, l) => s + l.total, 0) * 100) / 100
}

/** Percent change implied by a 12-month delta, or undefined when it cannot be computed. */
export function pctChange(netWorth: number | null | undefined, change: number | null | undefined): number | undefined {
  if (netWorth == null || change == null) return undefined
  const prev = netWorth - change
  if (prev === 0) return 0
  return (change / Math.abs(prev)) * 100
}

/** One independently loaded tile: data or an error, never both blanking the page. */
export interface Tile<T> {
  data: Ref<T | null>
  error: Ref<string | null>
  loading: Ref<boolean>
  load: (fn: () => Promise<T>) => Promise<void>
}

export function useTile<T>(): Tile<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<string | null>(null)
  const loading = ref(false)
  async function load(fn: () => Promise<T>) {
    loading.value = true
    error.value = null
    try {
      data.value = await fn()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }
  return { data, error, loading, load }
}
