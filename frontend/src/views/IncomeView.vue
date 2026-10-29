<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { useImportModal } from '../composables/useImportModal'
import { useDataExplorer } from '../composables/useDataExplorer'
import { splitW2, waterfallSteps, waterfallRunningTotals, type WaterfallStep } from '../composables/useIncomeMath'
import DataExplorer from '../components/common/DataExplorer.vue'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { api } from '../api/client'
import type { W2Record } from '../types'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { baseOption, COLORS, isMobile, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend } = useChartDefaults()
const { money, compact, percent, dash } = useFormatters()
const { openImport } = useImportModal()
const { openData } = useDataExplorer()

const loading = ref(true)
const error = ref('')
const w2Records = ref<W2Record[]>([])
const selectedYear = ref<number>(0)
const showYoySql = ref(false)

// ── Data ──

async function load() {
  try {
    const history = await api.getIncomeHistory()
    w2Records.value = (history.w2_records || []).sort((a, b) => b.tax_year - a.tax_year)
    if (!w2Records.value.find(w => w.tax_year === selectedYear.value) && w2Records.value.length > 0) {
      selectedYear.value = w2Records.value[0].tax_year
    }
    error.value = ''
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

const selectedW2 = computed(() => w2Records.value.find(w => w.tax_year === selectedYear.value))
const years = computed(() => w2Records.value.map(w => w.tax_year).sort((a, b) => a - b))
const split = computed(() => splitW2(selectedW2.value))

// ── "View SQL" text (Postgres; the year is the one selected on the page) ──

const yearSql = (body: string) => `${body}\nFROM w2_records\nWHERE tax_year = ${selectedYear.value || 2025};`

const grossPaySql = computed(() => yearSql(`SELECT tax_year, gross_pay, base_salary, rsu_income,
       gross_pay - base_salary - rsu_income AS other_income`))
const totalTaxSql = computed(() => yearSql(`SELECT tax_year,
       federal_tax + state_tax + social_security + medicare AS total_tax,
       ROUND((federal_tax + state_tax + social_security + medicare) * 100.0 / gross_pay, 1) AS effective_rate`))
const retirement401kSql = computed(() => yearSql(`SELECT tax_year, pretax_401k, roth_401k, pretax_401k + roth_401k AS total_401k`))
const benefitsSql = computed(() => yearSql(`SELECT tax_year, cafeteria_125, transit, cafeteria_125 + transit AS employee_pretax_benefits,
       employer_health AS employer_paid_health`))
const takeHomeSql = computed(() => yearSql(`SELECT tax_year, gross_pay,
       gross_pay
         - (federal_tax + state_tax + social_security + medicare)
         - (pretax_401k + roth_401k)
         - (cafeteria_125 + transit) AS take_home`))
const waterfallSql = computed(() => yearSql(`SELECT tax_year, gross_pay,
       federal_tax, state_tax, social_security, medicare,
       pretax_401k, roth_401k, cafeteria_125, transit,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k) - (cafeteria_125 + transit) AS take_home`))
const compHistorySql = `SELECT tax_year, gross_pay,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k) - (cafeteria_125 + transit) AS take_home,
       pretax_401k + roth_401k AS retirement,
       federal_tax + state_tax + social_security + medicare AS taxes,
       cafeteria_125 + transit AS pretax_benefits,
       employer_health
FROM w2_records
ORDER BY tax_year;`
const compSplitSql = `SELECT tax_year,
       ROUND(base_salary * 100.0 / gross_pay, 1) AS salary_pct,
       ROUND(rsu_income * 100.0 / gross_pay, 1) AS rsu_pct,
       ROUND((gross_pay - base_salary - rsu_income) * 100.0 / gross_pay, 1) AS other_pct
FROM w2_records
ORDER BY tax_year;`
const yoySql = `SELECT tax_year, gross_pay,
       federal_tax + state_tax + social_security + medicare AS taxes,
       ROUND((federal_tax + state_tax + social_security + medicare) * 100.0 / gross_pay, 1) AS tax_rate,
       pretax_401k + roth_401k AS retirement,
       cafeteria_125 + transit AS pretax_benefits,
       gross_pay - (federal_tax + state_tax + social_security + medicare)
                 - (pretax_401k + roth_401k) - (cafeteria_125 + transit) AS take_home
FROM w2_records
ORDER BY tax_year DESC;`

// ── Waterfall ──

const GROUP_COLORS: Record<WaterfallStep['group'], string> = {
  gross: COLORS[0],
  tax: COLORS[3],
  retirement: COLORS[5],
  benefit: COLORS[4],
  takeHome: COLORS[1],
}

const waterfallOption = computed(() => {
  const steps = waterfallSteps(split.value)
  const totals = waterfallRunningTotals(steps)
  const baseData = steps.map((s, i) => (s.kind === 'deduction' ? totals[i] : 0))
  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params : [params]
        const val = p.find((x: any) => x.seriesIndex === 1)
        return val ? `<strong>${val.name}</strong><br/>${money(val.value)}` : ''
      },
    },
    xAxis: {
      type: 'category' as const,
      data: steps.map(s => s.label),
      axisLabel: { ...mobileAxis(), interval: 0, rotate: isMobile.value ? 60 : 30 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } },
    },
    series: [
      { type: 'bar', stack: 'waterfall', data: baseData, itemStyle: { color: 'transparent' }, emphasis: { itemStyle: { color: 'transparent' } }, silent: true },
      {
        type: 'bar',
        stack: 'waterfall',
        data: steps.map(s => ({ value: s.value, itemStyle: { color: GROUP_COLORS[s.group] } })),
        label: {
          show: !isMobile.value,
          position: 'top' as const,
          formatter: (p: any) => compact(p.value),
          fontSize: 10,
          color: mutedTextColor.value,
        },
      },
    ],
  }
})

