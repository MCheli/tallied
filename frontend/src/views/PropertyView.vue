<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, LineChart, BarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useImportModal } from '../composables/useImportModal'

use([PieChart, LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent, CanvasRenderer])

const { baseOption, isDark } = useChartDefaults()
const { openImport } = useImportModal()
const API = import.meta.env.VITE_API_URL || ''

const loading = ref(true)
const error = ref('')
const summary = ref<any>(null)
const amortization = ref<any>(null)

// Manual entry state
const showManualEntry = ref(false)
const newValuation = ref('')
const valuationSource = ref('Manual')
const valuationDate = ref(new Date().toISOString().slice(0, 10))
const savingValuation = ref(false)

// Refresh state (combined estimate + history)
const refreshing = ref(false)

// Value history state
const valueHistory = ref<{ date: string; value: number; source: string; is_projected: boolean }[]>([])
const valueCommentary = ref<string | null>(null)
const valuePropertyDetails = ref<Record<string, any> | null>(null)
const historyError = ref('')

// SQL viewer state
const showPropertyValueSql = ref(false)
const showMortgageBalanceSql = ref(false)
const showEquitySql = ref(false)
const showInterestRateSql = ref(false)
const showMonthlyPaymentSql = ref(false)
const showAmortizationSql = ref(false)
const showPaymentBreakdownSql = ref(false)
const showEquityPositionSql = ref(false)

// SQL queries
const SQL = {
  propertyValue: `SELECT pv.value, pv.valuation_date, pv.source
FROM property_valuations pv
JOIN accounts a ON pv.account_id = a.id
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC
LIMIT 1`,

  mortgageBalance: `SELECT m.current_balance, m.original_amount,
  m.updated_at
FROM mortgages m
ORDER BY m.updated_at DESC
LIMIT 1`,

  equity: `-- Equity = Property Value - Mortgage Balance
SELECT pv.value AS property_value,
  m.current_balance AS mortgage_balance,
  (pv.value - m.current_balance) AS equity
FROM property_valuations pv
JOIN accounts a ON pv.account_id = a.id
CROSS JOIN (
  SELECT current_balance FROM mortgages
  ORDER BY updated_at DESC LIMIT 1
) m
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC
LIMIT 1`,

  interestRate: `SELECT m.rate, m.origination_date,
  m.original_payoff_date AS maturity_date
FROM mortgages m
ORDER BY m.updated_at DESC
LIMIT 1`,

  monthlyPayment: `SELECT m.monthly_payment, m.rate,
  m.current_balance, m.escrow_payment
FROM mortgages m
ORDER BY m.updated_at DESC
LIMIT 1`,

  amortization: `-- Amortization is computed from mortgage terms
SELECT m.original_amount, m.current_balance,
  m.rate, m.monthly_payment,
  m.origination_date, m.original_payoff_date,
  m.escrow_payment
FROM mortgages m
ORDER BY m.updated_at DESC
LIMIT 1
-- Schedule is calculated in Python using these values:
-- monthly_rate = rate / 12
-- For each month: interest = balance * monthly_rate
--                 principal = payment - interest - escrow
--                 balance = balance - principal`,

  paymentBreakdown: `-- Payment split computed from mortgage terms
SELECT m.monthly_payment AS total,
  m.current_balance * (m.rate / 12) AS interest,
  m.monthly_payment - m.current_balance * (m.rate / 12)
    - COALESCE(m.escrow_payment, 0) AS principal,
  COALESCE(m.escrow_payment, 0) AS escrow
FROM mortgages m
ORDER BY m.updated_at DESC
LIMIT 1`,

  equityPosition: `-- Equity from payments + appreciation
SELECT
  pv.value AS property_value,
  m.original_amount,
  m.current_balance,
  (m.original_amount - m.current_balance) AS equity_from_payments,
  (pv.value - m.original_amount) AS equity_from_appreciation,
  (pv.value - m.current_balance) AS total_equity
FROM property_valuations pv
JOIN accounts a ON pv.account_id = a.id
CROSS JOIN (
  SELECT original_amount, current_balance
  FROM mortgages ORDER BY updated_at DESC LIMIT 1
) m
WHERE a.account_type = 'real_estate'
ORDER BY pv.valuation_date DESC
LIMIT 1`,
}

