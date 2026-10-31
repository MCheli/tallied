<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, LineChart, BarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import DataExplorer from '../components/common/DataExplorer.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { useImportModal } from '../composables/useImportModal'
import { useDataExplorer } from '../composables/useDataExplorer'
import { apiErrorMessage } from '../composables/useApiError'
import { equityComposition, purchasePriceFromHistory } from '../composables/useEquityPosition'
import { api } from '../api/client'
import type { AmortizationResponse, PropertySummary, PropertyValuePoint, ValuationSourceLabel } from '../types'

use([PieChart, LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent, CanvasRenderer])

const { baseOption, COLORS, isDark, isMobile, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend } = useChartDefaults()
const { money, compact, percent, date: fmtDate, monthYear, dash } = useFormatters()
const { openImport } = useImportModal()
const { openData } = useDataExplorer()

// ── State ──
const loading = ref(true)
const error = ref('')
const summary = ref<PropertySummary | null>(null)
const amortization = ref<AmortizationResponse | null>(null)
const amortizationError = ref('')

const valueHistory = ref<PropertyValuePoint[]>([])
const valueCommentary = ref<string | null>(null)
const valuePropertyDetails = ref<Record<string, unknown> | null>(null)
const projectionNote = ref<string | null>(null)
const historyError = ref('')
const refreshing = ref(false)

// Add Entry form
const showManualEntry = ref(false)
const newValuation = ref('')
const valuationSource = ref<ValuationSourceLabel>('Manual')
const valuationDate = ref(new Date().toISOString().slice(0, 10))
const savingValuation = ref(false)
const valuationError = ref('')

// Inline purchase-price control (Equity Position)
const purchaseInput = ref('')
const savingPurchase = ref(false)
const purchaseError = ref('')

const showEquityPositionSql = ref(false)

// ── SQL (Postgres; what the endpoints compute) ──
const SQL = {
  propertyValue: `SELECT pv.value, pv.valuation_date, pv.source
FROM property_valuations pv
JOIN accounts a ON a.id = pv.account_id
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC, pv.id DESC
LIMIT 1;`,
  mortgageBalance: `SELECT current_balance, original_amount, updated_at
FROM mortgages
ORDER BY updated_at DESC
LIMIT 1;`,
  equity: `-- equity = latest valuation - mortgage balance
SELECT pv.value AS property_value,
       m.current_balance AS mortgage_balance,
       pv.value - m.current_balance AS equity
FROM property_valuations pv
JOIN accounts a ON a.id = pv.account_id
CROSS JOIN (SELECT current_balance FROM mortgages ORDER BY updated_at DESC LIMIT 1) m
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC, pv.id DESC
LIMIT 1;`,
  interestRate: `SELECT rate, origination_date, original_payoff_date
FROM mortgages
ORDER BY updated_at DESC
LIMIT 1;`,
  monthlyPayment: `SELECT monthly_payment, rate, current_balance, escrow
FROM mortgages
ORDER BY updated_at DESC
LIMIT 1;`,
  amortization: `-- The schedule is computed in Python from these terms, starting at origination_date:
--   interest  = balance * rate / 12
--   principal = monthly_payment - interest - COALESCE(escrow, 0)
--   balance   = balance - principal
SELECT original_amount, current_balance, rate, monthly_payment,
       origination_date, original_payoff_date, escrow
FROM mortgages
ORDER BY updated_at DESC
LIMIT 1;`,
  paymentBreakdown: `-- Computed from rate and balance, not read from the statement
SELECT monthly_payment AS total,
       current_balance * rate / 12 AS interest,
       monthly_payment - current_balance * rate / 12 - COALESCE(escrow, 0) AS principal,
       COALESCE(escrow, 0) AS escrow
FROM mortgages
ORDER BY updated_at DESC
LIMIT 1;`,
  equityPosition: `-- principal paid = original_amount - current_balance
-- down payment    = purchase price - original_amount   (needs the purchase price)
-- appreciation    = latest value - purchase price      (needs the purchase price)
SELECT pv.value AS property_value, m.original_amount, m.current_balance,
       m.original_amount - m.current_balance AS principal_paid,
       pv.value - m.current_balance AS total_equity
FROM property_valuations pv
JOIN accounts a ON a.id = pv.account_id
CROSS JOIN (SELECT original_amount, current_balance FROM mortgages ORDER BY updated_at DESC LIMIT 1) m
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC, pv.id DESC
LIMIT 1;`,
  valueHistory: `SELECT h.date, h.value, h.source, h.is_projected, h.details
FROM property_value_histories h
JOIN accounts a ON a.id = h.account_id
WHERE a.account_type = 'real_estate'
ORDER BY h.date;`,
}

