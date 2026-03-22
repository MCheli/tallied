<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { planningApi, type PlanListItem, type PlanTable, type CellValue, type RowStatus } from '../api/planning'
import { api } from '../api/client'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import AssumptionPanel from '../components/planning/AssumptionPanel.vue'
import type { AssumptionResponse, PlanResponse } from '../types'
import { Settings as SettingsIcon, ChevronRight, ChevronDown } from 'lucide-vue-next'

// ── Constants ─────────────────────────────────────────────────────────────────

const CURRENT_YEAR = new Date().getFullYear()

const METRIC_LABELS: Record<string, string> = {
  gross_income: 'Gross Income',
  base_salary: 'Base Salary',
  rsu_income: 'RSU Income',
  tax_paid: 'Tax Paid',
  take_home: 'Take-Home',
  contributions_401k: '401(k)',
  expenses_annual: 'Expenses',
  savings_rate: 'Savings Rate',
  net_worth: 'Net Worth',
  liquid_net_worth: 'Liquid NW',
  investment_balance: 'Investments',
  retirement_balance: 'Retirement',
  home_equity: 'Home Equity',
  mortgage_balance: 'Mortgage',
}

const METRIC_GROUPS: { label: string; metrics: string[] }[] = [
  { label: 'Income', metrics: ['gross_income', 'base_salary', 'rsu_income'] },
  { label: 'Tax & Take-home', metrics: ['tax_paid', 'take_home', 'contributions_401k'] },
  { label: 'Savings', metrics: ['expenses_annual', 'savings_rate'] },
  { label: 'Wealth', metrics: ['net_worth', 'liquid_net_worth', 'investment_balance', 'retirement_balance', 'home_equity', 'mortgage_balance'] },
]

const PERCENT_METRICS = new Set(['savings_rate'])

const METRIC_TOOLTIPS: Record<string, string> = {
  gross_income: 'Total annual compensation (base salary + RSU + other). Actuals from W2 gross_pay. Plan years from projection engine.',
  base_salary: 'Regular salary excluding RSU. Plan years grow by comp growth rate minus RSU share.',
  rsu_income: 'RSU vesting income. Near-term plan years use actual vest schedule; further years use projection % of comp.',
  tax_paid: 'Federal + state + Social Security + Medicare. Plan years estimated at ~35% of salary + RSU tax rate &times; RSU.',
  take_home: 'Gross minus taxes minus pre-tax deductions.',
  contributions_401k: 'Employee 401(k) contributions. Capped at IRS limit (inflation-adjusted).',
  net_worth: 'Total assets minus liabilities at year-end.',
  liquid_net_worth: 'Net worth minus home equity and retirement.',
  investment_balance: 'Taxable investments + company stock.',
  retirement_balance: '401(k) and IRA. Grows by return assumption + contributions + match.',
  home_equity: 'Property value minus mortgage. Appreciates by home_appreciation assumption.',
}

// ── State ─────────────────────────────────────────────────────────────────────

const plans = ref<PlanListItem[]>([])
const plansLoading = ref(false)
const plansError = ref<string | null>(null)

const plan1Id = ref<number | null>(null)
const plan2Id = ref<number | null>(null)

const plan1Data = ref<PlanTable | null>(null)
const plan2Data = ref<PlanTable | null>(null)
const plan1Loading = ref(false)
const plan2Loading = ref(false)
const plan1Error = ref<string | null>(null)
const plan2Error = ref<string | null>(null)

// Assumptions sidebar
const showAssumptions = ref(false)
const assumptions = ref<AssumptionResponse[]>([])
const recalculating = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Column group collapse
const collapsedGroups = ref<Set<string>>(new Set(
  JSON.parse(localStorage.getItem('planning-collapsed-groups') || '["Savings","Wealth"]')
))

