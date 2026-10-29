<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { useImportModal } from '../composables/useImportModal'
import { useDataExplorer } from '../composables/useDataExplorer'
import { deriveSymbol, upcomingVests, groupByYear, daysUntil } from '../composables/useRsuHelpers'
import DataExplorer from '../components/common/DataExplorer.vue'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { api } from '../api/client'
import type { RSUGrantDetail, RSUSummary, PricePoint } from '../types'

use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

const { baseOption, COLORS, isMobile, axisLineColor, splitLineColor, mobileAxis } = useChartDefaults()
const { money, compact, number, date: fmtDate, percent, dash } = useFormatters()
const { openImport } = useImportModal()
const { openData } = useDataExplorer()

const summary = ref<RSUSummary | null>(null)
const grants = ref<RSUGrantDetail[]>([])
const currentPrice = ref<number | null>(null)
const symbol = ref<string | null>(null)
const loading = ref(true)
const error = ref('')
const expandedGrant = ref<string | null>(null)
const priceHistory = ref<PricePoint[]>([])
const priceError = ref('')
const priceLoading = ref(false)

const showLiquidationSql = ref(false)
const showUpcomingVestsSql = ref(false)
const showVestingIncomeSql = ref(false)
const showGrantsSql = ref(false)

const ETRADE_URL = 'https://us.etrade.com/etx/sp/stockplan?accountIndex=0&traxui=tsp_accountshome#/holdings'

async function loadPriceHistory(sym: string) {
  priceLoading.value = true
  priceError.value = ''
  try {
    const data = await api.rsu.getPriceHistory(sym, '5y')
    priceHistory.value = data.points || []
  } catch (e: any) {
    priceHistory.value = []
    priceError.value = e.message || 'Price history unavailable'
  } finally {
    priceLoading.value = false
  }
}

