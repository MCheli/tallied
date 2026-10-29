<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { planningApi, type PlanListItem, type PlanTable, type CellValue, type RowStatus } from '../api/planning'
import { api } from '../api/client'
import PageHeader from '../components/common/PageHeader.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import AssumptionPanel from '../components/planning/AssumptionPanel.vue'
import { useFormatters } from '../composables/useFormatters'
import { useMediaQuery } from '../composables/useMediaQuery'
import { apiErrorMessage } from '../composables/useApiError'
import { METRIC_GROUPS, METRIC_LABELS, LOWER_IS_BETTER, isRetiredYear, orderedMetrics as orderMetrics } from '../composables/usePlanningTable'
import type { AssumptionResponse, PlanResponse } from '../types'
import { Settings as SettingsIcon, ChevronRight, ChevronDown, X } from 'lucide-vue-next'

const CURRENT_YEAR = new Date().getFullYear()
const { money, compact, percent, dash } = useFormatters()
const isNarrow = useMediaQuery('(max-width: 1023px)')

const METRIC_TOOLTIPS: Record<string, string> = {
  gross_income: 'Total compensation (base salary + RSU). Actual years from the W-2 gross pay; plan years from the projection engine.',
  base_salary: 'Regular salary excluding RSU. Plan years grow by the total comp growth assumption minus the RSU share.',
  rsu_income: 'RSU vesting income. Years with scheduled vests use the vest schedule at today\'s price; later years use the RSU % of comp assumption.',
  tax_paid: 'Actual years: federal + state + Social Security + Medicare from the W-2. Plan years: 35% of salary plus the RSU tax rate × RSU income.',
  take_home: 'Gross minus taxes and pre-tax deductions (401(k), cafeteria, transit in actual years).',
  contributions_401k: 'Employee 401(k) contributions: salary × the 401(k) contribution assumption, capped at the IRS limit (inflation-adjusted).',
  net_worth: 'Actual years: latest balance snapshots in that year. Plan years: the engine\'s year-end total.',
  liquid_net_worth: 'Net worth minus home equity and retirement.',
  investment_balance: 'Taxable investments plus company stock.',
  retirement_balance: '401(k) balance: grows by the return assumption plus contributions and match.',
  home_equity: 'Property value minus mortgage, appreciating by the home appreciation assumption.',
  mortgage_balance: 'Current mortgage balance (shown for actual and forecast years).',
}

// ── State ──
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

const showCreatePlan = ref(false)
const newPlanName = ref('')
const newPlanType = ref('base')
const creatingPlan = ref(false)

const showAssumptions = ref(false)
const assumptions = ref<AssumptionResponse[]>([])
const recalculating = ref(false)
const recalcError = ref<string | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const collapsedGroups = ref<Set<string>>(new Set(readCollapsed()))
function readCollapsed(): string[] {
  try {
    const raw = localStorage.getItem('planning-collapsed-groups')
    const parsed = raw ? JSON.parse(raw) : ['Wealth']
    return Array.isArray(parsed) ? parsed.filter((g: string) => METRIC_GROUPS.some((mg) => mg.label === g)) : ['Wealth']
  } catch {
    return ['Wealth']
  }
}
function toggleGroup(label: string) {
  const s = new Set(collapsedGroups.value)
  if (s.has(label)) s.delete(label)
  else s.add(label)
  collapsedGroups.value = s
  try { localStorage.setItem('planning-collapsed-groups', JSON.stringify([...s])) } catch { /* ignore */ }
}

const showProjectionSql = ref(false)
const showAssumptionsSql = ref(false)
const expandedYear = ref<number | null>(null)