// ── Where your gross pay goes (stack sums to gross) ──

const sortedW2 = computed(() => [...w2Records.value].sort((a, b) => a.tax_year - b.tax_year))

const compHistoryOption = computed(() => {
  const rows = sortedW2.value.map(w => ({ year: w.tax_year, ...splitW2(w) }))
  const series = [
    { name: 'Take-Home', key: 'takeHome' as const, color: GROUP_COLORS.takeHome },
    { name: '401(k)', key: 'retirement' as const, color: GROUP_COLORS.retirement },
    { name: 'Taxes', key: 'taxes' as const, color: GROUP_COLORS.tax },
    { name: 'Pre-tax benefits', key: 'pretaxBenefits' as const, color: GROUP_COLORS.benefit },
  ]
  return {
    ...baseOption.value,
    legend: { ...mobileLegend(), data: series.map(s => s.name) },
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 28 : 36 },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const row = rows.find(r => String(r.year) === params[0].name)
        let html = `<strong>${params[0].name}</strong>`
        if (row) {
          html += `<br/>Gross pay: ${money(row.gross)} (${money(row.baseSalary)} salary + ${money(row.rsuIncome)} RSU)`
        }
        for (const p of params) html += `<br/>${p.marker} ${p.seriesName}: ${money(p.value)}`
        if (row && row.employerHealth > 0) html += `<br/>Employer-paid health (not in the bar): ${money(row.employerHealth)}`
        return html
      },
    },
    xAxis: { type: 'category' as const, data: rows.map(r => String(r.year)), axisTick: { show: false }, axisLabel: mobileAxis(), axisLine: { lineStyle: { color: axisLineColor.value } } },
    yAxis: { type: 'value' as const, axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } } },
    series: series.map(s => ({
      name: s.name, type: 'bar', stack: 'gross', barMaxWidth: 60,
      data: rows.map(r => r[s.key]), itemStyle: { color: s.color },
    })),
  }
})

// ── Comp split (100% stacked) ──

