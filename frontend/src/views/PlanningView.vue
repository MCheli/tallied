<script setup lang="ts">
/**
 * Planning — "will this work out, and what would need to be true?" (docs/requirements/planning-v2.md).
 *
 * Levers on the left change a what-if outlook (nothing is saved until Save). The outlook comes from
 * the backend engine (app/engine/retirement_sim.py): 1,000 Monte Carlo paths, every complete
 * historical retirement since 1928, macro scenarios, goal-seek, sensitivity, and career shocks.
 * Age comes from the household birth date; the page asks for it rather than assuming one.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import OutlookFan from '../components/planning/OutlookFan.vue'
import SuccessCurve from '../components/planning/SuccessCurve.vue'
import ScenarioBars from '../components/planning/ScenarioBars.vue'
import CohortChart from '../components/planning/CohortChart.vue'
import CompositionChart from '../components/planning/CompositionChart.vue'
import LeverTornado from '../components/planning/LeverTornado.vue'
import LeverControl from '../components/planning/LeverControl.vue'
import StackedYears from '../components/planning/StackedYears.vue'
import SpendingBuilder from '../components/planning/SpendingBuilder.vue'
import SprintPanel from '../components/planning/SprintPanel.vue'
import { useFormatters } from '../composables/useFormatters'
import { useChartDefaults } from '../composables/useChartDefaults'
import { apiErrorMessage } from '../composables/useApiError'
import {
  INCOME_PATHS, bridgeSeries, changedLevers, cohortStats, costSeries, deltaPts, eventSummary, historyLine,
  retireAgeRows, successTone, templateAges, toneLabel, tornadoFromSensitivity, whatMustBeTrue, yearRanges,
} from '../composables/usePlanningOutlook'
import type {
  AssumptionSpec, EventTemplate, Household, PlanCatalogue, PlanEvent, PlanListItem, PlanOutlook, SpendingProfile,
  SpendingRule, SprintResult,
} from '../types'

const { money, compact, percent, date: fmtDate } = useFormatters()
const { bucketColors, statusColors } = useChartDefaults()

// ── State ──
const catalogue = ref<PlanCatalogue | null>(null)
const household = ref<Household | null>(null)
const plans = ref<PlanListItem[]>([])
const planId = ref<number | null>(null)
const outlook = ref<PlanOutlook | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const analyzing = ref(false)  // the outlook is shown; goal-seek, scenarios and sensitivity still computing
const error = ref<string | null>(null)
const actionError = ref<string | null>(null)
const notice = ref<string | null>(null)

const draft = ref<Record<string, number>>({})
const saved = ref<Record<string, number>>({})
const draftRule = ref<SpendingRule>('fixed')
const savedRule = ref<SpendingRule>('fixed')
const draftProfile = ref<SpendingProfile>('flat')
const savedProfile = ref<SpendingProfile>('flat')
const regime = ref('base')
const saving = ref(false)
const showMore = ref(false)
const showTable = ref(false)
const includeHome = ref(false)
const birthInput = ref('')
const editingBirth = ref(false)

const specs = computed<Record<string, AssumptionSpec>>(() =>
  Object.fromEntries((catalogue.value?.assumptions ?? []).map((a) => [a.key, a])))
const changed = computed(() => changedLevers(draft.value, saved.value))
const changeCount = computed(() => Object.keys(changed.value).length
  + (draftRule.value !== savedRule.value ? 1 : 0) + (draftProfile.value !== savedProfile.value ? 1 : 0))
const dirty = computed(() => changeCount.value > 0)

const PRIMARY = ['retirement_age', 'retirement_spending', 'monthly_cash_savings', 'total_comp_growth',
  'stock_allocation_retired', 'ss_monthly_at_fra', 'ss_claim_age', 'payoff_mortgage', 'use_sepp'] as const
const CATEGORY_LABELS: Record<string, string> = {
  career: 'Career and income', spending: 'Spending and housing', retirement: 'Retirement income and access',
  health: 'Health care', markets: 'Markets', tax: 'Taxes',
}
const moreGroups = computed(() => {
  const groups: Record<string, AssumptionSpec[]> = {}
  for (const a of catalogue.value?.assumptions ?? []) {
    if ((PRIMARY as readonly string[]).includes(a.key)) continue
    ;(groups[a.category] ||= []).push(a)
  }
  return groups
})

function setIncomePath(real: number) {
  draft.value = { ...draft.value, total_comp_growth: +(draft.value.inflation + real).toFixed(4) }
}
const activeIncomePath = computed(() => {
  const real = (draft.value.total_comp_growth ?? 0) - (draft.value.inflation ?? 0)
  return INCOME_PATHS.find((p) => Math.abs(p.real - real) < 0.0005)?.label ?? null
})
const shortfall = computed(() => (draft.value.ss_payable_share ?? 1) < 0.999)
function toggleShortfall() {
  draft.value = { ...draft.value, ss_payable_share: shortfall.value ? 1 : 0.81 }
}

// ── Loading ──
async function loadPlans() {
  plans.value = await api.getPlans()
  if (planId.value == null || !plans.value.some((p) => p.id === planId.value)) {
    planId.value = (plans.value.find((p) => p.is_active) ?? plans.value[0])?.id ?? null
  }
}

async function loadSaved(id: number) {
  if (!household.value?.birth_date) return
  loading.value = true
  error.value = null
  try {
    // The outlook alone is quick; "what would need to be true" re-runs the simulation 100+ times and
    // takes seconds on the server, so the page shows the outlook first and fills the analysis in after.
    const o = await api.planning.outlook(id, regime.value, false)
    outlook.value = o
    skipWatch = true  // loading the saved values is not a lever change
    saved.value = { ...o.values }
    draft.value = { ...o.values }
    savedRule.value = draftRule.value = o.plan.spending_rule
    savedProfile.value = draftProfile.value = o.plan.spending_profile
    const mine = ++seq
    loading.value = false
    void (async () => {
      await withAnalysis(mine, () => api.planning.outlook(id, regime.value, true))
      // The sprint takes a few seconds too: run it once in the background for the saved plan. Lever
      // changes clear it (it no longer matches) and the panel offers to run it again.
      if (mine === seq) void runSprint()
    })()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not compute the outlook')
    outlook.value = null
  } finally {
    loading.value = false
  }
}

let timer: ReturnType<typeof setTimeout> | null = null
let skipWatch = false
let sprintSeq = 0
let seq = 0
function scheduleWhatIf() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(runWhatIf, 450)
}
function whatIfBody(analysis = true) {
  return { overrides: changed.value, spending_rule: draftRule.value, spending_profile: draftProfile.value, regime: regime.value, analysis }
}
async function runWhatIf() {
  if (planId.value == null) return
  const id = planId.value
  const mine = ++seq
  refreshing.value = true
  actionError.value = null
  try {
    const o = await api.planning.whatIf(id, whatIfBody(false))
    if (mine !== seq) return
    outlook.value = o
    refreshing.value = false
    const body = whatIfBody()
    await withAnalysis(mine, () => api.planning.whatIf(id, body))
  } catch (e) {
    if (mine === seq) actionError.value = apiErrorMessage(e, 'Could not recompute')
  } finally {
    if (mine === seq) refreshing.value = false
  }
}
/** Fetch the full outlook (with the analysis) and show it unless a newer request replaced this one. */
async function withAnalysis(mine: number, fetchFull: () => Promise<PlanOutlook>) {
  analyzing.value = true
  try {
    const full = await fetchFull()
    if (mine === seq) outlook.value = full
  } catch (e) {
    if (mine === seq) actionError.value = apiErrorMessage(e, 'Could not work out what would need to be true')
  } finally {
    if (mine === seq) analyzing.value = false
  }
}