// ── SQL (Postgres) ──
const projectionTableSql = `-- Plan years come from the stored projection; actual years from w2_records and balance_snapshots
SELECT pv.name AS plan_name, pp.year, pp.age, pp.phase,
       pp.salary, pp.rsu_income, pp.total_comp,
       pp.cash, pp.investments, pp.company_stock, pp.home_equity, pp.retirement_bal,
       pp.net_worth, pp.withdrawal
FROM plan_projections pp
JOIN plan_versions pv ON pv.id = pp.plan_id
WHERE pv.id = :plan_id
ORDER BY pp.year;

-- Actual years: W-2 figures per tax year
SELECT tax_year, gross_pay, base_salary, rsu_income,
       federal_tax + state_tax + social_security + medicare AS tax_paid,
       pretax_401k + roth_401k AS contributions_401k
FROM w2_records
ORDER BY tax_year;

-- Actual years: last balance per account within the year, summed by display group
SELECT EXTRACT(YEAR FROM bs.snapshot_date)::int AS year, a.display_group, SUM(bs.balance) AS balance
FROM balance_snapshots bs
JOIN accounts a ON a.id = bs.account_id
WHERE bs.snapshot_date = (
  SELECT MAX(snapshot_date) FROM balance_snapshots b2
  WHERE b2.account_id = bs.account_id AND EXTRACT(YEAR FROM b2.snapshot_date) = EXTRACT(YEAR FROM bs.snapshot_date))
GROUP BY 1, 2
ORDER BY 1, 2;`

const assumptionsSql = `SELECT pa.key, pa.display_name, pa.category, pa.value, pa.description, pa.sensitivity
FROM plan_assumptions pa
JOIN plan_versions pv ON pv.id = pa.plan_id
WHERE pv.id = :plan_id
ORDER BY pa.category, pa.key;`

// ── Loaders ──
async function createPlan() {
  if (!newPlanName.value.trim()) return
  creatingPlan.value = true
  plansError.value = null
  try {
    const plan = await api.createPlan({ name: newPlanName.value.trim(), scenario_type: newPlanType.value, assumptions: [] })
    showCreatePlan.value = false
    newPlanName.value = ''
    await loadPlans()
    plan1Id.value = plan.id
  } catch (e) {
    plansError.value = apiErrorMessage(e, 'Could not create the plan')
  } finally {
    creatingPlan.value = false
  }
}

async function loadPlans() {
  plansLoading.value = true
  plansError.value = null
  try {
    plans.value = await planningApi.listPlans()
    const active = plans.value.find((p) => p.is_active) ?? plans.value[0] ?? null
    if (active && plan1Id.value == null) plan1Id.value = active.id
  } catch (e) {
    plansError.value = apiErrorMessage(e, 'Failed to load plans')
  } finally {
    plansLoading.value = false
  }
}

async function loadPlan1(id: number) {
  plan1Loading.value = true
  plan1Error.value = null
  plan1Data.value = null
  try {
    const [table, planRes] = await Promise.all([planningApi.getPlanTable(id), api.getPlan(id) as Promise<PlanResponse>])
    plan1Data.value = table
    assumptions.value = planRes.assumptions || []
  } catch (e) {
    plan1Error.value = apiErrorMessage(e, 'Failed to load plan')
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
    plan2Error.value = apiErrorMessage(e, 'Failed to load plan')
  } finally {
    plan2Loading.value = false
  }
}

async function onAssumptionUpdate(key: string, value: number) {
  const idx = assumptions.value.findIndex((a) => a.key === key)
  if (idx >= 0) assumptions.value[idx] = { ...assumptions.value[idx], value }
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    if (!plan1Id.value) return
    recalculating.value = true
    recalcError.value = null
    try {
      // Send the whole assumption so labels, categories and sensitivities survive the update.
      await api.updatePlan(plan1Id.value, {
        assumptions: assumptions.value.map((a) => ({
          key: a.key, value: a.value, display_name: a.display_name, category: a.category, sensitivity: a.sensitivity, description: a.description,
        })),
      })
      plan1Data.value = await planningApi.getPlanTable(plan1Id.value)
    } catch (e) {
      recalcError.value = apiErrorMessage(e, 'Update failed')
    } finally {
      recalculating.value = false
    }
  }, 600)
}