async function fetchData() {
  try {
    const [sum, grantData] = await Promise.all([api.rsu.getSummary(), api.rsu.getGrants()])
    summary.value = sum
    grants.value = grantData.grants || []
    currentPrice.value = grantData.current_price
    // The symbol always comes from the grants (never a hard-coded ticker), and is refreshed after import.
    symbol.value = deriveSymbol(grants.value, grantData.symbol || sum.symbol)
    error.value = ''
    if (symbol.value) await loadPriceHistory(symbol.value)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

function toggleGrant(id: string) {
  expandedGrant.value = expandedGrant.value === id ? null : id
}

const upcoming = computed(() => upcomingVests(summary.value?.upcoming_vests || []))
const upcomingByYear = computed(() => groupByYear(upcoming.value))
const lots = computed(() => summary.value?.tax_lots)
const unallocated = computed(() => lots.value?.unallocated_sellable_shares || 0)
const ratePct = (r: number) => `${Math.round(r * 100)}%`

const sortedGrants = computed(() =>
  [...grants.value].sort((a, b) => {
    const aU = a.unvested_shares || 0
    const bU = b.unvested_shares || 0
    if (aU > 0 && bU === 0) return -1
    if (aU === 0 && bU > 0) return 1
    return (b.grant_date || '').localeCompare(a.grant_date || '')
  }),
)

function vestProgress(grant: RSUGrantDetail): number {
  if (!grant.total_shares) return 0
  return Math.round(((grant.vested_shares || 0) / grant.total_shares) * 100)
}

// ── "View SQL" (Postgres) ──
const sym = computed(() => symbol.value || 'SYMBOL')
const summarySql = computed(() => `-- Share counts; values are shares × today's price from stock_prices
SELECT SUM(sellable_shares) AS sellable_shares,
       SUM(unvested_shares) AS unvested_shares,
       SUM(sellable_shares + unvested_shares) AS held_shares
FROM rsu_grants;

SELECT close_price FROM stock_prices
WHERE symbol = '${sym.value}' ORDER BY price_date DESC LIMIT 1;`)
const priceChartSql = computed(() => `-- Weekly closes come from Yahoo Finance (cached six hours); vest marks from vest_events
SELECT ve.vest_date, ve.fmv_at_vest
FROM vest_events ve
JOIN rsu_grants g ON ve.grant_id = g.id
WHERE ve.is_actual
ORDER BY ve.vest_date;`)
const liquidationSql = `-- Sellable shares allocated FIFO to actual vest lots (oldest first)
SELECT ve.grant_id, ve.vest_date, ve.shares_released, ve.fmv_at_vest AS cost_basis_per_share,
       CASE WHEN ve.vest_date <= CURRENT_DATE - INTERVAL '366 days' THEN 'Long Term' ELSE 'Short Term' END AS tax_status
FROM vest_events ve
WHERE ve.is_actual AND ve.shares_released > 0
ORDER BY ve.grant_id, ve.vest_date;
-- gain = (current price − fmv_at_vest) × lot shares; tax = gain × (federal rate + state rate)`
const upcomingSql = computed(() => `SELECT ve.vest_date, ve.shares, g.grant_date, g.id AS grant_id,
       ve.shares * sp.close_price AS est_value
FROM vest_events ve
JOIN rsu_grants g ON ve.grant_id = g.id
CROSS JOIN (SELECT close_price FROM stock_prices WHERE symbol = '${sym.value}' ORDER BY price_date DESC LIMIT 1) sp
WHERE NOT ve.is_actual AND ve.vest_date >= CURRENT_DATE
ORDER BY ve.vest_date;`)
const vestingIncomeSql = computed(() => `SELECT EXTRACT(YEAR FROM ve.vest_date) AS year,
       SUM(CASE WHEN ve.is_actual THEN ve.shares * ve.fmv_at_vest ELSE 0 END) AS actual,
       SUM(CASE WHEN NOT ve.is_actual THEN ve.shares * sp.close_price ELSE 0 END) AS projected
FROM vest_events ve
CROSS JOIN (SELECT close_price FROM stock_prices WHERE symbol = '${sym.value}' ORDER BY price_date DESC LIMIT 1) sp
GROUP BY 1 ORDER BY 1;`)
const grantsSql = `SELECT g.id, g.symbol, g.grant_date, g.total_shares, g.vested_shares, g.unvested_shares, g.sellable_shares
FROM rsu_grants g
ORDER BY g.unvested_shares DESC, g.grant_date DESC;

SELECT ve.grant_id, ve.vest_date, ve.shares, ve.shares_withheld, ve.shares_released, ve.fmv_at_vest, ve.total_taxes_paid, ve.is_actual
FROM vest_events ve
ORDER BY ve.vest_date;`

// ── Price chart ──
const priceChartOption = computed(() => {
  const dates = priceHistory.value.map(p => p.date)
  const prices = priceHistory.value.map(p => p.price)
  const minDate = dates[0] || ''
  const markLines = grants.value
    .flatMap(g => g.vest_events || [])
    .filter(ve => ve.is_actual && ve.vest_date && ve.vest_date >= minDate)
    .map(ve => ({ xAxis: ve.vest_date as string, label: { show: false }, lineStyle: { color: COLORS[5], width: 1, type: 'dashed' as const } }))

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        return `<strong>${p.name}</strong><br/>${money(p.value, { cents: true })}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: {
        ...mobileAxis(),
        formatter: (v: string) => v.slice(0, 4),
        interval: (index: number) => index === 0 || dates[index]?.slice(0, 4) !== dates[index - 1]?.slice(0, 4),
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => `$${v}` },
      splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } },
    },
    series: [{
      type: 'line',
      data: prices,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: COLORS[0] },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.15)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
      markLine: markLines.length > 0 ? { silent: true, symbol: 'none', data: markLines } : undefined,
    }],
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6 min-w-0">
    <PageHeader
      title="RSU Holdings"
      :subtitle="symbol ? `${symbol} · ${currentPrice ? money(currentPrice, { cents: true }) + '/share' : 'price unavailable'}` : 'Company stock grants and vests'"
      tooltip="<strong>RSU Holdings</strong><br>Grants and vest events come from the E-Trade export (Import button). Share values use the grants' own ticker at today's Yahoo Finance price, cached once a day."
    >
      <a :href="ETRADE_URL" target="_blank" rel="noopener" class="min-h-10 inline-flex items-center text-xs text-indigo-600 dark:text-indigo-400 hover:underline px-1">E-Trade Holdings</a>
      <button @click="openData('rsu')" class="min-h-10 px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">Data</button>
      <button @click="openImport({ context: 'rsu', onComplete: fetchData })" class="min-h-10 px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Import</button>
    </PageHeader>

    <div v-if="loading" class="text-sm text-gray-400">Loading RSU data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>

    <div v-else-if="!summary || (!grants.length && !summary.held_shares)" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No RSU data yet.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Use Import with your E-Trade vesting schedule export (.xlsx) to get started.</p>
    </div>

    <template v-else>
      <!-- Tiles -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Holdings" :value="compact(summary.held_value)" :subtitle="`${number(summary.sellable_shares)} sellable + ${number(summary.unvested_shares)} unvested`"
          :info="`<strong>Holdings</strong><br>Market value of the ${symbol} shares you hold or will receive: sellable (vested, in your account) plus unvested (scheduled to vest).<br><br><strong>Formula:</strong> (sellable + unvested shares) × today's price.`"
          :sql="summarySql" :sql-tables="['rsu_grants', 'stock_prices']" />
        <MetricCard label="Sellable" :value="compact(summary.sellable_value)" :subtitle="`${number(summary.sellable_shares)} shares`"
          info="<strong>Sellable</strong><br>Vested shares available to sell now, net of shares withheld for tax at vest.<br><br><strong>Source:</strong> rsu_grants.sellable_shares from the E-Trade export." />
        <MetricCard label="Unvested" :value="compact(summary.unvested_value)" :subtitle="`${number(summary.unvested_shares)} shares`"
          info="<strong>Unvested</strong><br>Granted shares that have not vested yet, valued at today's price. The value at vest will be whatever the stock is worth then.<br><br><strong>Source:</strong> rsu_grants.unvested_shares." />
        <MetricCard label="Unrealized Gain" :value="compact(lots?.all.gain)" :subtitle="`Cost basis ${compact(lots?.all.cost_basis)} on ${number(lots?.all.shares)} lot shares`"
          info="<strong>Unrealized gain</strong><br>(today's price − FMV at vest) × shares, over the sellable shares that could be matched to an actual vest lot (FIFO). Shares without a lot are listed under If You Sold Today." />
      </div>

      <!-- Price chart -->
      <ChartContainer :title="`${symbol} Stock Price`" subtitle="5-year weekly closes · dashed lines are vest dates"
        :info="`Weekly closing price of ${symbol} for the last five years from Yahoo Finance (cached six hours). Dashed vertical lines mark the dates your shares vested, so you can see whether they vested at good or bad prices.`"
        :sql="priceChartSql" :sql-tables="['stock_prices', 'vest_events', 'rsu_grants']"
        :loading="priceLoading" :empty="!priceLoading && priceHistory.length === 0"
        :empty-text="priceError ? `Price history unavailable: ${priceError}` : 'No price history for this symbol'">
        <v-chart :option="priceChartOption" :style="{ height: isMobile ? '220px' : '250px' }" autoresize />
      </ChartContainer>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- If you sold today -->
        <div class="group/liq relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
          <button @click="showLiquidationSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/liq:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all" title="View SQL" aria-label="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showLiquidationSql" :sql="liquidationSql" title="If You Sold Today" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showLiquidationSql = false" />
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1 pr-8">If You Sold Today <InfoTooltip text="What you would net after estimated tax if you sold the matched sellable shares at today's price. Lots held more than a year are taxed at the long-term rate, the rest at the short-term (ordinary income) rate; losses are valued as a tax benefit at the same rate.<br><br><strong>Source:</strong> FIFO allocation of sellable shares to actual vest lots; rates are deployment settings (see Assumptions)." /></h3>
          <p v-if="lots" class="text-xs text-gray-400 dark:text-gray-500 mb-1">
            Estimated tax impact on {{ number(lots.all.shares) }} lot shares at {{ money(currentPrice, { cents: true }) }}/sh
          </p>
          <p v-if="unallocated > 0" class="text-xs text-amber-600 dark:text-amber-400 mb-3">
            {{ number(unallocated) }} sellable shares are not matched to a vest lot and are not included.
          </p>
          <p v-else class="mb-3"></p>

          <template v-if="lots">
            <div v-for="block in [
                { key: 'long_term', name: 'Long Term', agg: lots.long_term, rate: lots.assumed_rates.ltcg + lots.assumed_rates.state, cls: 'green' },
                { key: 'short_term', name: 'Short Term', agg: lots.short_term, rate: lots.assumed_rates.stcg + lots.assumed_rates.state, cls: 'amber' },
              ]" :key="block.key"
              class="rounded-lg border p-3 mb-3"
              :class="block.cls === 'green' ? 'border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30' : 'border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/30'">
              <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="block.cls === 'green' ? 'bg-green-500' : 'bg-amber-500'"></span>
                  <span class="text-sm font-medium text-gray-900 dark:text-white">{{ block.name }}</span>
                  <span class="text-xs text-gray-400 whitespace-nowrap">{{ number(block.agg.shares) }} shares</span>
                </div>
                <span class="text-xs text-gray-400 whitespace-nowrap">{{ ratePct(block.rate) }} est. tax</span>
              </div>
              <div class="grid grid-cols-3 gap-2 text-xs">
                <div><div class="text-gray-400">Market Value</div><div class="font-medium text-gray-900 dark:text-white">{{ compact(block.agg.market_value) }}</div></div>
                <div><div class="text-gray-400">Cost Basis</div><div class="font-medium text-gray-600 dark:text-gray-400">{{ compact(block.agg.cost_basis) }}</div></div>
                <div><div class="text-gray-400">Gain/Loss</div><div class="font-medium" :class="block.agg.gain >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">{{ compact(block.agg.gain) }}</div></div>
              </div>
              <div class="mt-2 pt-2 border-t grid grid-cols-2 gap-2 text-xs" :class="block.cls === 'green' ? 'border-green-200 dark:border-green-900' : 'border-amber-200 dark:border-amber-900'">
                <div>
                  <div class="text-gray-400">{{ block.agg.est_tax >= 0 ? 'Est. Tax' : 'Tax Benefit' }}</div>
                  <div class="font-medium" :class="block.agg.est_tax >= 0 ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ block.agg.est_tax >= 0 ? '-' : '+' }}{{ compact(Math.abs(block.agg.est_tax)) }}</div>
                </div>
                <div>
                  <div class="text-gray-400 font-medium">Net Proceeds</div>
                  <div class="font-bold text-sm" :class="block.cls === 'green' ? 'text-green-700 dark:text-green-300' : 'text-amber-700 dark:text-amber-300'">{{ compact(block.agg.net_proceeds) }}</div>
                </div>
              </div>
            </div>

            <div class="rounded-lg bg-gray-50 dark:bg-gray-800 p-3">
              <div class="flex items-center justify-between text-sm gap-2">
                <span class="font-medium text-gray-700 dark:text-gray-300">Total if sold</span>
                <span class="font-bold text-gray-900 dark:text-white text-base">{{ compact(lots.all.net_proceeds) }}</span>
              </div>
              <div class="flex items-center justify-between text-xs text-gray-400 mt-1 gap-2 flex-wrap">
                <span>{{ compact(lots.all.market_value) }} market {{ lots.all.est_tax >= 0 ? '−' : '+' }} {{ compact(Math.abs(lots.all.est_tax)) }} {{ lots.all.est_tax >= 0 ? 'est. tax' : 'tax benefit' }}</span>
                <span>{{ number(lots.all.shares) }} shares</span>
              </div>
            </div>

            <details class="mt-3">
              <summary class="text-[11px] text-gray-400 dark:text-gray-500 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 min-h-10 flex items-center">Assumptions &amp; limitations</summary>
              <div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500 space-y-1.5 leading-relaxed">
                <p><strong class="text-gray-500 dark:text-gray-400">Tax rates</strong> (settings FINANCE_LTCG_RATE, FINANCE_STCG_RATE, FINANCE_STATE_TAX_RATE): long-term {{ ratePct(lots.assumed_rates.ltcg) }} federal + {{ ratePct(lots.assumed_rates.state) }} state; short-term {{ ratePct(lots.assumed_rates.stcg) }} federal + {{ ratePct(lots.assumed_rates.state) }} state.</p>
                <p><strong class="text-gray-500 dark:text-gray-400">Losses</strong> are valued at the same rate as gains. In reality losses first offset same-type gains, then other gains, and only $3K/yr of net loss offsets ordinary income.</p>
                <p><strong class="text-gray-500 dark:text-gray-400">Cost basis</strong> is FMV at vest (the price at which the income was taxed), which is correct for RSUs.</p>
                <p><strong class="text-gray-500 dark:text-gray-400">Lots</strong>: sellable shares are allocated to actual vest lots oldest-first (FIFO). Sellable shares the vest events cannot account for are reported above and left out rather than guessed.</p>
              </div>
            </details>
          </template>
        </div>

        <!-- Upcoming vests -->
        <div class="group/up relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
          <button @click="showUpcomingVestsSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/up:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all" title="View SQL" aria-label="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showUpcomingVestsSql" :sql="upcomingSql" title="Upcoming Vests" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showUpcomingVestsSql = false" />
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3 pr-8">Upcoming Vests <InfoTooltip :text="`Vest events dated today or later from your grants: date, shares and estimated value at today's ${symbol} price. Shares withheld for tax at vest will reduce what lands in your account.`" /></h3>
          <div v-if="upcoming.length === 0" class="text-sm text-gray-400 italic">No upcoming vest events.</div>
          <div v-else class="space-y-4">
            <div v-for="(vests, year) in upcomingByYear" :key="year">
              <div class="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">{{ year }}</div>
              <div class="space-y-2">
                <div v-for="v in vests" :key="`${v.grant_id}-${v.vest_date}`" class="flex items-center justify-between gap-3 py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm min-w-0">
                  <div class="min-w-0 flex items-center gap-2 flex-wrap">
                    <span class="text-gray-700 dark:text-gray-300 font-medium whitespace-nowrap">{{ fmtDate(v.vest_date) }}</span>
                    <span class="text-xs px-1.5 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-medium whitespace-nowrap">{{ daysUntil(v.vest_date) }}d</span>
                    <span class="text-gray-400 text-xs whitespace-nowrap">Grant {{ v.grant_date?.slice(0, 4) || v.grant_id }}</span>
                  </div>
                  <div class="text-right flex-shrink-0 whitespace-nowrap">
                    <span class="font-medium text-gray-900 dark:text-white">{{ number(v.shares) }} sh</span>
                    <span class="text-xs text-gray-400 ml-1">≈{{ compact(v.est_value) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Vest value by year -->
      <div class="group/vy relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
        <button @click="showVestingIncomeSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/vy:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showVestingIncomeSql" :sql="vestingIncomeSql" title="Vest Event Value by Year" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showVestingIncomeSql = false" />
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1 pr-8">Vest Event Value by Year <InfoTooltip :text="`Shares × FMV at vest for events that have happened, shares × today's ${symbol} price for scheduled ones. Can differ from W-2 RSU income because of payroll timing; the Income page has the W-2 figures.`" /></h3>
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">Actual years use the recorded FMV; grey years are projected at today's price.</p>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <div v-for="(entry, year) in summary.vesting_income_by_year" :key="year" class="text-center py-2 px-1 rounded-lg min-w-0" :class="(entry.is_projected || entry.is_mixed) ? 'bg-gray-50 dark:bg-gray-800' : ''">
            <div class="text-xs font-mono mb-1" :class="entry.is_projected ? 'text-gray-400 dark:text-gray-500' : 'text-gray-500 dark:text-gray-400'">{{ year }}</div>
            <div class="text-sm font-semibold truncate" :class="entry.is_projected ? 'text-gray-400 dark:text-gray-500' : 'text-gray-900 dark:text-white'">{{ compact(entry.value) }}</div>
            <div v-if="entry.is_mixed" class="text-[10px] mt-0.5 truncate"><span class="text-gray-500 dark:text-gray-400">{{ compact(entry.actual) }}</span><span class="text-gray-400 dark:text-gray-500"> + {{ compact(entry.projected) }} est</span></div>
            <div v-else-if="entry.is_projected" class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">projected</div>
          </div>
        </div>
      </div>

      <!-- Grants -->
      <div class="group/grants relative min-w-0">
        <button @click="showGrantsSql = true" class="sql-btn absolute top-0 right-0 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/grants:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all z-10" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showGrantsSql" :sql="grantsSql" title="All Grants &amp; Vest Events" :tables="['rsu_grants', 'vest_events']" @close="showGrantsSql = false" />
        <div class="flex flex-wrap items-baseline justify-between gap-2 mb-3 pr-10">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">All Grants ({{ grants.length }}) <InfoTooltip text="Every RSU grant, unvested first. The ring is the share of the grant that has vested. Open a grant to see each vest event with its cost basis, tax paid and holding period.<br><br><strong>Source:</strong> the E-Trade vesting schedule export, loaded with the Import button." /></h3>
          <p class="text-xs text-gray-400">Update with Import → E-Trade “Download by Type (expanded)” .xlsx</p>
        </div>
        <div class="space-y-2">
          <div v-for="grant in sortedGrants" :key="grant.id" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden min-w-0">
            <button @click="toggleGrant(grant.id)" class="w-full text-left px-4 sm:px-5 py-4 flex items-center gap-3 sm:gap-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors min-w-0" :aria-expanded="expandedGrant === grant.id">
              <div class="relative w-10 h-10 flex-shrink-0">
                <svg class="w-10 h-10 -rotate-90" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15" fill="none" stroke-width="3" class="stroke-gray-100 dark:stroke-gray-800" />
                  <circle cx="18" cy="18" r="15" fill="none" stroke-width="3" stroke-linecap="round" :class="vestProgress(grant) === 100 ? 'stroke-green-500' : 'stroke-indigo-500'" :stroke-dasharray="`${vestProgress(grant) * 0.9425} 94.25`" />
                </svg>
                <span class="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gray-600 dark:text-gray-400">{{ vestProgress(grant) }}%</span>
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-medium text-gray-900 dark:text-white text-sm whitespace-nowrap">Grant #{{ grant.id }}</span>
                  <span class="text-xs text-gray-400 whitespace-nowrap">{{ fmtDate(grant.grant_date) }}</span>
                  <span v-if="(grant.unvested_shares || 0) > 0" class="text-xs px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 whitespace-nowrap">{{ grant.unvested_shares }} unvested</span>
                  <span v-else class="text-xs px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300 whitespace-nowrap">Fully vested</span>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">{{ grant.total_shares }} shares · {{ grant.sellable_shares || 0 }} sellable</div>
              </div>
              <div class="text-right flex-shrink-0 whitespace-nowrap">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ compact(grant.held_value) }}</div>
                <div v-if="grant.sellable_value" class="text-xs text-green-600 dark:text-green-400">{{ compact(grant.sellable_value) }} sellable</div>
              </div>
              <span class="text-gray-400 text-xs ml-1 flex-shrink-0">{{ expandedGrant === grant.id ? '▲' : '▼' }}</span>
            </button>
            <div v-if="expandedGrant === grant.id" class="border-t border-gray-100 dark:border-gray-800 px-4 sm:px-5 pb-2">
              <DataTable dense :columns="8" :empty="!grant.vest_events?.length" empty-text="No vest events">
                <thead>
                  <tr>
                    <th>Vest Date</th><th class="text-right">Shares</th><th class="text-right">Withheld</th><th class="text-right">Released</th>
                    <th class="text-right">Cost Basis/sh</th><th class="text-right">Gain/sh</th><th class="text-right">Tax Paid</th><th class="text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ve in grant.vest_events" :key="ve.id" :class="ve.is_actual ? '' : 'text-gray-400 dark:text-gray-500 italic'" class="text-xs">
                    <td class="font-medium whitespace-nowrap" :class="ve.is_actual ? 'text-gray-900 dark:text-white' : ''">{{ fmtDate(ve.vest_date) }}</td>
                    <td class="text-right">{{ ve.shares }}</td>
                    <td class="text-right">{{ ve.shares_withheld ?? dash }}</td>
                    <td class="text-right">{{ ve.shares_released ?? dash }}</td>
                    <td class="text-right whitespace-nowrap">{{ ve.fmv_at_vest ? money(ve.fmv_at_vest, { cents: true }) : dash }}</td>
                    <td class="text-right whitespace-nowrap" :class="ve.gain_per_share != null ? (ve.gain_per_share >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400') : ''">{{ ve.gain_per_share != null ? `${ve.gain_per_share >= 0 ? '+' : ''}${money(ve.gain_per_share, { cents: true })}` : dash }}</td>
                    <td class="text-right whitespace-nowrap">{{ ve.total_taxes_paid ? compact(ve.total_taxes_paid) : dash }}</td>
                    <td class="text-center">
                      <span v-if="!ve.is_actual" class="px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500">Future</span>
                      <span v-else-if="ve.tax_status === 'Long Term'" class="px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300">Long</span>
                      <span v-else class="px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300">Short</span>
                    </td>
                  </tr>
                </tbody>
              </DataTable>
            </div>
          </div>
        </div>
        <p class="sr-only">{{ percent(0) }}</p>
      </div>
    </template>

    <DataExplorer />
  </div>
</template>

<style scoped>
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