// ── Loading ──
async function loadSummary() {
  summary.value = await api.property.summary()
}

async function loadAmortization() {
  amortizationError.value = ''
  try {
    amortization.value = await api.property.amortization()
  } catch (e) {
    amortization.value = null
    amortizationError.value = apiErrorMessage(e, 'Could not compute the amortization schedule')
  }
}

async function loadHistory() {
  try {
    const data = await api.property.valueHistory()
    valueHistory.value = data.history || []
    valueCommentary.value = data.commentary || null
    valuePropertyDetails.value = data.property_details || null
    if (data.projection_note) projectionNote.value = data.projection_note
  } catch (e) {
    historyError.value = apiErrorMessage(e, 'Could not load the value history')
  }
}

async function refreshData() {
  try {
    await Promise.all([loadSummary(), loadAmortization(), loadHistory()])
  } catch (e) {
    error.value = apiErrorMessage(e)
  }
}

onMounted(async () => {
  await refreshData()
  loading.value = false
})

// ── Actions ──
async function submitValuation() {
  const val = parseFloat(newValuation.value.replace(/[^0-9.]/g, ''))
  if (isNaN(val) || val <= 0) {
    valuationError.value = 'Enter a dollar amount'
    return
  }
  savingValuation.value = true
  valuationError.value = ''
  try {
    await api.property.addValuation({ value: val, source: valuationSource.value, valuation_date: valuationDate.value })
    showManualEntry.value = false
    newValuation.value = ''
    valuationSource.value = 'Manual'
    valuationDate.value = new Date().toISOString().slice(0, 10)
    await refreshData()
  } catch (e) {
    valuationError.value = apiErrorMessage(e, 'Could not save the valuation')
  } finally {
    savingValuation.value = false
  }
}

async function savePurchasePrice() {
  const val = parseFloat(purchaseInput.value.replace(/[^0-9.]/g, ''))
  if (isNaN(val) || val <= 0) {
    purchaseError.value = 'Enter the price you paid'
    return
  }
  savingPurchase.value = true
  purchaseError.value = ''
  try {
    await api.property.addValuation({
      value: val,
      source: 'Purchase price',
      valuation_date: summary.value?.mortgage?.origination_date || new Date().toISOString().slice(0, 10),
    })
    purchaseInput.value = ''
    await refreshData()
  } catch (e) {
    purchaseError.value = apiErrorMessage(e, 'Could not save the purchase price')
  } finally {
    savingPurchase.value = false
  }
}

async function refreshFromRealtor() {
  refreshing.value = true
  historyError.value = ''
  projectionNote.value = null
  try {
    const data = await api.property.refreshHistory()
    valueHistory.value = data.history || []
    valueCommentary.value = data.commentary || null
    valuePropertyDetails.value = data.property_details || null
    projectionNote.value = data.projection_note || null
    await Promise.all([loadSummary(), loadAmortization()])
  } catch (e) {
    historyError.value = apiErrorMessage(e, 'Refresh failed')
  } finally {
    refreshing.value = false
  }
}

// ── Derived ──
const purchasePrice = computed(() => summary.value?.property?.purchase_price ?? purchasePriceFromHistory(valueHistory.value))