watch(plan1Id, (id) => { if (id != null) loadPlan1(id); else plan1Data.value = null })
watch(plan2Id, (id) => { if (id != null) loadPlan2(id); else plan2Data.value = null })
onMounted(loadPlans)

// ── Derived ──
const orderedMetrics = computed<string[]>(() => orderMetrics(plan1Data.value?.metrics ?? []))
const years = computed<number[]>(() => plan1Data.value?.years ?? [])
const comparing = computed(() => plan2Data.value !== null)
const retirementYear = computed(() => plan1Data.value?.retirement_year ?? null)
const subtitle = computed(() => {
  const t = plan1Data.value
  if (!t?.retirement_year) return 'Year-by-year projection from now to retirement'
  return `Retirement at ${t.retirement_age} in ${t.retirement_year} · age ${t.current_age} today`
})
const assumptionMap = computed<Record<string, number>>(() => Object.fromEntries(assumptions.value.map((a) => [a.key, a.value])))

function groupMetrics(group: { metrics: string[] }): string[] {
  return group.metrics.filter((m) => orderedMetrics.value.includes(m))
}

function fmtVal(value: number | null): string {
  return value == null ? dash : compact(value)
}

function formatDelta(v1: number | null, v2: number | null): string {
  if (v1 === null || v2 === null) return dash
  const delta = v1 - v2
  if (delta === 0) return dash
  return `${delta > 0 ? '+' : '-'}${compact(Math.abs(delta)).replace('$', '$')}`
}

function getCellValue(data: PlanTable | null, year: number, metric: string): CellValue | null {
  const row = data?.rows[String(year)]
  const cell = row?.[metric]
  if (!cell || typeof cell === 'string') return null
  return cell as CellValue
}

function getRowStatus(data: PlanTable | null, year: number): RowStatus {
  return (data?.rows[String(year)]?.status as RowStatus) ?? 'plan'
}

function getRowMeta(year: number): any {
  return plan1Data.value?.rows[String(year)]?._meta || {}
}

function deltaClass(metric: string, v1: number | null, v2: number | null): string {
  if (v1 === null || v2 === null) return 'text-gray-400 dark:text-gray-500'
  const delta = v1 - v2
  if (delta === 0) return 'text-gray-400 dark:text-gray-500'
  const positive = LOWER_IS_BETTER.has(metric) ? delta < 0 : delta > 0
  return positive ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-red-500 dark:text-red-400 font-medium'
}

function rowBg(year: number): string {
  const status = getRowStatus(plan1Data.value, year)
  if (status === 'actuals') return 'bg-green-50/70 dark:bg-green-950/20'
  if (status === 'forecast') return 'bg-amber-50/60 dark:bg-amber-950/15'
  if (isRetiredYear(year, retirementYear.value)) return 'bg-slate-100/70 dark:bg-slate-800/40'
  return 'bg-white dark:bg-gray-900'
}

