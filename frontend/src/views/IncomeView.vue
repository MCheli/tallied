<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useImportModal } from '../composables/useImportModal'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { api } from '../api/client'
import type { W2Record } from '../types'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { baseOption, isDark } = useChartDefaults()
const { openImport } = useImportModal()
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const loading = ref(true)
const error = ref('')
const w2Records = ref<W2Record[]>([])
const rsuByYear = ref<Record<string, any>>({})
const selectedYear = ref<number>(0)

// SQL viewer state
const showGrossPaySql = ref(false)
const showTotalTaxSql = ref(false)
const show401kSql = ref(false)
const showBenefitsSql = ref(false)
const showTakeHomeSql = ref(false)
const showCompBreakdownSql = ref(false)
const showWaterfallSql = ref(false)
const showCompHistorySql = ref(false)
const showCompSplitSql = ref(false)
const showYoySql = ref(false)

// SQL queries
const grossPaySql = `SELECT tax_year, gross_pay, base_salary, rsu_income,
       (gross_pay - base_salary - rsu_income) AS other_income
FROM w2_records
WHERE tax_year = :selected_year
ORDER BY tax_year DESC;`

const totalTaxSql = `SELECT tax_year, federal_tax, state_tax,
       social_security, medicare,
       (federal_tax + state_tax + social_security + medicare) AS total_tax,
       ROUND((federal_tax + state_tax + social_security + medicare) * 100.0 / gross_pay, 1) AS effective_rate
FROM w2_records
WHERE tax_year = :selected_year;`

const retirement401kSql = `SELECT tax_year, pretax_401k, roth_401k,
       (pretax_401k + roth_401k) AS total_401k
FROM w2_records
WHERE tax_year = :selected_year;`

const benefitsSql = `SELECT tax_year, employer_health, cafeteria_125, transit,
       (employer_health + cafeteria_125 + transit) AS total_benefits
FROM w2_records
WHERE tax_year = :selected_year;`

const takeHomeSql = `SELECT tax_year, gross_pay,
       (federal_tax + state_tax + social_security + medicare) AS total_tax,
       (pretax_401k + roth_401k + cafeteria_125 + transit) AS pretax_deductions,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k + cafeteria_125 + transit) AS take_home
FROM w2_records
WHERE tax_year = :selected_year;`

const compBreakdownSql = `SELECT tax_year, base_salary, rsu_income, gross_pay,
       ROUND(base_salary * 100.0 / gross_pay, 1) AS salary_pct,
       ROUND(rsu_income * 100.0 / gross_pay, 1) AS rsu_pct
FROM w2_records
WHERE tax_year = :selected_year;`

const waterfallSql = `SELECT tax_year, gross_pay,
       federal_tax, state_tax, social_security, medicare,
       pretax_401k, roth_401k,
       employer_health, cafeteria_125, transit,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k + cafeteria_125 + transit) AS take_home
FROM w2_records
WHERE tax_year = :selected_year;`

const compHistorySql = `SELECT tax_year, gross_pay, base_salary, rsu_income,
       (federal_tax + state_tax + social_security + medicare) AS total_tax,
       (pretax_401k + roth_401k) AS total_401k,
       (employer_health + cafeteria_125 + transit) AS total_benefits,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k + cafeteria_125 + transit) AS take_home
FROM w2_records
ORDER BY tax_year ASC;`

const compSplitSql = `SELECT tax_year, gross_pay, base_salary, rsu_income,
       ROUND(base_salary * 100.0 / gross_pay, 1) AS salary_pct,
       ROUND(rsu_income * 100.0 / gross_pay, 1) AS rsu_pct,
       ROUND((gross_pay - base_salary - rsu_income) * 100.0 / gross_pay, 1) AS other_pct
FROM w2_records
ORDER BY tax_year ASC;`

const yoySql = `SELECT tax_year, gross_pay,
       (federal_tax + state_tax + social_security + medicare) AS total_tax,
       ROUND((federal_tax + state_tax + social_security + medicare) * 100.0 / gross_pay, 1) AS tax_rate,
       (pretax_401k + roth_401k) AS total_401k,
       (employer_health + cafeteria_125 + transit) AS total_benefits,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k + cafeteria_125 + transit) AS take_home
FROM w2_records
ORDER BY tax_year DESC;`

