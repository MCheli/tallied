<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useTransactionStore } from '../stores/transactions'
import { useDataExplorer } from '../composables/useDataExplorer'
import { useFormatters } from '../composables/useFormatters'
import { DEFAULT_PRESET, PRESETS, monthsInRange, presetLabel, presetRange, widerPreset, type DatePreset } from '../composables/useDatePresets'
import { api } from '../api/client'
import PageHeader from '../components/common/PageHeader.vue'
import DataExplorer from '../components/common/DataExplorer.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import TransactionTable from '../components/spending/TransactionTable.vue'
import CategoryChart from '../components/spending/CategoryChart.vue'
import RecurringList from '../components/spending/RecurringList.vue'
import MonthlyTrend from '../components/spending/MonthlyTrend.vue'
import type { AccountWithBalance } from '../types'

const store = useTransactionStore()
const { openData } = useDataExplorer()
const { date } = useFormatters()

// ── Account name lookup + account-type filter ────────────────────────────────
const accounts = ref<AccountWithBalance[]>([])
const selectedAccountTypes = ref<string[]>([])

const accountNames = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const a of accounts.value) m[a.id] = a.name
  return m
})

const accountTypeOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const a of accounts.value) counts.set(a.account_type, (counts.get(a.account_type) ?? 0) + 1)
  return Array.from(counts.entries()).map(([type, count]) => ({ type, count })).sort((a, b) => a.type.localeCompare(b.type))
})

function toggleAccountType(t: string) {
  const i = selectedAccountTypes.value.indexOf(t)
  if (i >= 0) selectedAccountTypes.value.splice(i, 1)
  else selectedAccountTypes.value.push(t)
}
function clearAccountTypes() { selectedAccountTypes.value = [] }

// ── Period ───────────────────────────────────────────────────────────────────
const activePreset = ref<DatePreset>(DEFAULT_PRESET)
const range = computed(() => presetRange(activePreset.value))
const rangeNote = ref('')
const excludedCategories = ref<string[]>([])

/** One date range and one account filter drive all four sections. */
async function loadData(opts: { allowFallback?: boolean } = {}) {
  const { from, to } = range.value
  store.filters.from_date = from
  store.filters.to_date = to
  store.filters.account_types = [...selectedAccountTypes.value]
  store.filters.page = 1
  await Promise.all([store.fetchTransactions(), store.fetchSections()])

  // First load only: if the default period is empty, widen it once and say so.
  if (opts.allowFallback && store.total === 0 && store.categoryBreakdown.length === 0) {
    const wider = widerPreset(activePreset.value)
    if (wider) {
      rangeNote.value = `Nothing in ${presetLabel(activePreset.value).toLowerCase()}; showing ${presetLabel(wider).toLowerCase()} instead.`
      activePreset.value = wider // the watcher reloads
    }
  }
}

watch(activePreset, (_, old) => {
  if (old !== undefined && !rangeNote.value.includes(presetLabel(activePreset.value).toLowerCase())) rangeNote.value = ''
  loadData()
})
watch(selectedAccountTypes, () => loadData(), { deep: true })

onMounted(async () => {
  const [acct, excl] = await Promise.allSettled([api.getAccounts(), api.getExcludedCategories()])
  if (acct.status === 'fulfilled') accounts.value = acct.value
  if (excl.status === 'fulfilled') excludedCategories.value = excl.value
  await loadData({ allowFallback: true })
})

function onPageChange(page: number) {
  store.filters.page = page
  store.fetchTransactions()
}

function onSearch(term: string) {
  store.filters.search = term
  store.filters.page = 1
  store.fetchTransactions()
}

const periodLabel = computed(() => `${date(range.value.from)} to ${date(range.value.to)}`)
const monthsLabel = computed(() => {
  const n = monthsInRange(range.value.from, range.value.to)
  return `${n} month${n === 1 ? '' : 's'}`
})
const exclusionText = computed(() =>
  excludedCategories.value.length ? excludedCategories.value.join(', ') : 'transfers and loan or card payments'
)

// ── SQL transparency (Postgres; what the API runs) ───────────────────────────
const showRecurringSql = ref(false)
const showTransactionsSql = ref(false)

const SPENDING_WHERE = `WHERE amount < 0
  AND (category IS NULL OR category NOT IN ('Transfer', 'Credit Card Payment', 'Loan Payment', 'Mortgage Payment'))
  AND date BETWEEN :from_date AND :to_date`

const categorySql = `-- Spending = negative amounts, excluding transfers and loan/card payments
SELECT category, category_group, SUM(amount) AS total, COUNT(*) AS count
FROM transactions
${SPENDING_WHERE}
GROUP BY category, category_group
ORDER BY SUM(amount)`

const recurringSql = `-- avg_monthly = total in the period / months in the period
SELECT merchant, category,
  SUM(amount) / :months_in_range AS avg_monthly,
  COUNT(DISTINCT to_char(date, 'YYYY-MM')) AS months_seen,
  MAX(date) AS last_date
FROM transactions
${SPENDING_WHERE}
  AND merchant IS NOT NULL
GROUP BY merchant, category
HAVING COUNT(DISTINCT to_char(date, 'YYYY-MM')) >= 2
ORDER BY SUM(amount)`