// ── Narrative ──
function buildNarrative(year: number): string[] {
  const lines: string[] = []
  const row = plan1Data.value?.rows[String(year)]
  const prevRow = plan1Data.value?.rows[String(year - 1)]
  if (!row) return lines
  const a = assumptionMap.value
  const v = (r: any, m: string) => (r?.[m] as CellValue)?.value ?? null
  const meta = getRowMeta(year)

  if (isRetiredYear(year, retirementYear.value)) lines.push(`Retired: no salary or RSU income; spending of ${money(a.retirement_spending)} a year (inflated) is withdrawn from cash, then investments, then retirement accounts.`)

  const prevBase = v(prevRow, 'base_salary'), curBase = v(row, 'base_salary')
  if (prevBase && curBase && prevBase > 0 && curBase > 0) {
    const growth = ((curBase - prevBase) / prevBase) * 100
    lines.push(`Base salary ${growth >= 0 ? 'rises' : 'falls'} ${Math.abs(growth).toFixed(1)}% from ${money(prevBase)} to ${money(curBase)}`)
  }
  const rsuVal = v(row, 'rsu_income')
  if (rsuVal) {
    if (meta.rsu_source === 'vest_schedule') lines.push(`RSU income of ${money(rsuVal)} from ${meta.rsu_vest_count} scheduled vest event${meta.rsu_vest_count !== 1 ? 's' : ''} at today's share price`)
    else lines.push(`RSU income projected at ${money(rsuVal)} (${percent(a.rsu_pct_of_comp)} of total comp, growing ${percent(a.rsu_pct_annual_increase || 0)} a year)`)
  }
  const grossVal = v(row, 'gross_income'), prevGross = v(prevRow, 'gross_income')
  if (grossVal && prevGross && prevGross > 0) {
    const growth = ((grossVal - prevGross) / prevGross) * 100
    lines.push(`Total compensation ${money(grossVal)} (${growth >= 0 ? '+' : ''}${growth.toFixed(1)}% vs prior year)`)
  }
  const contrib = v(row, 'contributions_401k'), retBal = v(row, 'retirement_balance')
  if (contrib && retBal !== null) lines.push(`${money(contrib)} goes into the 401(k), bringing it to ${money(retBal)}`)
  const prevInv = v(prevRow, 'investment_balance'), curInv = v(row, 'investment_balance')
  if (prevInv && curInv && a.investment_return) lines.push(`Investments assume a ${percent(a.investment_return)} return (${money(prevInv)} → ${money(curInv)})`)
  if (a.monthly_cash_savings && !isRetiredYear(year, retirementYear.value)) lines.push(`Cash savings of ${money(a.monthly_cash_savings)} a month (${money(a.monthly_cash_savings * 12)} a year)`)
  const homeEq = v(row, 'home_equity'), mortgage = v(row, 'mortgage_balance')
  if (homeEq !== null && a.home_appreciation) lines.push(`Home appreciates ${percent(a.home_appreciation)}; equity ${money(homeEq)}${mortgage !== null ? `, mortgage paid down to ${money(mortgage)}` : ''}`)
  const prevNW = v(prevRow, 'net_worth'), curNW = v(row, 'net_worth')
  if (prevNW && curNW && Math.floor(curNW / 1_000_000) > Math.floor(prevNW / 1_000_000)) lines.push(`Net worth crosses $${Math.floor(curNW / 1_000_000)}M this year`)
  return lines
}

const totalVisibleCols = computed(() => {
  let count = 2
  for (const group of METRIC_GROUPS) {
    if (collapsedGroups.value.has(group.label)) count += 1
    else count += groupMetrics(group).length * (comparing.value ? 2 : 1)
  }
  return count
})

const selectClass = 'px-3 py-2 min-h-10 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-white max-w-full'
</script>