const equity = computed(() => equityComposition({
  value: summary.value?.property?.value,
  mortgageBalance: summary.value?.mortgage?.balance,
  originalAmount: summary.value?.mortgage?.original_amount,
  purchasePrice: purchasePrice.value,
}))

const projectionLabel = computed(() => {
  const p = valueHistory.value.find((h) => h.source === 'ai_projection')
  const d = (p?.details || {}) as { model?: string; confidence?: string }
  if (!p) return 'AI projection'
  return `AI projection (${d.model || 'Claude'}, ${d.confidence || 'unknown'} confidence)`
})

const yAxisMoney = (v: number) => (v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `$${(v / 1_000).toFixed(0)}K` : `$${v}`)

// ── Value history chart ──
const valueHistoryChartOption = computed(() => {
  const history = valueHistory.value
  if (!history.length) return null

  const point = (h: PropertyValuePoint): [string, number] => [h.date, h.value]
  const saleData = history.filter((h) => h.source === 'sale').map(point)
  const estimateData = history.filter((h) => h.source === 'realtor_estimate').map(point)
  const manualData = history.filter((h) => h.source === 'manual').map(point)
  const projectionData = history.filter((h) => h.is_projected).map(point)
  const actualPoints = history.filter((h) => !h.is_projected).sort((a, b) => a.date.localeCompare(b.date)).map(point)
  const projectedLine: [string, number][] = []
  if (actualPoints.length && projectionData.length) projectedLine.push(actualPoints[actualPoints.length - 1], ...projectionData)

  const legendData = ['Value history']
  if (saleData.length) legendData.push('Sale price')
  if (estimateData.length) legendData.push('Realtor.com estimate')
  if (manualData.length) legendData.push('Manual entry')
  if (projectedLine.length) legendData.push(projectionLabel.value)

  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 48 : 36 },
    legend: { ...mobileLegend(), data: legendData },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params) || !params.length) return ''
        let html = `<strong>${monthYear(String(params[0].value[0]).slice(0, 10))}</strong>`
        for (const p of params) {
          if (p.value?.[1] != null) html += `<br/>${p.marker} ${p.seriesName}: ${money(p.value[1])}`
        }
        return html
      },
    },
    xAxis: {
      type: 'time' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => new Date(v).getFullYear().toString() },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: yAxisMoney },
      splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } },
    },
    series: [
      {
        name: 'Value history', type: 'line', data: actualPoints, smooth: false, symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2.5, color: COLORS[0] }, itemStyle: { color: COLORS[0] }, areaStyle: { color: COLORS[0], opacity: 0.08 },
      },
      ...(saleData.length ? [{ name: 'Sale price', type: 'scatter', data: saleData, symbol: 'diamond', symbolSize: 12, itemStyle: { color: COLORS[1] }, z: 20 }] : []),
      ...(estimateData.length ? [{ name: 'Realtor.com estimate', type: 'scatter', data: estimateData, symbol: 'circle', symbolSize: 10, itemStyle: { color: COLORS[5] }, z: 20 }] : []),
      ...(manualData.length ? [{ name: 'Manual entry', type: 'scatter', data: manualData, symbol: 'pin', symbolSize: 14, itemStyle: { color: COLORS[6] }, z: 20 }] : []),
      ...(projectedLine.length ? [{
        name: projectionLabel.value, type: 'line', data: projectedLine, smooth: false, symbol: 'circle', symbolSize: 5,
        lineStyle: { width: 2, color: COLORS[2], type: 'dashed' as const }, itemStyle: { color: COLORS[2] }, areaStyle: { color: COLORS[2], opacity: 0.06 },
      }] : []),
    ],
  }
})