onMounted(async () => {
  try {
    const [history, rsuRes] = await Promise.all([
      api.getIncomeHistory(),
      fetch(`${API}/api/v1/rsu/summary`, { credentials: 'include' }).then(r => r.json()),
    ])
    w2Records.value = (history.w2_records || []).sort((a, b) => b.tax_year - a.tax_year)
    rsuByYear.value = rsuRes.vesting_income_by_year || {}
    if (w2Records.value.length > 0) {
      selectedYear.value = w2Records.value[0].tax_year
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const selectedW2 = computed(() => w2Records.value.find(w => w.tax_year === selectedYear.value))

const years = computed(() => w2Records.value.map(w => w.tax_year).sort())

// ── Computed values for selected year ──

async function refreshData() {
  const [history, rsuRes] = await Promise.all([
    api.getIncomeHistory(),
    fetch(`${API}/api/v1/rsu/summary`, { credentials: 'include' }).then(r => r.json()),
  ])
  w2Records.value = (history.w2_records || []).sort((a, b) => b.tax_year - a.tax_year)
  rsuByYear.value = rsuRes.vesting_income_by_year || {}
  if (w2Records.value.length > 0 && !w2Records.value.find(w => w.tax_year === selectedYear.value)) {
    selectedYear.value = w2Records.value[0].tax_year
  }
}

function v(n: number | null | undefined): number { return n ?? 0 }
function pct(part: number | null | undefined, total: number | null | undefined): number {
  const t = v(total)
  return t > 0 ? v(part) / t * 100 : 0
}

const totalTax = computed(() => {
  const w = selectedW2.value
  if (!w) return 0
  return v(w.federal_tax) + v(w.state_tax) + v(w.social_security) + v(w.medicare)
})

const total401k = computed(() => {
  const w = selectedW2.value
  if (!w) return 0
  return v(w.pretax_401k) + v(w.roth_401k)
})

const totalBenefits = computed(() => {
  const w = selectedW2.value
  if (!w) return 0
  return v(w.cafeteria_125) + v(w.transit) + v(w.employer_health)
})

const pretaxDeductions = computed(() => {
  const w = selectedW2.value
  if (!w) return 0
  return v(w.pretax_401k) + v(w.roth_401k) + v(w.cafeteria_125) + v(w.transit)
})

const takeHome = computed(() => {
  const w = selectedW2.value
  if (!w) return 0
  return v(w.gross_pay) - totalTax.value - pretaxDeductions.value
})

const effectiveRate = computed(() => {
  const w = selectedW2.value
  if (!w || !w.gross_pay) return 0
  return totalTax.value / w.gross_pay * 100
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

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`
}

// ── Waterfall chart ──

const waterfallOption = computed(() => {
  const w = selectedW2.value
  if (!w) return null

  const items: { label: string; value: number; color: string; type: 'start' | 'deduction' | 'end' }[] = []

  items.push({ label: 'Gross Pay', value: v(w.gross_pay), color: '#6366f1', type: 'start' })

  // Taxes (reds/oranges)
  const taxes = [
    { label: 'Federal', value: v(w.federal_tax), color: '#ef4444' },
    { label: 'State', value: v(w.state_tax), color: '#f97316' },
    { label: 'Soc. Security', value: v(w.social_security), color: '#fb923c' },
    { label: 'Medicare', value: v(w.medicare), color: '#fdba74' },
  ].filter(d => d.value > 0)

  // Retirement (purples)
  const retirement = [
    { label: '401(k) Pretax', value: v(w.pretax_401k), color: '#8b5cf6' },
    { label: '401(k) Roth', value: v(w.roth_401k), color: '#a78bfa' },
  ].filter(d => d.value > 0)

  // Benefits (cyans)
  const benefits = [
    { label: 'Health Ins.', value: v(w.employer_health), color: '#06b6d4' },
    { label: 'Cafeteria/FSA', value: v(w.cafeteria_125), color: '#22d3ee' },
    { label: 'Transit', value: v(w.transit), color: '#67e8f9' },
  ].filter(d => d.value > 0)

  for (const d of [...taxes, ...retirement, ...benefits]) {
    items.push({ ...d, type: 'deduction' })
  }

  items.push({ label: 'Take-Home', value: takeHome.value, color: '#22c55e', type: 'end' })

  // Build waterfall: transparent base + visible bar
  let running = v(w.gross_pay)
  const labels = items.map(i => i.label)
  const baseData: (number | string)[] = []
  const valueData: number[] = []
  const colorData: string[] = []

  for (const item of items) {
    if (item.type === 'start') {
      baseData.push(0)
      valueData.push(item.value)
    } else if (item.type === 'deduction') {
      running -= item.value
      baseData.push(running)
      valueData.push(item.value)
    } else {
      baseData.push(0)
      valueData.push(item.value)
    }
    colorData.push(item.color)
  }

  return {
    ...baseOption.value,
    grid: { left: 100, right: 30, top: 20, bottom: 40 },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params : [params]
        const val = p.find((x: any) => x.seriesIndex === 1)
        if (!val) return ''
        return `<strong>${val.name}</strong><br/>${fmtFull(val.value)}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: labels,
      axisLabel: { fontSize: 11, interval: 0, rotate: 30 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        formatter: (v: number) => {
          if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`
          return `$${v}`
        },
      },
      splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
    },
    series: [
      {
        type: 'bar',
        stack: 'waterfall',
        data: baseData,
        itemStyle: { color: 'transparent' },
        emphasis: { itemStyle: { color: 'transparent' } },
      },
      {
        type: 'bar',
        stack: 'waterfall',
        data: valueData.map((val, i) => ({
          value: val,
          itemStyle: { color: colorData[i] },
        })),
        label: {
          show: true,
          position: 'top' as const,
          formatter: (p: any) => fmt(p.value),
          fontSize: 10,
          color: isDark.value ? '#9ca3af' : '#6b7280',
        },
      },
    ],
  }
})

// ── Comp History stacked bar ──

const compHistoryOption = computed(() => {
  // Use W2 records as the authoritative source for income
  // Only show years where we have W2 data
  const w2Sorted = [...w2Records.value].sort((a, b) => a.tax_year - b.tax_year)
  if (w2Sorted.length === 0) return null

  const sortedYears = w2Sorted.map(w => w.tax_year)
  const w2Map = new Map(w2Sorted.map(w => [w.tax_year, w]))

  const salaryData: (number | null)[] = []
  const rsuData: (number | null)[] = []
  const retirementData: (number | null)[] = []
  const taxData: (number | null)[] = []

  for (const year of sortedYears) {
    const w2 = w2Map.get(year)!
    salaryData.push(v(w2.base_salary))
    rsuData.push(v(w2.rsu_income))
    retirementData.push(v(w2.pretax_401k) + v(w2.roth_401k))
    taxData.push(v(w2.federal_tax) + v(w2.state_tax) + v(w2.social_security) + v(w2.medicare))
  }

  // Compute take-home per year for the chart
  const takeHomeData = sortedYears.map(year => {
    const w2 = w2Map.get(year)!
    const tax = v(w2.federal_tax) + v(w2.state_tax) + v(w2.social_security) + v(w2.medicare)
    const pretax = v(w2.pretax_401k) + v(w2.roth_401k) + v(w2.cafeteria_125) + v(w2.transit)
    return v(w2.gross_pay) - tax - pretax
  })

  return {
    ...baseOption.value,
    grid: { left: 55, right: 20, top: 30, bottom: 30 },
    legend: {
      data: ['Take-Home', '401(k)', 'Tax', 'Benefits'],
      top: 0,
      textStyle: { color: isDark.value ? '#9ca3af' : '#6b7280', fontSize: 11 },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const year = params[0].name
        const w2 = w2Map.get(parseInt(year))
        let html = `<strong>${year}</strong>`
        if (w2) {
          html += `<br/>Gross Pay: ${fmtFull(w2.gross_pay)}`
          html += `<br/>&nbsp; Base Salary: ${fmtFull(w2.base_salary)}`
          html += `<br/>&nbsp; RSU Income: ${fmtFull(w2.rsu_income)}`
        }
        for (const p of params) {
          if (p.value != null) {
            html += `<br/>${p.marker} ${p.seriesName}: ${fmtFull(p.value)}`
          }
        }
        return html
      },
    },
    xAxis: {
      type: 'category' as const,
      data: sortedYears.map(String),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: (val: number) => val >= 1000 ? `$${(val / 1000).toFixed(0)}K` : `$${val}` },
      splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
    },
    series: [
      {
        name: 'Take-Home',
        type: 'bar',
        stack: 'comp',
        data: takeHomeData,
        itemStyle: { color: '#22c55e' },
        barMaxWidth: 60,
      },
      {
        name: '401(k)',
        type: 'bar',
        stack: 'comp',
        data: retirementData,
        itemStyle: { color: '#8b5cf6' },
        barMaxWidth: 60,
      },
      {
        name: 'Tax',
        type: 'bar',
        stack: 'comp',
        data: taxData,
        itemStyle: { color: '#ef4444' },
        barMaxWidth: 60,
      },
      {
        name: 'Benefits',
        type: 'bar',
        stack: 'comp',
        data: sortedYears.map(year => {
          const w2 = w2Map.get(year)!
          return v(w2.cafeteria_125) + v(w2.transit) + v(w2.employer_health)
        }),
        itemStyle: { color: '#06b6d4' },
        barMaxWidth: 60,
      },
    ],
  }
})

// ── Income Composition (100% stacked) ──

const compositionOption = computed(() => {
  const w2Sorted = [...w2Records.value].sort((a, b) => a.tax_year - b.tax_year)
  if (w2Sorted.length === 0) return null

  const yearLabels = w2Sorted.map(w => String(w.tax_year))
  const salaryPct = w2Sorted.map(w => {
    const gross = v(w.gross_pay)
    return gross > 0 ? Math.round(v(w.base_salary) / gross * 100) : 0
  })
  const rsuPct = w2Sorted.map(w => {
    const gross = v(w.gross_pay)
    return gross > 0 ? Math.round(v(w.rsu_income) / gross * 100) : 0
  })
  const otherPct = w2Sorted.map(w => {
    const gross = v(w.gross_pay)
    const other = gross - v(w.base_salary) - v(w.rsu_income)
    return gross > 0 ? Math.round(Math.max(0, other) / gross * 100) : 0
  })

  return {
    ...baseOption.value,
    grid: { left: 45, right: 20, top: 30, bottom: 30 },
    legend: {
      data: ['Salary', 'RSU', 'Other'],
      top: 0,
      textStyle: { color: isDark.value ? '#9ca3af' : '#6b7280', fontSize: 11 },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        let html = `<strong>${params[0].name}</strong>`
        for (const p of params) {
          html += `<br/>${p.marker} ${p.seriesName}: ${p.value}%`
        }
        return html
      },
    },
    xAxis: {
      type: 'category' as const,
      data: yearLabels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      max: 100,
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
    },
    series: [
      {
        name: 'Salary',
        type: 'bar',
        stack: 'pct',
        data: salaryPct,
        itemStyle: { color: '#6366f1' },
        barMaxWidth: 50,
      },
      {
        name: 'RSU',
        type: 'bar',
        stack: 'pct',
        data: rsuPct,
        itemStyle: { color: '#22c55e' },
        barMaxWidth: 50,
      },
      {
        name: 'Other',
        type: 'bar',
        stack: 'pct',
        data: otherPct,
        itemStyle: { color: '#9ca3af' },
        barMaxWidth: 50,
      },
    ],
  }
})

// ── Table rows ──

const tableRows = computed(() => {
  return [...w2Records.value]
    .sort((a, b) => b.tax_year - a.tax_year)
    .map(w => {
      const tax = v(w.federal_tax) + v(w.state_tax) + v(w.social_security) + v(w.medicare)
      const retirement = v(w.pretax_401k) + v(w.roth_401k)
      const benefits = v(w.cafeteria_125) + v(w.transit) + v(w.employer_health)
      const th = v(w.gross_pay) - tax - retirement - v(w.cafeteria_125) - v(w.transit)
      const rate = w.gross_pay ? (tax / w.gross_pay * 100) : 0
      return {
        year: w.tax_year,
        gross: w.gross_pay,
        tax,
        rate,
        retirement,
        benefits,
        takeHome: th,
      }
    })
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Income</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Compensation, taxes, and take-home</p>
      </div>
      <!-- Year selector -->
      <div v-if="years.length > 0" class="flex gap-1">
        <button v-for="y in years" :key="y" @click="selectedYear = y"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
          :class="y === selectedYear
            ? 'bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
            : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'">
          {{ y }}
        </button>
      </div>
    </div>

    <!-- Import Button -->
    <div class="flex justify-end">
      <button @click="openImport({ context: 'income', onComplete: refreshData })"
        class="px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
        Import
      </button>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading income data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>
    <div v-else-if="w2Records.length === 0" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No W2 records found.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Add a W2 record in Settings to see income data.</p>
    </div>

    <template v-else-if="selectedW2">
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="group/gross relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showGrossPaySql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/gross:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showGrossPaySql" :sql="grossPaySql" title="Gross Pay" :tables="['w2_records']" @close="showGrossPaySql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Gross Pay <InfoTooltip text="<strong>Gross Pay</strong><br>Total compensation before any deductions or taxes. This is the sum of base salary, RSU vesting income, and any other compensation for the selected year.<br><br><strong>Source:</strong> W2 record gross_pay field for the selected tax year." /></div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(selectedW2.gross_pay) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ fmt(selectedW2.base_salary) }} salary + {{ fmt(selectedW2.rsu_income) }} RSU
            <span v-if="v(selectedW2.gross_pay) - v(selectedW2.base_salary) - v(selectedW2.rsu_income) > 100">
              + {{ fmt(v(selectedW2.gross_pay) - v(selectedW2.base_salary) - v(selectedW2.rsu_income)) }} other
            </span>
          </div>
        </div>
        <div class="group/tax relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTotalTaxSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/tax:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTotalTaxSql" :sql="totalTaxSql" title="Total Tax" :tables="['w2_records']" @close="showTotalTaxSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Total Tax <InfoTooltip text="<strong>Total Tax</strong><br>Sum of all taxes withheld: federal income tax + state income tax + Social Security + Medicare. Does not include employer-side taxes.<br><br><strong>Source:</strong> W2 record tax fields (federal_tax, state_tax, social_security, medicare)." /></div>
          <div class="text-xl font-bold text-red-500 mt-1">{{ fmt(totalTax) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmtPct(effectiveRate) }} effective rate</div>
        </div>
        <div class="group/k401 relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="show401kSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/k401:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="show401kSql" :sql="retirement401kSql" title="401(k) Contributions" :tables="['w2_records']" @close="show401kSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">401(k) <InfoTooltip text="<strong>401(k) Contributions</strong><br>Combined pre-tax and Roth 401(k) contributions for the year. Pre-tax reduces your taxable income; Roth is after-tax but grows tax-free.<br><br><strong>Source:</strong> W2 record pretax_401k + roth_401k fields." /></div>
          <div class="text-xl font-bold text-purple-600 dark:text-purple-400 mt-1">{{ fmt(total401k) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ fmt(selectedW2.pretax_401k) }} pretax + {{ fmt(selectedW2.roth_401k) }} Roth
          </div>
        </div>
        <div class="group/benefits relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showBenefitsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/benefits:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showBenefitsSql" :sql="benefitsSql" title="Benefits" :tables="['w2_records']" @close="showBenefitsSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Benefits <InfoTooltip text="<strong>Benefits</strong><br>Employer-provided benefits value: health insurance (employer contribution), cafeteria/FSA plan (Section 125), and transit/commuter benefits.<br><br><strong>Source:</strong> W2 record employer_health, cafeteria_125, and transit fields." /></div>
          <div class="text-xl font-bold text-cyan-600 dark:text-cyan-400 mt-1">{{ fmt(totalBenefits) }}</div>
          <div class="text-xs text-gray-400 mt-1">Health, cafeteria, transit</div>
        </div>
        <div class="group/takehome relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTakeHomeSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/takehome:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTakeHomeSql" :sql="takeHomeSql" title="Take-Home Pay" :tables="['w2_records']" @close="showTakeHomeSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Take-Home <InfoTooltip text="<strong>Take-Home Pay</strong><br>What actually hits your bank account. Calculated as: gross pay minus all taxes minus pre-tax deductions (401k, cafeteria, transit). Does not subtract employer health (that's employer-paid).<br><br><strong>Formula:</strong> <code>gross - taxes - pretax_401k - roth_401k - cafeteria - transit</code>" /></div>
          <div class="text-xl font-bold text-green-600 dark:text-green-400 mt-1">{{ fmt(takeHome) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmtPct(v(selectedW2.gross_pay) > 0 ? takeHome / v(selectedW2.gross_pay) * 100 : 0) }} of gross</div>
        </div>
      </div>

      <!-- Compensation Breakdown -->
      <div v-if="selectedW2 && (v(selectedW2.base_salary) > 0 || v(selectedW2.rsu_income) > 0)"
        class="group/compbreak relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showCompBreakdownSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/compbreak:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showCompBreakdownSql" :sql="compBreakdownSql" title="Compensation Breakdown" :tables="['w2_records']" @close="showCompBreakdownSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Compensation Breakdown ({{ selectedYear }}) <InfoTooltip text="Shows how your gross pay splits between base salary (regular pay) and RSU vesting income for the selected year. The percentages show each component's share of total compensation.<br><br><strong>Source:</strong> W2 record base_salary and rsu_income fields. If imported via pay stub, these come from the YTD &quot;Regular&quot; and &quot;RSU Gain&quot; lines." /></h2>
        <div class="flex items-center gap-4 mb-3">
          <div class="flex-1">
            <!-- Stacked bar -->
            <div class="h-8 rounded-lg overflow-hidden flex">
              <div class="bg-indigo-500 h-full flex items-center justify-center text-white text-xs font-medium px-2"
                :style="{ width: `${pct(selectedW2.base_salary, selectedW2.gross_pay)}%` }">
                {{ fmt(selectedW2.base_salary) }}
              </div>
              <div class="bg-green-500 h-full flex items-center justify-center text-white text-xs font-medium px-2"
                :style="{ width: `${pct(selectedW2.rsu_income, selectedW2.gross_pay)}%` }">
                {{ fmt(selectedW2.rsu_income) }}
              </div>
            </div>
          </div>
          <div class="text-right flex-shrink-0">
            <div class="text-sm font-bold text-gray-900 dark:text-white">{{ fmt(selectedW2.gross_pay) }}</div>
          </div>
        </div>
        <div class="flex gap-6 text-xs">
          <div class="flex items-center gap-1.5">
            <div class="w-3 h-3 rounded bg-indigo-500"></div>
            <span class="text-gray-600 dark:text-gray-400">Base Salary</span>
            <span class="font-medium text-gray-900 dark:text-white">{{ fmtFull(selectedW2.base_salary) }}</span>
            <span class="text-gray-400">({{ fmtPct(pct(selectedW2.base_salary, selectedW2.gross_pay)) }})</span>
          </div>
          <div class="flex items-center gap-1.5">
            <div class="w-3 h-3 rounded bg-green-500"></div>
            <span class="text-gray-600 dark:text-gray-400">RSU Income</span>
            <span class="font-medium text-gray-900 dark:text-white">{{ fmtFull(selectedW2.rsu_income) }}</span>
            <span class="text-gray-400">({{ fmtPct(pct(selectedW2.rsu_income, selectedW2.gross_pay)) }})</span>
          </div>
        </div>
      </div>

      <!-- Gross-to-Net Waterfall -->
      <div class="group/waterfall relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showWaterfallSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/waterfall:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showWaterfallSql" :sql="waterfallSql" title="Gross to Take-Home" :tables="['w2_records']" @close="showWaterfallSql = false" />
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Gross to Take-Home ({{ selectedYear }}) <InfoTooltip text="Waterfall chart showing every deduction from gross pay to take-home. Red/orange = taxes, purple = retirement contributions, cyan = benefits. Each bar shows the dollar amount being subtracted.<br><br><strong>Source:</strong> All W2 record fields for the selected year. Deductions with $0 are hidden." /></h2>
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">How each deduction reduces your gross pay</p>
        <v-chart v-if="waterfallOption" :option="waterfallOption" style="height: 300px" autoresize />
      </div>

      <!-- Comp History + Composition side by side -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="group/comphist lg:col-span-2 relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showCompHistorySql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/comphist:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showCompHistorySql" :sql="compHistorySql" title="Where Your Gross Pay Goes" :tables="['w2_records']" @close="showCompHistorySql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Where Your Gross Pay Goes <InfoTooltip text="Stacked bar showing how each year's gross pay is allocated: green = take-home, purple = 401(k), red = taxes, cyan = benefits. The total bar height equals gross pay. Hover for full breakdown including salary vs RSU split.<br><br><strong>Source:</strong> W2 records for all available years." /></h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">
            Stacked: take-home + 401(k) + taxes + benefits = gross pay
          </p>
          <v-chart v-if="compHistoryOption" :option="compHistoryOption" style="height: 280px" autoresize />
        </div>
        <div class="group/compsplit relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <button @click="showCompSplitSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/compsplit:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showCompSplitSql" :sql="compSplitSql" title="Comp Split" :tables="['w2_records']" @close="showCompSplitSql = false" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Comp Split <InfoTooltip text="Percentage breakdown of compensation composition by year. Shows what fraction of gross pay comes from base salary vs RSU income vs other compensation.<br><br><strong>Source:</strong> W2 record base_salary and rsu_income as percentage of gross_pay." /></h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">Salary vs RSU % of gross (from W2)</p>
          <v-chart v-if="compositionOption" :option="compositionOption" style="height: 280px" autoresize />
        </div>
      </div>

      <!-- Year-over-Year Table -->
      <div class="group/yoy relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        <button @click="showYoySql = true" class="absolute top-3.5 right-3.5 z-10 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/yoy:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showYoySql" :sql="yoySql" title="Year-over-Year" :tables="['w2_records']" @close="showYoySql = false" />
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Year-over-Year <InfoTooltip text="Summary table of all W2 years. Tax rate = total tax / gross pay. Take-home = gross minus taxes minus pre-tax deductions. Benefits includes employer health, cafeteria/FSA, and transit.<br><br><strong>Source:</strong> All W2 records in the database." /></h2>
        </div>
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400">
              <th class="text-left px-5 py-2.5 font-medium">Year</th>
              <th class="text-right px-3 py-2.5 font-medium">Gross Pay</th>
              <th class="text-right px-3 py-2.5 font-medium">Tax</th>
              <th class="text-right px-3 py-2.5 font-medium">Rate</th>
              <th class="text-right px-3 py-2.5 font-medium">401(k)</th>
              <th class="text-right px-3 py-2.5 font-medium">Benefits</th>
              <th class="text-right px-5 py-2.5 font-medium">Take-Home</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.year"
              class="border-b border-gray-50 dark:border-gray-800 last:border-0"
              :class="row.year === selectedYear ? 'bg-indigo-50/50 dark:bg-indigo-950/20' : ''">
              <td class="px-5 py-2.5 font-medium text-gray-900 dark:text-white font-mono">{{ row.year }}</td>
              <td class="text-right px-3 py-2.5 font-medium text-gray-900 dark:text-white">{{ fmtFull(row.gross) }}</td>
              <td class="text-right px-3 py-2.5 text-red-500">{{ fmtFull(row.tax) }}</td>
              <td class="text-right px-3 py-2.5 text-gray-500 dark:text-gray-400">{{ fmtPct(row.rate) }}</td>
              <td class="text-right px-3 py-2.5 text-purple-600 dark:text-purple-400">{{ fmtFull(row.retirement) }}</td>
              <td class="text-right px-3 py-2.5 text-cyan-600 dark:text-cyan-400">{{ fmtFull(row.benefits) }}</td>
              <td class="text-right px-5 py-2.5 font-semibold text-green-600 dark:text-green-400">{{ fmtFull(row.takeHome) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