const compositionOption = computed(() => {
  const rows = sortedW2.value.map(w => ({ year: w.tax_year, ...splitW2(w) }))
  const pctOf = (part: number, gross: number) => (gross > 0 ? Math.round((part / gross) * 100) : 0)
  return {
    ...baseOption.value,
    legend: { ...mobileLegend(), data: ['Salary', 'RSU', 'Other'] },
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 28 : 36 },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        let html = `<strong>${params[0].name}</strong>`
        for (const p of params) html += `<br/>${p.marker} ${p.seriesName}: ${p.value}%`
        return html
      },
    },
    xAxis: { type: 'category' as const, data: rows.map(r => String(r.year)), axisTick: { show: false }, axisLabel: mobileAxis(), axisLine: { lineStyle: { color: axisLineColor.value } } },
    yAxis: { type: 'value' as const, max: 100, axisLabel: { ...mobileAxis(), formatter: '{value}%' }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } } },
    series: [
      { name: 'Salary', type: 'bar', stack: 'pct', barMaxWidth: 50, data: rows.map(r => pctOf(r.baseSalary, r.gross)), itemStyle: { color: COLORS[0] } },
      { name: 'RSU', type: 'bar', stack: 'pct', barMaxWidth: 50, data: rows.map(r => pctOf(r.rsuIncome, r.gross)), itemStyle: { color: COLORS[1] } },
      { name: 'Other', type: 'bar', stack: 'pct', barMaxWidth: 50, data: rows.map(r => pctOf(r.other, r.gross)), itemStyle: { color: mutedTextColor.value } },
    ],
  }
})