watch(planId, (id) => { if (id != null) { sprint.value = null; loadSaved(id) } })
watch([draft, draftRule, draftProfile, regime], () => {
  if (skipWatch) { skipWatch = false; return }
  if (outlook.value) { sprint.value = null; sprintSeq++; scheduleWhatIf() }
}, { deep: true })

onMounted(async () => {
  loading.value = true
  try {
    const [cat, hh] = await Promise.all([api.planning.catalogue(), api.planning.household()])
    catalogue.value = cat
    household.value = hh
    await loadPlans()
    if (planId.value == null || !hh.birth_date) loading.value = false
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not load plans')
    loading.value = false
  }
})

async function saveBirthDate() {
  if (!birthInput.value) return
  saving.value = true
  actionError.value = null
  try {
    household.value = await api.planning.setBirthDate(birthInput.value)
    editingBirth.value = false
    notice.value = `Birth date saved: age ${household.value.age}.`
    if (planId.value != null) await loadSaved(planId.value)
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not save the birth date')
  } finally {
    saving.value = false
  }
}

// ── Save / reset / new ──
async function save() {
  if (planId.value == null) return
  saving.value = true
  actionError.value = null
  notice.value = null
  try {
    await api.updatePlan(planId.value, {
      spending_rule: draftRule.value,
      spending_profile: draftProfile.value,
      assumptions: Object.entries(changed.value).map(([key, value]) => ({ key, value })),
    })
    await loadSaved(planId.value)
    notice.value = 'Saved to the plan.'
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Save failed; nothing was changed')
  } finally {
    saving.value = false
  }
}
function reset() {
  draft.value = { ...saved.value }
  draftRule.value = savedRule.value
  draftProfile.value = savedProfile.value
}

const newName = ref('')
const showNew = ref(false)
async function saveAsNew() {
  if (!newName.value.trim() || planId.value == null) return
  saving.value = true
  actionError.value = null
  try {
    const p = await api.createPlan({
      name: newName.value.trim(), copy_from: planId.value, spending_rule: draftRule.value, spending_profile: draftProfile.value,
      assumptions: Object.entries(draft.value).map(([key, value]) => ({ key, value })),
    })
    showNew.value = false
    newName.value = ''
    await loadPlans()
    planId.value = p.id
    notice.value = `Created “${p.name}” from the current levers.`
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not create the plan')
  } finally {
    saving.value = false
  }
}
async function createFirst() {
  saving.value = true
  actionError.value = null
  try {
    const p = await api.createPlan({ name: 'My plan', assumptions: [] })
    await loadPlans()
    planId.value = p.id
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not create the plan')
  } finally {
    saving.value = false
  }
}

// ── Life events (saved immediately; the outlook reloads) ──
const templateIndex = ref<number | ''>('')
const editing = ref<PlanEvent | null>(null)
const LAYOFF_FIELDS: { key: string; label: string; step: number; help: string }[] = [
  { key: 'severance_weeks', label: 'Severance (weeks of pay)', step: 1, help: 'Paid at the layoff.' },
  { key: 'gap_months', label: 'Months out of work', step: 1, help: 'No pay; spending and health cover from savings.' },
  { key: 'ui_weekly', label: 'Unemployment benefit a week', step: 5, help: 'Up to 26 weeks, taxed as pay. Massachusetts maximum $1,105 from Oct 2025.' },
  { key: 'gap_health_annual', label: 'Health cover during the gap (a year)', step: 100, help: 'COBRA (up to 102% of the full premium) or marketplace.' },
  { key: 'next_pay_pct', label: "Next job's pay (share of today's)", step: 0.05, help: '1 = same as today.' },
  { key: 'next_equity', label: 'Next job grants equity (1 yes, 0 no)', step: 1, help: '' },
  { key: 'never_reemployed', label: 'Never re-employed (1 yes, 0 no)', step: 1, help: 'Retire at the layoff instead.' },
  { key: 'part_time_income', label: 'Part-time income a year until retirement age', step: 1000, help: 'Today\'s dollars, before tax.' },
]
async function afterEventChange(message: string) {
  notice.value = message
  if (dirty.value) await runWhatIf()
  else if (planId.value != null) await loadSaved(planId.value)
}
async function addFromTemplate() {
  if (templateIndex.value === '' || !outlook.value || planId.value == null) return
  const t: EventTemplate = catalogue.value!.event_templates[templateIndex.value]
  const ages = templateAges(t, outlook.value.current_age, draft.value.retirement_age)
  actionError.value = null
  try {
    const ev = await api.planning.addEvent(planId.value, {
      kind: t.kind, label: t.label, start_age: ages.start_age, end_age: ages.end_age, amount: t.amount, pct: t.pct, enabled: true,
      params: t.params ?? null,
    })
    templateIndex.value = ''
    editing.value = { ...ev, params: { ...(catalogue.value?.layoff_defaults ?? {}), ...(ev.params ?? {}) } }
    await afterEventChange(`Added “${ev.label}”. Adjust it below.`)
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not add the event')
  }
}
async function toggleEvent(ev: PlanEvent) {
  actionError.value = null
  try {
    await api.planning.updateEvent(ev.id, { enabled: !ev.enabled })
    await afterEventChange(`${ev.enabled ? 'Turned off' : 'Turned on'} “${ev.label}”.`)
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not change the event')
  }
}
function startEdit(ev: PlanEvent) {
  editing.value = editing.value?.id === ev.id ? null
    : { ...ev, params: ev.kind === 'layoff' ? { ...(catalogue.value?.layoff_defaults ?? {}), ...(ev.params ?? {}) } : ev.params }
}
async function saveEvent() {
  if (!editing.value) return
  const ev = editing.value
  actionError.value = null
  try {
    await api.planning.updateEvent(ev.id, {
      label: ev.label, start_age: ev.start_age, end_age: ev.end_age, amount: ev.amount, pct: ev.pct,
      ...(ev.kind === 'layoff' ? { params: ev.params ?? {} } : {}),
    })
    editing.value = null
    await afterEventChange(`Saved “${ev.label}”.`)
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not save the event')
  }
}
async function deleteEvent(ev: PlanEvent) {
  actionError.value = null
  try {
    await api.planning.deleteEvent(ev.id)
    if (editing.value?.id === ev.id) editing.value = null
    await afterEventChange(`Removed “${ev.label}”.`)
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not remove the event')
  }
}
function templateFor(kind: string) {
  return catalogue.value?.event_templates.find((t) => t.kind === kind)
}
function impactFor(id: number) {
  return outlook.value?.event_impacts?.find((i) => i.id === id)
}

// ── Sprint ──
const sprint = ref<SprintResult | null>(null)
const sprintLoading = ref(false)
const sprintError = ref<string | null>(null)
async function runSprint() {
  if (planId.value == null) return
  const mine = ++sprintSeq
  sprintLoading.value = true
  sprintError.value = null
  try {
    const result = await api.planning.sprint(planId.value, whatIfBody(false))
    if (mine === sprintSeq) sprint.value = result  // a lever moved meanwhile: this answer is stale
  } catch (e) {
    if (mine === sprintSeq) sprintError.value = apiErrorMessage(e, 'The sprint did not run')
  } finally {
    sprintLoading.value = false
  }
}