const transactionsSql = `-- All transactions in the period (income and transfers included), newest first
SELECT id, date, merchant, category, amount, account_id, notes
FROM transactions
WHERE date BETWEEN :from_date AND :to_date
  AND (merchant ILIKE '%' || :search || '%'
       OR category ILIKE '%' || :search || '%'
       OR notes ILIKE '%' || :search || '%')
ORDER BY date DESC
LIMIT :limit OFFSET :offset`

const monthlyTrendSql = `SELECT to_char(date, 'YYYY-MM') AS month, SUM(amount) AS total, COUNT(*) AS count
FROM transactions
${SPENDING_WHERE}
GROUP BY to_char(date, 'YYYY-MM')
ORDER BY month`
</script>

<template>
  <div>
    <PageHeader
      title="Spending"
      :subtitle="rangeNote || `${periodLabel} (${monthsLabel})`"
      :tooltip="`Where the money went in one period. Every section on this page uses the same date range and account filter. Spending means money out; ${exclusionText} are never counted.`"
    >
      <button @click="openData('spending')"
        class="px-3 py-2 min-h-[40px] text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">
        Data
      </button>
      <template #below>
        <div class="flex flex-wrap items-center gap-2">
          <div class="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5" role="group" aria-label="Period">
            <button
              v-for="p in PRESETS"
              :key="p.key"
              @click="activePreset = p.key"
              :aria-pressed="activePreset === p.key"
              :class="[
                'px-3 py-1.5 min-h-[36px] text-sm rounded-md transition-colors',
                activePreset === p.key
                  ? 'bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 font-medium shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-white/60 dark:hover:bg-gray-700/60'
              ]"
            >
              {{ p.label }}
            </button>
          </div>
          <div v-if="accountTypeOptions.length > 0" class="flex flex-wrap items-center gap-1.5">
            <span class="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Accounts</span>
            <button
              @click="clearAccountTypes"
              :class="[
                'px-2.5 py-1.5 text-xs rounded-full border transition-colors',
                selectedAccountTypes.length === 0
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              ]"
            >
              All
            </button>
            <button
              v-for="opt in accountTypeOptions"
              :key="opt.type"
              @click="toggleAccountType(opt.type)"
              :class="[
                'px-2.5 py-1.5 text-xs rounded-full border transition-colors',
                selectedAccountTypes.includes(opt.type)
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              ]"
            >
              {{ opt.type }} <span class="opacity-60">({{ opt.count }})</span>
            </button>
          </div>
        </div>
      </template>
    </PageHeader>

    <p v-if="store.sectionError" class="mb-4 text-sm text-red-600 dark:text-red-400">Some sections could not load: {{ store.sectionError }}</p>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6 items-start">
      <div class="space-y-4 min-w-0">
        <ChartContainer
          title="Spending by Category"
          :subtitle="periodLabel"
          :loading="store.sectionsLoading && store.categoryBreakdown.length === 0"
          :empty="!store.sectionsLoading && store.categoryBreakdown.length === 0"
          empty-text="No spending in this period"
          :info="`Total spent per category in the selected period, largest first (top 15). Spending is negative transactions; ${exclusionText} are excluded.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions grouped by category, scoped by the period and account filter.`"
          :sql="categorySql"
          :sqlTables="['transactions']"
        >
          <CategoryChart :categories="store.categoryBreakdown" />
        </ChartContainer>
        <div class="group/recurring relative min-w-0">
          <RecurringList :expenses="store.recurring" :loading="store.sectionsLoading && store.recurring.length === 0" :period-label="periodLabel" />
          <button @click="showRecurringSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/recurring:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showRecurringSql" :sql="recurringSql" title="Recurring Expenses" :tables="['transactions']" @close="showRecurringSql = false" />
        </div>
      </div>
      <div class="lg:col-span-2 min-w-0">
        <div class="group/txns relative min-w-0">
          <TransactionTable
            :transactions="store.items"
            :loading="store.loading"
            :page="store.filters.page"
            :pageSize="store.filters.page_size"
            :total="store.total"
            :accountNames="accountNames"
            @page-change="onPageChange"
            @search="onSearch"
            @categorized="() => { store.fetchTransactions(); store.fetchSections() }"
          />
          <button @click="showTransactionsSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/txns:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTransactionsSql" :sql="transactionsSql" title="Transactions" :tables="['transactions']" @close="showTransactionsSql = false" />
        </div>
      </div>
    </div>

    <!-- Monthly Trend -->
    <ChartContainer
      title="Monthly Spending Trend"
      :subtitle="`By month, ${periodLabel}`"
      :loading="store.sectionsLoading && store.monthlyTrend.length === 0"
      :empty="!store.sectionsLoading && store.monthlyTrend.length === 0"
      empty-text="No spending in this period"
      :info="`Total spending per calendar month inside the selected period, so the bars match the category chart and the transactions table. ${exclusionText} are excluded; income is never counted.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions summed by month.`"
      :sql="monthlyTrendSql"
      :sqlTables="['transactions']"
    >
      <MonthlyTrend :data="store.monthlyTrend" />
    </ChartContainer>

    <DataExplorer />
  </div>
</template>

<style scoped>
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
