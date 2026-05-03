<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useTransactionStore } from '../stores/transactions'
import { useDataExplorer } from '../composables/useDataExplorer'
import { api } from '../api/client'
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

// ── Account name lookup + account-type filter ────────────────────────────────
const accounts = ref<AccountWithBalance[]>([])
const selectedAccountTypes = ref<string[]>([])

const accountNames = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const a of accounts.value) m[a.id] = a.name
  return m
})

// Distinct account_types present, with a count so users see what's available.
const accountTypeOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const a of accounts.value) {
    counts.set(a.account_type, (counts.get(a.account_type) ?? 0) + 1)
  }
  return Array.from(counts.entries())
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => a.type.localeCompare(b.type))
})

function toggleAccountType(t: string) {
  const i = selectedAccountTypes.value.indexOf(t)
  if (i >= 0) selectedAccountTypes.value.splice(i, 1)
  else selectedAccountTypes.value.push(t)
}

function clearAccountTypes() {
  selectedAccountTypes.value = []
}

const showRecurringSql = ref(false)
const showTransactionsSql = ref(false)

const categorySql = `SELECT
  category,
  category_group,
  SUM(amount) AS total,
  COUNT(*) AS count
FROM transactions
WHERE amount < 0
  AND source != 'plaid'
  AND date >= :from_date
  AND date <= :to_date
GROUP BY category, category_group
ORDER BY SUM(amount) ASC`

const recurringSql = `SELECT
  merchant,
  category,
  AVG(amount) AS avg_amount,
  COUNT(DISTINCT strftime('%Y-%m', date)) AS months_seen,
  MAX(date) AS last_date
FROM transactions
WHERE amount < 0
  AND source != 'plaid'
  AND date >= date('now', '-6 months')
  AND merchant IS NOT NULL
GROUP BY merchant, category
HAVING COUNT(DISTINCT strftime('%Y-%m', date)) >= 2
ORDER BY AVG(amount) ASC`

const transactionsSql = `SELECT id, date, merchant, category, amount, account_id, notes
FROM transactions
WHERE source != 'plaid'
  AND date >= :from_date
  AND date <= :to_date
  AND (merchant LIKE '%' || :search || '%'
       OR category LIKE '%' || :search || '%'
       OR notes LIKE '%' || :search || '%')
ORDER BY date DESC
LIMIT :limit OFFSET :offset`

const monthlyTrendSql = `SELECT
  strftime('%Y-%m', date) AS month,
  SUM(amount) AS total,
  COUNT(*) AS count
FROM transactions
WHERE amount < 0
  AND source != 'plaid'
GROUP BY strftime('%Y-%m', date)
ORDER BY month ASC`

type DatePreset = 'month' | '3mo' | 'ytd' | '12mo'
const activePreset = ref<DatePreset>('3mo')

function getDateRange(preset: DatePreset): { from: string; to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)
  let from: string
  switch (preset) {
    case 'month': {
      const d = new Date(now.getFullYear(), now.getMonth(), 1)
      from = d.toISOString().slice(0, 10)
      break
    }
    case '3mo': {
      const d = new Date(now)
      d.setMonth(d.getMonth() - 3)
      from = d.toISOString().slice(0, 10)
      break
    }
    case 'ytd': {
      from = `${now.getFullYear()}-01-01`
      break
    }
    case '12mo': {
      const d = new Date(now)
      d.setFullYear(d.getFullYear() - 1)
      from = d.toISOString().slice(0, 10)
      break
    }
  }
  return { from, to }
}

function loadData() {
  const { from, to } = getDateRange(activePreset.value)
  store.filters.from_date = from
  store.filters.to_date = to
  store.filters.account_types = [...selectedAccountTypes.value]
  store.filters.page = 1
  store.fetchTransactions()
  store.fetchCategoryBreakdown(from, to)
  store.fetchRecurring()
  store.fetchMonthlyTrend()
}

watch(activePreset, () => loadData())
watch(selectedAccountTypes, () => loadData(), { deep: true })

onMounted(async () => {
  try {
    accounts.value = await api.getAccounts()
  } catch { /* ignore — table just shows ids */ }
  loadData()
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

const presets: { key: DatePreset; label: string }[] = [
  { key: 'month', label: 'This Month' },
  { key: '3mo', label: 'Last 3 Months' },
  { key: 'ytd', label: 'YTD' },
  { key: '12mo', label: 'Last 12 Months' },
]
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold text-gray-900 dark:text-white">Spending</h2>
      <div class="flex items-center gap-2">
        <button @click="openData('spending')"
          class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">
          Data
        </button>
        <span class="w-px h-5 bg-gray-200 dark:bg-gray-700"></span>
        <button
          v-for="p in presets"
          :key="p.key"
          @click="activePreset = p.key"
          :class="[
            'px-3 py-1.5 text-sm rounded-lg transition-colors',
            activePreset === p.key
              ? 'bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 font-medium'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
          ]"
        >
          {{ p.label }}
        </button>
      </div>
    </div>

    <!-- Account-type filter chips -->
    <div v-if="accountTypeOptions.length > 0" class="flex items-center gap-2 mb-6 flex-wrap">
      <span class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Account types:</span>
      <button
        @click="clearAccountTypes"
        :class="[
          'px-2.5 py-1 text-xs rounded-full border transition-colors',
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
          'px-2.5 py-1 text-xs rounded-full border transition-colors',
          selectedAccountTypes.includes(opt.type)
            ? 'bg-indigo-600 text-white border-indigo-600'
            : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
        ]"
      >
        {{ opt.type }} <span class="opacity-60">({{ opt.count }})</span>
      </button>
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      <!-- Left Column -->
      <div class="space-y-4">
        <ChartContainer title="Spending by Category" info="Horizontal bar chart showing total spending by category for the selected time period. Only includes expenses (negative transaction amounts). Categories are sorted by total spend.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table grouped by category field. Includes both Plaid-synced and imported transactions." :loading="store.categoryBreakdown.length === 0 && store.loading" :sql="categorySql" :sqlTables="['transactions']">
          <CategoryChart :categories="store.categoryBreakdown" />
        </ChartContainer>
        <div class="group/recurring relative">
          <RecurringList :expenses="store.recurring" />
          <button @click="showRecurringSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/recurring:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showRecurringSql" :sql="recurringSql" title="Recurring Expenses" :tables="['transactions']" @close="showRecurringSql = false" />
        </div>
      </div>
      <!-- Right Column -->
      <div class="lg:col-span-2">
        <div class="group/txns relative">
          <TransactionTable
            :transactions="store.items"
            :loading="store.loading"
            :page="store.filters.page"
            :pageSize="store.filters.page_size"
            :total="store.total"
            :accountNames="accountNames"
            @page-change="onPageChange"
            @search="onSearch"
          />
          <button @click="showTransactionsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/txns:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTransactionsSql" :sql="transactionsSql" title="Transactions" :tables="['transactions']" @close="showTransactionsSql = false" />
        </div>
      </div>
    </div>

    <!-- Monthly Trend -->
    <ChartContainer title="Monthly Spending Trend" info="Monthly total spending over time. Shows how your spending has trended month over month. Only includes expenses, not income. Useful for spotting seasonal patterns or lifestyle changes.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table, summed by month (expenses only)." :loading="store.monthlyTrend.length === 0 && store.loading" :sql="monthlyTrendSql" :sqlTables="['transactions']">
      <MonthlyTrend :data="store.monthlyTrend" />
    </ChartContainer>

    <DataExplorer />
  </div>
</template>