function toggleGroup(label: string) {
  const s = new Set(collapsedGroups.value)
  if (s.has(label)) s.delete(label)
  else s.add(label)
  collapsedGroups.value = s
  localStorage.setItem('planning-collapsed-groups', JSON.stringify([...s]))
}

// Expandable narrative rows
const expandedYear = ref<number | null>(null)

// ── Loaders ───────────────────────────────────────────────────────────────────

async function loadPlans() {
  plansLoading.value = true
  plansError.value = null
  try {
    plans.value = await planningApi.listPlans()
    const active = plans.value.find(p => p.is_active) ?? plans.value[0] ?? null
    if (active) plan1Id.value = active.id
  } catch (e) {
    plansError.value = e instanceof Error ? e.message : 'Failed to load plans'
  } finally {
    plansLoading.value = false
  }
}

async function loadPlan1(id: number) {
  plan1Loading.value = true
  plan1Error.value = null
  plan1Data.value = null
  try {
    plan1Data.value = await planningApi.getPlanTable(id)
    // Also load assumptions
    const planRes = await api.getPlan(id) as PlanResponse
    assumptions.value = planRes.assumptions || []
  } catch (e) {
    plan1Error.value = e instanceof Error ? e.message : 'Failed to load plan'
  } finally {
    plan1Loading.value = false
  }
}

async function loadPlan2(id: number) {
  plan2Loading.value = true
  plan2Error.value = null
  plan2Data.value = null
  try {
    plan2Data.value = await planningApi.getPlanTable(id)
  } catch (e) {
    plan2Error.value = e instanceof Error ? e.message : 'Failed to load plan'
  } finally {
    plan2Loading.value = false
  }
}

async function onAssumptionUpdate(key: string, value: number) {
  // Update local state immediately
  const idx = assumptions.value.findIndex(a => a.key === key)
  if (idx >= 0) assumptions.value[idx] = { ...assumptions.value[idx], value }

  // Debounce the API call
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    if (!plan1Id.value) return
    recalculating.value = true
    try {
      await api.updatePlan(plan1Id.value, {
        assumptions: assumptions.value.map(a => ({ key: a.key, value: a.value })),
      })
      plan1Data.value = await planningApi.getPlanTable(plan1Id.value)
    } catch (e) {
      plan1Error.value = e instanceof Error ? e.message : 'Update failed'
    } finally {
      recalculating.value = false
    }
  }, 600)
}

watch(plan1Id, (id) => { if (id != null) loadPlan1(id); else plan1Data.value = null })
watch(plan2Id, (id) => { if (id != null) loadPlan2(id); else plan2Data.value = null })

onMounted(loadPlans)

// ── Derived ───────────────────────────────────────────────────────────────────

const orderedMetrics = computed<string[]>(() => {
  const available = new Set(plan1Data.value?.metrics ?? [])
  const result: string[] = []
  for (const group of METRIC_GROUPS) {
    for (const m of group.metrics) {
      if (available.has(m)) result.push(m)
    }
  }
  return result
})

const years = computed<number[]>(() => plan1Data.value?.years ?? [])
const comparing = computed(() => plan2Data.value !== null)

const assumptionMap = computed<Record<string, number>>(() => {
  const map: Record<string, number> = {}
  for (const a of assumptions.value) map[a.key] = a.value
  return map
})

// ── Formatting ────────────────────────────────────────────────────────────────

function fmtVal(metric: string, value: number | null): string {
  if (value === null || value === undefined) return '—'
  if (PERCENT_METRICS.has(metric)) return value.toFixed(1) + '%'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}K`
  return `${sign}$${Math.round(abs)}`
}

function fmtFull(n: number | null): string {
  if (n === null || n === undefined) return '—'
  return `$${Math.round(n).toLocaleString()}`
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

function formatDelta(_metric: string, v1: number | null, v2: number | null): string {
  if (v1 === null || v2 === null) return '—'
  const delta = v1 - v2
  if (delta === 0) return '—'
  const abs = Math.abs(delta)
  const sign = delta > 0 ? '+' : '-'
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}K`
  return `${sign}$${Math.round(abs)}`
}

