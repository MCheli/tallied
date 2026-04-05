<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useImportModal } from '../composables/useImportModal'
import { useDataExplorer } from '../composables/useDataExplorer'
import DataExplorer from '../components/common/DataExplorer.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'

use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

const { baseOption } = useChartDefaults()
const { openImport } = useImportModal()
const { openData } = useDataExplorer()

const API = import.meta.env.VITE_API_URL || ''

const summary = ref<any>(null)
const grants = ref<any[]>([])
const currentPrice = ref<number | null>(null)
const symbol = ref<string>('PTC')
const loading = ref(true)
const error = ref('')
const expandedGrant = ref<string | null>(null)
const priceHistory = ref<any[]>([])

// SQL transparency modal state
const showSummaryCardsSql = ref(false)
const showPriceChartSql = ref(false)
const showLiquidationSql = ref(false)
const showUpcomingVestsSql = ref(false)
const showVestingIncomeSql = ref(false)
const showGrantsSql = ref(false)

const ETRADE_URL = 'https://us.etrade.com/etx/sp/stockplan?accountIndex=0&traxui=tsp_accountshome#/holdings'

onMounted(async () => {
  try {
    const [sumRes, grantRes, priceRes] = await Promise.all([
      fetch(`${API}/api/v1/rsu/summary`, { credentials: 'include' }),
      fetch(`${API}/api/v1/rsu/grants`, { credentials: 'include' }),
      fetch(`${API}/api/v1/rsu/price-history?symbol=PTC&range=5y`, { credentials: 'include' }),
    ])
    summary.value = await sumRes.json()
    const grantData = await grantRes.json()
    grants.value = grantData.grants || []
    currentPrice.value = grantData.current_price
    symbol.value = grantData.symbol || 'PTC'
    const priceData = await priceRes.json()
    priceHistory.value = priceData.points || []
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function fetchData() {
  const [sumRes, grantRes, priceRes] = await Promise.all([
    fetch(`${API}/api/v1/rsu/summary`, { credentials: 'include' }),
    fetch(`${API}/api/v1/rsu/grants`, { credentials: 'include' }),
    fetch(`${API}/api/v1/rsu/price-history?symbol=PTC&range=5y`, { credentials: 'include' }),
  ])
  summary.value = await sumRes.json()
  const grantData = await grantRes.json()
  grants.value = grantData.grants || []
  currentPrice.value = grantData.current_price
  const priceData = await priceRes.json()
  priceHistory.value = priceData.points || []
}

function toggleGrant(id: string) {
  expandedGrant.value = expandedGrant.value === id ? null : id
}

// Upcoming vests grouped by year
const upcomingByYear = computed(() => {
  if (!summary.value?.upcoming_vests) return {}
  const grouped: Record<string, any[]> = {}
  for (const v of summary.value.upcoming_vests) {
    const year = v.vest_date.substring(0, 4)
    if (!grouped[year]) grouped[year] = []
    grouped[year].push(v)
  }
  return grouped
})

// Sorted grants: unvested first, then by grant date desc
const sortedGrants = computed(() => {
  return [...grants.value].sort((a, b) => {
    // Grants with unvested shares first
    const aUnvested = a.unvested_shares || 0
    const bUnvested = b.unvested_shares || 0
    if (aUnvested > 0 && bUnvested === 0) return -1
    if (aUnvested === 0 && bUnvested > 0) return 1
    // Then by grant date descending
    return (b.grant_date || '').localeCompare(a.grant_date || '')
  })
})

function fmt(n: number | null | undefined, style: 'currency' | 'number' = 'currency'): string {
  if (n === null || n === undefined) return '--'
  if (style === 'currency') {
    const abs = Math.abs(n)
    const sign = n < 0 ? '-' : ''
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
    if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
    return `${sign}$${abs.toFixed(2)}`
  }
  return n.toLocaleString()
}

function fmtDate(d: string | null): string {
  if (!d) return '--'
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function vestProgress(grant: any): number {
  if (!grant.total_shares) return 0
  return Math.round(((grant.vested_shares || 0) / grant.total_shares) * 100)
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T00:00:00')
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

// Price chart option
const priceChartOption = computed(() => {
  if (!priceHistory.value.length) return null

  const dates = priceHistory.value.map(p => p.date)
  const prices = priceHistory.value.map(p => p.price)

  // Collect vest event dates for mark lines
  const vestDates: { date: string; label: string }[] = []
  for (const g of grants.value) {
    for (const ve of g.vest_events || []) {
      if (ve.is_actual && ve.vest_date) {
        vestDates.push({ date: ve.vest_date, label: `Vest $${ve.fmv_at_vest?.toFixed(0) || '?'}` })
      }
    }
  }

  // Filter vest marks to ones within chart range
  const minDate = dates[0]
  const markLines = vestDates
    .filter(v => v.date >= minDate)
    .map(v => ({
      xAxis: v.date,
      label: { show: false },
      lineStyle: { color: '#a78bfa', width: 1, type: 'dashed' as const },
    }))

  return {
    ...baseOption.value,
    grid: { left: 55, right: 20, top: 20, bottom: 30 },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        return `<strong>${p.name}</strong><br/>$${p.value.toFixed(2)}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: {
        formatter: (v: string) => {
          const d = new Date(v + 'T00:00:00')
          return d.getFullYear().toString()
        },
        // Only show label at first data point of each year
        interval: (index: number) => {
          if (index === 0) return true
          const cur = dates[index]?.substring(0, 4)
          const prev = dates[index - 1]?.substring(0, 4)
          return cur !== prev
        },
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: '${value}' },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' as const } },
    },
    series: [{
      type: 'line',
      data: prices,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: '#6366f1' },
      areaStyle: {
        color: {
          type: 'linear' as const,
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(99,102,241,0.15)' },
            { offset: 1, color: 'rgba(99,102,241,0.02)' },
          ],
        },
      },
      markLine: markLines.length > 0 ? {
        silent: true,
        symbol: 'none',
        data: markLines,
      } : undefined,
    }],
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">RSU Holdings</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ symbol }} &middot;
          <span v-if="currentPrice" class="font-medium text-gray-700 dark:text-gray-300">{{ fmt(currentPrice) }}/share</span>
          <span v-else>Price unavailable</span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <a :href="ETRADE_URL" target="_blank"
          class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
          E-Trade Holdings
        </a>
        <button @click="openData('rsu')"
          class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          Data
        </button>
        <button @click="openImport({ context: 'rsu', onComplete: fetchData })"
          class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
          Import
        </button>
        <InfoTooltip text="Import RSU data from E-Trade holdings spreadsheets or other documents." />
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading RSU data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>

    <div v-else-if="!summary || (!grants.length && !summary.held_shares)" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No RSU data found.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Import your RSU grants from E-Trade to get started.</p>
    </div>

    <template v-else-if="summary">
      <!-- Summary Cards -->
      <div class="group/summary relative grid grid-cols-2 sm:grid-cols-4 gap-3">
        <button @click="showSummaryCardsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/summary:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all z-10" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showSummaryCardsSql" :sql="`-- RSU Holdings Summary\nSELECT\n  SUM(sellable_shares) AS sellable_shares,\n  SUM(unvested_shares) AS unvested_shares,\n  SUM(sellable_shares + unvested_shares) AS total_shares\nFROM rsu_grants;\n\n-- Values computed as: shares × current stock price\n-- Current price fetched from stock_prices table (Yahoo Finance cache)`" title="RSU Summary Cards" :tables="['rsu_grants', 'stock_prices']" @close="showSummaryCardsSql = false" />
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Holdings <InfoTooltip text="<strong>Total RSU Holdings</strong><br>Current market value of all PTC shares you own or will receive. Includes sellable shares (vested, in your account) plus unvested shares (scheduled to vest in the future).<br><br><strong>Formula:</strong> <code>(sellable + unvested shares) × current PTC price</code><br><strong>Source:</strong> RSU grants table × live PTC price from Yahoo Finance (cached daily)." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(summary.held_value) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmt(summary.sellable_shares, 'number') }} sellable + {{ fmt(summary.unvested_shares, 'number') }} unvested</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Sellable <InfoTooltip text="<strong>Sellable Shares</strong><br>Shares that have vested and are available to sell right now through E-Trade. These are net of shares withheld for taxes at vesting.<br><br><strong>Source:</strong> RSU grants table, sellable_shares field from E-Trade export." /></div>
          <div class="text-xl font-bold text-green-600 dark:text-green-400 mt-1">{{ fmt(summary.sellable_value) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmt(summary.sellable_shares, 'number') }} shares</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Unvested <InfoTooltip text="<strong>Unvested Shares</strong><br>Shares granted but not yet vested. These will vest according to their schedule (typically annually over 3 years). Value is estimated at current price — actual value depends on stock price at vest date.<br><br><strong>Source:</strong> RSU grants table, unvested_shares field." /></div>
          <div class="text-xl font-bold text-amber-600 dark:text-amber-400 mt-1">{{ fmt(summary.unvested_value) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmt(summary.unvested_shares, 'number') }} shares</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Unrealized Gain <InfoTooltip text="<strong>Unrealized Gain/Loss</strong><br>How much your sellable shares have gained or lost since vesting. Positive = stock price is above your cost basis; negative = below.<br><br><strong>Formula:</strong> <code>(current price - cost basis per share) × sellable shares</code><br><strong>Source:</strong> FIFO lot allocation across vest events, cost basis = FMV at vest date." /></div>
          <div class="text-xl font-bold mt-1" :class="summary.tax_lots.all.gain >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
            {{ fmt(summary.tax_lots.all.gain) }}
          </div>
          <div class="text-xs text-gray-400 mt-1">Cost basis {{ fmt(summary.tax_lots.all.cost_basis) }}</div>
        </div>
      </div>

      <!-- Stock Price Chart -->
      <div v-if="priceChartOption" class="group/price relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showPriceChartSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/price:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showPriceChartSql" :sql="`-- Stock price history (5-year weekly)\nSELECT date, close_price AS price\nFROM stock_prices\nWHERE symbol = 'PTC'\n  AND date >= date('now', '-5 years')\nORDER BY date;\n\n-- Vest event overlay marks\nSELECT ve.vest_date, ve.fmv_at_vest\nFROM vest_events ve\nJOIN rsu_grants g ON ve.grant_id = g.id\nWHERE ve.is_actual = 1\nORDER BY ve.vest_date;`" title="Stock Price Chart" :tables="['stock_prices', 'vest_events', 'rsu_grants']" @close="showPriceChartSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">{{ symbol }} Stock Price <InfoTooltip text="5-year weekly closing price for PTC stock. Dashed vertical lines mark dates when RSU shares vested. Useful for seeing whether shares vested at favorable or unfavorable prices.<br><br><strong>Source:</strong> Yahoo Finance historical data (weekly interval), vest event dates from vest_events table." /></h2>
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">5-year weekly &middot; dashed lines = vest events</p>
        <v-chart :option="priceChartOption" style="height: 250px" autoresize />
      </div>

      <!-- Liquidation Analysis + Upcoming Vests side by side -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Liquidation Analysis -->
        <div class="group/liquidation relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showLiquidationSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/liquidation:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showLiquidationSql" :sql="`-- Tax lot analysis (FIFO allocation of sellable shares to vest events)\nSELECT\n  ve.vest_date,\n  ve.shares_released,\n  ve.fmv_at_vest AS cost_basis_per_share,\n  CASE\n    WHEN ve.vest_date <= date('now', '-1 year') THEN 'Long Term'\n    ELSE 'Short Term'\n  END AS tax_status\nFROM vest_events ve\nJOIN rsu_grants g ON ve.grant_id = g.id\nWHERE ve.is_actual = 1\n  AND ve.shares_released > 0\nORDER BY ve.vest_date;  -- FIFO: oldest lots first\n\n-- Gain per lot: (current_price - fmv_at_vest) × allocated_shares\n-- Tax: gain × (federal_rate + state_rate)\n-- Net proceeds: market_value - est_tax`" title="Liquidation Analysis" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showLiquidationSql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">If You Sold Today <InfoTooltip text="Estimates what you would net after taxes if you sold all sellable shares at the current price. Long-term lots (held >1 year) are taxed at lower capital gains rates; short-term lots at ordinary income rates. Losses generate a tax benefit.<br><br><strong>Source:</strong> FIFO lot allocation, current PTC price, assumed tax rates (see Assumptions section)." /></h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">
            Estimated tax impact on {{ fmt(summary.tax_lots.all.shares, 'number') }} sellable shares at {{ fmt(currentPrice) }}/sh
          </p>

          <!-- Long Term block -->
          <div class="rounded-lg border border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30 p-3 mb-3">
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2">
                <div class="w-2.5 h-2.5 rounded-full bg-green-500"></div>
                <span class="text-sm font-medium text-gray-900 dark:text-white">Long Term</span>
                <span class="text-xs text-gray-400">{{ fmt(summary.tax_lots.long_term.shares, 'number') }} shares</span>
              </div>
              <span class="text-xs text-gray-400">{{ fmt(summary.tax_lots.assumed_rates.ltcg * 100 + summary.tax_lots.assumed_rates.state * 100, 'number') }}% est. tax</span>
            </div>
            <div class="grid grid-cols-3 gap-2 text-xs">
              <div>
                <div class="text-gray-400">Market Value</div>
                <div class="font-medium text-gray-900 dark:text-white">{{ fmt(summary.tax_lots.long_term.market_value) }}</div>
              </div>
              <div>
                <div class="text-gray-400">Cost Basis</div>
                <div class="font-medium text-gray-600 dark:text-gray-400">{{ fmt(summary.tax_lots.long_term.cost_basis) }}</div>
              </div>
              <div>
                <div class="text-gray-400">Gain/Loss</div>
                <div class="font-medium" :class="summary.tax_lots.long_term.gain >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
                  {{ fmt(summary.tax_lots.long_term.gain) }}
                </div>
              </div>
            </div>
            <div class="mt-2 pt-2 border-t border-green-200 dark:border-green-900 grid grid-cols-2 gap-2 text-xs">
              <div>
                <div class="text-gray-400">{{ summary.tax_lots.long_term.est_tax >= 0 ? 'Est. Tax' : 'Tax Benefit' }}</div>
                <div class="font-medium" :class="summary.tax_lots.long_term.est_tax >= 0 ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
                  {{ summary.tax_lots.long_term.est_tax >= 0 ? `-${fmt(summary.tax_lots.long_term.est_tax)}` : `+${fmt(Math.abs(summary.tax_lots.long_term.est_tax))}` }}
                </div>
              </div>
              <div>
                <div class="text-gray-400 font-medium">Net Proceeds</div>
                <div class="font-bold text-green-700 dark:text-green-300 text-sm">{{ fmt(summary.tax_lots.long_term.net_proceeds) }}</div>
              </div>
            </div>
          </div>

          <!-- Short Term block -->
          <div class="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/30 p-3 mb-3">
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2">
                <div class="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
                <span class="text-sm font-medium text-gray-900 dark:text-white">Short Term</span>
                <span class="text-xs text-gray-400">{{ fmt(summary.tax_lots.short_term.shares, 'number') }} shares</span>
              </div>
              <span class="text-xs text-gray-400">{{ fmt(summary.tax_lots.assumed_rates.stcg * 100 + summary.tax_lots.assumed_rates.state * 100, 'number') }}% est. tax</span>
            </div>
            <div class="grid grid-cols-3 gap-2 text-xs">
              <div>
                <div class="text-gray-400">Market Value</div>
                <div class="font-medium text-gray-900 dark:text-white">{{ fmt(summary.tax_lots.short_term.market_value) }}</div>
              </div>
              <div>
                <div class="text-gray-400">Cost Basis</div>
                <div class="font-medium text-gray-600 dark:text-gray-400">{{ fmt(summary.tax_lots.short_term.cost_basis) }}</div>
              </div>
              <div>
                <div class="text-gray-400">Gain/Loss</div>
                <div class="font-medium" :class="summary.tax_lots.short_term.gain >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
                  {{ fmt(summary.tax_lots.short_term.gain) }}
                </div>
              </div>
            </div>
            <div class="mt-2 pt-2 border-t border-amber-200 dark:border-amber-900 grid grid-cols-2 gap-2 text-xs">
              <div>
                <div class="text-gray-400">{{ summary.tax_lots.short_term.est_tax >= 0 ? 'Est. Tax' : 'Tax Benefit' }}</div>
                <div class="font-medium" :class="summary.tax_lots.short_term.est_tax >= 0 ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
                  {{ summary.tax_lots.short_term.est_tax >= 0 ? `-${fmt(summary.tax_lots.short_term.est_tax)}` : `+${fmt(Math.abs(summary.tax_lots.short_term.est_tax))}` }}
                </div>
              </div>
              <div>
                <div class="text-gray-400 font-medium">Net Proceeds</div>
                <div class="font-bold text-amber-700 dark:text-amber-300 text-sm">{{ fmt(summary.tax_lots.short_term.net_proceeds) }}</div>
              </div>
            </div>
          </div>

          <!-- Total -->
          <div class="rounded-lg bg-gray-50 dark:bg-gray-800 p-3">
            <div class="flex items-center justify-between text-sm">
              <span class="font-medium text-gray-700 dark:text-gray-300">Total if sold</span>
              <span class="font-bold text-gray-900 dark:text-white text-base">{{ fmt(summary.tax_lots.all.net_proceeds) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs text-gray-400 mt-1">
              <span>
                {{ fmt(summary.tax_lots.all.market_value) }} market
                {{ summary.tax_lots.all.est_tax >= 0 ? '&minus;' : '+' }}
                {{ fmt(Math.abs(summary.tax_lots.all.est_tax)) }}
                {{ summary.tax_lots.all.est_tax >= 0 ? 'est. tax' : 'tax benefit' }}
              </span>
              <span>{{ fmt(summary.tax_lots.all.shares, 'number') }} shares</span>
            </div>
          </div>

          <!-- Assumptions -->
          <details class="mt-3">
            <summary class="text-[11px] text-gray-400 dark:text-gray-500 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400">
              Assumptions &amp; limitations
            </summary>
            <div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500 space-y-1.5 leading-relaxed">
              <p>
                <strong class="text-gray-500 dark:text-gray-400">Tax rates:</strong>
                Long-term gains taxed at {{ summary.tax_lots.assumed_rates.ltcg * 100 }}% federal +
                {{ summary.tax_lots.assumed_rates.state * 100 }}% state =
                {{ (summary.tax_lots.assumed_rates.ltcg + summary.tax_lots.assumed_rates.state) * 100 }}%.
                Short-term gains taxed at {{ summary.tax_lots.assumed_rates.stcg * 100 }}% federal +
                {{ summary.tax_lots.assumed_rates.state * 100 }}% state =
                {{ (summary.tax_lots.assumed_rates.stcg + summary.tax_lots.assumed_rates.state) * 100 }}% (ordinary income rate).
              </p>
              <p>
                <strong class="text-gray-500 dark:text-gray-400">Tax benefit on losses:</strong>
                Losses are valued at the same rate as gains for each category — long-term losses at
                {{ (summary.tax_lots.assumed_rates.ltcg + summary.tax_lots.assumed_rates.state) * 100 }}%,
                short-term losses at
                {{ (summary.tax_lots.assumed_rates.stcg + summary.tax_lots.assumed_rates.state) * 100 }}%.
                In reality, losses first offset same-type gains, then cross-type gains, and only up to $3K/yr of
                net losses can offset ordinary income. Actual benefit depends on your full capital gains picture for the year.
              </p>
              <p>
                <strong class="text-gray-500 dark:text-gray-400">Cost basis:</strong>
                Uses FMV at vest date (the price at which income was recognized). This is the correct cost basis for RSU shares.
              </p>
              <p>
                <strong class="text-gray-500 dark:text-gray-400">Lot allocation:</strong>
                Sellable shares are allocated to vest lots using FIFO (oldest lots first), matching E-Trade's default.
              </p>
            </div>
          </details>
        </div>

        <!-- Upcoming Vests -->
        <div class="group/upcoming relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showUpcomingVestsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/upcoming:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showUpcomingVestsSql" :sql="`-- Upcoming vest events\nSELECT\n  ve.vest_date,\n  ve.shares,\n  g.grant_date,\n  g.id AS grant_id,\n  ve.shares * sp.close_price AS est_value\nFROM vest_events ve\nJOIN rsu_grants g ON ve.grant_id = g.id\nCROSS JOIN (\n  SELECT close_price FROM stock_prices\n  WHERE symbol = 'PTC'\n  ORDER BY date DESC LIMIT 1\n) sp\nWHERE ve.is_actual = 0\n  AND ve.vest_date > date('now')\nORDER BY ve.vest_date;`" title="Upcoming Vests" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showUpcomingVestsSql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Upcoming Vests <InfoTooltip text="Future vest events from your active RSU grants. Shows the date, number of shares, and estimated value at current stock price. Days until vest shown as a countdown badge.<br><br><strong>Note:</strong> Estimated values will change as PTC stock price moves. Shares withheld for taxes (typically ~37-42%) are deducted at vesting." /></h2>
          <div v-if="Object.keys(upcomingByYear).length === 0" class="text-sm text-gray-400 italic">
            No upcoming vest events.
          </div>
          <div v-else class="space-y-4">
            <div v-for="(vests, year) in upcomingByYear" :key="year">
              <div class="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">{{ year }}</div>
              <div class="space-y-2">
                <div v-for="v in vests" :key="`${v.grant_id}-${v.vest_date}`"
                  class="flex items-center justify-between py-1.5 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
                  <div>
                    <span class="text-gray-700 dark:text-gray-300 font-medium">{{ fmtDate(v.vest_date) }}</span>
                    <span class="text-xs ml-1.5 px-1.5 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-medium">{{ daysUntil(v.vest_date) }}d</span>
                    <span class="text-gray-400 ml-2 text-xs">Grant {{ v.grant_date?.substring(0, 4) }}</span>
                  </div>
                  <div class="text-right">
                    <span class="font-medium text-gray-900 dark:text-white">{{ v.shares }} shares</span>
                    <span class="text-xs text-gray-400 ml-1">&asymp;{{ fmt(v.est_value) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Vesting Income by Year -->
      <div class="group/vestincome relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showVestingIncomeSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/vestincome:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showVestingIncomeSql" :sql="`-- Vest event value by year\nSELECT\n  strftime('%Y', ve.vest_date) AS year,\n  SUM(ve.shares * COALESCE(ve.fmv_at_vest, sp.close_price)) AS value,\n  SUM(CASE WHEN ve.is_actual = 1 THEN ve.shares * ve.fmv_at_vest ELSE 0 END) AS actual,\n  SUM(CASE WHEN ve.is_actual = 0 THEN ve.shares * sp.close_price ELSE 0 END) AS projected\nFROM vest_events ve\nJOIN rsu_grants g ON ve.grant_id = g.id\nCROSS JOIN (\n  SELECT close_price FROM stock_prices\n  WHERE symbol = 'PTC'\n  ORDER BY date DESC LIMIT 1\n) sp\nGROUP BY strftime('%Y', ve.vest_date)\nORDER BY year;`" title="Vest Event Value by Year" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showVestingIncomeSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Vest Event Value by Year <InfoTooltip text="Total value of shares that vested (or will vest) each year, calculated as shares × FMV at vest date for past events, or shares × current price for future events. May differ from W2 RSU income due to employer payroll adjustments.<br><br><strong>Source:</strong> Vest events table. Actual years use recorded FMV; projected years use current PTC price." /></h2>
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">Shares &times; FMV at each vest date. May differ from W2 RSU income due to employer adjustments and tax lot accounting — see the Income page for W2-based figures.</p>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <div v-for="(entry, year) in summary.vesting_income_by_year" :key="year"
            class="text-center py-2 px-1 rounded-lg"
            :class="(entry.is_projected || entry.is_mixed) ? 'bg-gray-50 dark:bg-gray-800' : ''">
            <div class="text-xs font-mono mb-1" :class="entry.is_projected ? 'text-gray-400 dark:text-gray-500' : 'text-gray-500 dark:text-gray-400'">{{ year }}</div>
            <div class="text-sm font-semibold" :class="entry.is_projected ? 'text-gray-400 dark:text-gray-500' : 'text-gray-900 dark:text-white'">
              {{ fmt(entry.value) }}
            </div>
            <div v-if="entry.is_mixed" class="text-[10px] mt-0.5">
              <span class="text-gray-500 dark:text-gray-400">{{ fmt(entry.actual) }}</span>
              <span class="text-gray-400 dark:text-gray-500"> + {{ fmt(entry.projected) }} est</span>
            </div>
            <div v-else-if="entry.is_projected" class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">projected</div>
          </div>
        </div>
      </div>

      <!-- Grants List -->
      <div class="group/grants relative">
        <button @click="showGrantsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/grants:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all z-10" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showGrantsSql" :sql="`-- All RSU grants with vest details\nSELECT\n  g.id,\n  g.grant_date,\n  g.total_shares,\n  g.vested_shares,\n  g.unvested_shares,\n  g.sellable_shares,\n  g.sellable_shares * sp.close_price AS sellable_value,\n  (g.sellable_shares + g.unvested_shares) * sp.close_price AS held_value\nFROM rsu_grants g\nCROSS JOIN (\n  SELECT close_price FROM stock_prices\n  WHERE symbol = 'PTC'\n  ORDER BY date DESC LIMIT 1\n) sp\nORDER BY g.unvested_shares DESC, g.grant_date DESC;\n\n-- Vest events per grant\nSELECT\n  ve.grant_id,\n  ve.vest_date,\n  ve.shares,\n  ve.shares_withheld,\n  ve.shares_released,\n  ve.fmv_at_vest,\n  ve.total_taxes_paid,\n  ve.is_actual,\n  CASE\n    WHEN ve.vest_date <= date('now', '-1 year') THEN 'Long Term'\n    ELSE 'Short Term'\n  END AS tax_status\nFROM vest_events ve\nORDER BY ve.vest_date;`" title="All Grants &amp; Vest Events" :tables="['rsu_grants', 'vest_events', 'stock_prices']" @close="showGrantsSql = false" />
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">All Grants ({{ grants.length }}) <InfoTooltip text="Every RSU grant from E-Trade, sorted with unvested grants first. The progress ring shows what percentage of the grant has vested. Click any grant to see individual vest event details including cost basis, tax paid, and holding period status.<br><br><strong>Source:</strong> E-Trade &quot;Download by Type (expanded)&quot; spreadsheet export via the RSU data loader." /></h2>
          <p class="text-xs text-gray-400">
            Upload: E-Trade &rarr; Holdings &rarr; Download by Type (expanded) + Download by Status (expanded)
          </p>
        </div>
        <div class="space-y-2">
          <div v-for="grant in sortedGrants" :key="grant.id"
            class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
            <!-- Grant header -->
            <button @click="toggleGrant(grant.id)"
              class="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <!-- Vesting progress ring -->
              <div class="relative w-10 h-10 flex-shrink-0">
                <svg class="w-10 h-10 -rotate-90" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15" fill="none" stroke-width="3"
                    class="stroke-gray-100 dark:stroke-gray-800" />
                  <circle cx="18" cy="18" r="15" fill="none" stroke-width="3"
                    stroke-linecap="round"
                    :class="vestProgress(grant) === 100 ? 'stroke-green-500' : 'stroke-indigo-500'"
                    :stroke-dasharray="`${vestProgress(grant) * 0.9425} 94.25`" />
                </svg>
                <span class="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gray-600 dark:text-gray-400">
                  {{ vestProgress(grant) }}%
                </span>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-medium text-gray-900 dark:text-white text-sm">
                    Grant #{{ grant.id }}
                  </span>
                  <span class="text-xs text-gray-400">{{ fmtDate(grant.grant_date) }}</span>
                  <span v-if="grant.unvested_shares > 0"
                    class="text-xs px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300">
                    {{ grant.unvested_shares }} unvested
                  </span>
                  <span v-else
                    class="text-xs px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300">
                    Fully vested
                  </span>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {{ grant.total_shares }} shares &middot;
                  {{ grant.sellable_shares || 0 }} sellable
                </div>
              </div>

              <div class="text-right">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ fmt(grant.held_value) }}</div>
                <div v-if="grant.sellable_value" class="text-xs text-green-600 dark:text-green-400">{{ fmt(grant.sellable_value) }} sellable</div>
              </div>

              <span class="text-gray-400 text-xs ml-2">{{ expandedGrant === grant.id ? '▲' : '▼' }}</span>
            </button>

            <!-- Vest events detail -->
            <div v-if="expandedGrant === grant.id" class="border-t border-gray-100 dark:border-gray-800">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-gray-500 dark:text-gray-400 border-b border-gray-50 dark:border-gray-800">
                    <th class="text-left px-5 py-2 font-medium">Vest Date</th>
                    <th class="text-right px-3 py-2 font-medium">Shares</th>
                    <th class="text-right px-3 py-2 font-medium">Withheld</th>
                    <th class="text-right px-3 py-2 font-medium">Released</th>
                    <th class="text-right px-3 py-2 font-medium">Cost Basis/sh</th>
                    <th class="text-right px-3 py-2 font-medium">Gain/sh</th>
                    <th class="text-right px-3 py-2 font-medium">Tax Paid</th>
                    <th class="text-center px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ve in grant.vest_events" :key="ve.id"
                    :class="ve.is_actual ? '' : 'text-gray-400 dark:text-gray-500 italic'"
                    class="border-b border-gray-50 dark:border-gray-800 last:border-0">
                    <td class="px-5 py-2.5 font-medium" :class="ve.is_actual ? 'text-gray-900 dark:text-white' : ''">
                      {{ fmtDate(ve.vest_date) }}
                    </td>
                    <td class="text-right px-3 py-2.5">{{ ve.shares }}</td>
                    <td class="text-right px-3 py-2.5">{{ ve.shares_withheld ?? '--' }}</td>
                    <td class="text-right px-3 py-2.5">{{ ve.shares_released ?? '--' }}</td>
                    <td class="text-right px-3 py-2.5">{{ ve.fmv_at_vest ? `$${ve.fmv_at_vest.toFixed(2)}` : '--' }}</td>
                    <td class="text-right px-3 py-2.5" :class="ve.gain_per_share != null ? (ve.gain_per_share >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400') : ''">
                      {{ ve.gain_per_share != null ? `${ve.gain_per_share >= 0 ? '+' : ''}$${ve.gain_per_share.toFixed(2)}` : '--' }}
                    </td>
                    <td class="text-right px-3 py-2.5">{{ ve.total_taxes_paid ? fmt(ve.total_taxes_paid) : '--' }}</td>
                    <td class="text-center px-3 py-2.5">
                      <span v-if="!ve.is_actual" class="px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500">Future</span>
                      <span v-else-if="ve.tax_status === 'Long Term'" class="px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300">Long</span>
                      <span v-else class="px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300">Short</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </template>

    <DataExplorer />
  </div>
</template>