const tableRows = computed(() => w2Records.value.map(w => ({ year: w.tax_year, ...splitW2(w) })))
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6 min-w-0">
    <PageHeader
      title="Income"
      subtitle="Compensation, taxes and take-home, one tax year at a time"
      tooltip="<strong>Income</strong><br>Every figure on this page comes from the W-2 record for the selected tax year, entered on Settings → Income or read from a W-2 or pay stub by the import. Take-home = gross − taxes − 401(k) − employee pre-tax benefits; employer-paid health insurance is shown for information and never deducted."
    >
      <button @click="openData('income')" class="min-h-10 px-4 py-2 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">Data</button>
      <button @click="openImport({ context: 'income', onComplete: load })" class="min-h-10 px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Import</button>
      <template #below>
        <div v-if="years.length > 0" class="flex flex-wrap gap-1.5" role="tablist" aria-label="Tax year">
          <button v-for="y in years" :key="y" @click="selectedYear = y" role="tab" :aria-selected="y === selectedYear"
            class="min-h-10 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
            :class="y === selectedYear
              ? 'bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
              : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'">
            {{ y }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div v-if="loading" class="text-sm text-gray-400">Loading income data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>
    <div v-else-if="w2Records.length === 0" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
      <p class="text-gray-500 dark:text-gray-400">No W-2 records yet.</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Import a W-2 or pay stub, or add a year on Settings → Income.</p>
    </div>

    <template v-else-if="selectedW2">
      <!-- Tiles -->
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard label="Gross Pay" :value="compact(split.gross)"
          :subtitle="`${compact(split.baseSalary)} salary + ${compact(split.rsuIncome)} RSU${split.other > 100 ? ' + ' + compact(split.other) + ' other' : ''}`"
          info="<strong>Gross Pay</strong><br>Total compensation before any tax or deduction: base salary + RSU vesting income + anything else on the W-2.<br><br><strong>Source:</strong> w2_records.gross_pay for the selected year."
          :sql="grossPaySql" :sql-tables="['w2_records']" />
        <MetricCard label="Taxes" :value="compact(split.taxes)" :subtitle="`${percent(split.effectiveRate)} effective rate`"
          info="<strong>Taxes</strong><br>Federal income tax + state income tax + Social Security + Medicare withheld. Employer-side payroll taxes are not included.<br><br><strong>Source:</strong> federal_tax, state_tax, social_security, medicare."
          :sql="totalTaxSql" :sql-tables="['w2_records']" />
        <MetricCard label="401(k)" :value="compact(split.retirement)" :subtitle="`${compact(split.pretax401k)} pre-tax + ${compact(split.roth401k)} Roth`"
          info="<strong>401(k) contributions</strong><br>Your pre-tax and Roth 401(k) deferrals for the year. Both are deducted from pay, so both reduce take-home.<br><br><strong>Source:</strong> pretax_401k + roth_401k."
          :sql="retirement401kSql" :sql-tables="['w2_records']" />
        <MetricCard label="Benefits" :value="compact(split.pretaxBenefits)"
          :subtitle="split.employerHealth > 0 ? `+ ${compact(split.employerHealth)} employer-paid health` : 'Cafeteria/FSA + transit'"
          info="<strong>Benefits</strong><br>The tile shows what you paid pre-tax: cafeteria/Section 125 (FSA, health premiums) + transit/commuter. These reduce take-home.<br><br>The employer's health insurance contribution (Box 12 DD) is shown underneath as <em>employer-paid</em>: it is information about the value of the plan and is never deducted from your pay.<br><br><strong>Source:</strong> cafeteria_125, transit, employer_health."
          :sql="benefitsSql" :sql-tables="['w2_records']" />
        <div class="col-span-2 lg:col-span-1 min-w-0">
          <MetricCard label="Take-Home" :value="compact(split.takeHome)" :subtitle="`${percent(split.takeHomeRate)} of gross`"
            info="<strong>Take-Home</strong><br>What actually reached your bank account.<br><br><strong>Formula:</strong> gross − taxes − 401(k) − cafeteria/FSA − transit. Employer-paid health is not subtracted. The same formula is used by the waterfall, the stacked bar and the year-over-year table."
            :sql="takeHomeSql" :sql-tables="['w2_records']" />
        </div>
      </div>

      <!-- Compensation breakdown -->
      <ChartContainer :title="`Compensation Breakdown (${selectedYear})`" subtitle="Base salary vs RSU vesting income as a share of gross pay"
        info="How gross pay splits between base salary and RSU vesting income for the selected year. Anything else on the W-2 (bonus, other comp) is the 'other' remainder.<br><br><strong>Source:</strong> base_salary and rsu_income; for pay stubs these come from the YTD Regular and RSU Gain lines."
        :sql="grossPaySql" :sql-tables="['w2_records']" :empty="split.gross <= 0" empty-text="No gross pay recorded for this year">
        <div class="flex items-center gap-4 mb-3 min-w-0">
          <div class="flex-1 min-w-0">
            <div class="h-8 rounded-lg overflow-hidden flex">
              <div class="h-full flex items-center justify-center text-white text-xs font-medium px-2 truncate" :style="{ width: `${(split.baseSalary / split.gross) * 100}%`, background: COLORS[0] }">{{ compact(split.baseSalary) }}</div>
              <div class="h-full flex items-center justify-center text-white text-xs font-medium px-2 truncate" :style="{ width: `${(split.rsuIncome / split.gross) * 100}%`, background: COLORS[1] }">{{ compact(split.rsuIncome) }}</div>
              <div v-if="split.other > 0" class="h-full flex items-center justify-center text-white text-xs font-medium px-2 truncate" :style="{ width: `${(split.other / split.gross) * 100}%`, background: mutedTextColor }">{{ compact(split.other) }}</div>
            </div>
          </div>
          <div class="text-sm font-bold text-gray-900 dark:text-white flex-shrink-0">{{ compact(split.gross) }}</div>
        </div>
        <div class="flex flex-wrap gap-x-6 gap-y-1 text-xs">
          <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded" :style="{ background: COLORS[0] }"></span><span class="text-gray-600 dark:text-gray-400">Base Salary</span><span class="font-medium text-gray-900 dark:text-white">{{ money(split.baseSalary) }}</span><span class="text-gray-400">({{ percent(split.gross > 0 ? split.baseSalary / split.gross : 0) }})</span></span>
          <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded" :style="{ background: COLORS[1] }"></span><span class="text-gray-600 dark:text-gray-400">RSU Income</span><span class="font-medium text-gray-900 dark:text-white">{{ money(split.rsuIncome) }}</span><span class="text-gray-400">({{ percent(split.gross > 0 ? split.rsuIncome / split.gross : 0) }})</span></span>
          <span v-if="split.other > 0" class="flex items-center gap-1.5"><span class="w-3 h-3 rounded" :style="{ background: mutedTextColor }"></span><span class="text-gray-600 dark:text-gray-400">Other</span><span class="font-medium text-gray-900 dark:text-white">{{ money(split.other) }}</span></span>
        </div>
      </ChartContainer>

      <!-- Waterfall -->
      <ChartContainer :title="`Gross to Take-Home (${selectedYear})`" subtitle="Each deduction steps gross pay down; the last bar is the Take-Home tile"
        info="Waterfall from gross pay to take-home. Red = taxes, violet = 401(k), cyan = employee pre-tax benefits, green = take-home. Deductions of $0 are hidden. Employer-paid health is not a step because it never leaves your pay.<br><br><strong>Source:</strong> the W-2 fields for the selected year."
        :sql="waterfallSql" :sql-tables="['w2_records']" :empty="split.gross <= 0" empty-text="No gross pay recorded for this year">
        <v-chart :option="waterfallOption" :style="{ height: isMobile ? '300px' : '320px' }" autoresize />
      </ChartContainer>

      <!-- History + composition -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 min-w-0">
          <ChartContainer title="Where Your Gross Pay Goes" subtitle="Take-home + 401(k) + taxes + pre-tax benefits = gross pay, per year"
            info="Stacked bar per W-2 year. The bar height is gross pay exactly: green take-home, violet 401(k), red taxes, cyan employee pre-tax benefits. Employer-paid health is listed in the tooltip but is not part of the bar.<br><br><strong>Source:</strong> all W-2 records."
            :sql="compHistorySql" :sql-tables="['w2_records']">
            <v-chart :option="compHistoryOption" style="height: 280px" autoresize />
          </ChartContainer>
        </div>
        <ChartContainer title="Comp Split" subtitle="Salary vs RSU share of gross, per year"
          info="Percentage of gross pay from base salary, RSU income and anything else, for each W-2 year.<br><br><strong>Source:</strong> base_salary and rsu_income over gross_pay."
          :sql="compSplitSql" :sql-tables="['w2_records']">
          <v-chart :option="compositionOption" style="height: 280px" autoresize />
        </ChartContainer>
      </div>

      <!-- Year-over-year -->
      <div class="group/yoy relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
        <button @click="showYoySql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/yoy:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showYoySql" :sql="yoySql" title="Year-over-Year" :tables="['w2_records']" @close="showYoySql = false" />
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3 pr-8">Year-over-Year <InfoTooltip text="One row per W-2 year. Rate = taxes ÷ gross. Benefits = cafeteria/FSA + transit (employee pre-tax). Take-home uses the same formula as the tiles above." /></h3>
        <DataTable :columns="7" :empty="tableRows.length === 0" empty-text="No W-2 years">
          <thead>
            <tr>
              <th>Year</th>
              <th class="text-right">Gross Pay</th>
              <th class="text-right">Taxes</th>
              <th class="text-right">Rate</th>
              <th class="text-right">401(k)</th>
              <th class="text-right">Benefits</th>
              <th class="text-right">Take-Home</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.year" :class="row.year === selectedYear ? 'bg-indigo-50/50 dark:bg-indigo-950/20' : ''">
              <td class="font-medium text-gray-900 dark:text-white font-mono whitespace-nowrap">{{ row.year }}</td>
              <td class="text-right font-medium text-gray-900 dark:text-white whitespace-nowrap">{{ money(row.gross) }}</td>
              <td class="text-right text-red-500 whitespace-nowrap">{{ money(row.taxes) }}</td>
              <td class="text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ percent(row.effectiveRate) }}</td>
              <td class="text-right text-purple-600 dark:text-purple-400 whitespace-nowrap">{{ money(row.retirement) }}</td>
              <td class="text-right text-cyan-600 dark:text-cyan-400 whitespace-nowrap">{{ row.pretaxBenefits > 0 ? money(row.pretaxBenefits) : dash }}</td>
              <td class="text-right font-semibold text-green-600 dark:text-green-400 whitespace-nowrap">{{ money(row.takeHome) }}</td>
            </tr>
          </tbody>
        </DataTable>
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