function getCellValue(data: PlanTable | null, year: number, metric: string): CellValue | null {
  if (!data) return null
  const row = data.rows[String(year)]
  if (!row) return null
  const cell = row[metric]
  if (!cell || typeof cell === 'string') return null
  return cell as CellValue
}

function getRowStatus(data: PlanTable | null, year: number): RowStatus {
  if (!data) return 'plan'
  const row = data.rows[String(year)]
  if (!row) return 'plan'
  return row.status as RowStatus
}

function getRowMeta(year: number): any {
  if (!plan1Data.value) return {}
  const row = plan1Data.value.rows[String(year)]
  return row?._meta || {}
}

function deltaClass(metric: string, v1: number | null, v2: number | null): string {
  if (v1 === null || v2 === null) return 'text-gray-400 dark:text-gray-500'
  const delta = v1 - v2
  if (delta === 0) return 'text-gray-400 dark:text-gray-500'
  const lowerIsBetter = metric === 'mortgage_balance' || metric === 'tax_paid' || metric === 'expenses_annual'
  const positive = lowerIsBetter ? delta < 0 : delta > 0
  return positive ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-red-500 dark:text-red-400 font-medium'
}

function rowBg(status: string): string {
  if (status === 'actuals') return 'bg-green-50/70 dark:bg-green-950/20 hover:bg-green-50 dark:hover:bg-green-950/30'
  if (status === 'forecast') return 'bg-amber-50/60 dark:bg-amber-950/15 hover:bg-amber-50 dark:hover:bg-amber-950/25'
  return 'bg-white dark:bg-gray-900 hover:bg-gray-50/80 dark:hover:bg-gray-800/50'
}

function stickyBg(status: string): string {
  if (status === 'actuals') return 'bg-green-50/70 dark:bg-green-950/20 group-hover:bg-green-50 dark:group-hover:bg-green-950/30'
  if (status === 'forecast') return 'bg-amber-50/60 dark:bg-amber-950/15 group-hover:bg-amber-50 dark:group-hover:bg-amber-950/25'
  return 'bg-white dark:bg-gray-900 group-hover:bg-gray-50/80 dark:group-hover:bg-gray-800/50'
}

// ── Narrative builder ─────────────────────────────────────────────────────────