<template>
  <div class="min-w-0">
    <PageHeader
      title="Planning"
      :subtitle="subtitle"
      tooltip="Year-by-year projection to retirement. Green rows are actual years (W-2 and balance snapshots), the amber row is this year's forecast, white rows are plan years from the assumptions, and shaded rows are retirement. Click a plan year for what it assumes."
    >
      <div v-if="recalculating" class="flex items-center gap-1.5 text-xs text-indigo-500"><div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-indigo-400"></div>Recalculating…</div>
      <div v-else-if="plan1Loading || plan2Loading" class="flex items-center gap-1.5 text-xs text-gray-400"><div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-indigo-400"></div>Loading…</div>
      <button @click="showAssumptions = !showAssumptions" :aria-expanded="showAssumptions"
        :class="['flex items-center gap-1.5 px-3 min-h-10 rounded-lg border text-xs font-medium transition-colors', showAssumptions ? 'bg-indigo-50 dark:bg-indigo-950 border-indigo-200 dark:border-indigo-800 text-indigo-600' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300']">
        <SettingsIcon class="w-4 h-4" /> Assumptions
      </button>
      <button @click="showCreatePlan = !showCreatePlan" class="px-3 min-h-10 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700">{{ showCreatePlan ? 'Cancel' : '+ New plan' }}</button>
      <template #below>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label class="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">Plan
            <select v-model="plan1Id" :disabled="plansLoading" :class="selectClass">
              <option :value="null" disabled>Select plan…</option>
              <option v-for="p in plans" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">Compare with
            <select v-model="plan2Id" :disabled="plansLoading" :class="selectClass">
              <option :value="null">None</option>
              <option v-for="p in plans" :key="p.id" :value="p.id" :disabled="p.id === plan1Id">{{ p.name }}</option>
            </select>
          </label>
        </div>
      </template>
    </PageHeader>

    <div v-if="showCreatePlan" class="mb-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex-1 min-w-[12rem] text-xs font-medium text-gray-700 dark:text-gray-300">Plan name
          <input v-model="newPlanName" type="text" placeholder="e.g. Retire at 55" @keydown.enter="createPlan"
            class="mt-1 w-full px-3 py-2 min-h-10 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white" />
        </label>
        <label class="text-xs font-medium text-gray-700 dark:text-gray-300">Type
          <select v-model="newPlanType" :class="selectClass" class="mt-1 block"><option value="base">Base</option><option value="optimistic">Optimistic</option><option value="pessimistic">Pessimistic</option><option value="custom">Custom</option></select>
        </label>
        <button @click="createPlan" :disabled="creatingPlan || !newPlanName.trim()" class="px-4 min-h-10 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50">{{ creatingPlan ? 'Creating…' : 'Create plan' }}</button>
      </div>
    </div>

    <div v-if="plansError || plan1Error || plan2Error || recalcError" class="mb-4 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
      {{ plansError || plan1Error || plan2Error || recalcError }}
    </div>

    <div v-if="plansLoading || plan1Loading" class="flex items-center justify-center h-64"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div></div>
    <div v-else-if="!plan1Data" class="flex items-center justify-center h-64 text-gray-400 text-sm">Select a plan above to view the projection table.</div>

    <div v-else class="flex flex-col lg:flex-row gap-4 min-w-0">
      <!-- Table -->
      <div class="group/table flex-1 min-w-0 relative">
        <button @click="showProjectionSql = true" class="absolute top-0 right-0 z-30 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/table:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all sql-btn" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showProjectionSql" :sql="projectionTableSql" title="Projection Table" :tables="['plan_versions', 'plan_projections', 'w2_records', 'balance_snapshots']" @close="showProjectionSql = false" />

        <div class="flex flex-wrap items-center gap-x-5 gap-y-1 mb-3 text-xs pr-10">
          <div class="flex items-center gap-1.5"><span class="inline-block w-3 h-3 rounded-sm bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-800"></span><span class="text-gray-500 dark:text-gray-400">Actuals</span></div>
          <div class="flex items-center gap-1.5"><span class="inline-block w-3 h-3 rounded-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800"></span><span class="text-gray-500 dark:text-gray-400">Forecast</span></div>
          <div class="flex items-center gap-1.5"><span class="inline-block w-3 h-3 rounded-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700"></span><span class="text-gray-500 dark:text-gray-400">Plan (tap to expand)</span></div>
          <div class="flex items-center gap-1.5"><span class="inline-block w-3 h-3 rounded-sm bg-slate-100 dark:bg-slate-800/60 border border-slate-300 dark:border-slate-700"></span><span class="text-gray-500 dark:text-gray-400">Retired</span></div>
        </div>

        <DataTable sticky dense :empty="years.length === 0" empty-text="No projection data available for this plan." :columns="totalVisibleCols" class="rounded-xl border border-gray-200 dark:border-gray-800 planning-table">
          <thead>
            <tr class="bg-gray-50 dark:bg-gray-800/80">
              <th class="sticky left-0 z-30 bg-gray-50 dark:bg-gray-800 text-left border-r border-gray-200 dark:border-gray-700">Year</th>
              <th class="text-left">Status</th>
              <template v-for="group in METRIC_GROUPS" :key="group.label">
                <th v-if="collapsedGroups.has(group.label)" class="border-l-2 border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 !px-1" style="min-width: 28px; max-width: 28px;" @click="toggleGroup(group.label)" :title="`Show ${group.label}`">
                  <span class="text-[9px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500" style="writing-mode: vertical-rl; transform: rotate(180deg);">{{ group.label }}</span>
                </th>
                <template v-else>
                  <th v-for="(metric, mi) in groupMetrics(group)" :key="metric" :class="['text-right', mi === 0 ? 'border-l-2 border-l-gray-200 dark:border-l-gray-700' : '']">
                    <button v-if="mi === 0" class="cursor-pointer mr-1 text-gray-400 hover:text-gray-600 align-middle" @click="toggleGroup(group.label)" :title="`Collapse ${group.label}`"><ChevronDown class="w-3 h-3 inline" /></button>
                    {{ METRIC_LABELS[metric] ?? metric }}
                    <InfoTooltip v-if="METRIC_TOOLTIPS[metric]" :text="METRIC_TOOLTIPS[metric]" />
                  </th>
                  <template v-if="comparing">
                    <th v-for="metric in groupMetrics(group)" :key="'d-' + metric" class="text-right text-gray-400 !px-2"><span class="text-[10px]">Δ</span></th>
                  </template>
                </template>
              </template>
            </tr>
          </thead>
          <tbody>
            <template v-for="year in years" :key="year">
              <tr :class="['transition-colors group', rowBg(year), getRowStatus(plan1Data, year) === 'plan' ? 'cursor-pointer hover:bg-gray-50/80 dark:hover:bg-gray-800/50' : '']"
                @click="getRowStatus(plan1Data, year) === 'plan' ? (expandedYear = expandedYear === year ? null : year) : null">
                <td :class="['sticky left-0 z-10 font-semibold border-r border-gray-100 dark:border-gray-800 whitespace-nowrap tabular-nums', rowBg(year), year === CURRENT_YEAR ? 'border-l-2 border-l-indigo-500 text-indigo-700 dark:text-indigo-300' : 'text-gray-700 dark:text-gray-200']">
                  <span v-if="getRowStatus(plan1Data, year) === 'plan'" class="text-gray-400 mr-1"><component :is="expandedYear === year ? ChevronDown : ChevronRight" class="w-3 h-3 inline" /></span>
                  {{ year }}
                </td>
                <td class="whitespace-nowrap">
                  <span :class="['inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide', getRowStatus(plan1Data, year) === 'actuals' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' : getRowStatus(plan1Data, year) === 'forecast' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400' : isRetiredYear(year, retirementYear) ? 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400']">
                    {{ getRowStatus(plan1Data, year) === 'plan' && isRetiredYear(year, retirementYear) ? 'retired' : getRowStatus(plan1Data, year) }}
                  </span>
                </td>
                <template v-for="group in METRIC_GROUPS" :key="group.label + '-' + year">
                  <td v-if="collapsedGroups.has(group.label)" class="border-l-2 border-l-gray-200 dark:border-l-gray-700 !p-0" style="min-width: 28px; max-width: 28px;"></td>
                  <template v-else>
                    <td v-for="(metric, mi) in groupMetrics(group)" :key="metric + '-' + year"
                      :class="['text-right tabular-nums whitespace-nowrap', year === CURRENT_YEAR ? 'font-semibold' : '', getRowStatus(plan1Data, year) === 'actuals' ? 'text-gray-800 dark:text-gray-100' : getRowStatus(plan1Data, year) === 'forecast' ? 'italic text-gray-600 dark:text-gray-400' : 'text-gray-600 dark:text-gray-400', mi === 0 ? 'border-l-2 border-l-gray-200 dark:border-l-gray-700' : '']">
                      {{ fmtVal(getCellValue(plan1Data, year, metric)?.value ?? null) }}
                    </td>
                    <template v-if="comparing">
                      <td v-for="metric in groupMetrics(group)" :key="'d-' + metric + '-' + year" :class="['text-right tabular-nums whitespace-nowrap text-[11px] !px-2', deltaClass(metric, getCellValue(plan1Data, year, metric)?.value ?? null, getCellValue(plan2Data, year, metric)?.value ?? null)]">
                        {{ formatDelta(getCellValue(plan1Data, year, metric)?.value ?? null, getCellValue(plan2Data, year, metric)?.value ?? null) }}
                      </td>
                    </template>
                  </template>
                </template>
              </tr>
              <tr v-if="expandedYear === year && getRowStatus(plan1Data, year) === 'plan'">
                <td :colspan="totalVisibleCols" class="!px-6 !py-4 bg-indigo-50/40 dark:bg-indigo-950/20 border-b border-indigo-100 dark:border-indigo-900 whitespace-normal">
                  <div class="text-xs font-semibold text-indigo-700 dark:text-indigo-300 mb-2">What {{ year }} assumes</div>
                  <ul class="space-y-1.5 text-sm text-gray-700 dark:text-gray-300 max-w-prose">
                    <li v-for="(line, i) in buildNarrative(year)" :key="i" class="flex items-start gap-2"><span class="text-indigo-400 mt-0.5 flex-shrink-0">•</span><span>{{ line }}</span></li>
                  </ul>
                  <div v-if="buildNarrative(year).length === 0" class="text-sm text-gray-400 italic">No projection data for this year.</div>
                </td>
              </tr>
            </template>
          </tbody>
        </DataTable>

        <div v-if="comparing && plan2Data" class="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Δ = <span class="font-medium text-gray-600 dark:text-gray-300">{{ plan1Data.plan_name }}</span> minus <span class="font-medium text-gray-600 dark:text-gray-300">{{ plan2Data.plan_name }}</span>.
        </div>
      </div>

      <!-- Assumptions: sidebar on wide screens, bottom sheet on phones -->
      <template v-if="showAssumptions">
        <div v-if="isNarrow" class="fixed inset-0 z-40" role="dialog" aria-label="Assumptions">
          <div class="absolute inset-0 bg-black/40" @click="showAssumptions = false"></div>
          <div class="absolute inset-x-0 bottom-0 max-h-[75vh] rounded-t-2xl bg-gray-50 dark:bg-gray-950 border-t border-gray-200 dark:border-gray-800 flex flex-col" style="padding-bottom: env(safe-area-inset-bottom, 0px)">
            <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Assumptions</h3>
              <button @click="showAssumptions = false" class="w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-800" aria-label="Close"><X class="w-4 h-4" /></button>
            </div>
            <div class="overflow-y-auto p-4"><AssumptionPanel :assumptions="assumptions" @update="onAssumptionUpdate" /></div>
          </div>
        </div>
        <div v-else class="group/assumptions w-80 flex-shrink-0 relative">
          <div class="sticky top-6">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Assumptions</h3>
              <div class="flex items-center gap-1">
                <button @click="showAssumptionsSql = true" class="w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/assumptions:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 sql-btn" title="View SQL" aria-label="View SQL">
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                </button>
                <button @click="showAssumptions = false" class="min-h-10 px-2 text-gray-400 hover:text-gray-600 text-xs">Close</button>
              </div>
            </div>
            <SqlViewerModal :open="showAssumptionsSql" :sql="assumptionsSql" title="Plan Assumptions" :tables="['plan_assumptions', 'plan_versions']" @close="showAssumptionsSql = false" />
            <div class="max-h-[calc(100vh-200px)] overflow-y-auto"><AssumptionPanel :assumptions="assumptions" @update="onAssumptionUpdate" /></div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.planning-table :deep(thead th) {
  position: sticky;
  top: 0;
}
.planning-table :deep(tbody td) {
  padding: 0.5rem 0.75rem;
}
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
