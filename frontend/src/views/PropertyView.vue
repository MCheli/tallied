<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useImportModal } from '../composables/useImportModal'

use([PieChart, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent, CanvasRenderer])

const { baseOption, isDark } = useChartDefaults()
const { openImport } = useImportModal()
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const loading = ref(true)
const error = ref('')
const summary = ref<any>(null)
const amortization = ref<any>(null)

// Valuation update state
const showValuationInput = ref(false)
const newValuation = ref('')
const savingValuation = ref(false)

onMounted(async () => {
  try {
    const [sumRes, amortRes] = await Promise.all([
      fetch(`${API}/api/property/summary`),
      fetch(`${API}/api/property/amortization`),
    ])
    if (sumRes.ok) summary.value = await sumRes.json()
    if (amortRes.ok) amortization.value = await amortRes.json()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function refreshData() {
  try {
    const [sumRes, amortRes] = await Promise.all([
      fetch(`${API}/api/property/summary`),
      fetch(`${API}/api/property/amortization`),
    ])
    if (sumRes.ok) summary.value = await sumRes.json()
    if (amortRes.ok) amortization.value = await amortRes.json()
  } catch (e: any) {
    error.value = e.message
  }
}

// ── Valuation update ──

async function submitValuation() {
  const val = parseFloat(newValuation.value.replace(/[^0-9.]/g, ''))
  if (isNaN(val) || val <= 0) return

  savingValuation.value = true
  try {
    const res = await fetch(`${API}/api/property/valuation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: val, source: 'manual' }),
    })

    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Update failed (${res.status}): ${text}`)
    }

    showValuationInput.value = false
    newValuation.value = ''
    await refreshData()
  } catch (e: any) {
    error.value = e.message
  } finally {
    savingValuation.value = false
  }
}

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

const equityFromPayments = computed(() => {
  if (!summary.value?.mortgage?.original_amount || !summary.value?.mortgage?.balance) return 0
  return summary.value.mortgage.original_amount - summary.value.mortgage.balance
})

const equityFromAppreciation = computed(() => {
  if (!summary.value?.property?.value || !summary.value?.mortgage?.original_amount) return 0
  return summary.value.property.value - summary.value.mortgage.original_amount
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
    <div v-else-if="!summary" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No property data found.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Upload a mortgage statement to get started.</p>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Property Value <InfoTooltip text="<strong>Property Value</strong><br>Current estimated market value of the property.<br><br><strong>Source:</strong> Most recent valuation — may come from Zillow, Redfin, appraisal, or manual entry." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(summary.property.value) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ summary.property.valuation_source || 'Unknown source' }} &middot; {{ fmtDate(summary.property.valuation_date) }}
          </div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Mortgage Balance <InfoTooltip text="<strong>Mortgage Balance</strong><br>Outstanding principal balance on the mortgage. This decreases with each monthly payment as principal is paid down.<br><br><strong>Source:</strong> Mortgage statement or amortization calculation." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(summary.mortgage.balance) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            of {{ fmt(summary.mortgage.original_amount) }} original
          </div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Equity <InfoTooltip text="<strong>Home Equity</strong><br>The portion of the property you actually own. Calculated as property value minus outstanding mortgage balance.<br><br><strong>Formula:</strong> <code>property value - mortgage balance</code>" /></div>
          <div class="text-xl font-bold text-green-600 dark:text-green-400 mt-1">{{ fmt(summary.equity) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ equityPct.toFixed(1) }}% of value</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Interest Rate <InfoTooltip text="<strong>Interest Rate</strong><br>Annual interest rate on the mortgage. This is the fixed (or current adjustable) rate used to calculate monthly interest charges.<br><br><strong>Source:</strong> Mortgage origination documents or statement." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmtPct(summary.mortgage.rate) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ fmtDate(summary.mortgage.origination_date) }} &ndash; {{ fmtDate(summary.mortgage.maturity_date) }}
          </div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Monthly Payment <InfoTooltip text="<strong>Monthly Payment</strong><br>Total monthly mortgage payment including principal, interest, and escrow (taxes + insurance).<br><br><strong>Source:</strong> Mortgage statement payment_breakdown." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(summary.mortgage.monthly_payment) }}</div>
          <div class="text-xs text-gray-400 mt-1">P+I+Escrow</div>
        </div>
      </div>

      <!-- Two-column layout -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left column: Amortization -->
        <div class="lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
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
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
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
          <div v-if="summary.payment_breakdown" class="mt-3 space-y-1.5">
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

      <!-- Equity Visualization -->
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Equity Position
          <InfoTooltip text="<strong>Equity Position</strong><br>Your equity comes from two sources:<br>1. <strong>Principal payments</strong> (blue) — how much of the original loan you've paid down<br>2. <strong>Appreciation</strong> (green) — how much the property has gained in value above what you paid<br><br><strong>Formula:</strong> <code>total equity = (original amount - current balance) + (current value - original amount)</code>" />
        </h2>

        <!-- Stacked bar: appreciation + payments + mortgage -->
        <div class="relative w-full h-10 rounded-lg overflow-hidden flex">
          <div class="bg-green-500 h-full flex items-center justify-center text-white text-[10px] font-medium transition-all"
            :style="{ width: `${appreciationPct}%` }">
            <span v-if="appreciationPct > 8">{{ fmt(equityFromAppreciation) }}</span>
          </div>
          <div class="bg-indigo-500 h-full flex items-center justify-center text-white text-[10px] font-medium transition-all"
            :style="{ width: `${paymentsPct}%` }">
            <span v-if="paymentsPct > 5">{{ fmt(equityFromPayments) }}</span>
          </div>
          <div class="bg-gray-300 dark:bg-gray-600 h-full flex-1 flex items-center justify-center text-gray-600 dark:text-gray-300 text-[10px] font-medium">
            {{ fmt(summary.mortgage.balance) }}
          </div>
        </div>

        <!-- Legend -->
        <div class="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs">
          <div class="flex items-center gap-1.5">
            <div class="w-3 h-3 rounded bg-green-500"></div>
            <span class="text-gray-600 dark:text-gray-400">Appreciation</span>
            <span class="font-medium text-green-600 dark:text-green-400">{{ fmtFull(equityFromAppreciation) }}</span>
            <span class="text-gray-400">({{ appreciationPct.toFixed(1) }}%)</span>
          </div>
          <div class="flex items-center gap-1.5">
            <div class="w-3 h-3 rounded bg-indigo-500"></div>
            <span class="text-gray-600 dark:text-gray-400">Principal Paid</span>
            <span class="font-medium text-indigo-600 dark:text-indigo-400">{{ fmtFull(equityFromPayments) }}</span>
            <span class="text-gray-400">({{ paymentsPct.toFixed(1) }}%)</span>
          </div>
          <div class="flex items-center gap-1.5">
            <div class="w-3 h-3 rounded bg-gray-300 dark:bg-gray-600"></div>
            <span class="text-gray-600 dark:text-gray-400">Remaining Mortgage</span>
            <span class="font-medium text-gray-700 dark:text-gray-300">{{ fmtFull(summary.mortgage.balance) }}</span>
            <span class="text-gray-400">({{ (100 - equityPct).toFixed(1) }}%)</span>
          </div>
        </div>

        <div class="mt-2 text-xs text-gray-400">
          Total equity: <span class="font-medium text-gray-700 dark:text-gray-300">{{ fmtFull(summary.equity) }}</span>
          ({{ equityPct.toFixed(1) }}% of property value)
        </div>
      </div>

      <!-- Property Value / Valuation Section -->
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
              Property Valuation
              <InfoTooltip text="<strong>Property Valuation</strong><br>The estimated market value of your property. You can update this manually or it may come from an external source like Zillow, Redfin, or a formal appraisal.<br><br>Updating the valuation will recalculate your equity position." />
            </h2>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Current value: <span class="font-medium text-gray-700 dark:text-gray-300">{{ fmtFull(summary.property.value) }}</span>
              &middot; Source: {{ summary.property.valuation_source || 'Unknown' }}
              &middot; As of {{ fmtDate(summary.property.valuation_date) }}
            </p>
          </div>
          <button v-if="!showValuationInput" @click="showValuationInput = true"
            class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">
            Update Valuation
          </button>
        </div>
        <div v-if="showValuationInput" class="mt-3 flex items-center gap-3">
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
            <input v-model="newValuation" type="text" placeholder="e.g. 550000"
              class="pl-7 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent w-44"
              @keyup.enter="submitValuation" />
          </div>
          <button @click="submitValuation" :disabled="savingValuation"
            class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {{ savingValuation ? 'Saving...' : 'Save' }}
          </button>
          <button @click="showValuationInput = false; newValuation = ''"
            class="px-3 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
            Cancel
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
