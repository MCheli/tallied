<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useTransactionStore } from '../stores/transactions'
import ChartContainer from '../components/common/ChartContainer.vue'
import TransactionTable from '../components/spending/TransactionTable.vue'
import CategoryChart from '../components/spending/CategoryChart.vue'
import RecurringList from '../components/spending/RecurringList.vue'
import MonthlyTrend from '../components/spending/MonthlyTrend.vue'

const store = useTransactionStore()

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
  store.filters.page = 1
  store.fetchTransactions()
  store.fetchCategoryBreakdown(from, to)
  store.fetchRecurring()
  store.fetchMonthlyTrend()
}

watch(activePreset, () => loadData())
onMounted(() => loadData())

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
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-lg font-bold text-gray-900 dark:text-white">Spending</h2>
      <div class="flex gap-2">
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

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      <!-- Left Column -->
      <div class="space-y-4">
        <ChartContainer title="Spending by Category" info="Horizontal bar chart showing total spending by category for the selected time period. Only includes expenses (negative transaction amounts). Categories are sorted by total spend.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table grouped by category field. Includes both Plaid-synced and imported transactions." :loading="store.categoryBreakdown.length === 0 && store.loading">
          <CategoryChart :categories="store.categoryBreakdown" />
        </ChartContainer>
        <RecurringList :expenses="store.recurring" />
      </div>
      <!-- Right Column -->
      <div class="lg:col-span-2">
        <TransactionTable
          :transactions="store.items"
          :loading="store.loading"
          :page="store.filters.page"
          :pageSize="store.filters.page_size"
          :total="store.total"
          @page-change="onPageChange"
          @search="onSearch"
        />
      </div>
    </div>

    <!-- Monthly Trend -->
    <ChartContainer title="Monthly Spending Trend" info="Monthly total spending over time. Shows how your spending has trended month over month. Only includes expenses, not income. Useful for spotting seasonal patterns or lifestyle changes.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table, summed by month (expenses only)." :loading="store.monthlyTrend.length === 0 && store.loading">
      <MonthlyTrend :data="store.monthlyTrend" />
    </ChartContainer>
  </div>
</template>
