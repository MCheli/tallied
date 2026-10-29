import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Transaction, CategorySummary, RecurringExpense, MonthlySpending } from '../types'

/**
 * Spending page state. One date range (filters.from_date/to_date) and one account-type
 * filter scope all four sections: transactions, category breakdown, recurring, monthly trend.
 */
export const useTransactionStore = defineStore('transactions', () => {
  const items = ref<Transaction[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filters = reactive({
    from_date: '',
    to_date: '',
    category: '',
    category_group: '',
    account_id: '',
    account_types: [] as string[],
    merchant: '',
    page: 1,
    page_size: 25,
    search: '',
  })

  const categoryBreakdown = ref<CategorySummary[]>([])
  const recurring = ref<RecurringExpense[]>([])
  const monthlyTrend = ref<MonthlySpending[]>([])
  const sectionsLoading = ref(false)
  const sectionError = ref<string | null>(null)

  async function fetchTransactions() {
    loading.value = true
    error.value = null
    try {
      const { account_types, page, page_size, ...rest } = filters
      const params: Record<string, unknown> = {
        ...rest,
        account_types: account_types.length ? account_types.join(',') : undefined,
        offset: (page - 1) * page_size,
        limit: page_size,
      }
      const result = await api.getTransactions(params)
      items.value = result.items
      total.value = result.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load transactions'
    } finally {
      loading.value = false
    }
  }

  /** Category breakdown, recurring merchants and monthly trend for the current range and account filter. */
  async function fetchSections() {
    sectionsLoading.value = true
    sectionError.value = null
    const from = filters.from_date || undefined
    const to = filters.to_date || undefined
    const types = filters.account_types
    const [cats, rec, trend] = await Promise.allSettled([
      api.getSpendingByCategory(from, to, types),
      api.getRecurring(from, to, types),
      api.getMonthlyTrend(from, to, types),
    ])
    categoryBreakdown.value = cats.status === 'fulfilled' ? cats.value : []
    recurring.value = rec.status === 'fulfilled' ? rec.value : []
    monthlyTrend.value = trend.status === 'fulfilled' ? trend.value : []
    const failed = [cats, rec, trend].find(r => r.status === 'rejected') as PromiseRejectedResult | undefined
    if (failed) sectionError.value = failed.reason instanceof Error ? failed.reason.message : String(failed.reason)
    sectionsLoading.value = false
  }

  return {
    items, total, loading, error, filters,
    categoryBreakdown, recurring, monthlyTrend, sectionsLoading, sectionError,
    fetchTransactions, fetchSections,
  }
})