// ── Plans side by side ──
interface PlanRow { id: number; name: string; retire: number; spending: number; rule: string; success: number; atRet: number; end: number }
const compareRows = ref<PlanRow[]>([])
const comparing = ref(false)
async function loadCompare() {
  comparing.value = true
  try {
    compareRows.value = await Promise.all(plans.value.map(async (p) => {
      const o = await api.planning.outlook(p.id, 'base', false)
      return { id: p.id, name: p.name, retire: o.retirement_age, spending: o.values.retirement_spending,
        rule: o.plan.spending_rule, success: o.summary.success_rate, atRet: o.summary.median_at_retirement, end: o.summary.median_at_end }
    }))
  } catch (e) {
    actionError.value = apiErrorMessage(e, 'Could not compare plans')
  } finally {
    comparing.value = false
  }
}

// ── Derived for the page ──
const o = computed(() => outlook.value)
const target = computed(() => o.value?.success_target ?? 0.85)
const tone = computed(() => (o.value ? successTone(o.value.summary.success_rate, target.value) : 'warning'))
const cards = computed(() => (o.value?.goal_seek ? whatMustBeTrue(o.value, o.value.goal_seek) : []))
const cohort = computed(() => cohortStats(o.value?.cohorts ?? []))
const ruleInfo = computed(() => catalogue.value?.spending_rules.find((r) => r.key === draftRule.value))
const regimeInfo = computed(() => catalogue.value?.regimes.find((r) => r.key === regime.value))
const retIndex = computed(() => (o.value ? o.value.fan.ages.indexOf(o.value.retirement_age) : -1))
const fanBands = computed(() => (o.value ? (includeHome.value ? o.value.fan.net_worth : o.value.fan.liquid) : null))
const fanOverlay = computed(() => (o.value && !includeHome.value ? { name: 'Net worth incl. home (median)', data: o.value.fan.net_worth.p50 } : null))
const emptyHousehold = computed(() => !!o.value && o.value.starting_point.investable <= 0 && o.value.starting_point.salary <= 0)
const costs = computed(() => (o.value ? costSeries(o.value.rows) : null))
const bridgeTo = computed(() => (o.value ? Math.max(70, o.value.retirement_age + 5) : 70))
const bridge = computed(() => (o.value ? bridgeSeries(o.value.rows, bridgeTo.value) : null))
const ageRows = computed(() => (o.value?.goal_seek ? retireAgeRows(o.value.goal_seek.by_age, o.value.planned_retirement_age) : []))
const outcomes = computed(() => o.value?.event_outcomes ?? [])
const toneClass: Record<string, string> = {
  good: 'text-green-700 dark:text-green-400', warning: 'text-amber-700 dark:text-amber-400', critical: 'text-red-700 dark:text-red-400',
}
const toneIcon: Record<string, string> = { good: '✓', warning: '!', critical: '✕' }
const MILESTONE_NOTE: Record<number, string> = {
  50: 'Bridge years: taxable, Roth basis or 72(t)', 55: 'Rule of 55 opens this 401(k)', 60: 'Past 59½: all accounts',
  62: 'Social Security possible (reduced)', 65: 'Medicare', 67: 'Full Social Security', 70: 'Largest Social Security',
}

const sp = computed(() => o.value?.starting_point)
const startInfo = `<strong>What feeds the plan.</strong> Investable = cash and credit cards + taxable investments + company stock + 401(k), from the latest balance per account (Dashboard's numbers).
Company stock = sellable vested shares × today's price when no account holds it. Salary and RSU come from the latest W-2; a gross-only W-2 is split using that year's vests.
Scheduled vests = unvested vest events × today's price. Roth basis = Roth contributions on the latest 401(k) statement. Age comes from the household birth date. Living spending = the last year's spending net of refunds, without projects and hobbies (home improvement and services, vehicle purchases, auctions, parts, repairs) and one-off spikes, scaled to a year when history is shorter; projects come from the Projects & Hobby Budget instead; while working, savings from pay are take-home salary minus living spending, housing and loan payments (equity covers a shortfall).`
</script>