function buildNarrative(year: number): string[] {
  const lines: string[] = []
  const row = plan1Data.value?.rows[String(year)]
  const prevRow = plan1Data.value?.rows[String(year - 1)]
  if (!row) return lines

  const a = assumptionMap.value
  const v = (r: any, m: string) => (r?.[m] as CellValue)?.value ?? null
  const meta = getRowMeta(year)

  // Salary
  const prevBase = v(prevRow, 'base_salary')
  const curBase = v(row, 'base_salary')
  if (prevBase && curBase && prevBase > 0) {
    const growth = ((curBase - prevBase) / prevBase * 100)
    lines.push(`Your base salary ${growth >= 0 ? 'increases' : 'decreases'} by ${Math.abs(growth).toFixed(1)}% from ${fmtFull(prevBase)} to ${fmtFull(curBase)}`)
  }

  // RSU
  const rsuVal = v(row, 'rsu_income')
  if (rsuVal !== null) {
    if (meta.rsu_source === 'vest_schedule') {
      lines.push(`RSU vesting income of ${fmtFull(rsuVal)} based on ${meta.rsu_vest_count} known vest event${meta.rsu_vest_count !== 1 ? 's' : ''} from your E-Trade grants`)
    } else {
      const rsuPct = a.rsu_pct_of_comp ? fmtPct(a.rsu_pct_of_comp) : '?'
      lines.push(`RSU income projected at ${fmtFull(rsuVal)} (${rsuPct} of total comp, growing ${fmtPct(a.rsu_pct_annual_increase || 0)}/year)`)
    }
  }

  // Gross
  const grossVal = v(row, 'gross_income')
  if (grossVal !== null) {
    const prevGross = v(prevRow, 'gross_income')
    if (prevGross && prevGross > 0) {
      const growth = ((grossVal - prevGross) / prevGross * 100)
      lines.push(`Total compensation: ${fmtFull(grossVal)} (${growth >= 0 ? '+' : ''}${growth.toFixed(1)}% vs prior year)`)
    }
  }

  // 401k
  const contrib = v(row, 'contributions_401k')
  const retBal = v(row, 'retirement_balance')
  if (contrib !== null && retBal !== null) {
    lines.push(`You'll contribute ${fmtFull(contrib)} to your 401(k), bringing the total to ${fmtFull(retBal)}`)
  }

  // Investments
  const prevInv = v(prevRow, 'investment_balance')
  const curInv = v(row, 'investment_balance')
  if (prevInv && curInv && a.investment_return) {
    lines.push(`Investments grow by ${fmtPct(a.investment_return)} (${fmtFull(prevInv)} → ${fmtFull(curInv)})`)
  }

  // Cash
  if (a.monthly_cash_savings) {
    lines.push(`You'll save $${Math.round(a.monthly_cash_savings).toLocaleString()}/month in cash ($${Math.round(a.monthly_cash_savings * 12).toLocaleString()}/year)`)
  }

  // Home
  const homeEq = v(row, 'home_equity')
  const mortgage = v(row, 'mortgage_balance')
  if (homeEq !== null && a.home_appreciation) {
    const mortgageStr = mortgage !== null ? `, mortgage paid down to ${fmtFull(mortgage)}` : ''
    lines.push(`Home appreciates ${fmtPct(a.home_appreciation)} to ${fmtFull(homeEq)} equity${mortgageStr}`)
  }

  // Net worth milestone
  const prevNW = v(prevRow, 'net_worth')
  const curNW = v(row, 'net_worth')
  if (prevNW && curNW) {
    const prevM = Math.floor(prevNW / 1_000_000)
    const curM = Math.floor(curNW / 1_000_000)
    if (curM > prevM) {
      lines.push(`You'll cross the $${curM}M net worth milestone this year`)
    }
  }

  return lines
}