// ── Amortization chart ──
const amortChartOption = computed(() => {
  const schedule = amortization.value?.schedule
  if (!schedule?.length) return null
  const currentIdx = amortization.value?.current_month_index ?? 0
  const dates = schedule.map((s) => s.date)
  const yearTicks = (index: number) => {
    if (index === 0) return true
    const cur = dates[index]?.substring(0, 4)
    const prev = dates[index - 1]?.substring(0, 4)
    return cur !== prev && parseInt(cur) % (isMobile.value ? 10 : 5) === 0
  }
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 44 : 36 },
    legend: { ...mobileLegend(), data: ['Balance', 'Principal', 'Interest', 'Escrow'] },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params) || !params.length) return ''
        let html = `<strong>${monthYear(params[0].name)}</strong>`
        let paymentTotal = 0
        for (const p of params) {
          html += `<br/>${p.marker} ${p.seriesName}: ${money(p.value)}`
          if (p.seriesName !== 'Balance') paymentTotal += p.value
        }
        if (paymentTotal > 0) html += `<br/><strong>Total payment: ${money(paymentTotal)}</strong>`
        return html
      },
    },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: { ...mobileAxis(), interval: yearTicks, formatter: (v: string) => v.substring(0, 4) },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: [
      { type: 'value' as const, position: 'left' as const, axisLabel: { ...mobileAxis(), formatter: yAxisMoney }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } } },
      { type: 'value' as const, position: 'right' as const, axisLabel: { ...mobileAxis(), formatter: (v: number) => money(v) }, splitLine: { show: false } },
    ],
    series: [
      {
        name: 'Balance', type: 'line', yAxisIndex: 0, data: schedule.map((s) => s.balance), smooth: true, symbol: 'none',
        lineStyle: { width: 2.5, color: COLORS[0] }, areaStyle: { color: COLORS[0], opacity: 0.08 }, z: 10,
        markLine: {
          silent: true, symbol: 'none',
          data: [{ xAxis: currentIdx, lineStyle: { color: mutedTextColor.value, width: 2, type: 'dashed' as const },
            label: { show: true, formatter: 'Today', position: 'insideEndTop' as const, color: mutedTextColor.value, fontSize: 11, fontWeight: 'bold' as const } }],
        },
        markArea: currentIdx > 0 ? { silent: true, data: [[{ xAxis: 0, itemStyle: { color: isDark.value ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' } }, { xAxis: currentIdx }]] } : undefined,
      },
      { name: 'Principal', type: 'bar', yAxisIndex: 1, stack: 'payment', data: schedule.map((s) => s.principal), itemStyle: { color: COLORS[1], opacity: 0.5 }, barMaxWidth: 3 },
      { name: 'Interest', type: 'bar', yAxisIndex: 1, stack: 'payment', data: schedule.map((s) => s.interest), itemStyle: { color: COLORS[3], opacity: 0.35 }, barMaxWidth: 3 },
      { name: 'Escrow', type: 'bar', yAxisIndex: 1, stack: 'payment', data: schedule.map((s) => s.escrow), itemStyle: { color: COLORS[4], opacity: 0.35 }, barMaxWidth: 3 },
    ],
  }
})

// ── Payment breakdown ──
const paymentRows = computed(() => {
  const pb = summary.value?.payment_breakdown
  if (!pb) return []
  return [
    { name: 'Principal', value: pb.principal, color: COLORS[1] },
    { name: 'Interest', value: pb.interest, color: COLORS[3] },
    { name: 'Escrow', value: pb.escrow, color: COLORS[4] },
  ].filter((d) => d.value > 0)
})

const paymentPieOption = computed(() => {
  if (!paymentRows.value.length) return null
  return {
    ...baseOption.value,
    tooltip: { ...baseOption.value.tooltip, trigger: 'item' as const, formatter: (p: any) => `<strong>${p.name}</strong><br/>${money(p.value)} (${p.percent.toFixed(1)}%)` },
    series: [{
      type: 'pie', radius: ['45%', '75%'], center: ['50%', '50%'], avoidLabelOverlap: true,
      label: { show: false },  // the legend table below names each slice
      labelLine: { show: !isMobile.value },
      data: paymentRows.value.map((r) => ({ value: r.value, name: r.name, itemStyle: { color: r.color } })),
    }],
  }
})

const sourceOptions: ValuationSourceLabel[] = ['Manual', 'Redfin', 'Zillow', 'Appraisal', 'Tax Assessment', 'Purchase price']
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <PageHeader
      title="Property"
      :subtitle="summary?.property?.address || 'No property data'"
      tooltip="<strong>Property</strong><br>Value, mortgage, equity and the amortization schedule for the house. Values come from statements you import, entries you add, and optional Realtor.com lookups. The latest valuation is also what net worth and Planning use for the house."
    >
      <button @click="openData('property')"
        class="px-4 py-2 min-h-10 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">
        Data
      </button>
      <button v-demo-lock @click="openImport({ context: 'property', onComplete: refreshData })"
        class="px-4 py-2 min-h-10 text-xs font-medium bg-purple-600 text-white rounded-lg hover:bg-purple-700">
        Import statement
      </button>
    </PageHeader>

    <div v-if="loading" class="text-sm text-gray-400">Loading property data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>
    <div v-else-if="!summary?.property && !summary?.mortgage" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No property data found.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Import a mortgage statement to get started.</p>
    </div>

    <template v-else>
      <!-- Summary cards -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 items-start">
        <MetricCard label="Property Value" :value="compact(summary?.property?.value)"
          :subtitle="summary?.property ? `${summary.property.valuation_source || 'No valuation'}${summary.property.valuation_date ? ' · ' + fmtDate(summary.property.valuation_date) : ''}` : 'No valuation'"
          info="<strong>Property Value</strong><br>The most recent valuation on file: an entry you added, an imported figure, or a Realtor.com estimate. This figure also feeds net worth."
          :sql="SQL.propertyValue" :sql-tables="['property_valuations', 'accounts']" />
        <MetricCard label="Mortgage Balance" :value="compact(summary?.mortgage?.balance)"
          :subtitle="summary?.mortgage?.original_amount ? `of ${compact(summary.mortgage.original_amount)} original` : ''"
          info="<strong>Mortgage Balance</strong><br>Unpaid principal from the newest mortgage statement you imported."
          :sql="SQL.mortgageBalance" :sql-tables="['mortgages']" />
        <MetricCard label="Equity" :value="compact(summary?.equity)" :subtitle="equity ? `${equity.equityPct.toFixed(1)}% of value` : ''"
          info="<strong>Home Equity</strong><br>Property value minus mortgage balance."
          :sql="SQL.equity" :sql-tables="['property_valuations', 'mortgages', 'accounts']" />
        <MetricCard label="Interest Rate" :value="percent(summary?.mortgage?.rate, 2)"
          :subtitle="summary?.mortgage?.origination_date ? `since ${fmtDate(summary.mortgage.origination_date)}` : ''"
          info="<strong>Interest Rate</strong><br>Annual rate on the mortgage, from the statement."
          :sql="SQL.interestRate" :sql-tables="['mortgages']" />
        <MetricCard label="Monthly Payment" :value="money(summary?.mortgage?.monthly_payment)"
          :subtitle="summary?.mortgage?.escrow != null ? `incl. ${money(summary.mortgage.escrow)} escrow` : 'escrow unknown'"
          info="<strong>Monthly Payment</strong><br>Total payment from the statement. The principal/interest split shown below is computed from the rate and balance."
          :sql="SQL.monthlyPayment" :sql-tables="['mortgages']" />
      </div>

      <!-- Value over time -->
      <ChartContainer
        title="Property Value Over Time"
        :empty="!valueHistoryChartOption"
        empty-text="No value history yet. Add an entry below or refresh from Realtor.com."
        info="<strong>Property Value History</strong><br>Points you entered (pins), Realtor.com estimates and tax assessments, any sale record, and a dashed line of projected values. Projections are an AI estimate: Claude supplies an expected yearly appreciation rate and commentary, and the points are computed from it. They never feed equity or net worth."
        :sql="SQL.valueHistory" :sql-tables="['property_value_histories', 'accounts']"
      >
        <div class="h-72"><VChart v-if="valueHistoryChartOption" :option="valueHistoryChartOption" autoresize class="w-full h-full" /></div>
      </ChartContainer>

      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-4">
        <div v-if="valueCommentary" class="rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 p-3">
          <div class="text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400 mb-1">{{ projectionLabel }}</div>
          <p class="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{{ valueCommentary }}</p>
        </div>
        <div v-if="valuePropertyDetails" class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span v-if="valuePropertyDetails.beds">{{ valuePropertyDetails.beds }} bed</span>
          <span v-if="valuePropertyDetails.baths">{{ valuePropertyDetails.baths }} bath</span>
          <span v-if="valuePropertyDetails.sqft">{{ Number(valuePropertyDetails.sqft).toLocaleString() }} sqft</span>
          <span v-if="valuePropertyDetails.year_built">Built {{ valuePropertyDetails.year_built }}</span>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-xs text-gray-500 dark:text-gray-400 min-w-0">
            <template v-if="summary?.property?.value">
              Current value <span class="font-medium text-gray-700 dark:text-gray-300">{{ money(summary.property.value) }}</span>
              · {{ summary.property.valuation_source || 'Unknown source' }} · {{ fmtDate(summary.property.valuation_date) }}
            </template>
            <template v-else>No property valuation on file.</template>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button v-demo-lock @click="refreshFromRealtor" :disabled="refreshing"
              class="px-3 py-2 min-h-10 text-xs font-medium bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 whitespace-nowrap">
              {{ refreshing ? 'Refreshing…' : 'Refresh from Realtor.com' }}
            </button>
            <button v-if="!showManualEntry" v-demo-lock @click="showManualEntry = true"
              class="px-3 py-2 min-h-10 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 whitespace-nowrap">
              Add entry
            </button>
          </div>
        </div>
        <div v-if="historyError" class="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">{{ historyError }}</div>
        <div v-if="projectionNote" class="text-xs text-amber-700 dark:text-amber-400">{{ projectionNote }}</div>

        <!-- Add entry form -->
        <div v-if="showManualEntry" class="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label class="block text-xs text-gray-500 dark:text-gray-400">Date
              <input v-model="valuationDate" type="date" class="mt-1 w-full py-2 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
            </label>
            <label class="block text-xs text-gray-500 dark:text-gray-400">Value
              <input v-model="newValuation" type="text" inputmode="decimal" placeholder="e.g. 550000" @keyup.enter="submitValuation"
                class="mt-1 w-full py-2 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
            </label>
            <label class="block text-xs text-gray-500 dark:text-gray-400">Source
              <select v-model="valuationSource" class="mt-1 w-full py-2 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
                <option v-for="s in sourceOptions" :key="s" :value="s">{{ s }}</option>
              </select>
            </label>
          </div>
          <p class="text-[11px] text-gray-400 mt-2">Entries you add are kept when refreshing from Realtor.com. "Purchase price" records what you paid so equity can show the down payment and appreciation.</p>
          <div v-if="valuationError" class="text-xs text-red-500 mt-2">{{ valuationError }}</div>
          <div class="flex flex-wrap gap-2 mt-3">
            <button v-demo-lock @click="submitValuation" :disabled="savingValuation" class="px-4 py-2 min-h-10 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ savingValuation ? 'Saving…' : 'Add' }}
            </button>
            <button @click="showManualEntry = false; valuationError = ''" class="px-4 py-2 min-h-10 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
          </div>
        </div>
      </div>

      <!-- Equity position -->
      <div class="group/eqpos relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showEquityPositionSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/eqpos:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showEquityPositionSql" :sql="SQL.equityPosition" title="Equity Position" :tables="['property_valuations', 'mortgages', 'accounts']" @close="showEquityPositionSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Equity Position
          <InfoTooltip text="<strong>Equity Position</strong><br>Equity = value − mortgage balance. It is made of the <strong>down payment</strong> (purchase price − original loan), <strong>principal paid</strong> (original loan − balance) and <strong>appreciation</strong> (value − purchase price). Without the purchase price the first and last cannot be separated, so they are not guessed." />
        </h2>

        <template v-if="equity && summary?.mortgage">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-xs">
            <div><div class="text-gray-500 dark:text-gray-400">Property Value</div><div class="font-semibold text-gray-900 dark:text-white">{{ money(summary?.property?.value) }}</div></div>
            <div><div class="text-gray-500 dark:text-gray-400">Mortgage Balance</div><div class="font-semibold text-gray-900 dark:text-white">{{ money(summary.mortgage.balance) }}</div></div>
            <div><div class="text-gray-500 dark:text-gray-400">Total Equity</div><div class="font-semibold text-green-600 dark:text-green-400">{{ money(equity.totalEquity) }}</div></div>
            <div><div class="text-gray-500 dark:text-gray-400">Equity %</div><div class="font-semibold text-green-600 dark:text-green-400">{{ equity.equityPct.toFixed(1) }}%</div></div>
          </div>

          <div class="relative w-full h-10 rounded-lg overflow-hidden flex">
            <div v-if="equity.widths.downPayment > 0" class="bg-amber-500 h-full flex items-center justify-center text-white text-[10px] font-medium" :style="{ width: `${equity.widths.downPayment}%` }">
              <span v-if="equity.widths.downPayment > 8">{{ compact(equity.downPayment) }}</span>
            </div>
            <div v-if="equity.widths.appreciation > 0" class="bg-green-500 h-full flex items-center justify-center text-white text-[10px] font-medium" :style="{ width: `${equity.widths.appreciation}%` }">
              <span v-if="equity.widths.appreciation > 8">{{ compact(equity.appreciation) }}</span>
            </div>
            <div v-if="equity.needsPurchasePrice && equity.totalEquity - equity.principalPaid > 0" class="bg-gray-400/60 dark:bg-gray-500/60 h-full flex items-center justify-center text-white text-[10px] font-medium"
              :style="{ width: `${Math.max(0, equity.equityPct - equity.widths.principalPaid)}%` }" title="Down payment + appreciation (needs purchase price to split)">
              <span v-if="equity.equityPct - equity.widths.principalPaid > 10">{{ compact(equity.totalEquity - equity.principalPaid) }}</span>
            </div>
            <div v-if="equity.widths.principalPaid > 0" class="bg-indigo-500 h-full flex items-center justify-center text-white text-[10px] font-medium" :style="{ width: `${equity.widths.principalPaid}%` }">
              <span v-if="equity.widths.principalPaid > 6">{{ compact(equity.principalPaid) }}</span>
            </div>
            <div class="bg-gray-300 dark:bg-gray-600 h-full flex-1 flex items-center justify-center text-gray-600 dark:text-gray-300 text-[10px] font-medium">
              {{ compact(equity.remaining) }}
            </div>
          </div>

          <div class="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs">
            <div class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-amber-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Down payment</span>
              <span class="font-medium text-amber-600 dark:text-amber-400">{{ equity.downPayment != null ? money(equity.downPayment) : 'unknown' }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-green-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Appreciation</span>
              <span class="font-medium text-green-600 dark:text-green-400">{{ equity.appreciation != null ? money(equity.appreciation) : 'needs purchase price' }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-indigo-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Principal paid</span>
              <span class="font-medium text-indigo-600 dark:text-indigo-400">{{ money(equity.principalPaid) }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-gray-300 dark:bg-gray-600"></div>
              <span class="text-gray-600 dark:text-gray-400">Remaining mortgage</span>
              <span class="font-medium text-gray-700 dark:text-gray-300">{{ money(equity.remaining) }}</span>
            </div>
          </div>

          <div v-if="equity.needsPurchasePrice" class="mt-4 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 p-3">
            <div class="text-xs text-gray-600 dark:text-gray-400 mb-2">Enter what you paid for the house to split equity into down payment and appreciation.</div>
            <div class="flex flex-wrap gap-2 items-center">
              <input v-model="purchaseInput" type="text" inputmode="decimal" placeholder="Purchase price, e.g. 450000" @keyup.enter="savePurchasePrice"
                class="py-2 px-3 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white w-full sm:w-56" />
              <button v-demo-lock @click="savePurchasePrice" :disabled="savingPurchase" class="px-4 py-2 min-h-10 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {{ savingPurchase ? 'Saving…' : 'Save purchase price' }}
              </button>
            </div>
            <div v-if="purchaseError" class="text-xs text-red-500 mt-2">{{ purchaseError }}</div>
          </div>
        </template>
        <p v-else class="text-sm text-gray-400">Need both a property value and a mortgage to show the equity position.</p>
      </div>

      <!-- Amortization + payment breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        <div class="lg:col-span-2 min-w-0">
          <ChartContainer
            title="Amortization Schedule"
            :empty="!amortChartOption"
            :empty-text="amortizationError || 'No amortization data available'"
            info="<strong>Amortization Schedule</strong><br>Computed from the mortgage terms starting at its origination date: each month's interest is balance × rate ÷ 12, principal is the payment minus interest and escrow. The curve flattens early (mostly interest) and steepens later."
            :sql="SQL.amortization" :sql-tables="['mortgages']"
          >
            <div class="h-72"><VChart v-if="amortChartOption" :option="amortChartOption" autoresize class="w-full h-full" /></div>
            <div v-if="amortization?.summary" class="mt-3 text-xs text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
              <span>{{ amortization.summary.months_remaining }} months remaining</span>
              <span>Payoff {{ amortization.summary.payoff_date ? monthYear(amortization.summary.payoff_date) : dash }}</span>
              <span>Interest paid <span class="text-red-500">{{ money(amortization.summary.total_interest_paid) }}</span></span>
              <span>Interest remaining <span class="text-red-400">{{ money(amortization.summary.total_interest_remaining) }}</span></span>
              <span>Principal paid <span class="text-green-600">{{ money(amortization.summary.total_principal_paid) }}</span></span>
            </div>
          </ChartContainer>
        </div>

        <ChartContainer
          title="Payment Breakdown"
          :empty="!paymentPieOption"
          empty-text="No payment data available"
          info="<strong>Payment Breakdown</strong><br>How this month's payment splits: interest is computed as balance × rate ÷ 12, escrow is the statement's escrow amount, principal is the rest. It is a computation from the mortgage terms, not a figure read off the statement."
          :sql="SQL.paymentBreakdown" :sql-tables="['mortgages']"
        >
          <div class="h-56"><VChart v-if="paymentPieOption" :option="paymentPieOption" autoresize class="w-full h-full" /></div>
          <DataTable v-if="paymentRows.length" dense class="mt-3">
            <tbody>
              <tr v-for="r in paymentRows" :key="r.name">
                <td class="text-xs text-gray-500 dark:text-gray-400"><span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" :style="{ background: r.color }"></span>{{ r.name }}</td>
                <td class="text-xs font-medium text-right text-gray-900 dark:text-white">{{ money(r.value) }}</td>
              </tr>
              <tr>
                <td class="text-xs font-medium text-gray-500 dark:text-gray-400">Total</td>
                <td class="text-xs font-bold text-right text-gray-900 dark:text-white">{{ money(summary?.payment_breakdown?.total) }}</td>
              </tr>
            </tbody>
          </DataTable>
        </ChartContainer>
      </div>
    </template>

    <DataExplorer />
  </div>
</template>