onMounted(async () => {
  try {
    const [sumRes, amortRes] = await Promise.all([
      fetch(`${API}/api/v1/property/summary`, { credentials: 'include' }),
      fetch(`${API}/api/v1/property/amortization`, { credentials: 'include' }),
    ])
    if (sumRes.ok) summary.value = await sumRes.json()
    if (amortRes.ok) amortization.value = await amortRes.json()
    // Load value history in background
    fetchValueHistory()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function refreshData() {
  try {
    const [sumRes, amortRes] = await Promise.all([
      fetch(`${API}/api/v1/property/summary`, { credentials: 'include' }),
      fetch(`${API}/api/v1/property/amortization`, { credentials: 'include' }),
    ])
    if (sumRes.ok) summary.value = await sumRes.json()
    if (amortRes.ok) amortization.value = await amortRes.json()
  } catch (e: any) {
    error.value = e.message
  }
}

// ── Manual valuation submission ──

async function submitValuation() {
  const val = parseFloat(newValuation.value.replace(/[^0-9.]/g, ''))
  if (isNaN(val) || val <= 0) return

  savingValuation.value = true
  try {
    const res = await fetch(`${API}/api/v1/property/valuation`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        value: val,
        source: valuationSource.value,
        valuation_date: valuationDate.value,
      }),
    })

    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Update failed (${res.status}): ${text}`)
    }

    showManualEntry.value = false
    newValuation.value = ''
    valuationSource.value = 'Manual'
    valuationDate.value = new Date().toISOString().slice(0, 10)
    await Promise.all([refreshData(), fetchValueHistory()])
  } catch (e: any) {
    error.value = e.message
  } finally {
    savingValuation.value = false
  }
}

// ── Value history ──

async function fetchValueHistory() {
  try {
    const res = await fetch(`${API}/api/v1/property/value-history`, { credentials: 'include' })
    if (res.ok) {
      const data = await res.json()
      valueHistory.value = data.history || []
      valueCommentary.value = data.commentary || null
      valuePropertyDetails.value = data.property_details || null
    }
  } catch (e: any) {
    historyError.value = e.message
  }
}

async function refreshFromRealtor() {
  refreshing.value = true
  historyError.value = ''
  try {
    const res = await fetch(`${API}/api/v1/property/refresh-history`, {
      method: 'POST',
      credentials: 'include',
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || `Request failed (${res.status})`)
    }
    valueHistory.value = data.history || []
    valueCommentary.value = data.commentary || null
    valuePropertyDetails.value = data.property_details || null
    // Refresh summary cards (estimate may have updated valuation)
    await refreshData()
  } catch (e: any) {
    historyError.value = e.message
  } finally {
    refreshing.value = false
  }
}

// ── Value history chart ──

const valueHistoryChartOption = computed(() => {
  if (!valueHistory.value.length) return null

  const history = valueHistory.value

  // Separate data by source
  const saleData: [string, number][] = []
  const estimateData: [string, number][] = []
  const projectionData: [string, number][] = []
  const manualData: [string, number][] = []

  for (const h of history) {
    const point: [string, number] = [h.date, h.value]
    if (h.source === 'sale') saleData.push(point)
    else if (h.source === 'realtor_estimate') estimateData.push(point)
    else if (h.source === 'ai_projection') projectionData.push(point)
    else if (h.source === 'manual') manualData.push(point)
  }

  // Build the actual (non-projected) line data: all non-projected points, sorted
  const actualPoints = history
    .filter(h => !h.is_projected)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(h => [h.date, h.value] as [string, number])

  // Build projected line data: last actual point + projections
  const projectedLine: [string, number][] = []
  if (actualPoints.length > 0 && projectionData.length > 0) {
    projectedLine.push(actualPoints[actualPoints.length - 1])
    projectedLine.push(...projectionData)
  }

  const legendData = ['Value History', 'Sale Price', 'Current Estimate', 'Projected']
  if (manualData.length > 0) legendData.push('Manual Entry')

  return {
    ...baseOption.value,
    grid: { left: 70, right: 20, top: 40, bottom: 35 },
    legend: {
      data: legendData,
      top: 0,
      textStyle: { color: isDark.value ? '#9ca3af' : '#6b7280', fontSize: 11 },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || !params.length) return ''
        const d = new Date(params[0].value[0] + 'T00:00:00')
        const dateStr = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
        let html = `<strong>${dateStr}</strong>`
        for (const p of params) {
          if (p.value[1] !== undefined && p.value[1] !== null) {
            html += `<br/>${p.marker} ${p.seriesName}: $${Math.round(p.value[1]).toLocaleString()}`
          }
        }
        return html
      },
    },
    xAxis: {
      type: 'time' as const,
      axisLabel: {
        formatter: (v: number) => new Date(v).getFullYear().toString(),
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        formatter: (v: number) => v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `$${(v / 1_000).toFixed(0)}K` : `$${v}`,
      },
      splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
    },
    series: [
      {
        name: 'Value History',
        type: 'line',
        data: actualPoints,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.5, color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59,130,246,0.10)' },
              { offset: 1, color: 'rgba(59,130,246,0.01)' },
            ],
          },
        },
      },
      {
        name: 'Sale Price',
        type: 'scatter',
        data: saleData,
        symbol: 'diamond',
        symbolSize: 12,
        itemStyle: { color: '#22c55e' },
        z: 20,
      },
      {
        name: 'Current Estimate',
        type: 'scatter',
        data: estimateData,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#8b5cf6', borderColor: '#fff', borderWidth: 2 },
        z: 20,
      },
      {
        name: 'Projected',
        type: 'line',
        data: projectedLine,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b', type: 'dashed' as const },
        itemStyle: { color: '#f59e0b' },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245,158,11,0.08)' },
              { offset: 1, color: 'rgba(245,158,11,0.01)' },
            ],
          },
        },
      },
      ...(manualData.length > 0 ? [{
        name: 'Manual Entry',
        type: 'scatter' as const,
        data: manualData,
        symbol: 'pin',
        symbolSize: 14,
        itemStyle: { color: '#ec4899' },
        z: 20,
      }] : []),
    ],
  }
})

// ── Format helpers ──

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
  return `${sign}$${abs.toFixed(0)}`
}

function fmtFull(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--'
  return `$${Math.round(n).toLocaleString()}`
}

function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--'
  return `${(n * 100).toFixed(2)}%`
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '--'
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Computed values ──

const equityPct = computed(() => {
  if (!summary.value?.property?.value || !summary.value?.equity) return 0
  return (summary.value.equity / summary.value.property.value) * 100
})

const purchasePrice = computed(() => {
  return summary.value?.property?.purchase_price || summary.value?.mortgage?.original_amount || 0
})

const downPayment = computed(() => {
  if (!purchasePrice.value || !summary.value?.mortgage?.original_amount) return 0
  return purchasePrice.value - summary.value.mortgage.original_amount
})

const equityFromPayments = computed(() => {
  if (!summary.value?.mortgage?.original_amount || !summary.value?.mortgage?.balance) return 0
  return summary.value.mortgage.original_amount - summary.value.mortgage.balance
})

const equityFromAppreciation = computed(() => {
  if (!summary.value?.property?.value || !purchasePrice.value) return 0
  return summary.value.property.value - purchasePrice.value
})

const downPaymentPct = computed(() => {
  if (!summary.value?.property?.value || downPayment.value <= 0) return 0
  return (downPayment.value / summary.value.property.value) * 100
})

const paymentsPct = computed(() => {
  if (!summary.value?.property?.value || equityFromPayments.value <= 0) return 0
  return (equityFromPayments.value / summary.value.property.value) * 100
})

const appreciationPct = computed(() => {
  if (!summary.value?.property?.value || equityFromAppreciation.value <= 0) return 0
  return (equityFromAppreciation.value / summary.value.property.value) * 100
})

// ── Amortization chart ──

const amortChartOption = computed(() => {
  if (!amortization.value?.schedule?.length) return null

  const schedule = amortization.value.schedule
  const currentIdx = amortization.value.current_month_index ?? 0
  const dates = schedule.map((s: any) => s.date)
  const balances = schedule.map((s: any) => s.balance)
  const principals = schedule.map((s: any) => s.principal)
  const interests = schedule.map((s: any) => s.interest)
  const escrows = schedule.map((s: any) => s.escrow ?? 842)

  // Find the current date — use the index from backend
  const currentDate = currentIdx < dates.length ? dates[currentIdx] : null

  return {
    ...baseOption.value,
    grid: { left: 65, right: 20, top: 30, bottom: 35 },
    legend: {
      data: ['Balance', 'Principal', 'Interest', 'Escrow'],
      top: 0,
      textStyle: { color: isDark.value ? '#9ca3af' : '#6b7280', fontSize: 11 },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || !params.length) return ''
        const d = new Date(params[0].name + 'T00:00:00')
        const dateStr = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
        let html = `<strong>${dateStr}</strong>`
        let paymentTotal = 0
        for (const p of params) {
          html += `<br/>${p.marker} ${p.seriesName}: ${fmtFull(p.value)}`
          if (p.seriesName !== 'Balance') paymentTotal += p.value
        }
        if (paymentTotal > 0) html += `<br/><strong>Total Payment: ${fmtFull(paymentTotal)}</strong>`
        return html
      },
    },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: {
        formatter: (v: string) => new Date(v + 'T00:00:00').getFullYear().toString(),
        interval: (index: number) => {
          if (index === 0) return true
          const cur = dates[index]?.substring(0, 4)
          const prev = dates[index - 1]?.substring(0, 4)
          return cur !== prev && parseInt(cur) % 5 === 0
        },
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: [
      {
        type: 'value' as const,
        position: 'left' as const,
        axisLabel: {
          formatter: (v: number) => v >= 1_000 ? `$${(v / 1_000).toFixed(0)}K` : `$${v}`,
        },
        splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
      },
      {
        type: 'value' as const,
        position: 'right' as const,
        axisLabel: {
          formatter: (v: number) => v >= 1_000 ? `$${(v / 1_000).toFixed(0)}K` : `$${v}`,
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Balance',
        type: 'line',
        yAxisIndex: 0,
        data: balances,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.5, color: '#6366f1' },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(99,102,241,0.12)' },
              { offset: 1, color: 'rgba(99,102,241,0.02)' },
            ],
          },
        },
        z: 10,
        markLine: currentDate ? {
          silent: true,
          symbol: 'none',
          data: [{
            xAxis: currentIdx,
            lineStyle: { color: '#111827', width: 2, type: 'dashed' as const },
            label: {
              show: true,
              formatter: 'Today',
              position: 'insideEndTop' as const,
              color: '#111827',
              fontSize: 11,
              fontWeight: 'bold' as const,
              backgroundColor: 'rgba(255,255,255,0.9)',
              padding: [2, 6],
              borderRadius: 3,
            },
          }],
        } : undefined,
        markArea: currentIdx > 0 ? {
          silent: true,
          data: [[
            { xAxis: 0, itemStyle: { color: 'rgba(0,0,0,0.04)' } },
            { xAxis: currentIdx },
          ]],
        } : undefined,
      },
      {
        name: 'Principal',
        type: 'bar',
        yAxisIndex: 1,
        stack: 'payment',
        data: principals,
        itemStyle: { color: 'rgba(34,197,94,0.5)' },
        barMaxWidth: 3,
      },
      {
        name: 'Interest',
        type: 'bar',
        yAxisIndex: 1,
        stack: 'payment',
        data: interests,
        itemStyle: { color: 'rgba(239,68,68,0.3)' },
        barMaxWidth: 3,
      },
      {
        name: 'Escrow',
        type: 'bar',
        yAxisIndex: 1,
        stack: 'payment',
        data: escrows,
        itemStyle: { color: 'rgba(59,130,246,0.3)' },
        barMaxWidth: 3,
      },
    ],
  }
})

// ── Payment breakdown pie ──

const paymentPieOption = computed(() => {
  if (!summary.value?.payment_breakdown) return null

  const pb = summary.value.payment_breakdown
  const data = [
    { value: pb.principal, name: 'Principal', itemStyle: { color: '#22c55e' } },
    { value: pb.interest, name: 'Interest', itemStyle: { color: '#ef4444' } },
    { value: pb.escrow, name: 'Escrow', itemStyle: { color: '#3b82f6' } },
  ].filter(d => d.value > 0)

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'item' as const,
      formatter: (params: any) => {
        return `<strong>${params.name}</strong><br/>${fmtFull(params.value)} (${params.percent.toFixed(1)}%)`
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['45%', '75%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: {
          show: true,
          formatter: '{b}\n{d}%',
          fontSize: 11,
          color: isDark.value ? '#9ca3af' : '#6b7280',
        },
        labelLine: { show: true },
        data,
      },
    ],
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Property</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ summary?.property?.address || 'No property data' }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button @click="openImport({ context: 'property', onComplete: refreshData })"
          class="px-4 py-2 text-xs font-medium bg-purple-600 text-white rounded-lg hover:bg-purple-700">
          Import
        </button>
        <InfoTooltip text="Import a mortgage statement. AI will extract key values (balance, rate, payment breakdown) for review before saving." />
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading property data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>
    <div v-else-if="!summary?.property && !summary?.mortgage" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No property data found.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Upload a mortgage statement to get started.</p>
    </div>

    <template v-else>
      <!-- Summary Cards: Property Value | Mortgage Balance | Equity | Rate | Monthly Payment -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="group/propval relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showPropertyValueSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/propval:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showPropertyValueSql" :sql="SQL.propertyValue" title="Property Value" :tables="['property_valuations', 'accounts']" @close="showPropertyValueSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Property Value <InfoTooltip text="<strong>Property Value</strong><br>Current estimated market value of the property.<br><br><strong>Source:</strong> Most recent valuation — may come from Realtor.com, AI estimate, appraisal, or manual entry." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ summary?.property ? fmt(summary.property.value) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ summary?.property?.valuation_source || 'No valuation' }} {{ summary?.property?.valuation_date ? '· ' + fmtDate(summary.property.valuation_date) : '' }}
          </div>
        </div>
        <div class="group/mortbal relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showMortgageBalanceSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/mortbal:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showMortgageBalanceSql" :sql="SQL.mortgageBalance" title="Mortgage Balance" :tables="['mortgages']" @close="showMortgageBalanceSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Mortgage Balance <InfoTooltip text="<strong>Mortgage Balance</strong><br>Outstanding principal balance on the mortgage. This decreases with each monthly payment as principal is paid down.<br><br><strong>Source:</strong> Mortgage statement or amortization calculation." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ summary?.mortgage ? fmt(summary.mortgage.balance) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ summary?.mortgage ? 'of ' + fmt(summary.mortgage.original_amount) + ' original' : '' }}
          </div>
        </div>
        <div class="group/equity relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showEquitySql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/equity:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showEquitySql" :sql="SQL.equity" title="Equity" :tables="['property_valuations', 'mortgages', 'accounts']" @close="showEquitySql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Equity <InfoTooltip text="<strong>Home Equity</strong><br>The portion of the property you actually own. Calculated as property value minus outstanding mortgage balance.<br><br><strong>Formula:</strong> <code>property value - mortgage balance</code>" /></div>
          <div class="text-xl font-bold text-green-600 dark:text-green-400 mt-1">{{ fmt(summary?.equity) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ equityPct.toFixed(1) }}% of value</div>
        </div>
        <div class="group/rate relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showInterestRateSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/rate:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showInterestRateSql" :sql="SQL.interestRate" title="Interest Rate" :tables="['mortgages']" @close="showInterestRateSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Interest Rate <InfoTooltip text="<strong>Interest Rate</strong><br>Annual interest rate on the mortgage. This is the fixed (or current adjustable) rate used to calculate monthly interest charges.<br><br><strong>Source:</strong> Mortgage origination documents or statement." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ summary?.mortgage ? fmtPct(summary.mortgage.rate) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ summary?.mortgage ? fmtDate(summary.mortgage.origination_date) : '' }} {{ summary?.mortgage?.maturity_date ? '– ' + fmtDate(summary.mortgage.maturity_date) : '' }}
          </div>
        </div>
        <div class="group/payment relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showMonthlyPaymentSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/payment:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showMonthlyPaymentSql" :sql="SQL.monthlyPayment" title="Monthly Payment" :tables="['mortgages']" @close="showMonthlyPaymentSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Monthly Payment <InfoTooltip text="<strong>Monthly Payment</strong><br>Total monthly mortgage payment including principal, interest, and escrow (taxes + insurance).<br><br><strong>Source:</strong> Mortgage statement payment_breakdown." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ summary?.mortgage ? fmt(summary.mortgage.monthly_payment) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">P+I+Escrow</div>
        </div>
      </div>

      <!-- Property Value Over Time (combined with valuation) -->
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
            Property Value Over Time
            <InfoTooltip text="<strong>Property Value History</strong><br>Shows tax assessments (blue), sale price (green diamond), current estimate (purple), manual entries (pink pin), and AI-projected future values (dashed amber).<br><br><strong>Sources:</strong> Realtor.com tax history, sale records, manual entries, and Claude AI projections." />
          </h2>
        </div>

        <div v-if="historyError" class="text-xs text-red-500 mb-2">{{ historyError }}</div>

        <!-- Chart -->
        <div v-if="valueHistoryChartOption" class="h-72">
          <VChart :option="valueHistoryChartOption" autoresize class="w-full h-full" />
        </div>
        <div v-else class="h-48 flex items-center justify-center text-sm text-gray-400">
          <div class="text-center">
            <p>No value history yet.</p>
            <p class="text-xs mt-1">Click "Refresh from Realtor.com" to fetch tax assessments and AI projections, or add a manual entry below.</p>
          </div>
        </div>

        <!-- AI Commentary -->
        <div v-if="valueCommentary" class="mt-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 p-3">
          <div class="flex items-start gap-2">
            <span class="text-amber-600 dark:text-amber-400 text-xs font-semibold mt-0.5 whitespace-nowrap">AI Analysis</span>
            <p class="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{{ valueCommentary }}</p>
          </div>
        </div>

        <!-- Property details from Realtor.com -->
        <div v-if="valuePropertyDetails" class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span v-if="valuePropertyDetails.beds">{{ valuePropertyDetails.beds }} bed</span>
          <span v-if="valuePropertyDetails.baths">{{ valuePropertyDetails.baths }} bath</span>
          <span v-if="valuePropertyDetails.sqft">{{ valuePropertyDetails.sqft?.toLocaleString() }} sqft</span>
          <span v-if="valuePropertyDetails.year_built">Built {{ valuePropertyDetails.year_built }}</span>
          <span v-if="valuePropertyDetails.lot_sqft">{{ valuePropertyDetails.lot_sqft?.toLocaleString() }} sqft lot</span>
        </div>

        <!-- Current valuation info + actions -->
        <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
          <div class="flex items-center justify-between">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <template v-if="summary?.property">
                Current value: <span class="font-medium text-gray-700 dark:text-gray-300">{{ fmtFull(summary.property.value) }}</span>
                <span class="mx-1">&middot;</span> {{ summary.property.valuation_source || 'Unknown' }}
                <span class="mx-1">&middot;</span> {{ fmtDate(summary.property.valuation_date) }}
              </template>
              <template v-else>
                No property valuation on file.
              </template>
            </div>
            <div class="flex items-center gap-2">
              <button @click="refreshFromRealtor" :disabled="refreshing"
                class="px-3 py-1.5 text-xs font-medium bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 whitespace-nowrap">
                {{ refreshing ? 'Refreshing...' : 'Refresh from Realtor.com' }}
              </button>
              <button v-if="!showManualEntry" @click="showManualEntry = true"
                class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                Add Entry
              </button>
            </div>
          </div>

          <!-- Manual entry form -->
          <div v-if="showManualEntry" class="mt-3 flex items-center gap-3 flex-wrap">
            <input v-model="valuationDate" type="date"
              class="py-1.5 px-2 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
            <div class="relative">
              <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input v-model="newValuation" type="text" placeholder="e.g. 550000"
                class="pl-7 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent w-36"
                @keyup.enter="submitValuation" />
            </div>
            <select v-model="valuationSource"
              class="py-1.5 px-2 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
              <option value="Manual">Manual</option>
              <option value="Redfin">Redfin</option>
              <option value="Zillow">Zillow</option>
              <option value="Appraisal">Appraisal</option>
              <option value="Tax Assessment">Tax Assessment</option>
            </select>
            <button @click="submitValuation" :disabled="savingValuation"
              class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ savingValuation ? 'Saving...' : 'Add' }}
            </button>
            <button @click="showManualEntry = false; newValuation = ''; valuationSource = 'Manual'; valuationDate = new Date().toISOString().slice(0, 10)"
              class="px-3 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- Equity Position -->
      <div class="group/eqpos relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showEquityPositionSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/eqpos:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showEquityPositionSql" :sql="SQL.equityPosition" title="Equity Position" :tables="['property_valuations', 'mortgages', 'accounts']" @close="showEquityPositionSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Equity Position
          <InfoTooltip text="<strong>Equity Position</strong><br>Your equity comes from two sources:<br>1. <strong>Principal payments</strong> (indigo) — how much of the original loan you've paid down<br>2. <strong>Appreciation</strong> (green) — how much the property has gained in value above the original loan amount<br><br><strong>Formula:</strong> <code>total equity = paydown equity + appreciation equity</code>" />
        </h2>

        <template v-if="summary?.property && summary?.mortgage">
          <!-- Key figures -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-xs">
            <div>
              <div class="text-gray-500 dark:text-gray-400">Property Value</div>
              <div class="font-semibold text-gray-900 dark:text-white">{{ fmtFull(summary.property.value) }}</div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">Mortgage Balance</div>
              <div class="font-semibold text-gray-900 dark:text-white">{{ fmtFull(summary.mortgage.balance) }}</div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">Total Equity</div>
              <div class="font-semibold text-green-600 dark:text-green-400">{{ fmtFull(summary.equity) }}</div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">Equity %</div>
              <div class="font-semibold text-green-600 dark:text-green-400">{{ equityPct.toFixed(1) }}%</div>
            </div>
          </div>

          <!-- Stacked bar: down payment + appreciation + payments + mortgage -->
          <div class="relative w-full h-10 rounded-lg overflow-hidden flex">
            <div v-if="downPayment > 0" class="bg-amber-500 h-full flex items-center justify-center text-white text-[10px] font-medium transition-all"
              :style="{ width: `${downPaymentPct}%` }">
              <span v-if="downPaymentPct > 6">{{ fmt(downPayment) }}</span>
            </div>
            <div v-if="equityFromAppreciation > 0" class="bg-green-500 h-full flex items-center justify-center text-white text-[10px] font-medium transition-all"
              :style="{ width: `${appreciationPct}%` }">
              <span v-if="appreciationPct > 8">{{ fmt(equityFromAppreciation) }}</span>
            </div>
            <div v-if="equityFromPayments > 0" class="bg-indigo-500 h-full flex items-center justify-center text-white text-[10px] font-medium transition-all"
              :style="{ width: `${paymentsPct}%` }">
              <span v-if="paymentsPct > 5">{{ fmt(equityFromPayments) }}</span>
            </div>
            <div class="bg-gray-300 dark:bg-gray-600 h-full flex-1 flex items-center justify-center text-gray-600 dark:text-gray-300 text-[10px] font-medium">
              {{ summary.mortgage ? fmt(summary.mortgage.balance) : '--' }}
            </div>
          </div>

          <!-- Legend -->
          <div class="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs">
            <div v-if="downPayment > 0" class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-amber-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Down Payment</span>
              <span class="font-medium text-amber-600 dark:text-amber-400">{{ fmtFull(downPayment) }}</span>
              <span class="text-gray-400">({{ downPaymentPct.toFixed(1) }}%)</span>
            </div>
            <div v-if="equityFromAppreciation > 0" class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-green-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Appreciation</span>
              <span class="font-medium text-green-600 dark:text-green-400">{{ fmtFull(equityFromAppreciation) }}</span>
              <span class="text-gray-400">({{ appreciationPct.toFixed(1) }}%)</span>
            </div>
            <div v-if="equityFromPayments > 0" class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-indigo-500"></div>
              <span class="text-gray-600 dark:text-gray-400">Principal Paid</span>
              <span class="font-medium text-indigo-600 dark:text-indigo-400">{{ fmtFull(equityFromPayments) }}</span>
              <span class="text-gray-400">({{ paymentsPct.toFixed(1) }}%)</span>
            </div>
            <div class="flex items-center gap-1.5">
              <div class="w-3 h-3 rounded bg-gray-300 dark:bg-gray-600"></div>
              <span class="text-gray-600 dark:text-gray-400">Remaining Mortgage</span>
              <span class="font-medium text-gray-700 dark:text-gray-300">{{ summary.mortgage ? fmtFull(summary.mortgage.balance) : '--' }}</span>
              <span class="text-gray-400">({{ (100 - equityPct).toFixed(1) }}%)</span>
            </div>
          </div>
        </template>
        <template v-else>
          <p class="text-sm text-gray-400">Need both property value and mortgage data to show equity position.</p>
        </template>
      </div>

      <!-- Two-column layout: Amortization + Payment Breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left column: Amortization -->
        <div class="group/amort relative lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showAmortizationSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/amort:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showAmortizationSql" :sql="SQL.amortization" title="Amortization Schedule" :tables="['mortgages']" @close="showAmortizationSql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Amortization Schedule
            <InfoTooltip text="<strong>Amortization Schedule</strong><br>Shows how the mortgage balance declines over time with each monthly payment. The curve flattens early (more interest) and steepens later (more principal).<br><br><strong>Source:</strong> Calculated from loan terms (balance, rate, payment amount)." />
          </h2>
          <div v-if="amortChartOption" class="h-72">
            <VChart :option="amortChartOption" autoresize class="w-full h-full" />
          </div>
          <div v-else class="h-72 flex items-center justify-center text-sm text-gray-400">
            No amortization data available
          </div>
          <div v-if="amortization?.summary" class="mt-3 text-xs text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
            <span>{{ amortization.summary.months_remaining }} months remaining</span>
            <span>Payoff: {{ amortization.summary.payoff_date ? new Date(amortization.summary.payoff_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '--' }}</span>
            <span>Interest paid: <span class="text-red-500">{{ fmtFull(amortization.summary.total_interest_paid) }}</span></span>
            <span>Interest remaining: <span class="text-red-400">{{ fmtFull(amortization.summary.total_interest_remaining) }}</span></span>
            <span>Principal paid: <span class="text-green-600">{{ fmtFull(amortization.summary.total_principal_paid) }}</span></span>
          </div>
        </div>

        <!-- Right column: Payment Breakdown -->
        <div class="group/pbreak relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showPaymentBreakdownSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/pbreak:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showPaymentBreakdownSql" :sql="SQL.paymentBreakdown" title="Payment Breakdown" :tables="['mortgages']" @close="showPaymentBreakdownSql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Payment Breakdown
            <InfoTooltip text="<strong>Payment Breakdown</strong><br>How your monthly payment is split between principal (builds equity), interest (cost of borrowing), and escrow (property taxes + homeowner's insurance).<br><br><strong>Source:</strong> Mortgage statement payment_breakdown." />
          </h2>
          <div v-if="paymentPieOption" class="h-56">
            <VChart :option="paymentPieOption" autoresize class="w-full h-full" />
          </div>
          <div v-else class="h-56 flex items-center justify-center text-sm text-gray-400">
            No payment data available
          </div>
          <div v-if="summary?.payment_breakdown" class="mt-3 space-y-1.5">
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full bg-green-500 inline-block"></span>
                Principal
              </span>
              <span class="font-medium text-gray-900 dark:text-white">{{ fmtFull(summary.payment_breakdown.principal) }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
                Interest
              </span>
              <span class="font-medium text-gray-900 dark:text-white">{{ fmtFull(summary.payment_breakdown.interest) }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block"></span>
                Escrow
              </span>
              <span class="font-medium text-gray-900 dark:text-white">{{ fmtFull(summary.payment_breakdown.escrow) }}</span>
            </div>
            <div class="flex justify-between text-xs pt-1.5 border-t border-gray-100 dark:border-gray-800">
              <span class="text-gray-500 dark:text-gray-400 font-medium">Total</span>
              <span class="font-bold text-gray-900 dark:text-white">{{ fmtFull(summary.payment_breakdown.total) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