// Total visible columns for colspan
const totalVisibleCols = computed(() => {
  let count = 2 // Year + Status
  for (const group of METRIC_GROUPS) {
    if (collapsedGroups.value.has(group.label)) {
      count += 1 // collapsed column
    } else {
      count += group.metrics.filter(m => orderedMetrics.value.includes(m)).length
      if (comparing.value) count += group.metrics.filter(m => orderedMetrics.value.includes(m)).length
    }
  }
  return count
})
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-5">
      <h2 class="text-lg font-bold text-gray-900 dark:text-white">
        Financial Planning
        <InfoTooltip text="Year-by-year projection from now until retirement. Green = actuals (W2/balance data). Amber = forecast (current year YTD). White = plan (projections from assumptions).<br><br>Click any plan year row to see a plain English summary of what that year assumes." />
      </h2>

      <div class="flex items-center gap-3">
        <!-- Recalculating indicator -->
        <div v-if="recalculating" class="flex items-center gap-1.5 text-xs text-indigo-500">
          <div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-indigo-400"></div>
          Recalculating…
        </div>
        <div v-else-if="plan1Loading || plan2Loading" class="flex items-center gap-1.5 text-xs text-gray-400">
          <div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-indigo-400"></div>
          Loading…
        </div>

        <!-- Assumptions toggle -->
        <button @click="showAssumptions = !showAssumptions"
          :class="['p-2 rounded-lg border transition-colors', showAssumptions ? 'bg-indigo-50 dark:bg-indigo-950 border-indigo-200 dark:border-indigo-800 text-indigo-600' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300']">
          <SettingsIcon class="w-4 h-4" />
        </button>

        <!-- Plan selectors -->
        <div class="flex items-center gap-2">
          <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Plan</label>
          <select v-model="plan1Id" :disabled="plansLoading"
            class="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-white">
            <option :value="null" disabled>Select plan…</option>
            <option v-for="p in plans" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <span class="text-xs text-gray-400">vs.</span>
        <div class="flex items-center gap-2">
          <label class="text-xs font-medium text-gray-500 dark:text-gray-400">Compare</label>
          <select v-model="plan2Id" :disabled="plansLoading"
            class="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-white">
            <option :value="null">None</option>
            <option v-for="p in plans" :key="p.id" :value="p.id" :disabled="p.id === plan1Id">{{ p.name }}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Errors -->
    <div v-if="plansError || plan1Error || plan2Error" class="mb-4 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
      {{ plansError || plan1Error || plan2Error }}
    </div>

    <!-- Loading / empty states -->
    <div v-if="plansLoading || plan1Loading" class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>
    <div v-else-if="!plan1Data" class="flex items-center justify-center h-64 text-gray-400 text-sm">
      Select a plan above to view the projection table.
    </div>

    <!-- Main layout: table + optional assumptions sidebar -->
    <div v-else class="flex gap-4">
      <!-- Table area -->
      <div class="flex-1 min-w-0 relative">
        <!-- Legend -->
        <div class="flex items-center gap-5 mb-3 text-xs">
          <div class="flex items-center gap-1.5">
            <span class="inline-block w-3 h-3 rounded-sm bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-800"></span>
            <span class="text-gray-500 dark:text-gray-400">Actuals</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="inline-block w-3 h-3 rounded-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800"></span>
            <span class="text-gray-500 dark:text-gray-400">Forecast</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="inline-block w-3 h-3 rounded-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700"></span>
            <span class="text-gray-500 dark:text-gray-400">Plan (click to expand)</span>
          </div>
        </div>

        <!-- Scroll wrapper -->
        <div class="overflow-auto rounded-xl border border-gray-200 dark:border-gray-800" style="max-height: calc(100vh - 200px);">
          <table class="text-xs border-collapse" style="min-width: max-content;">
            <thead>
              <!-- Column headers -->
              <tr class="bg-gray-50 dark:bg-gray-800/80">
                <th class="sticky left-0 top-0 z-30 bg-gray-50 dark:bg-gray-800/80 px-4 py-3 text-left font-semibold text-gray-500 dark:text-gray-400 border-b border-r border-gray-200 dark:border-gray-700 whitespace-nowrap">Year</th>
                <th class="sticky top-0 z-20 bg-gray-50 dark:bg-gray-800/80 px-3 py-3 text-left font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 whitespace-nowrap">Status</th>

                <template v-for="group in METRIC_GROUPS" :key="group.label">
                  <!-- Collapsed group: single thin column -->
                  <th v-if="collapsedGroups.has(group.label)"
                    class="sticky top-0 z-20 bg-gray-50 dark:bg-gray-800/80 border-b border-l-2 border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 px-1"
                    style="min-width: 28px; max-width: 28px;"
                    @click="toggleGroup(group.label)">
                    <span class="text-[9px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500" style="writing-mode: vertical-rl; transform: rotate(180deg);">
                      {{ group.label }}
                    </span>
                  </th>

                  <!-- Expanded group: all metric columns -->
                  <template v-else>
                    <th v-for="(metric, mi) in group.metrics.filter(m => orderedMetrics.includes(m))" :key="metric"
                      :class="['sticky top-0 z-20 bg-gray-50 dark:bg-gray-800/80 px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700 whitespace-nowrap', mi === 0 ? 'border-l-2 border-l-gray-200 dark:border-l-gray-700' : '']">
                      <span v-if="mi === 0" class="cursor-pointer mr-1 text-gray-400 hover:text-gray-600" @click="toggleGroup(group.label)">
                        <ChevronDown class="w-3 h-3 inline" />
                      </span>
                      {{ METRIC_LABELS[metric] ?? metric }}
                      <InfoTooltip v-if="METRIC_TOOLTIPS[metric]" :text="METRIC_TOOLTIPS[metric]" />
                    </th>
                    <!-- Delta headers when comparing -->
                    <template v-if="comparing">
                      <th v-for="metric in group.metrics.filter(m => orderedMetrics.includes(m))" :key="'d-' + metric"
                        class="sticky top-0 z-20 bg-gray-50 dark:bg-gray-800/80 px-2 py-3 text-right text-gray-400 border-b border-gray-200 dark:border-gray-700 whitespace-nowrap">
                        <span class="text-[10px]">Δ</span>
                      </th>
                    </template>
                  </template>
                </template>
              </tr>

              <!-- Group label sub-header -->
              <tr class="bg-white dark:bg-gray-900">
                <th class="sticky left-0 z-30 bg-white dark:bg-gray-900 border-b border-r border-gray-100 dark:border-gray-800" style="min-width: 60px;"></th>
                <th class="sticky z-20 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800" style="min-width: 70px;"></th>
                <template v-for="group in METRIC_GROUPS" :key="'gl-' + group.label">
                  <th v-if="collapsedGroups.has(group.label)"
                    class="bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800"
                    style="min-width: 28px; max-width: 28px;"></th>
                  <template v-else>
                    <th v-for="(metric, mi) in group.metrics.filter(m => orderedMetrics.includes(m))" :key="'gl2-' + metric"
                      :class="['bg-white dark:bg-gray-900 px-4 py-1 text-right border-b border-gray-100 dark:border-gray-800', mi === 0 ? 'border-l-2 border-l-gray-200 dark:border-l-gray-700' : '']">
                      <span v-if="mi === 0" class="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">{{ group.label }}</span>
                    </th>
                    <template v-if="comparing">
                      <th v-for="metric in group.metrics.filter(m => orderedMetrics.includes(m))" :key="'gld-' + metric"
                        class="bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800"></th>
                    </template>
                  </template>
                </template>
              </tr>
            </thead>

            <tbody>
              <template v-for="year in years" :key="year">
                <!-- Data row -->
                <tr :class="['transition-colors group', rowBg(getRowStatus(plan1Data, year))]"
                  :style="getRowStatus(plan1Data, year) === 'plan' ? 'cursor: pointer' : ''"
                  @click="getRowStatus(plan1Data, year) === 'plan' ? (expandedYear = expandedYear === year ? null : year) : null">
                  <!-- Year cell -->
                  <td :class="['sticky left-0 z-10 px-4 py-2.5 font-semibold border-r border-gray-100 dark:border-gray-800 whitespace-nowrap tabular-nums', year === CURRENT_YEAR ? 'border-l-2 border-l-indigo-500 text-indigo-700 dark:text-indigo-300' : 'text-gray-700 dark:text-gray-200', stickyBg(getRowStatus(plan1Data, year))]">
                    <span v-if="getRowStatus(plan1Data, year) === 'plan'" class="text-gray-400 mr-1">
                      <component :is="expandedYear === year ? ChevronDown : ChevronRight" class="w-3 h-3 inline" />
                    </span>
                    {{ year }}
                  </td>

                  <!-- Status badge -->
                  <td class="px-3 py-2.5 whitespace-nowrap">
                    <span :class="['inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide', getRowStatus(plan1Data, year) === 'actuals' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' : getRowStatus(plan1Data, year) === 'forecast' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400']">
                      {{ getRowStatus(plan1Data, year) }}
                    </span>
                  </td>

                  <!-- Metric cells by group -->
                  <template v-for="group in METRIC_GROUPS" :key="group.label + '-' + year">
                    <!-- Collapsed group: empty thin cell -->
                    <td v-if="collapsedGroups.has(group.label)"
                      class="border-l-2 border-l-gray-200 dark:border-l-gray-700 p-0"
                      style="min-width: 28px; max-width: 28px;"></td>

                    <!-- Expanded group: metric cells -->
                    <template v-else>
                      <td v-for="(metric, mi) in group.metrics.filter(m => orderedMetrics.includes(m))" :key="metric + '-' + year"
                        :class="['px-4 py-2.5 text-right tabular-nums whitespace-nowrap', year === CURRENT_YEAR ? 'font-semibold' : 'font-normal', getRowStatus(plan1Data, year) === 'actuals' ? 'text-gray-800 dark:text-gray-100' : getRowStatus(plan1Data, year) === 'forecast' ? 'italic text-gray-600 dark:text-gray-400' : 'text-gray-600 dark:text-gray-400', mi === 0 ? 'border-l-2 border-l-gray-200 dark:border-l-gray-700' : '']">
                        {{ fmtVal(metric, getCellValue(plan1Data, year, metric)?.value ?? null) }}
                      </td>
                      <!-- Delta cells -->
                      <template v-if="comparing">
                        <td v-for="metric in group.metrics.filter(m => orderedMetrics.includes(m))" :key="'d-' + metric + '-' + year"
                          :class="['px-2 py-2.5 text-right tabular-nums whitespace-nowrap text-[11px]', deltaClass(metric, getCellValue(plan1Data, year, metric)?.value ?? null, getCellValue(plan2Data, year, metric)?.value ?? null)]">
                          {{ formatDelta(metric, getCellValue(plan1Data, year, metric)?.value ?? null, getCellValue(plan2Data, year, metric)?.value ?? null) }}
                        </td>
                      </template>
                    </template>
                  </template>
                </tr>

                <!-- Narrative expansion row -->
                <tr v-if="expandedYear === year && getRowStatus(plan1Data, year) === 'plan'">
                  <td :colspan="totalVisibleCols" class="px-6 py-4 bg-indigo-50/40 dark:bg-indigo-950/20 border-b border-indigo-100 dark:border-indigo-900">
                    <div class="text-xs font-semibold text-indigo-700 dark:text-indigo-300 mb-2">What {{ year }} assumes:</div>
                    <ul class="space-y-1.5 text-sm text-gray-700 dark:text-gray-300">
                      <li v-for="(line, i) in buildNarrative(year)" :key="i" class="flex items-start gap-2">
                        <span class="text-indigo-400 mt-0.5 flex-shrink-0">•</span>
                        <span>{{ line }}</span>
                      </li>
                    </ul>
                    <div v-if="buildNarrative(year).length === 0" class="text-sm text-gray-400 italic">No projection data available for this year.</div>
                  </td>
                </tr>
              </template>

              <!-- Empty state -->
              <tr v-if="years.length === 0">
                <td :colspan="totalVisibleCols" class="px-4 py-12 text-center text-gray-400 dark:text-gray-500">
                  No projection data available for this plan.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Comparing footer -->
        <div v-if="comparing && plan2Data" class="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Δ = <span class="font-medium text-gray-600 dark:text-gray-300">{{ plan1Data.plan_name }}</span>
          minus <span class="font-medium text-gray-600 dark:text-gray-300">{{ plan2Data.plan_name }}</span>.
        </div>
      </div>

      <!-- Assumptions Sidebar -->
      <div v-if="showAssumptions" class="w-80 flex-shrink-0">
        <div class="sticky top-6">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Assumptions</h3>
            <button @click="showAssumptions = false" class="text-gray-400 hover:text-gray-600 text-xs">Close</button>
          </div>
          <div class="max-h-[calc(100vh-200px)] overflow-y-auto">
            <AssumptionPanel :assumptions="assumptions" @update="onAssumptionUpdate" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