<template>
  <div class="min-w-0">
    <PageHeader
      title="Planning"
      subtitle="Will it work out, and what would need to be true?"
      tooltip="<strong>Planning</strong> projects your household from today's balances and pay to the plan-to age under 1,000 simulated markets, every historical retirement since 1928 and a set of macro scenarios. Levers change a what-if; <strong>Save</strong> writes them to the plan."
    >
      <label class="sr-only" for="plan-pick">Plan</label>
      <select id="plan-pick" v-model="planId" class="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-white max-w-[12rem]">
        <option v-for="p in plans" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <button v-if="planId != null && o" type="button" class="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800" v-demo-lock @click="showNew = !showNew">Save as new plan</button>
      <template v-if="dirty">
        <button type="button" class="rounded-lg px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800" @click="reset">Reset</button>
        <button type="button" :disabled="saving" class="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50" v-demo-lock @click="save">{{ saving ? 'Saving…' : 'Save changes' }}</button>
      </template>
      <template #below>
        <form v-if="showNew" class="flex flex-wrap items-center gap-2" @submit.prevent="saveAsNew">
          <input v-model="newName" placeholder="Name, e.g. Sprint to 50" class="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-white min-w-0 flex-1 max-w-xs" />
          <button v-demo-lock type="submit" :disabled="saving || !newName.trim()" class="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">Create from these levers</button>
          <span class="text-xs text-gray-500 dark:text-gray-400">Copies every lever, the spending rule and shape, and the life events.</span>
        </form>
        <p v-if="dirty && !showNew" class="text-xs text-indigo-700 dark:text-indigo-300">Showing a what-if: {{ changeCount }} change(s) not saved.</p>
      </template>
    </PageHeader>

    <div v-if="error" role="alert" class="mb-4 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-3 text-sm text-red-700 dark:text-red-300">{{ error }}</div>
    <div v-if="actionError" role="alert" class="mb-4 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-3 text-sm text-red-700 dark:text-red-300">{{ actionError }}</div>
    <div v-if="notice && !actionError" role="status" class="mb-4 rounded-lg border border-green-200 dark:border-green-900 bg-green-50 dark:bg-green-950/40 p-3 text-sm text-green-800 dark:text-green-300">{{ notice }}</div>

    <!-- Birth date first: no age is ever assumed -->
    <form v-if="household && (!household.birth_date || editingBirth)" class="mb-6 rounded-xl border border-indigo-200 dark:border-indigo-900 bg-white dark:bg-gray-900 p-5 max-w-xl" @submit.prevent="saveBirthDate">
      <h2 class="text-sm font-semibold text-gray-900 dark:text-white">When were you born? <InfoTooltip text="Planning computes your age from this every day: it decides your working years, when the 401(k), Social Security and Medicare open, and your full retirement age. Stored once for the household; every plan uses it." /></h2>
      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">The plan never assumes an age.</p>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <label class="sr-only" for="birth-date">Birth date</label>
        <input id="birth-date" v-model="birthInput" type="date" required class="rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1 text-sm text-gray-900 dark:text-white" />
        <button v-demo-lock type="submit" :disabled="saving || !birthInput" class="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50">Save birth date</button>
        <button v-if="editingBirth" type="button" class="text-sm text-gray-500" @click="editingBirth = false">Cancel</button>
      </div>
    </form>

    <div v-if="!loading && planId == null && !error" class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-8 text-center text-sm text-gray-500 dark:text-gray-400">
      <p>No plans yet. A plan starts from today's balances and pay with default assumptions you can then change.</p>
      <button type="button" :disabled="saving" class="mt-3 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50" v-demo-lock @click="createFirst">Create a plan</button>
    </div>

    <div v-else-if="loading && !o" class="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <div class="h-96 rounded-xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
      <div class="h-96 rounded-xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
    </div>

    <div v-else-if="o" class="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)] items-start">
      <!-- ── Levers ── -->
      <aside class="lg:sticky lg:top-4 space-y-4 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 min-w-0">
        <div>
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Levers <InfoTooltip text="Moving a lever recomputes the outlook without saving. A dot marks a lever that differs from the saved plan. <strong>Save changes</strong> writes them; <strong>Reset</strong> goes back." /></h2>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Age {{ o.current_age }} (born {{ fmtDate(o.birth_date) }}) · plan to {{ o.plan_to_age }}
            <button type="button" class="text-indigo-600 dark:text-indigo-400" v-demo-lock @click="editingBirth = true; birthInput = o.birth_date">change</button>
          </p>
        </div>

        <fieldset>
          <legend class="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Spending rule <InfoTooltip :text="(catalogue?.spending_rules ?? []).map((r) => `<strong>${r.label}</strong>: ${r.description}`).join('<br/><br/>')" /></legend>
          <div class="grid grid-cols-3 gap-1">
            <button v-for="r in catalogue?.spending_rules ?? []" :key="r.key" type="button"
              class="rounded-md border px-1.5 py-1 text-xs" :aria-pressed="draftRule === r.key"
              :class="draftRule === r.key ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300' : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300'"
              @click="draftRule = r.key">{{ r.label }}</button>
          </div>
        </fieldset>
        <fieldset>
          <legend class="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Spending shape <InfoTooltip :text="(catalogue?.spending_profiles ?? []).map((r) => `<strong>${r.label}</strong>: ${r.description}`).join('<br/><br/>')" /></legend>
          <div class="grid grid-cols-2 gap-1">
            <button v-for="r in catalogue?.spending_profiles ?? []" :key="r.key" type="button"
              class="rounded-md border px-1.5 py-1 text-xs" :aria-pressed="draftProfile === r.key"
              :class="draftProfile === r.key ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300' : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300'"
              @click="draftProfile = r.key">{{ r.label }}</button>
          </div>
        </fieldset>

        <template v-for="key in PRIMARY" :key="key">
          <LeverControl v-if="specs[key] && draft[key] !== undefined" v-model="draft[key]" :spec="specs[key]" :changed="key in changed"
            :min="key === 'retirement_age' ? o.current_age + 1 : undefined" />
          <div v-if="key === 'total_comp_growth'" class="flex flex-wrap gap-1 -mt-2">
            <button v-for="p in INCOME_PATHS" :key="p.label" type="button" :title="p.help"
              class="rounded-full border px-2 py-0.5 text-[11px]" :aria-pressed="activeIncomePath === p.label"
              :class="activeIncomePath === p.label ? 'border-indigo-600 text-indigo-700 dark:text-indigo-300' : 'border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400'"
              @click="setIncomePath(p.real)">{{ p.label }}</button>
          </div>
          <label v-if="key === 'ss_claim_age'" class="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300 -mt-1">
            <input type="checkbox" class="accent-indigo-600" :checked="shortfall" @change="toggleShortfall" />
            Trust-fund shortfall: 81% from 2034
            <InfoTooltip text="The 2025 Social Security Trustees Report projects the combined trust funds run out in 2034, after which incoming taxes pay about 81% of scheduled benefits unless Congress acts. The exact share is under All assumptions." />
          </label>
        </template>

        <button type="button" class="text-xs font-medium text-indigo-600 dark:text-indigo-400" :aria-expanded="showMore" @click="showMore = !showMore">
          {{ showMore ? 'Fewer assumptions' : 'All assumptions' }}
        </button>
        <div v-if="showMore" class="space-y-4">
          <div v-for="(group, cat) in moreGroups" :key="cat" class="space-y-3">
            <h3 class="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{{ CATEGORY_LABELS[cat] ?? cat }}</h3>
            <LeverControl v-for="a in group" :key="a.key" v-model="draft[a.key]" :spec="a" :changed="a.key in changed" />
          </div>
        </div>
      </aside>

      <!-- ── Results ── -->
      <div class="space-y-6 min-w-0 transition-opacity" :class="{ 'opacity-60': refreshing }" :aria-busy="refreshing">
        <ul v-if="o.warnings.length" class="space-y-2">
          <li v-for="w in o.warnings" :key="w.key" class="flex gap-2 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-800 dark:text-amber-200">
            <span aria-hidden="true" class="font-bold">!</span><span>{{ w.text }}</span>
          </li>
        </ul>
        <p v-if="o.retirement_age !== o.planned_retirement_age" class="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-800 dark:text-amber-200">
          A layoff with no next job retires the plan at {{ o.retirement_age }} instead of {{ o.planned_retirement_age }}.
        </p>

        <!-- Headline -->
        <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <div class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0">
            <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Chance of success
              <InfoTooltip :text="`Share of ${o.summary.paths.toLocaleString()} simulated markets in which the money lasts to ${o.plan_to_age}${draftRule !== 'fixed' ? ` and real spending never falls below ${percent(o.values.spending_floor, 0)} of the target` : ''}. Returns are drawn around your assumptions with historical volatility for your stock share; inflation varies year to year. Scenario: <strong>${regimeInfo?.label ?? ''}</strong>.`" />
            </p>
            <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ percent(o.summary.success_rate, 0) }}</p>
            <p class="mt-1 text-sm" :class="toneClass[tone]"><span aria-hidden="true">{{ toneIcon[tone] }}</span> {{ toneLabel(tone) }} · target {{ percent(target, 0) }}</p>
          </div>
          <MetricCard label="Historical record"
            :value="cohort.total ? `${cohort.lasted} of ${cohort.total}` : '—'"
            :subtitle="cohort.total ? 'start years lasted' : `no complete ${o.plan_to_age - o.retirement_age}-year sequence`"
            :info="`Your plan up to retirement at median returns, then retired into each complete historical sequence of US stocks, 10-year Treasuries and CPI (1928–2025, Damodaran/NYU Stern and BLS) at your retirement stock share. A start year counts when its sequence covers all ${o.plan_to_age - o.retirement_age + 1} retired years.`" />
          <MetricCard label="At retirement (median)" :value="compact(o.summary.median_at_retirement)"
            :subtitle="`bad case ${compact(o.summary.p10_at_retirement)} · age ${o.retirement_age}`"
            info="Investable assets (cash, taxable, company stock, 401(k); not the house) at the end of the last working year, in today's dollars. Median of the simulated markets; bad case is the 10th percentile." />
          <MetricCard v-if="draftRule === 'fixed'" label="If it runs out"
            :value="o.summary.median_failure_age != null ? `age ${o.summary.median_failure_age}` : 'never'"
            :subtitle="o.summary.earliest_failure_age != null ? `earliest age ${o.summary.earliest_failure_age}` : `lasts to ${o.plan_to_age} in every path`"
            info="Among the simulated markets where the money runs out, the median and the earliest age it happens. The fixed rule never cuts spending, so this is when it stops." />
          <MetricCard v-else label="Spending in retirement"
            :value="o.summary.spending_median != null ? compact(o.summary.spending_median) : '—'"
            :subtitle="`bad-case low ${compact(o.summary.spending_p10_lowest)}`"
            :info="`Median yearly living spending across all retired years and paths (today's dollars). Bad case low = the 10th percentile of each path's lowest year. Under ${ruleInfo?.label}, spending moves with markets; ${percent(o.summary.prob_spending_cut, 0)} of paths see at least one cut of more than 5%.`" />
        </div>

        <!-- Starting point -->
        <section v-if="sp" class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 text-sm text-gray-600 dark:text-gray-300 min-w-0">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Starting from <InfoTooltip :text="startInfo" /></h3>
          <p v-if="emptyHousehold" class="text-gray-500 dark:text-gray-400">No balances or pay on file yet. Connect accounts or add a W-2 in Settings; until then the plan starts from zero.</p>
          <dl class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-x-4 gap-y-2">
            <div><dt class="text-xs text-gray-400">Investable</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ money(sp.investable) }}</dd><dd class="text-[11px] text-gray-400">as of {{ fmtDate(sp.balances_as_of) }}</dd></div>
            <div><dt class="text-xs text-gray-400">401(k)</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ money(sp.retirement) }}</dd><dd class="text-[11px] text-gray-400">{{ compact(sp.roth_basis) }} Roth basis</dd></div>
            <div><dt class="text-xs text-gray-400">Company stock</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ money(sp.company_stock) }}</dd><dd class="text-[11px] text-gray-400">{{ sp.company_stock_source === 'sellable_shares' ? `sellable ${sp.company_symbol} shares` : sp.company_stock_source }}</dd></div>
            <div><dt class="text-xs text-gray-400">Pay ({{ sp.w2_year ?? 'no W-2' }})</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ compact(sp.salary) }} + {{ compact(sp.rsu_income) }} RSU</dd><dd class="text-[11px] text-gray-400">{{ sp.comp_source === 'vests' ? 'split from vests' : sp.comp_source === 'w2' ? 'from the W-2' : 'none on file' }}</dd></div>
            <div><dt class="text-xs text-gray-400">Scheduled vests</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ compact(sp.scheduled_vest_value) }}</dd><dd class="text-[11px] text-gray-400">{{ sp.scheduled_vest_count }} through {{ fmtDate(sp.last_scheduled_vest) }}</dd></div>
            <div v-if="sp.savings_from === 'cash_flow'"><dt class="text-xs text-gray-400">Living spending</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ compact(sp.living_spending ?? 0) }}/yr typical</dd><dd class="text-[11px] text-gray-400">+ {{ compact(sp.projects_allowance ?? 0) }} projects budget (recent pace {{ compact(sp.projects_observed ?? 0) }}) + {{ compact(sp.other_debt_payments ?? 0) }} loans</dd></div>
            <div><dt class="text-xs text-gray-400">Home</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ compact(sp.home_value - sp.mortgage_balance) }} equity</dd><dd class="text-[11px] text-gray-400">{{ compact(sp.mortgage_balance) }} at {{ percent(sp.mortgage_rate, 2) }}</dd></div>
          </dl>
        </section>

        <!-- Wealth fan -->
        <ChartContainer
          :title="includeHome ? 'Net worth over time' : 'Investable wealth over time'"
          :subtitle="`Today's dollars · ${regimeInfo?.label ?? ''}`"
          :empty="!fanBands || fanBands.p50.every((v) => v === 0)"
          empty-text="Nothing to project: no balances, pay or savings in this plan."
          :info="`The spread of outcomes across ${o.summary.paths.toLocaleString()} simulated markets, in today's dollars. The dark band holds the middle half of outcomes, the light band 80% of them; the line is the median. ${includeHome ? 'Includes home equity, which pays nothing towards spending unless you downsize.' : 'Cash, taxable investments, company stock and 401(k); the green line is the median net worth including the house.'} Thin rules mark when money and cover open up: 55 (rule of 55), 59½, 62, 65 (Medicare), full retirement age, 70.`"
        >
          <div class="flex flex-wrap items-center gap-3 mb-2 text-xs">
            <label class="inline-flex items-center gap-1 text-gray-600 dark:text-gray-300"><input v-model="includeHome" type="checkbox" class="accent-indigo-600" /> Bands include home equity</label>
            <label class="inline-flex items-center gap-1 text-gray-600 dark:text-gray-300">Scenario
              <select v-model="regime" class="rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-0.5 text-xs text-gray-900 dark:text-white max-w-[14rem]">
                <option v-for="r in catalogue?.regimes ?? []" :key="r.key" :value="r.key">{{ r.label }}</option>
              </select>
            </label>
          </div>
          <OutlookFan v-if="fanBands" :bands="fanBands" :ages="o.fan.ages" :retirement-age="o.retirement_age" :milestones="o.milestones" :overlay="fanOverlay" />
        </ChartContainer>

        <div v-if="analyzing && !o.goal_seek" role="status" data-testid="plan-analyzing"
          class="flex items-center gap-3 rounded-xl border border-dashed border-indigo-200 dark:border-indigo-900 bg-indigo-50/50 dark:bg-indigo-950/30 p-4 text-sm text-indigo-900 dark:text-indigo-200">
          <div class="h-4 w-4 flex-shrink-0 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
          Working out what would need to be true: other retirement ages, market scenarios and which levers matter. This re-runs the simulation about 150 times.
        </div>

        <!-- Retirement age as a dimension -->
        <ChartContainer v-if="o.goal_seek" title="Retire at different ages" :empty="!ageRows.length" empty-text="No milestone ages fall in the range compared."
          :info="`The plan as shown, retiring at each access milestone instead (same simulated markets, scenario: ${regimeInfo?.label}). Before 55 the early years are paid from taxable savings, the Roth basis or 72(t) payments; from 55 (leaving your employer then) the 401(k) opens without penalty; Social Security from 62; Medicare at 65.`">
          <DataTable dense :columns="5">
            <thead><tr><th>Retire at</th><th class="text-right">Chance</th><th class="text-right">At retirement</th><th class="text-right">At {{ o.plan_to_age }}</th><th>What opens</th></tr></thead>
            <tbody>
              <tr v-for="r in ageRows" :key="r.age" :class="r.age === o.planned_retirement_age ? 'font-semibold' : ''">
                <td>{{ r.age }}<span v-if="r.age === o.planned_retirement_age"> (plan)</span></td>
                <td class="text-right tabular-nums" :class="toneClass[successTone(r.success, target)]">{{ percent(r.success, 0) }}</td>
                <td class="text-right tabular-nums">{{ compact(r.median_at_retirement) }}</td>
                <td class="text-right tabular-nums">{{ compact(r.median_at_end) }}</td>
                <td class="text-xs text-gray-500 dark:text-gray-400">{{ MILESTONE_NOTE[r.age] ?? '' }}</td>
              </tr>
            </tbody>
          </DataTable>
        </ChartContainer>

        <!-- What would need to be true -->
        <section v-if="o.goal_seek" class="space-y-4 min-w-0">
          <div>
            <h2 class="text-base font-semibold text-gray-900 dark:text-white">What would need to be true
              <InfoTooltip :text="`Each card moves one lever on its own, with everything else as shown, until the chance of success reaches the target (${percent(target, 0)}; set it under All assumptions). Same simulated markets throughout and the selected scenario (${regimeInfo?.label}), so differences come from the lever, not luck.`" />
            </h2>
            <p class="text-xs text-gray-500 dark:text-gray-400">To reach {{ percent(target, 0) }} under {{ regimeInfo?.label?.toLowerCase() }} — any one of these is enough.</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <div v-for="c in cards" :key="c.key" class="rounded-xl border bg-white dark:bg-gray-900 p-4 min-w-0"
              :class="c.met ? 'border-green-200 dark:border-green-900' : 'border-gray-200 dark:border-gray-800'">
              <p class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ c.title }} <span v-if="c.met" class="text-green-700 dark:text-green-400">✓ met</span></p>
              <p class="text-xl font-bold text-gray-900 dark:text-white mt-0.5">{{ c.value }}</p>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ c.detail }}</p>
            </div>
          </div>
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <ChartContainer title="Chance of success by retirement age" :empty="!o.goal_seek.by_age.length" empty-text="No retirement ages to compare."
              info="The plan as shown, retiring at each age instead. Later retirement means more saving years, fewer retired years and fewer years bridging to 59½ and Medicare.">
              <SuccessCurve :x="o.goal_seek.by_age.map((r) => r.age)" :y="o.goal_seek.by_age.map((r) => r.success)" kind="age" :target="target" :current="draft.retirement_age" />
            </ChartContainer>
            <ChartContainer title="Chance of success by spending" :empty="!o.goal_seek.by_spending.length"
              info="The plan as shown, with retirement living spending at 50% to 200% of the plan's (today's dollars, before tax, excluding housing and health care, which the plan adds).">
              <SuccessCurve :x="o.goal_seek.by_spending.map((r) => r.spending)" :y="o.goal_seek.by_spending.map((r) => r.success)" kind="usd" :target="target" :current="draft.retirement_spending" />
            </ChartContainer>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400">Yardstick: {{ historyLine(o.history_reference.working) }} {{ historyLine(o.history_reference.retired) }} Your plan assumes {{ percent(o.values.investment_return, 1) }} and {{ percent(o.values.retirement_return, 1) }} with {{ percent(o.values.inflation, 1) }} inflation.</p>
        </section>

        <!-- What will retirement cost -->
        <SpendingBuilder :builder="o.spending_builder" :current="draft.retirement_spending" @use="(v) => (draft = { ...draft, retirement_spending: v })" />
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <ChartContainer title="What a retired year costs" subtitle="Plan line, today's dollars" :empty="!costs || !costs.ages.length" empty-text="No retired years in this plan."
            info="Each retired year on the plan line: living spending (your target, shaped by the rule and profile), housing (mortgage principal and interest until payoff, property tax and insurance for good), health care (marketplace premiums before 65 linked to that year's income, Medicare costs after, rising 2 points a year above inflation by default) and other life events.">
            <StackedYears v-if="costs" :ages="costs.ages" :milestones="o.milestones" :series="[
              { name: 'Living', data: costs.living, color: bucketColors[0] },
              { name: 'Housing', data: costs.housing, color: bucketColors[1] },
              { name: 'Health care', data: costs.health, color: bucketColors[2] },
              { name: 'Life events', data: costs.other, color: bucketColors[3] },
            ]" />
          </ChartContainer>
          <ChartContainer title="How the early years are paid" :subtitle="`Plan line to ${bridgeTo}, today's dollars`" :empty="!bridge || !bridge.ages.length" empty-text="No retired years before this age."
            info="Where each retired year's money comes from: taxable savings and company stock first; then before 59½ the Roth contribution basis (tax- and penalty-free once rolled to a Roth IRA; converted amounts need 5 years), 401(k) withdrawals that avoid the penalty (rule of 55 if you leave work at 55 or later, or 72(t) payments if switched on), and anything else from the 401(k) with the 10% penalty. Social Security and part-time pay reduce what has to be withdrawn.">
            <StackedYears v-if="bridge" :ages="bridge.ages" :milestones="o.milestones" :series="[
              { name: 'Taxable and company stock', data: bridge.taxable, color: bucketColors[1] },
              { name: 'Roth basis', data: bridge.roth, color: bucketColors[2] },
              { name: '401(k), no penalty', data: bridge.k401, color: bucketColors[3] },
              { name: '401(k) with 10% penalty', data: bridge.penalty, color: statusColors.critical },
              { name: 'Social Security', data: bridge.social, color: bucketColors[4] },
              { name: 'Part-time pay', data: bridge.work, color: bucketColors[0] },
            ]" />
          </ChartContainer>
        </div>

        <!-- Nest egg -->
        <ChartContainer title="What nest egg this needs" :empty="!o.nest_egg.rows.length"
          :info="`The first retired year's need on the plan line (living spending, housing and health care, less Social Security and part-time pay, grossed up for tax): ${money(o.nest_egg.need_first_year)} in today's dollars. Divided by the withdrawal rate each rule allows. Fixed: the highest constant real withdrawal that survived every (worst) or 90% (10th percentile) of complete US sequences since 1928 at your ${Math.round(o.nest_egg.stock_share * 100)}% stock share. VPW: its first-year payment at your expected real return.`">
          <DataTable dense :columns="6">
            <thead><tr><th>Years</th><th class="text-right">Fixed, worst case</th><th class="text-right">Fixed, 90% of history</th><th class="text-right">VPW start</th><th class="text-right">Nest egg (worst)</th><th class="text-right">Nest egg (90%)</th></tr></thead>
            <tbody>
              <tr v-for="r in o.nest_egg.rows" :key="r.horizon" :class="r.is_plan ? 'font-semibold' : ''">
                <td>{{ r.horizon }}<span v-if="r.is_plan"> (plan)</span></td>
                <td class="text-right tabular-nums">{{ r.fixed_worst != null ? `${percent(r.fixed_worst, 2)} (${r.fixed_worst_start})` : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.fixed_p10 != null ? percent(r.fixed_p10, 2) : '—' }}</td>
                <td class="text-right tabular-nums">{{ percent(r.vpw_first_year, 2) }}</td>
                <td class="text-right tabular-nums">{{ r.nest_egg_fixed_worst != null ? compact(r.nest_egg_fixed_worst) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.nest_egg_fixed_p10 != null ? compact(r.nest_egg_fixed_p10) : '—' }}</td>
              </tr>
            </tbody>
          </DataTable>
          <ul class="mt-2 space-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            <li v-for="ref_ in o.nest_egg.references" :key="ref_.label">{{ ref_.label }}: {{ ref_.rate != null ? percent(ref_.rate, 1) : (ref_.rates ?? []).map((x) => percent(x, 2)).join(' / ') }}</li>
          </ul>
        </ChartContainer>

        <!-- Macro scenarios + history -->
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <ChartContainer title="Market scenarios" :empty="!o.scenarios?.length" empty-text="Scenarios are still computing."
            info="The same plan under each macro scenario. Historical replays (stagflation 1966–1981, lost decade 2000–2009, depression 1929–1941) start the year you retire, where sequence risk bites; the 1982–1999 bull market starts today. Years outside a replay use your assumptions. Click a bar to draw it in the wealth chart and run the goal-seek under it.">
            <ScenarioBars v-if="o.scenarios" :scenarios="o.scenarios" :target="target" :selected="regime" @select="(k) => (regime = k)" />
          </ChartContainer>
          <ChartContainer title="Every historical start year" :empty="!o.cohorts.length"
            :empty-text="`The record (1928–2025) has no complete ${o.plan_to_age - o.retirement_age + 1}-year retirement; lower the plan-to age or retire later to see this.`"
            :info="`Each bar is a retirement that began in that year and ran on the actual sequence of stock, bond and inflation returns. Green: money left at ${o.plan_to_age} (today's dollars). Red: it ran out.`">
            <CohortChart :cohorts="o.cohorts" :plan-to-age="o.plan_to_age" />
            <p v-if="cohort.failed.length" class="mt-2 text-xs text-gray-500 dark:text-gray-400">Ran out when retiring into {{ yearRanges(cohort.failed) }}.</p>
            <p v-else class="mt-2 text-xs text-gray-500 dark:text-gray-400">Lasted in every complete historical sequence.</p>
          </ChartContainer>
        </div>

        <!-- Spending + composition -->
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <ChartContainer title="Spending in retirement" subtitle="Living spending, today's dollars"
            :empty="(draftRule === 'fixed' && draftProfile === 'flat') || retIndex < 0"
            :empty-text="draftRule === 'fixed' ? `Fixed rule, flat shape: spending is ${money(o.values.retirement_spending)} a year in every path until the money runs out. Choose Guardrails, VPW or the Smile shape to see it move.` : 'No retired years in this plan.'"
            :info="`How the ${ruleInfo?.label} rule${draftProfile === 'smile' ? ' and the smile shape' : ''} move yearly living spending across the simulated markets: bands as in the wealth chart. Paths that run out drop to what is left. Housing, health care and events are paid on top.`">
            <OutlookFan :bands="o.fan.spending" :ages="o.fan.ages" :from="Math.max(0, retIndex)" :height="260" median-label="Median spending" />
          </ChartContainer>
          <ChartContainer title="What the wealth is made of" subtitle="Plan line: every return at its median"
            :empty="!o.rows.length || o.rows.every((r) => r.net_worth === 0)" empty-text="No wealth to break down."
            info="The plan line year by year, in today's dollars: cash, taxable investments (savings and sold RSUs), company stock (RSUs kept), 401(k) and home equity.">
            <CompositionChart :rows="o.rows" :retirement-age="o.retirement_age" :milestones="o.milestones" />
          </ChartContainer>
        </div>

        <!-- Life events -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0">
          <div class="flex flex-wrap items-start justify-between gap-3 mb-3">
            <div class="min-w-0">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Life events and career shocks
                <InfoTooltip text="Things that change the money at a given age: an acquisition, a layoff (with severance, unemployment benefit, accelerated vesting, a gap, then a new job or none), part-time years, college, a big purchase, a move, downsizing, a stock crash, long-term care. Amounts are in today's dollars. Events are saved to the plan as you add, change or switch them; the change in chance of success is each event on its own." />
              </h3>
              <p class="text-xs text-gray-500 dark:text-gray-400">Saved to the plan as you change them.</p>
            </div>
            <form class="flex flex-wrap items-center gap-2" @submit.prevent="addFromTemplate">
              <label class="sr-only" for="add-event">Add a life event</label>
              <select id="add-event" v-model="templateIndex" class="rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1 text-sm text-gray-900 dark:text-white max-w-[15rem]">
                <option value="" disabled>Add a life event…</option>
                <option v-for="(t, i) in catalogue?.event_templates ?? []" :key="i" :value="i">{{ t.label }}</option>
              </select>
              <button v-demo-lock type="submit" :disabled="templateIndex === ''" class="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50">Add</button>
            </form>
          </div>
          <p v-if="!o.events.length" class="py-6 text-center text-sm text-gray-400 dark:text-gray-500">No life events in this plan. Add one to see what it does to the outlook.</p>
          <ul v-else class="divide-y divide-gray-100 dark:divide-gray-800">
            <li v-for="ev in o.events" :key="ev.id" class="py-3 min-w-0">
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <label class="inline-flex items-center gap-2 min-w-0 flex-1">
                  <input v-demo-lock type="checkbox" :checked="ev.enabled" class="accent-indigo-600" :aria-label="`Include ${ev.label}`" @change="toggleEvent(ev)" />
                  <span class="font-medium text-sm text-gray-900 dark:text-white break-words min-w-0" :class="{ 'line-through text-gray-400 dark:text-gray-500': !ev.enabled }">{{ ev.label }}</span>
                </label>
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ eventSummary(ev) }}</span>
                <span v-if="impactFor(ev.id)" class="text-xs font-medium tabular-nums" :title="`Chance of success with it ${percent(impactFor(ev.id)!.success_with, 0)}, without it ${percent(impactFor(ev.id)!.success_without, 0)}`"
                  :class="impactFor(ev.id)!.success_with >= impactFor(ev.id)!.success_without ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'">
                  {{ deltaPts(impactFor(ev.id)!.success_with, impactFor(ev.id)!.success_without) }}
                </span>
                <button type="button" class="text-xs text-indigo-600 dark:text-indigo-400" v-demo-lock @click="startEdit(ev)">{{ editing?.id === ev.id ? 'Close' : 'Edit' }}</button>
                <button type="button" class="text-xs text-red-600 dark:text-red-400" v-demo-lock @click="deleteEvent(ev)">Remove</button>
              </div>
              <form v-if="editing?.id === ev.id" class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs" @submit.prevent="saveEvent">
                <label class="col-span-2 sm:col-span-1">Label<input v-model="editing.label" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" /></label>
                <label>{{ ev.kind === 'layoff' || ev.kind === 'acquisition' ? 'At age' : 'From age' }}<input v-model.number="editing.start_age" type="number" min="0" max="120" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" /></label>
                <label v-if="!['layoff', 'acquisition', 'rsu_shock', 'one_off_expense', 'windfall', 'downsize', 'spending_change'].includes(ev.kind)">To age<input v-model.number="editing.end_age" type="number" min="0" max="120" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" /></label>
                <label v-if="templateFor(ev.kind)?.amount_label">{{ templateFor(ev.kind)?.amount_label }}<input v-model.number="editing.amount" type="number" step="500" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" /></label>
                <label v-if="templateFor(ev.kind)?.pct_label">{{ templateFor(ev.kind)?.pct_label }} (fraction)<input v-model.number="editing.pct" type="number" step="0.05" min="-1" max="10" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" /></label>
                <template v-if="ev.kind === 'layoff' && editing.params">
                  <label v-for="f in LAYOFF_FIELDS" :key="f.key" :title="f.help">{{ f.label }}
                    <input v-model.number="editing.params[f.key]" type="number" :step="f.step" min="0" class="mt-0.5 w-full rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-gray-900 dark:text-white" />
                  </label>
                </template>
                <div class="col-span-2 sm:col-span-4 flex flex-wrap items-center gap-2">
                  <button v-demo-lock type="submit" class="rounded bg-indigo-600 px-3 py-1 font-medium text-white">Save event</button>
                  <span class="text-gray-500 dark:text-gray-400">{{ templateFor(ev.kind)?.help }}</span>
                </div>
              </form>
            </li>
          </ul>

          <div v-if="outcomes.length" class="mt-4 space-y-3">
            <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400">Career shocks: does the money run out?
              <InfoTooltip text="For each layoff, acquisition or job loss that is switched on: whether the plan line (median returns) runs out and when, the share of simulated markets that run out, and the smallest extra part-time income from the shock to the planned retirement age that keeps the plan line solvent, gets back to the chance of success without the shock, or reaches the target. 'Not reachable' means even $300,000 a year would not." />
            </h4>
            <div v-for="oc in outcomes" :key="oc.id" class="rounded-lg border border-gray-200 dark:border-gray-800 p-3 text-sm min-w-0">
              <p class="font-medium text-gray-900 dark:text-white">{{ oc.label }}</p>
              <p class="mt-1 text-gray-600 dark:text-gray-300">
                <span :class="oc.plan_line_runs_out_at != null ? 'text-red-700 dark:text-red-400' : 'text-green-700 dark:text-green-400'">
                  {{ oc.plan_line_runs_out_at != null ? `✕ Plan line runs out at ${oc.plan_line_runs_out_at}` : '✓ Plan line lasts' }}
                </span>
                · {{ percent(oc.share_running_out, 0) }} of markets run out<span v-if="oc.median_failure_age != null"> (median age {{ oc.median_failure_age }})</span>
                · chance {{ percent(oc.success_with, 0) }} vs {{ percent(oc.success_without, 0) }} without it
              </p>
              <dl class="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                <div><dt class="text-gray-400">Part-time income to stay solvent (ages {{ oc.income_window[0] }}–{{ oc.income_window[1] }})</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ oc.income_for_plan_line == null ? 'not reachable' : oc.income_for_plan_line === 0 ? 'none needed' : `${money(oc.income_for_plan_line)}/yr` }}</dd></div>
                <div><dt class="text-gray-400">…to undo the shock</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ oc.income_to_restore == null ? 'not reachable' : oc.income_to_restore === 0 ? 'none needed' : `${money(oc.income_to_restore)}/yr` }}</dd></div>
                <div><dt class="text-gray-400">…to reach {{ percent(target, 0) }}</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ oc.income_for_target == null ? 'not reachable' : oc.income_for_target === 0 ? 'none needed' : `${money(oc.income_for_target)}/yr` }}</dd></div>
              </dl>
            </div>
          </div>
        </section>

        <!-- Sprint -->
        <SprintPanel :result="sprint" :loading="sprintLoading" :error="sprintError" @run="runSprint" />

        <!-- Sensitivity -->
        <ChartContainer title="Which levers matter most" :empty="!o.sensitivity?.length" empty-text="Sensitivity is still computing."
          :info="`Change in chance of success (percentage points from the plan's ${percent(o.goal_seek?.base_success ?? 0, 0)}) when one lever is set lower or higher and nothing else moves: retirement age ±3 years, spending ±20%, comp growth, returns and inflation ±1 point, savings ±50%, company stock growth ±5 points, retirement stock share ±20 points, claim age ±3 years. Hover for the exact settings.`">
          <LeverTornado v-if="o.sensitivity" :rows="tornadoFromSensitivity(o.sensitivity)" :base="o.goal_seek?.base_success ?? o.summary.success_rate" />
        </ChartContainer>

        <!-- Year by year -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0">
          <button type="button" class="flex w-full items-center justify-between text-left" :aria-expanded="showTable" @click="showTable = !showTable">
            <span class="text-sm font-semibold text-gray-900 dark:text-white">Year by year (plan line) <InfoTooltip text="The plan line in nominal dollars (what the numbers will say in that year): every return at its median, inflation at the assumption. Withdrawn is what savings cover after Social Security and other income. The same rows are stored in plan_projections for SQL." /></span>
            <span class="text-xs text-indigo-600 dark:text-indigo-400">{{ showTable ? 'Hide' : 'Show' }}</span>
          </button>
          <DataTable v-if="showTable" class="mt-3" dense sticky :empty="!o.rows.length" :columns="11" empty-text="No years to show.">
            <thead>
              <tr><th>Year</th><th>Age</th><th class="text-right">Salary</th><th class="text-right">RSU</th><th class="text-right">Saved</th><th class="text-right">Living</th><th class="text-right">Housing</th><th class="text-right">Health</th><th class="text-right">Withdrawn</th><th class="text-right">Investable</th><th class="text-right">Net worth</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in o.rows" :key="r.year" :class="r.phase === 'retired' ? 'bg-gray-50/60 dark:bg-gray-800/30' : ''">
                <td>{{ r.year }}</td><td>{{ r.age }}</td>
                <td class="text-right tabular-nums">{{ r.salary ? compact(r.salary) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.rsu_income ? compact(r.rsu_income) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.saved ? compact(r.saved) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.spending ? compact(r.spending) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.housing ? compact(r.housing) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.healthcare ? compact(r.healthcare) : '—' }}</td>
                <td class="text-right tabular-nums">{{ r.withdrawal ? compact(r.withdrawal) : '—' }}</td>
                <td class="text-right tabular-nums">{{ compact(r.cash + r.investments + r.company_stock + r.retirement_bal) }}</td>
                <td class="text-right tabular-nums">{{ compact(r.net_worth) }}</td>
              </tr>
            </tbody>
          </DataTable>
        </section>

        <!-- Plans side by side -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0">
          <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Your plans side by side <InfoTooltip text="Every saved plan's outlook under its own saved levers and your assumptions scenario. Unsaved what-ifs are not included; use Save as new plan to keep one." /></h3>
            <button type="button" :disabled="comparing" class="rounded-md border border-gray-300 dark:border-gray-700 px-3 py-1 text-xs text-gray-700 dark:text-gray-200 disabled:opacity-50" @click="loadCompare">{{ comparing ? 'Comparing…' : compareRows.length ? 'Refresh' : 'Compare plans' }}</button>
          </div>
          <DataTable v-if="compareRows.length" dense :columns="7">
            <thead><tr><th>Plan</th><th>Retire at</th><th class="text-right">Spending</th><th>Rule</th><th class="text-right">Success</th><th class="text-right">At retirement</th><th class="text-right">At the end</th></tr></thead>
            <tbody>
              <tr v-for="r in compareRows" :key="r.id" :class="r.id === planId ? 'font-semibold' : ''">
                <td>{{ r.name }}</td><td>{{ r.retire }}</td><td class="text-right tabular-nums">{{ compact(r.spending) }}</td><td>{{ r.rule }}</td>
                <td class="text-right tabular-nums">{{ percent(r.success, 0) }}</td><td class="text-right tabular-nums">{{ compact(r.atRet) }}</td><td class="text-right tabular-nums">{{ compact(r.end) }}</td>
              </tr>
            </tbody>
          </DataTable>
          <p v-else class="text-xs text-gray-500 dark:text-gray-400">{{ plans.length }} saved plan(s). Compare runs each one's outlook.</p>
        </section>

        <p class="text-[11px] text-gray-400 dark:text-gray-500">Model: yearly steps from today; one tax rate each on pay, RSUs and withdrawals (Roth basis tax-free); 401(k) penalty-free from 59½, or from 55 when you leave work then; Social Security from your ssa.gov estimate; marketplace premiums capped by income below 400% of the poverty line; Medicare from 65. Not advice.</p>
      </div>
    </div>
  </div>
</template>
